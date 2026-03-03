"""
CatalogService
--------------
Serviço principal do fluxo de cadastro e manutenção do catálogo.

Fluxo por produto:
  1. DiffService produz um ProductDiff (Excel vs JSON em disco)
  2. CatalogService age sobre o diff:
     a. Produto novo          → processa imagens + gera JSON + atualiza Excel
     b. Imagem principal nova → reprocessa imagem, atualiza NAS/bucket/JSON/Excel
     c. Imagem secundária nova → idem para o slot correspondente
     d. Colunas NAS mudaram  → move pasta no NAS, atualiza caminhos no JSON/Excel
     e. Só dados mudaram     → atualiza JSON (caminhos NAS/bucket são preservados do JSON)
  3. Planilha salva no NAS com os novos valores
  4. Landing limpa (apenas arquivos processados nesta execução)
"""

import logging
import shutil
import tempfile
from pathlib import Path
from typing import Optional

from config.settings import settings
from models.product_model import (
    ProductModel,
    SECONDARY_SLOTS,
    SECONDARY_EXCEL_COLS,
    SECONDARY_NAS_FIELDS,
    SECONDARY_BUCKET_FIELDS,
)
from services.diff_service import DiffService, ProductDiff, SecondaryImageDiff
from services.image_service import ImageService
from services.json_service import JsonService
from services.nas_service import NasService
from services.spreadsheet_service import SpreadsheetService
from services.storage_service import StorageService

_PROCESSED_MARKER = "Processada"


