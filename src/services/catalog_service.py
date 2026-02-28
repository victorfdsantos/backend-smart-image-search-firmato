import json
import logging
import os
import shutil
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd

from config.settings import settings
from models.product_model import ProductModel, COLUMN_MAP
from services.image_service import ImageService
from services.nas_service import NasService
from services.storage_service import StorageService


_PROCESSED_MARKER = "Processada"


class CatalogService:
    """
    Serviço principal do fluxo de cadastro do catálogo.
    Orquestra leitura da planilha, processamento de imagens,
    escrita de JSONs, atualização do Excel e limpeza da landing.
    """

    def __init__(self, logger: logging.Logger):
        self.logger = logger
        self.image_service = ImageService(logger)
        self.nas_service = NasService(logger)
        # self.storage_service = StorageService(logger)
        self._filenames_to_clean: list[str] = []

    # ------------------------------------------------------------------
    # Ponto de entrada
    # ------------------------------------------------------------------

    def process_spreadsheet(self, xlsx_path: Path) -> dict:
        """
        Executa o fluxo completo de cadastro a partir de uma planilha.
        Retorna um dicionário com estatísticas da execução.
        """
        stats = {
            "total": 0,
            "processados": 0,
            "secundarias_processadas": 0,
            "ignorados": 0,
            "erros": 0,
            "arquivos_limpos": 0,
        }

        self.logger.info(f"Iniciando processamento da planilha: {xlsx_path}")

        # 1. Ler planilha
        try:
            df = pd.read_excel(xlsx_path, sheet_name="Catalogo_Produtos", dtype=str)
            df = df.where(pd.notna(df), None)
            self.logger.info(f"Planilha carregada: {len(df)} linhas encontradas.")
        except Exception as exc:
            self.logger.error(f"Falha ao abrir planilha: {exc}", exc_info=True)
            raise

        stats["total"] = len(df)

        # 2. Processar cada linha
        for idx, row in df.iterrows():
            row_dict = row.to_dict()
            product_id = self._parse_id(row_dict.get("Id_produto"))

            if product_id is None:
                self.logger.warning(f"Linha {idx + 2}: Id_produto inválido ou vazio. Pulando.")
                stats["erros"] += 1
                continue

            self.logger.info(f"--- Processando linha {idx + 2} | Id_produto: {product_id} ---")

            caminho_img = self._clean_str(row_dict.get("Caminho_Imagem"))
            caminho_sec = self._clean_str(row_dict.get("Caminho_Imagem_Secundaria"))

            is_new = self._is_new_process(caminho_img)

            if is_new:
                # ---- PROCESSO NOVO ----
                success, updated_row = self._process_new_product(
                    row_dict, product_id, caminho_img, caminho_sec
                )
                if success:
                    # Atualiza o DataFrame com os novos valores
                    for col, val in updated_row.items():
                        if col in df.columns:
                            df.at[idx, col] = val
                    stats["processados"] += 1
                else:
                    stats["erros"] += 1

            else:
                # ---- PROCESSO EXISTENTE: verificar secundárias ----
                if not caminho_sec or caminho_sec.upper() == _PROCESSED_MARKER.upper():
                    self.logger.info(
                        f"Id {product_id}: Imagem principal já processada e "
                        "sem secundárias pendentes. Ignorando."
                    )
                    stats["ignorados"] += 1
                    continue

                success, updated_row = self._process_secondary_images(
                    row_dict, product_id, caminho_sec
                )
                if success:
                    for col, val in updated_row.items():
                        if col in df.columns:
                            df.at[idx, col] = val
                    stats["secundarias_processadas"] += 1
                else:
                    stats["erros"] += 1

        # 3. Salvar planilha atualizada
        self._save_spreadsheet(df, xlsx_path)

        # 4. Limpar landing
        cleaned = self._cleanup_landing()
        stats["arquivos_limpos"] = cleaned

        self.logger.info(
            f"Processamento concluído. Stats: {stats}"
        )
        return stats

    # ------------------------------------------------------------------
    # Processo novo (imagem principal)
    # ------------------------------------------------------------------

    def _process_new_product(
        self,
        row_dict: dict,
        product_id: int,
        caminho_img: str,
        caminho_sec: Optional[str],
    ) -> tuple[bool, dict]:
        """
        Executa o fluxo completo para um produto novo:
        - valida, processa e move imagem principal
        - processa imagens secundárias se houver
        - gera hash, JSON e atualiza caminhos
        """
        updated = {}

        # --- Validar imagem principal ---
        filename_principal = caminho_img
        if not self.image_service.validate_extension(filename_principal):
            self.logger.error(
                f"Id {product_id}: Extensão inválida para '{filename_principal}'. "
                "Linha ignorada."
            )
            return False, {}

        landing_path = self.image_service.file_exists_in_landing(filename_principal)
        if landing_path is None:
            return False, {}

        # --- Processar imagem principal ---
        img_name = self.image_service.primary_image_name(product_id)
        temp_dir = Path(tempfile.mkdtemp())
        temp_img = temp_dir / img_name

        if not self.image_service.process_image(landing_path, temp_img):
            return False, {}

        # --- Definir caminhos organizacionais ---
        nas_folder = self.nas_service.build_product_path(row_dict, product_id)
        # blob_name = self.storage_service.build_blob_path(row_dict, product_id, img_name)

        # --- Mover para NAS ---
        nas_result = self.nas_service.save_image(temp_img, nas_folder, img_name)
        if nas_result is None:
            return False, {}

        # --- Upload para GCS ---
        # gcs_uri = self.storage_service.upload_image(temp_img, blob_name)
        # if gcs_uri is None:
        #     self.logger.warning(
        #         f"Id {product_id}: Upload GCS falhou. Continuando apenas com NAS."
        #     )

        # --- Gerar hash (chave_especial) ---
        chave = self.image_service.generate_hash(row_dict)
        updated["Chave_Especial"] = chave
        updated["Caminho_Imagem"] = str(nas_result)
        # if gcs_uri:
        #     updated["Caminho_Bucket"] = gcs_uri

        self._filenames_to_clean.append(filename_principal)

        # --- Processar imagens secundárias (se houver) ---
        if caminho_sec and caminho_sec.strip():
            sec_paths, sec_bucket_paths = self._handle_secondary_images(
                row_dict, product_id, caminho_sec
            )
            if sec_paths:
                updated["Caminho_Imagem_Secundaria"] = _PROCESSED_MARKER
            # bucket das secundárias pode ser armazenado ou ignorado conforme necessidade futura

        # --- Gerar JSON ---
        row_dict.update(updated)
        self._save_json(row_dict, product_id)

        # --- Limpeza temporária ---
        shutil.rmtree(temp_dir, ignore_errors=True)

        self.logger.info(f"Id {product_id}: Produto novo processado com sucesso.")
        return True, updated

    # ------------------------------------------------------------------
    # Processo de secundárias (produto já existente)
    # ------------------------------------------------------------------

    def _process_secondary_images(
        self,
        row_dict: dict,
        product_id: int,
        caminho_sec: str,
    ) -> tuple[bool, dict]:
        """Processa somente as imagens secundárias de um produto já cadastrado."""
        self.logger.info(f"Id {product_id}: Processando apenas imagens secundárias.")
        sec_paths, _ = self._handle_secondary_images(row_dict, product_id, caminho_sec)

        if not sec_paths:
            return False, {}

        updated = {"Caminho_Imagem_Secundaria": _PROCESSED_MARKER}
        # Atualizar JSON existente com novo estado
        row_dict.update(updated)
        self._save_json(row_dict, product_id)
        self.logger.info(f"Id {product_id}: Imagens secundárias processadas com sucesso.")
        return True, updated

    # ------------------------------------------------------------------
    # Lógica compartilhada de imagens secundárias
    # ------------------------------------------------------------------

    def _handle_secondary_images(
        self,
        row_dict: dict,
        product_id: int,
        caminho_sec: str,
    ) -> tuple[list[str], list[str]]:
        """
        Processa todas as imagens secundárias (separadas por ' / ').
        Retorna lista de paths NAS e lista de URIs GCS processadas com sucesso.
        """
        nas_paths = []
        # gcs_uris = []
        filenames = [f.strip() for f in caminho_sec.split("/") if f.strip()]

        for i, filename in enumerate(filenames):
            if not self.image_service.validate_extension(filename):
                continue

            landing_path = self.image_service.file_exists_in_landing(filename)
            if landing_path is None:
                continue

            img_name = self.image_service.secondary_image_name(product_id, i)
            temp_dir = Path(tempfile.mkdtemp())
            temp_img = temp_dir / img_name

            if not self.image_service.process_image(landing_path, temp_img):
                shutil.rmtree(temp_dir, ignore_errors=True)
                continue

            nas_folder = self.nas_service.build_product_path(row_dict, product_id)
            # blob_name = self.storage_service.build_blob_path(row_dict, product_id, img_name)

            nas_result = self.nas_service.save_image(temp_img, nas_folder, img_name)
            if nas_result:
                nas_paths.append(str(nas_result))
                self._filenames_to_clean.append(filename)

            # gcs_uri = self.storage_service.upload_image(temp_img, blob_name)
            # if gcs_uri:
            #     gcs_uris.append(gcs_uri)

            shutil.rmtree(temp_dir, ignore_errors=True)

        return nas_paths, f"gs://mock-bucket/{product_id}/{img_name}"

    # ------------------------------------------------------------------
    # JSON
    # ------------------------------------------------------------------

    def _save_json(self, row_dict: dict, product_id: int) -> None:
        """Salva o JSON do produto em data/{ID}.json"""
        try:
            data_dir = settings.general.data_path
            data_dir.mkdir(parents=True, exist_ok=True)
            json_path = data_dir / f"{product_id}.json"

            # Converte para modelo e serializa
            model_data = self._row_to_model(row_dict).to_dict()

            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(model_data, f, ensure_ascii=False, indent=2)

            self.logger.info(f"JSON salvo: {json_path}")
        except Exception as exc:
            self.logger.error(
                f"Erro ao salvar JSON do produto {product_id}: {exc}", exc_info=True
            )

    # ------------------------------------------------------------------
    # Excel
    # ------------------------------------------------------------------

    def _save_spreadsheet(self, df: pd.DataFrame, original_path: Path) -> None:
        """
        Tenta salvar o Excel no caminho original.
        Em caso de falha, salva com sufixo de data/hora para não perder dados.
        """
        nas_dir = settings.nas.base_path / "planilhas"
        nas_dir.mkdir(parents=True, exist_ok=True)

        dest_path = nas_dir / original_path.name
        try:
            df.to_excel(dest_path, index=False, sheet_name="Catalogo_Produtos")
            self.logger.info(f"Planilha salva: {dest_path}")
        except Exception as exc:
            self.logger.error(
                f"Erro ao salvar planilha original: {exc}. Tentando salvar com sufixo.",
                exc_info=True,
            )
            try:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                fallback_path = nas_dir / f"{original_path.stem}_{timestamp}{original_path.suffix}"

                df.to_excel(fallback_path, index=False, sheet_name="Catalogo_Produtos")
                self.logger.info(f"Planilha salva com fallback: {fallback_path}")
            except Exception as exc2:
                self.logger.error(
                    f"Falha crítica ao salvar planilha fallback: {exc2}", exc_info=True
                )

    # ------------------------------------------------------------------
    # Limpeza da landing
    # ------------------------------------------------------------------

    def _cleanup_landing(self) -> int:
        """
        Remove da landing apenas os arquivos que foram processados nesta execução.
        Arquivos que não estavam na planilha são mantidos.
        Retorna o número de arquivos removidos.
        """
        count = 0
        for filename in set(self._filenames_to_clean):
            path = settings.general.landing_path / filename
            try:
                if path.exists():
                    path.unlink()
                    self.logger.info(f"[Cleanup] Removido da landing: {filename}")
                    count += 1
                else:
                    self.logger.debug(
                        f"[Cleanup] Arquivo não encontrado na landing (já removido?): {filename}"
                    )
            except Exception as exc:
                self.logger.error(
                    f"[Cleanup] Erro ao remover '{filename}': {exc}", exc_info=True
                )
        self.logger.info(f"[Cleanup] {count} arquivo(s) removido(s) da landing.")
        return count

    # ------------------------------------------------------------------
    # Utilitários internos
    # ------------------------------------------------------------------

    def _is_new_process(self, caminho_img: Optional[str]) -> bool:
        """
        Determina se a linha é um processo novo.
        Um processo novo = Caminho_Imagem é apenas um nome de arquivo (sem '/' ou '\').
        Um caminho definido (processado) contém separadores de pasta.
        """
        if not caminho_img:
            return False
        # Se contém separadores de diretório, é caminho definido (já processado ou parcialmente)
        return "/" not in caminho_img and "\\" not in caminho_img

    def _parse_id(self, value) -> Optional[int]:
        try:
            return int(float(str(value)))
        except (ValueError, TypeError):
            return None

    def _clean_str(self, value) -> Optional[str]:
        if value is None:
            return None
        s = str(value).strip()
        return s if s and s.lower() not in ("nan", "none") else None

    def _row_to_model(self, row_dict: dict) -> ProductModel:
        """Converte um dicionário de linha do Excel para ProductModel."""
        model = ProductModel()
        for excel_col, model_field in COLUMN_MAP.items():
            val = row_dict.get(excel_col)
            if val is not None and str(val).lower() not in ("nan", "none", ""):
                setattr(model, model_field, val)
        return model
