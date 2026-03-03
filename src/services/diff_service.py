"""
diff_service.py
---------------
Compara o estado atual do Excel com os JSONs em disco e produz
um ProductDiff em memória para cada produto.

Responsabilidade única: observar e reportar diferenças.
Não executa nenhuma ação sobre arquivos ou banco de dados.

Regras de comparação:
  - Excel   → fonte de dados de produto (nome, marca, descrições, etc.)
  - JSON    → fonte de verdade sobre o que já foi processado
               (caminhos NAS/bucket vivem apenas no JSON)
  - Campos de imagem no Excel contêm um filename original (pendente)
    ou um caminho NAS completo (já processado)
  - Produto sem JSON → cadastro novo
"""

import logging
from typing import Optional

from models.product_model import (
    SECONDARY_SLOTS,
    SECONDARY_EXCEL_COLS,
    SECONDARY_NAS_FIELDS,
    SECONDARY_BUCKET_FIELDS,
    COLUMN_MAP,
)
from models.product_diff_model import ProductDiff
from models.secondary_image_diff_model import SecondaryImageDiff
from services.json_service import JsonService

_PROCESSED_MARKER = "Processada"

# Campos do JSON que não existem no Excel — ignorados na comparação de dados
_JSON_ONLY_FIELDS = {
    "caminho_imagem",
    "caminho_bucket_principal",
    "caminho_imagem_secundaria1", "caminho_imagem_secundaria2",
    "caminho_imagem_secundaria3", "caminho_imagem_secundaria4",
    "caminho_bucket_secundaria1", "caminho_bucket_secundaria2",
    "caminho_bucket_secundaria3", "caminho_bucket_secundaria4",
}

# Colunas do Excel que, se mudarem, exigem mover a pasta do produto no NAS
_NAS_ORGANIZER_FIELDS = {
    "Marca":               "marca",
    "Linha_Colecao":       "linha_colecao",
    "Categoria_Principal": "categoria_principal",
}