class CatalogService:

    def __init__(self, logger: logging.Logger):
        self.logger = logger
        self.image_service = ImageService(logger)
        self.nas_service = NasService(logger)
        self.spreadsheet_service = SpreadsheetService(logger)
        self.json_service = JsonService(logger)
        self.diff_service = DiffService(logger, JsonService(logger))
        # self.storage_service = StorageService(logger)

        # Nomes de arquivo da landing que foram processados nesta execução
        self._filenames_to_clean: list[str] = []

    # ======================================================================
    # Ponto de entrada
    # ======================================================================

    def process_spreadsheet(self, xlsx_path: Path) -> dict:
        """
        Executa o fluxo completo de cadastro/manutenção a partir de uma planilha.
        Retorna dicionário com estatísticas da execução.
        """
        stats = {
            "total": 0,
            "novos": 0,
            "imagem_principal_atualizada": 0,
            "secundarias_processadas": 0,
            "secundarias_deletadas": 0,
            "pasta_nas_movida": 0,
            "dados_atualizados": 0,
            "ignorados": 0,
            "erros": 0,
            "arquivos_limpos": 0,
        }

        self.logger.info("=" * 60)
        self.logger.info(f"Iniciando processamento da planilha: {xlsx_path}")
        self.logger.info("=" * 60)

        # 1. Carregar planilha
        try:
            df = self.spreadsheet_service.load(xlsx_path)
        except Exception as exc:
            self.logger.error(f"Falha crítica ao abrir planilha: {exc}", exc_info=True)
            raise

        stats["total"] = len(df)
        self.logger.info(f"Total de linhas a processar: {stats['total']}")

        # 2. Iterar linhas
        for idx, row in df.iterrows():
            row_dict = row.to_dict()
            product_id = self.spreadsheet_service.parse_id(row_dict.get("Id_produto"))

            if product_id is None:
                self.logger.warning(
                    f"Linha {idx + 2}: Id_produto inválido ou vazio — pulando."
                )
                stats["erros"] += 1
                continue

            self.logger.info(f"{'─' * 50}")
            self.logger.info(f"Linha {idx + 2} | Id_produto: {product_id}")

            # 2a. Gerar diff
            try:
                diff = self.diff_service.build(product_id, row_dict)
            except Exception as exc:
                self.logger.error(
                    f"Id {product_id}: Falha ao gerar diff: {exc}", exc_info=True
                )
                stats["erros"] += 1
                continue

            if not diff.has_any_change:
                self.logger.info(f"Id {product_id}: Sem alterações detectadas — ignorando.")
                stats["ignorados"] += 1
                continue

            # 2b. Executar ações com base no diff
            try:
                excel_updates = self._execute_diff(diff)
            except Exception as exc:
                self.logger.error(
                    f"Id {product_id}: Erro inesperado ao executar diff: {exc}",
                    exc_info=True,
                )
                stats["erros"] += 1
                continue

            if excel_updates is None:
                # Retorno None = erro já logado em _execute_diff
                stats["erros"] += 1
                continue

            # 2c. Aplicar atualizações ao DataFrame
            for col, val in excel_updates.items():
                if col in df.columns:
                    df.at[idx, col] = val
                    self.logger.debug(
                        f"Id {product_id}: Excel atualizado — '{col}' = '{val}'"
                    )

            # 2d. Contabilizar estatísticas
            if diff.is_new_product:
                stats["novos"] += 1
            else:
                if diff.primary_is_changed:
                    stats["imagem_principal_atualizada"] += 1
                if diff.secondary_changes:
                    stats["secundarias_processadas"] += len(diff.secondary_changes)
                if diff.secondary_deletions:
                    stats["secundarias_deletadas"] += len(diff.secondary_deletions)
                if diff.nas_path_changed:
                    stats["pasta_nas_movida"] += 1
                if diff.data_fields_changed and not (
                    diff.primary_is_changed or diff.secondary_changes
                    or diff.secondary_deletions or diff.nas_path_changed
                ):
                    stats["dados_atualizados"] += 1

        self.logger.info("=" * 60)
        self.logger.info("Finalizando: salvando planilha e limpando landing.")

        # 3. Salvar planilha atualizada no NAS
        self.spreadsheet_service.save(df, xlsx_path)

        # 4. Limpar landing
        stats["arquivos_limpos"] = self._cleanup_landing()

        self.logger.info(f"Processamento concluído. Stats: {stats}")
        self.logger.info("=" * 60)
        return stats

    # ======================================================================
    # Executor do diff
    # ======================================================================

    def _execute_diff(self, diff: ProductDiff) -> Optional[dict]:
        """
        Recebe um ProductDiff e executa todas as ações necessárias.

        Retorna dict com as colunas do Excel que precisam ser atualizadas,
        ou None em caso de erro bloqueante.

        Ordem de execução:
          1. Produto novo → fluxo completo
          2. Imagem principal trocada → reprocessar
          3. Secundárias novas/trocadas → reprocessar cada slot
          4. Pasta NAS mudou → mover pasta
          5. Só dados → atualizar JSON
        """
        product_id = diff.product_id

        if diff.is_new_product:
            return self._handle_new_product(diff)

        # Produto existente — cada ação é independente e acumulativa
        excel_updates: dict = {}

        # --- Imagem principal trocada ---
        if diff.primary_is_new or diff.primary_is_changed:
            updates = self._handle_primary_image(diff)
            if updates is None:
                return None  # erro bloqueante na imagem principal
            excel_updates.update(updates)

        # --- Secundárias novas ou trocadas ---
        for sec in diff.secondary_changes:
            updates = self._handle_secondary_image(diff, sec)
            if updates:
                excel_updates.update(updates)
            # Falha numa secundária não bloqueia as demais

        # --- Secundárias deletadas (Excel vazio + JSON tem caminho) ---
        for sec in diff.secondary_deletions:
            self._handle_secondary_deletion(diff, sec)

        # --- Pasta NAS mudou (colunas organizadoras) ---
        if diff.nas_path_changed:
            updates = self._handle_nas_path_change(diff)
            if updates is None:
                self.logger.error(
                    f"Id {product_id}: Falha ao mover pasta NAS — "
                    "JSON e Excel não serão atualizados para este produto."
                )
                return None
            excel_updates.update(updates)

        # --- Atualizar JSON com estado final ---
        # Sempre que há qualquer mudança, reconstruímos o JSON
        # preservando os caminhos NAS/bucket já gravados
        self._update_json(diff, excel_updates)

        return excel_updates

    # ======================================================================
    # Handlers individuais
    # ======================================================================

    # ------------------------------------------------------------------
    # Produto novo
    # ------------------------------------------------------------------

    def _handle_new_product(self, diff: ProductDiff) -> Optional[dict]:
        """
        Fluxo completo para produto que ainda não tem JSON.
        Processa imagem principal + todas as secundárias presentes.
        Gera hash, JSON e retorna atualizações para o Excel.
        """
        product_id = diff.product_id
        row_dict = diff.row_dict
        excel_updates: dict = {}

        self.logger.info(f"Id {product_id}: Iniciando cadastro de produto novo.")

        # --- Imagem principal ---
        if not diff.primary_excel_value:
            self.logger.error(
                f"Id {product_id}: Produto novo sem imagem principal definida. "
                "Linha ignorada."
            )
            return None

        nas_path, bucket_uri = self._process_and_store_image(
            product_id=product_id,
            source_filename=diff.primary_excel_value,
            dest_filename=self.image_service.primary_image_name(product_id),
            row_dict=row_dict,
            label="principal",
        )
        if nas_path is None:
            return None  # erro já logado

        excel_updates["Chave_Especial"] = self.image_service.generate_hash(row_dict)
        excel_updates["Caminho_Imagem"] = str(nas_path)

        # --- Secundárias ---
        for sec in diff.secondaries:
            if not sec.is_new:
                continue
            updates = self._handle_secondary_image(diff, sec)
            if updates:
                excel_updates.update(updates)

        # --- Construir model e salvar JSON ---
        model = self._build_model(diff, excel_updates, existing_json=None)
        self.json_service.save(model, product_id)

        self.logger.info(
            f"Id {product_id}: Cadastro novo concluído. "
            f"Atualizações Excel: {list(excel_updates.keys())}"
        )
        return excel_updates

    # ------------------------------------------------------------------
    # Imagem principal trocada
    # ------------------------------------------------------------------

    def _handle_primary_image(self, diff: ProductDiff) -> Optional[dict]:
        """
        Reprocessa a imagem principal quando ela foi trocada no Excel.
        Remove o arquivo antigo do NAS (e futuramente do bucket).
        """
        product_id = diff.product_id
        excel_updates: dict = {}

        self.logger.info(
            f"Id {product_id}: Reprocessando imagem principal. "
            f"Arquivo novo: '{diff.primary_excel_value}'"
        )

        # Remover imagem antiga do NAS
        if diff.primary_json_nas_path:
            removed = self.nas_service.delete_image(diff.primary_json_nas_path)
            self.logger.info(
                f"Id {product_id}: Imagem principal antiga removida do NAS: "
                f"{diff.primary_json_nas_path} — ok={removed}"
            )
        # Remover do bucket (comentado até ativar GCS)
        # if diff.primary_json_bucket_uri:
        #     filename = Path(diff.primary_json_bucket_uri).name
        #     self.storage_service.delete_image(filename)

        # Processar nova imagem
        nas_path, bucket_uri = self._process_and_store_image(
            product_id=product_id,
            source_filename=diff.primary_excel_value,
            dest_filename=self.image_service.primary_image_name(product_id),
            row_dict=diff.row_dict,
            label="principal",
        )
        if nas_path is None:
            return None

        excel_updates["Caminho_Imagem"] = str(nas_path)
        # excel_updates["Caminho_Bucket_Principal"] = bucket_uri  # quando ativar GCS

        self.logger.info(
            f"Id {product_id}: Imagem principal atualizada → NAS: {nas_path}"
        )
        return excel_updates

    # ------------------------------------------------------------------
    # Imagem secundária nova ou trocada
    # ------------------------------------------------------------------

    def _handle_secondary_image(
        self, diff: ProductDiff, sec: SecondaryImageDiff
    ) -> dict:
        """
        Processa ou reprocessa um slot de imagem secundária.
        Remove o arquivo antigo do NAS se houver troca.
        Retorna as colunas do Excel a atualizar (coluna SecundariaX → caminho NAS).
        """
        product_id = diff.product_id
        slot = sec.slot
        excel_col = SECONDARY_EXCEL_COLS[slot]
        excel_updates: dict = {}

        action = "nova" if sec.is_new else "trocada"
        self.logger.info(
            f"Id {product_id}: Imagem secundária slot {slot} {action}. "
            f"Arquivo: '{sec.excel_value}'"
        )

        # Remover imagem antiga do NAS se é troca
        if sec.is_changed and sec.json_nas_path:
            removed = self.nas_service.delete_image(sec.json_nas_path)
            self.logger.info(
                f"Id {product_id}: Secundária {slot} antiga removida do NAS: "
                f"{sec.json_nas_path} — ok={removed}"
            )
        # Remover do bucket se for troca (comentado até ativar GCS)
        # if sec.is_changed and sec.json_bucket_uri:
        #     filename = Path(sec.json_bucket_uri).name
        #     self.storage_service.delete_image(filename)

        # Processar nova imagem (índice baseado em 0 para sufixo alfabético)
        dest_filename = self.image_service.secondary_image_name(product_id, slot - 1)

        nas_path, bucket_uri = self._process_and_store_image(
            product_id=product_id,
            source_filename=sec.excel_value,
            dest_filename=dest_filename,
            row_dict=diff.row_dict,
            label=f"secundária slot {slot}",
        )

        if nas_path is None:
            self.logger.warning(
                f"Id {product_id}: Falha ao processar secundária slot {slot}. "
                "Excel não será atualizado para este slot."
            )
            return {}

        # Registrar NAS path no cache para _build_model preservar
        self._register_secondary_nas(product_id, slot, nas_path)

        # Marcar slot como processado no Excel
        excel_updates[excel_col] = str(nas_path)

        self.logger.info(
            f"Id {product_id}: Secundária slot {slot} processada → NAS: {nas_path}"
        )
        return excel_updates

    # ------------------------------------------------------------------
    # Deleção de imagem secundária
    # ------------------------------------------------------------------

    def _handle_secondary_deletion(
        self, diff: ProductDiff, sec: SecondaryImageDiff
    ) -> None:
        """
        Remove um slot de imagem secundária que foi apagado no Excel.
        Deleta do NAS, do bucket (quando ativo) e limpa os campos no JSON.
        Não retorna atualizações para o Excel pois o campo já está vazio.
        """
        product_id = diff.product_id
        slot = sec.slot

        self.logger.info(
            f"Id {product_id}: Secundária slot {slot} removida no Excel — "
            f"iniciando limpeza. NAS='{sec.json_nas_path}'"
        )

        # Remover do NAS
        if sec.json_nas_path:
            removed = self.nas_service.delete_image(sec.json_nas_path)
            self.logger.info(
                f"Id {product_id}: Secundária slot {slot} removida do NAS: "
                f"'{sec.json_nas_path}' — ok={removed}"
            )
        else:
            self.logger.warning(
                f"Id {product_id}: Secundária slot {slot} — "
                "nenhum caminho NAS no JSON para remover."
            )

        # Remover do bucket (comentado até ativar GCS)
        # if sec.json_bucket_uri:
        #     filename = Path(sec.json_bucket_uri).name
        #     self.storage_service.delete_image(filename)
        #     self.logger.info(
        #         f"Id {product_id}: Secundária slot {slot} removida do bucket: "
        #         f"'{sec.json_bucket_uri}'"
        #     )

        # Limpar os campos do slot no JSON
        # Feito via _register_secondary_nas com None, que será persistido em _update_json
        self._register_secondary_deletion(product_id, slot)
        self.logger.info(
            f"Id {product_id}: Secundária slot {slot} marcada para limpeza no JSON."
        )

    # ------------------------------------------------------------------
    # Mudança de caminho NAS (colunas organizadoras)
    # ------------------------------------------------------------------

    def _handle_nas_path_change(self, diff: ProductDiff) -> Optional[dict]:
        """
        Move a pasta do produto no NAS quando colunas organizadoras mudaram.
        Atualiza o Caminho_Imagem e caminhos das secundárias no JSON.
        O GCS não precisa de ação pois a estrutura é flat (images/{filename}).
        """
        product_id = diff.product_id
        row_dict = diff.row_dict
        excel_updates: dict = {}

        self.logger.info(
            f"Id {product_id}: Colunas organizadoras NAS mudaram — iniciando movimentação."
        )

        expected_path = self.nas_service.build_product_path(row_dict, product_id)
        current_path = self.nas_service.find_product_folder(product_id)

        if current_path is None:
            self.logger.warning(
                f"Id {product_id}: Pasta atual no NAS não encontrada. "
                "Nada a mover — apenas atualizando JSON com novo caminho esperado."
            )
            # Atualiza o caminho esperado no JSON mesmo sem mover
            primary_img_name = self.image_service.primary_image_name(product_id)
            excel_updates["Caminho_Imagem"] = str(expected_path / primary_img_name)
            return excel_updates

        move_ok = self.nas_service.move_product_folder(current_path, expected_path)
        if not move_ok:
            self.logger.error(
                f"Id {product_id}: Falha ao mover pasta NAS de '{current_path}' "
                f"para '{expected_path}'."
            )
            return None

        # Atualiza Caminho_Imagem com novo path (GCS não muda — flat)
        primary_img_name = self.image_service.primary_image_name(product_id)
        excel_updates["Caminho_Imagem"] = str(expected_path / primary_img_name)

        self.logger.info(
            f"Id {product_id}: Pasta movida com sucesso. "
            f"Novo Caminho_Imagem: {excel_updates['Caminho_Imagem']}"
        )
        return excel_updates

    # ======================================================================
    # Construção do JSON final
    # ======================================================================

    def _update_json(self, diff: ProductDiff, excel_updates: dict) -> None:
        """
        Reconstrói e salva o JSON do produto após todas as ações do diff.

        Estratégia:
          - Parte do JSON existente (para preservar campos que o Excel não tem,
            como caminhos NAS/bucket das secundárias não alteradas)
          - Sobrescreve com os dados atuais do Excel
          - Sobrescreve com os novos caminhos gerados nesta execução (excel_updates)
        """
        product_id = diff.product_id
        existing_json = self.json_service.load(product_id) or {}

        # Construir model base a partir dos dados do Excel
        model = self._build_model(diff, excel_updates, existing_json=existing_json)

        self.json_service.save(model, product_id)
        self.logger.info(
            f"Id {product_id}: JSON atualizado. "
            f"Campos de dados alterados: {diff.changed_data_fields or '(nenhum)'}"
        )

    def _build_model(
        self,
        diff: ProductDiff,
        excel_updates: dict,
        existing_json: Optional[dict],
    ) -> ProductModel:
        """
        Constrói um ProductModel completo combinando:
          1. Dados do produto vindos do Excel (via row_dict + COLUMN_MAP)
          2. Caminhos NAS/bucket já salvos no JSON existente (preservados)
          3. Novos caminhos gerados nesta execução (excel_updates internos)
        """
        product_id = diff.product_id
        row_dict = diff.row_dict
        existing = existing_json or {}

        model = self.spreadsheet_service.row_to_model(row_dict)

        # --- Imagem principal ---
        # Prioridade: novo caminho gerado agora > caminho do JSON existente
        new_primary_nas = excel_updates.get("Caminho_Imagem")
        model.caminho_imagem = new_primary_nas or existing.get("caminho_imagem")
        model.caminho_bucket_principal = existing.get("caminho_bucket_principal")
        # model.caminho_bucket_principal = (
        #     excel_updates.get("Caminho_Bucket_Principal")
        #     or existing.get("caminho_bucket_principal")
        # )

        # --- Secundárias ---
        for slot in SECONDARY_SLOTS:
            excel_col = SECONDARY_EXCEL_COLS[slot]
            nas_field = SECONDARY_NAS_FIELDS[slot]
            bucket_field = SECONDARY_BUCKET_FIELDS[slot]

            # Distingue três estados no cache:
            #   _SENTINEL → slot não foi tocado nesta execução → preserva JSON
            #   None      → slot foi deletado → limpa campos
            #   string    → slot foi processado → usa novo caminho
            _SENTINEL = object()
            cached = self._secondary_nas_cache.get((product_id, slot), _SENTINEL)

            if cached is _SENTINEL:
                final_nas = existing.get(nas_field)
                final_bucket = existing.get(bucket_field)
            elif cached is None:
                # Deletado: limpa ambos os campos no JSON
                final_nas = None
                final_bucket = None
                self.logger.debug(
                    f"Id {product_id}: Slot secundária {slot} limpo no JSON (deletado)."
                )
            else:
                # Processado nesta execução: novo caminho NAS
                final_nas = cached
                final_bucket = existing.get(bucket_field)  # preserva bucket até ativar GCS

            setattr(model, nas_field, final_nas)
            setattr(model, bucket_field, final_bucket)

            self.logger.debug(
                f"Id {product_id}: Slot secundária {slot} no JSON — "
                f"NAS: {final_nas} | Bucket: {final_bucket}"
            )

        return model

    # ======================================================================
    # Processamento de imagem (NAS + GCS)
    # ======================================================================

    def _process_and_store_image(
        self,
        product_id: int,
        source_filename: str,
        dest_filename: str,
        row_dict: dict,
        label: str,
    ) -> tuple[Optional[Path], Optional[str]]:
        """
        Pipeline completo para uma imagem:
          1. Valida extensão
          2. Verifica existência na landing
          3. Redimensiona e converte para JPG (em temp dir)
          4. Salva no NAS
          5. (Futuro) Upload para GCS

        Retorna (nas_path, bucket_uri) ou (None, None) em caso de erro.
        Registra o filename original para limpeza da landing.
        """
        self.logger.info(
            f"Id {product_id}: [{label}] Processando imagem '{source_filename}' → '{dest_filename}'"
        )

        # 1. Validar extensão
        if not self.image_service.validate_extension(source_filename):
            self.logger.error(
                f"Id {product_id}: [{label}] Extensão inválida para '{source_filename}'."
            )
            return None, None

        # 2. Verificar na landing
        landing_path = self.image_service.file_exists_in_landing(source_filename)
        if landing_path is None:
            self.logger.error(
                f"Id {product_id}: [{label}] Arquivo '{source_filename}' não encontrado "
                "na landing. Processamento interrompido para esta imagem."
            )
            return None, None

        # 3. Processar (resize + conversão JPG)
        temp_dir = Path(tempfile.mkdtemp())
        temp_img = temp_dir / dest_filename

        try:
            if not self.image_service.process_image(landing_path, temp_img):
                self.logger.error(
                    f"Id {product_id}: [{label}] Falha no processamento da imagem "
                    f"'{source_filename}'."
                )
                return None, None

            # 4. Salvar no NAS
            nas_folder = self.nas_service.build_product_path(row_dict, product_id)
            nas_result = self.nas_service.save_image(temp_img, nas_folder, dest_filename)
            if nas_result is None:
                self.logger.error(
                    f"Id {product_id}: [{label}] Falha ao salvar '{dest_filename}' no NAS."
                )
                return None, None

            # 5. Upload GCS (comentado até ativar)
            # bucket_uri = self.storage_service.upload_image(temp_img, dest_filename)
            # if bucket_uri is None:
            #     self.logger.warning(
            #         f"Id {product_id}: [{label}] Upload GCS falhou. "
            #         "Continuando apenas com NAS."
            #     )
            bucket_uri = None

            # Registrar para limpeza da landing
            self._filenames_to_clean.append(source_filename)
            self.logger.info(
                f"Id {product_id}: [{label}] Imagem armazenada com sucesso. "
                f"NAS: {nas_result}"
            )
            return nas_result, bucket_uri

        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    # ======================================================================
    # Cache de caminhos de secundárias (para _build_model)
    # ======================================================================

    @property
    def _secondary_nas_cache(self) -> dict:
        """Cache em memória: (product_id, slot) → nas_path."""
        if not hasattr(self, "_sec_nas_cache"):
            self._sec_nas_cache = {}
        return self._sec_nas_cache

    def _register_secondary_nas(
        self, product_id: int, slot: int, nas_path: Path
    ) -> None:
        """Registra o NAS path de uma secundária recém-processada."""
        self._secondary_nas_cache[(product_id, slot)] = str(nas_path)
        self.logger.debug(
            f"Id {product_id}: Cache secundária slot {slot} → {nas_path}"
        )

    def _register_secondary_deletion(self, product_id: int, slot: int) -> None:
        """
        Marca um slot como deletado no cache usando None como sentinela.
        _build_model ao encontrar None limpa os campos NAS e bucket no JSON.
        """
        self._secondary_nas_cache[(product_id, slot)] = None
        self.logger.debug(
            f"Id {product_id}: Cache secundária slot {slot} → None (deletado)"
        )

    # ======================================================================
    # Limpeza da landing
    # ======================================================================

    def _cleanup_landing(self) -> int:
        """
        Remove da landing apenas os arquivos que foram processados nesta execução.
        Arquivos presentes na landing mas ausentes da planilha são mantidos.
        Retorna o número de arquivos removidos.
        """
        count = 0
        self.logger.info(
            f"[Cleanup] Iniciando limpeza da landing. "
            f"Arquivos a remover: {len(set(self._filenames_to_clean))}"
        )
        for filename in set(self._filenames_to_clean):
            path = settings.general.landing_path / filename
            try:
                if path.exists():
                    path.unlink()
                    self.logger.info(f"[Cleanup] Removido da landing: {filename}")
                    count += 1
                else:
                    self.logger.debug(
                        f"[Cleanup] Arquivo não encontrado na landing "
                        f"(já removido?): {filename}"
                    )
            except Exception as exc:
                self.logger.error(
                    f"[Cleanup] Erro ao remover '{filename}': {exc}", exc_info=True
                )
        self.logger.info(f"[Cleanup] {count} arquivo(s) removido(s) da landing.")
        return count
