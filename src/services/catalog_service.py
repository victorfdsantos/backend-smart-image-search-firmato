"""
CatalogService
--------------
Orquestra o fluxo de cadastro e manutenção do catálogo.

Por produto:
  1. DiffService compara Excel vs JSON → ProductDiff
  2. CatalogService executa as ações indicadas pelo diff
  3. JSON é salvo com o estado final
  4. Excel é atualizado com novos caminhos
"""

import logging
import shutil
import tempfile
from pathlib import Path
from typing import Optional

from config.settings import settings
from models.product_model import ProductModel, SECONDARY_SLOTS, SECONDARY_EXCEL_COLS, SECONDARY_NAS_FIELDS, SECONDARY_BUCKET_FIELDS
from models.product_diff_model import ProductDiff
from models.secondary_image_diff_model import SecondaryImageDiff
from services.diff_service import DiffService
from services.image_service import ImageService
from services.json_service import JsonService
from services.nas_service import NasService
from services.spreadsheet_service import SpreadsheetService


class CatalogService:

    def __init__(self, logger: logging.Logger):
        self.logger = logger
        self.image_service = ImageService(logger)
        self.nas_service = NasService(logger)
        self.spreadsheet_service = SpreadsheetService(logger)
        self.json_service = JsonService(logger)
        self.diff_service = DiffService(logger, self.json_service)

        self._filenames_to_clean: list[str] = []
        # Cache de caminhos NAS gerados nesta execução: (product_id, slot) → str | None
        # None = slot foi deletado; ausente = não tocado (preserva JSON)
        self._secondary_cache: dict[tuple[int, int], Optional[str]] = {}

    # ------------------------------------------------------------------
    # Ponto de entrada
    # ------------------------------------------------------------------

    def process_spreadsheet(self, xlsx_path: Path) -> dict:
        stats = {
            "total": 0, "novos": 0, "imagem_principal_atualizada": 0,
            "secundarias_processadas": 0, "secundarias_deletadas": 0,
            "pasta_nas_movida": 0, "dados_atualizados": 0,
            "ignorados": 0, "erros": 0, "arquivos_limpos": 0,
        }

        self.logger.info(f"{'=' * 60}\nIniciando processamento: {xlsx_path}\n{'=' * 60}")

        try:
            df = self.spreadsheet_service.load(xlsx_path)
        except Exception as exc:
            self.logger.error(f"Falha crítica ao abrir planilha: {exc}", exc_info=True)
            raise

        stats["total"] = len(df)

        for idx, row in df.iterrows():
            row_dict = row.to_dict()
            product_id = self.spreadsheet_service.parse_id(row_dict.get("Id_produto"))

            if product_id is None:
                self.logger.warning(f"Linha {idx + 2}: Id_produto inválido — pulando.")
                stats["erros"] += 1
                continue

            self.logger.info(f"{'─' * 50}\nLinha {idx + 2} | Id {product_id}")

            try:
                diff = self.diff_service.build(product_id, row_dict)
            except Exception as exc:
                self.logger.error(f"Id {product_id}: erro no diff: {exc}", exc_info=True)
                stats["erros"] += 1
                continue

            if not diff.has_any_change:
                self.logger.info(f"Id {product_id}: sem alterações.")
                stats["ignorados"] += 1
                continue

            try:
                excel_updates = self._execute(diff)
            except Exception as exc:
                self.logger.error(f"Id {product_id}: erro inesperado: {exc}", exc_info=True)
                stats["erros"] += 1
                continue

            if excel_updates is None:
                stats["erros"] += 1
                continue

            for col, val in excel_updates.items():
                if col in df.columns:
                    df.at[idx, col] = val

            self._count_stats(stats, diff)

        self.spreadsheet_service.save(df, xlsx_path)
        stats["arquivos_limpos"] = self._cleanup_landing()
        self.logger.info(f"Concluído. Stats: {stats}")
        return stats

    def _count_stats(self, stats: dict, diff: ProductDiff) -> None:
        if diff.is_new_product:
            stats["novos"] += 1
            return
        if diff.primary_is_changed:
            stats["imagem_principal_atualizada"] += 1
        if diff.secondary_changes:
            stats["secundarias_processadas"] += len(diff.secondary_changes)
        if diff.secondary_deletions:
            stats["secundarias_deletadas"] += len(diff.secondary_deletions)
        if diff.nas_path_changed:
            stats["pasta_nas_movida"] += 1
        if diff.data_fields_changed and not any([
            diff.primary_is_changed, diff.secondary_changes,
            diff.secondary_deletions, diff.nas_path_changed
        ]):
            stats["dados_atualizados"] += 1

    # ------------------------------------------------------------------
    # Execução do diff
    # ------------------------------------------------------------------

    def _execute(self, diff: ProductDiff) -> Optional[dict]:
        """Executa todas as ações indicadas pelo diff. Retorna updates para o Excel ou None em erro bloqueante."""
        if diff.is_new_product:
            return self._handle_new_product(diff)

        updates: dict = {}

        if diff.primary_is_new or diff.primary_is_changed:
            result = self._handle_primary_image(diff)
            if result is None:
                return None
            updates.update(result)

        for sec in diff.secondary_changes:
            updates.update(self._handle_secondary_image(diff, sec))

        for sec in diff.secondary_deletions:
            self._handle_secondary_deletion(diff, sec)

        if diff.nas_path_changed:
            result = self._handle_nas_path_change(diff)
            if result is None:
                return None
            updates.update(result)

        self._save_json(diff)
        return updates

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------

    def _handle_new_product(self, diff: ProductDiff) -> Optional[dict]:
        pid = diff.product_id
        self.logger.info(f"Id {pid}: cadastro novo.")

        if not diff.primary_excel_value:
            self.logger.error(f"Id {pid}: produto novo sem imagem principal — ignorado.")
            return None

        nas_path = self._process_image(pid, diff.primary_excel_value,
                                       self.image_service.primary_image_name(pid),
                                       diff.row_dict, label="principal")
        if nas_path is None:
            return None

        updates = {
            "Chave_Especial": self.image_service.generate_hash(diff.row_dict),
            "Caminho_Imagem": str(nas_path),
        }

        for sec in diff.secondaries:
            if sec.is_new:
                updates.update(self._handle_secondary_image(diff, sec))

        self._save_json(diff, primary_nas=str(nas_path))
        return updates

    def _handle_primary_image(self, diff: ProductDiff) -> Optional[dict]:
        pid = diff.product_id
        self.logger.info(f"Id {pid}: trocando imagem principal → '{diff.primary_excel_value}'")

        if diff.primary_json_nas_path:
            self.nas_service.delete_image(diff.primary_json_nas_path)
        # GCS: self.storage_service.delete_image(Path(diff.primary_json_bucket_uri).name)

        nas_path = self._process_image(pid, diff.primary_excel_value,
                                       self.image_service.primary_image_name(pid),
                                       diff.row_dict, label="principal")
        if nas_path is None:
            return None

        return {"Caminho_Imagem": str(nas_path)}

    def _handle_secondary_image(self, diff: ProductDiff, sec: SecondaryImageDiff) -> dict:
        pid = diff.product_id
        slot = sec.slot

        if sec.is_changed and sec.json_nas_path:
            self.nas_service.delete_image(sec.json_nas_path)
            # GCS: self.storage_service.delete_image(Path(sec.json_bucket_uri).name)

        nas_path = self._process_image(
            pid, sec.excel_value,
            self.image_service.secondary_image_name(pid, slot - 1),
            diff.row_dict, label=f"secundária {slot}"
        )

        if nas_path is None:
            self.logger.warning(f"Id {pid}: falha na secundária slot {slot} — slot ignorado.")
            return {}

        self._secondary_cache[(pid, slot)] = str(nas_path)
        return {SECONDARY_EXCEL_COLS[slot]: str(nas_path)}

    def _handle_secondary_deletion(self, diff: ProductDiff, sec: SecondaryImageDiff) -> None:
        pid = diff.product_id
        self.logger.info(f"Id {pid}: deletando secundária slot {sec.slot}.")

        if sec.json_nas_path:
            self.nas_service.delete_image(sec.json_nas_path)
        # GCS: if sec.json_bucket_uri: self.storage_service.delete_image(...)

        self._secondary_cache[(pid, sec.slot)] = None  # sentinela: limpar no JSON

    def _handle_nas_path_change(self, diff: ProductDiff) -> Optional[dict]:
        pid = diff.product_id
        self.logger.info(f"Id {pid}: movendo pasta NAS.")

        new_path = self.nas_service.build_product_path(diff.row_dict, pid)
        current_path = self.nas_service.find_product_folder(pid)

        if current_path is not None:
            if not self.nas_service.move_product_folder(current_path, new_path):
                self.logger.error(f"Id {pid}: falha ao mover pasta NAS.")
                return None

        primary_name = self.image_service.primary_image_name(pid)
        return {"Caminho_Imagem": str(new_path / primary_name)}

    # ------------------------------------------------------------------
    # JSON
    # ------------------------------------------------------------------

    def _save_json(self, diff: ProductDiff, primary_nas: Optional[str] = None) -> None:
        """Constrói e salva o JSON do produto com o estado final."""
        pid = diff.product_id
        existing = self.json_service.load(pid) or {}

        model = self.spreadsheet_service.row_to_model(diff.row_dict)

        # Imagem principal: novo caminho > existente no JSON
        model.caminho_imagem = primary_nas or existing.get("caminho_imagem")
        model.caminho_bucket_principal = existing.get("caminho_bucket_principal")

        # Secundárias: cache desta execução > existente no JSON
        # Cache ausente = não tocado (preserva); None = deletado (limpa); str = novo
        _ABSENT = object()
        for slot in SECONDARY_SLOTS:
            cached = self._secondary_cache.get((pid, slot), _ABSENT)
            if cached is _ABSENT:
                nas = existing.get(SECONDARY_NAS_FIELDS[slot])
                bucket = existing.get(SECONDARY_BUCKET_FIELDS[slot])
            elif cached is None:
                nas, bucket = None, None
            else:
                nas = cached
                bucket = existing.get(SECONDARY_BUCKET_FIELDS[slot])

            setattr(model, SECONDARY_NAS_FIELDS[slot], nas)
            setattr(model, SECONDARY_BUCKET_FIELDS[slot], bucket)

        self.json_service.save(model, pid)
        self.logger.info(f"Id {pid}: JSON salvo.")

    # ------------------------------------------------------------------
    # Processamento de imagem
    # ------------------------------------------------------------------

    def _process_image(
        self, product_id: int, source_filename: str,
        dest_filename: str, row_dict: dict, label: str
    ) -> Optional[Path]:
        """
        Pipeline: valida → landing → resize/convert → NAS.
        Retorna o Path NAS em sucesso ou None em falha (já logada).
        """
        self.logger.info(f"Id {product_id}: [{label}] '{source_filename}' → '{dest_filename}'")

        landing_path = self.image_service.file_exists_in_landing(source_filename)
        if landing_path is None:
            self.logger.error(f"Id {product_id}: [{label}] '{source_filename}' não encontrado na landing.")
            return None

        temp_dir = Path(tempfile.mkdtemp())
        try:
            temp_img = temp_dir / dest_filename
            if not self.image_service.process_image(landing_path, temp_img):
                self.logger.error(f"Id {product_id}: [{label}] falha ao processar imagem.")
                return None

            nas_folder = self.nas_service.build_product_path(row_dict, product_id)
            nas_path = self.nas_service.save_image(temp_img, nas_folder, dest_filename)
            if nas_path is None:
                self.logger.error(f"Id {product_id}: [{label}] falha ao salvar no NAS.")
                return None

            # GCS: self.storage_service.upload_image(temp_img, dest_filename)

            self._filenames_to_clean.append(source_filename)
            self.logger.info(f"Id {product_id}: [{label}] salvo em {nas_path}")
            return nas_path

        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    # ------------------------------------------------------------------
    # Limpeza da landing
    # ------------------------------------------------------------------

    def _cleanup_landing(self) -> int:
        count = 0
        for filename in set(self._filenames_to_clean):
            path = settings.general.landing_path / filename
            try:
                if path.exists():
                    path.unlink()
                    count += 1
            except Exception as exc:
                self.logger.error(f"[Cleanup] Erro ao remover '{filename}': {exc}")
        self.logger.info(f"[Cleanup] {count} arquivo(s) removido(s) da landing.")
        return count