class DiffService:
    """
    Constrói um ProductDiff comparando a linha do Excel com o JSON em disco.
    """

    def __init__(self, logger: logging.Logger, json_service: JsonService):
        self.logger = logger
        self.json_service = json_service

    # ------------------------------------------------------------------
    # Ponto de entrada
    # ------------------------------------------------------------------

    def build(self, product_id: int, row_dict: dict) -> ProductDiff:
        """
        Constrói o ProductDiff para um produto.

        Args:
            product_id: ID numérico do produto.
            row_dict:   Linha do Excel como dicionário (coluna → valor).

        Returns:
            ProductDiff com todas as flags preenchidas.
        """
        self.logger.debug(f"[Diff] Iniciando diff — Id {product_id}.")

        diff = ProductDiff(product_id=product_id, row_dict=row_dict)
        existing_json = self.json_service.load(product_id)

        if existing_json is None:
            self.logger.info(
                f"[Diff] Id {product_id}: JSON não encontrado → cadastro novo."
            )
            diff.is_new_product = True
            diff.primary_excel_value = self._clean(row_dict.get("Caminho_Imagem"))
            diff.primary_is_new = self._is_filename(diff.primary_excel_value)
            self._fill_secondaries_new(diff, row_dict)
            return diff

        self.logger.debug(f"[Diff] Id {product_id}: JSON encontrado. Comparando campos.")

        self._diff_primary_image(diff, row_dict, existing_json)
        self._diff_secondary_images(diff, row_dict, existing_json)
        self._diff_nas_path(diff, row_dict, existing_json)
        self._diff_data_fields(diff, row_dict, existing_json)

        self.logger.info(
            f"[Diff] Id {product_id}: "
            f"novo={diff.is_new_product} | "
            f"primary_new={diff.primary_is_new} | "
            f"primary_changed={diff.primary_is_changed} | "
            f"nas_moved={diff.nas_path_changed} | "
            f"sec_changes={len(diff.secondary_changes)} | "
            f"sec_deletions={len(diff.secondary_deletions)} | "
            f"data_changed={diff.data_fields_changed} ({diff.changed_data_fields})"
        )

        return diff

    # ------------------------------------------------------------------
    # Imagem principal
    # ------------------------------------------------------------------

    def _diff_primary_image(
        self, diff: ProductDiff, row_dict: dict, existing_json: dict
    ) -> None:
        """
        Casos possíveis:
          filename no Excel + JSON tem caminho → imagem trocada
          filename no Excel + JSON sem caminho → nova (JSON inconsistente)
          caminho NAS no Excel ou vazio        → já processado, sem mudança
        """
        excel_val = self._clean(row_dict.get("Caminho_Imagem"))
        json_nas = existing_json.get("caminho_imagem")
        json_bucket = existing_json.get("caminho_bucket_principal")

        diff.primary_excel_value = excel_val
        diff.primary_json_nas_path = json_nas
        diff.primary_json_bucket_uri = json_bucket

        if self._is_filename(excel_val):
            if json_nas:
                diff.primary_is_changed = True
                self.logger.info(
                    f"[Diff] Id {diff.product_id}: Imagem principal TROCADA. "
                    f"Excel='{excel_val}' | JSON NAS='{json_nas}'"
                )
            else:
                diff.primary_is_new = True
                self.logger.info(
                    f"[Diff] Id {diff.product_id}: Imagem principal NOVA (JSON sem caminho). "
                    f"Excel='{excel_val}'"
                )
        else:
            self.logger.debug(
                f"[Diff] Id {diff.product_id}: Imagem principal sem mudança. "
                f"Excel='{excel_val}'"
            )

    # ------------------------------------------------------------------
    # Imagens secundárias — produto existente
    # ------------------------------------------------------------------

    def _diff_secondary_images(
        self, diff: ProductDiff, row_dict: dict, existing_json: dict
    ) -> None:
        """Avalia cada slot (1-4) comparando Excel e JSON."""
        for slot in SECONDARY_SLOTS:
            excel_col   = SECONDARY_EXCEL_COLS[slot]
            nas_field   = SECONDARY_NAS_FIELDS[slot]
            bucket_field = SECONDARY_BUCKET_FIELDS[slot]

            excel_val  = self._clean(row_dict.get(excel_col))
            json_nas   = existing_json.get(nas_field)
            json_bucket = existing_json.get(bucket_field)

            sec = SecondaryImageDiff(
                slot=slot,
                excel_value=excel_val,
                json_nas_path=json_nas,
                json_bucket_uri=json_bucket,
            )

            if not excel_val and json_nas:
                sec.is_deleted = True
                self.logger.info(
                    f"[Diff] Id {diff.product_id}: Slot {slot} DELETADO. "
                    f"NAS='{json_nas}'"
                )
            elif not excel_val and not json_nas:
                sec.is_empty = True
                self.logger.debug(
                    f"[Diff] Id {diff.product_id}: Slot {slot} vazio."
                )
            elif self._is_processed(excel_val) and json_nas:
                sec.is_processed = True
                self.logger.debug(
                    f"[Diff] Id {diff.product_id}: Slot {slot} já processado."
                )
            elif self._is_filename(excel_val) and not json_nas:
                sec.is_new = True
                self.logger.info(
                    f"[Diff] Id {diff.product_id}: Slot {slot} NOVA. "
                    f"Excel='{excel_val}'"
                )
            elif self._is_filename(excel_val) and json_nas:
                sec.is_changed = True
                self.logger.info(
                    f"[Diff] Id {diff.product_id}: Slot {slot} TROCADA. "
                    f"Excel='{excel_val}' | JSON NAS='{json_nas}'"
                )
            else:
                sec.is_empty = True
                self.logger.warning(
                    f"[Diff] Id {diff.product_id}: Slot {slot} — "
                    f"valor não reconhecido: '{excel_val}'. Tratando como vazio."
                )

            diff.secondaries.append(sec)

    # ------------------------------------------------------------------
    # Imagens secundárias — produto novo (sem JSON)
    # ------------------------------------------------------------------

    def _fill_secondaries_new(self, diff: ProductDiff, row_dict: dict) -> None:
        """Para produtos novos, qualquer filename no Excel é marcado como is_new."""
        for slot in SECONDARY_SLOTS:
            excel_col = SECONDARY_EXCEL_COLS[slot]
            excel_val = self._clean(row_dict.get(excel_col))

            sec = SecondaryImageDiff(
                slot=slot,
                excel_value=excel_val,
                json_nas_path=None,
                json_bucket_uri=None,
            )
            if self._is_filename(excel_val):
                sec.is_new = True
                self.logger.info(
                    f"[Diff] Id {diff.product_id}: Slot {slot} NOVA (produto novo). "
                    f"Excel='{excel_val}'"
                )
            else:
                sec.is_empty = True

            diff.secondaries.append(sec)

    # ------------------------------------------------------------------
    # Colunas organizadoras do NAS
    # ------------------------------------------------------------------

    def _diff_nas_path(
        self, diff: ProductDiff, row_dict: dict, existing_json: dict
    ) -> None:
        """Detecta se Marca, Linha_Colecao ou Categoria_Principal mudaram."""
        for excel_col, json_field in _NAS_ORGANIZER_FIELDS.items():
            excel_val = self._clean(row_dict.get(excel_col)) or ""
            json_val  = str(existing_json.get(json_field) or "")

            if excel_val != json_val:
                diff.nas_path_changed = True
                self.logger.info(
                    f"[Diff] Id {diff.product_id}: Campo organizador NAS mudou: "
                    f"'{excel_col}' Excel='{excel_val}' → JSON='{json_val}'"
                )
                return  # um campo diferente já é suficiente

        self.logger.debug(
            f"[Diff] Id {diff.product_id}: Colunas organizadoras NAS sem mudança."
        )

    # ------------------------------------------------------------------
    # Campos de dados
    # ------------------------------------------------------------------

    def _diff_data_fields(
        self, diff: ProductDiff, row_dict: dict, existing_json: dict
    ) -> None:
        """Compara todos os campos de produto (non-image) entre Excel e JSON."""
        changed = []
        for excel_col, model_field in COLUMN_MAP.items():
            if model_field in _JSON_ONLY_FIELDS:
                continue
            excel_val = self._normalize(row_dict.get(excel_col))
            json_val  = self._normalize(existing_json.get(model_field))
            if excel_val != json_val:
                changed.append(excel_col)
                self.logger.debug(
                    f"[Diff] Id {diff.product_id}: Campo '{excel_col}' mudou. "
                    f"Excel='{excel_val}' → JSON='{json_val}'"
                )

        if changed:
            diff.data_fields_changed = True
            diff.changed_data_fields = changed
            self.logger.info(
                f"[Diff] Id {diff.product_id}: {len(changed)} campo(s) alterado(s): {changed}"
            )

    # ------------------------------------------------------------------
    # Utilitários
    # ------------------------------------------------------------------

    def _clean(self, value) -> Optional[str]:
        """Normaliza célula: None/NaN/vazio → None."""
        if value is None:
            return None
        s = str(value).strip()
        return s if s and s.lower() not in ("nan", "none") else None

    def _normalize(self, value) -> str:
        """Para comparação: None e string vazia são equivalentes."""
        if value is None:
            return ""
        return str(value).strip()

    def _is_filename(self, value: Optional[str]) -> bool:
        """
        True se o valor é um filename solto (sem separador de pasta),
        indicando imagem pendente de processamento.
        Caminhos NAS (com '/') retornam False naturalmente.
        """
        if not value:
            return False
        return "/" not in value and "\\" not in value

    def _is_processed(self, value: Optional[str]) -> bool:
        """
        True se o slot já foi processado.
        Detecta caminho NAS (contém '/' ou '\\').
        Mantém compatibilidade com o marcador legado 'Processada'.
        """
        if not value:
            return False
        if "/" in value or "\\" in value:
            return True
        return value.strip().lower() == _PROCESSED_MARKER.lower()
