"""
DiffService
-----------
Compara a linha do Excel com o JSON em disco e devolve um ProductDiff.
Responsabilidade única: observar e reportar — nunca executa ações.
"""

import logging
from typing import Optional

from models.product_model import SECONDARY_SLOTS, SECONDARY_EXCEL_COLS, SECONDARY_NAS_FIELDS, SECONDARY_BUCKET_FIELDS, COLUMN_MAP
from models.product_diff_model import ProductDiff
from models.secondary_image_diff_model import SecondaryImageDiff
from services.json_service import JsonService

_PROCESSED_MARKER = "Processada"

# Campos que existem só no JSON — ignorados na comparação de dados
_JSON_ONLY_FIELDS = {
    "caminho_imagem", "caminho_bucket_principal",
    *[f"caminho_imagem_secundaria{i}" for i in SECONDARY_SLOTS],
    *[f"caminho_bucket_secundaria{i}" for i in SECONDARY_SLOTS],
}

# Colunas do Excel que, se mudarem, exigem mover a pasta no NAS
_NAS_ORGANIZER_FIELDS = {
    "Marca": "marca",
    "Linha_Colecao": "linha_colecao",
    "Categoria_Principal": "categoria_principal",
}


def _clean(value) -> Optional[str]:
    """Célula do Excel → string limpa ou None."""
    if value is None:
        return None
    s = str(value).strip()
    return s if s and s.lower() not in ("nan", "none") else None


def _normalize(value) -> str:
    """Para comparação: None e string vazia são equivalentes."""
    return "" if value is None else str(value).strip()


def _is_filename(value: Optional[str]) -> bool:
    """True se é um filename solto (sem separador) — imagem pendente de processamento."""
    return bool(value) and "/" not in value and "\\" not in value


def _is_processed(value: Optional[str]) -> bool:
    """True se o slot já foi processado: caminho NAS (tem '/') ou marcador legado."""
    if not value:
        return False
    if "/" in value or "\\" in value:
        return True
    return value.strip().lower() == _PROCESSED_MARKER.lower()


class DiffService:

    def __init__(self, logger: logging.Logger, json_service: JsonService):
        self.logger = logger
        self.json_service = json_service

    def build(self, product_id: int, row_dict: dict) -> ProductDiff:
        """Constrói o ProductDiff comparando linha do Excel com JSON em disco."""
        diff = ProductDiff(product_id=product_id, row_dict=row_dict)
        existing = self.json_service.load(product_id)

        if existing is None:
            self.logger.info(f"[Diff] Id {product_id}: sem JSON → produto novo.")
            diff.is_new_product = True
            diff.primary_excel_value = _clean(row_dict.get("Caminho_Imagem"))
            diff.primary_is_new = _is_filename(diff.primary_excel_value)
            diff.secondaries = self._build_secondaries(row_dict, existing_json=None)
            return diff

        self._diff_primary(diff, row_dict, existing)
        diff.secondaries = self._build_secondaries(row_dict, existing)
        self._diff_nas_path(diff, row_dict, existing)
        self._diff_data_fields(diff, row_dict, existing)

        self.logger.info(
            f"[Diff] Id {product_id}: "
            f"primary_new={diff.primary_is_new} | primary_changed={diff.primary_is_changed} | "
            f"sec_changes={len(diff.secondary_changes)} | sec_del={len(diff.secondary_deletions)} | "
            f"nas_moved={diff.nas_path_changed} | data_changed={diff.changed_data_fields}"
        )
        return diff

    def _diff_primary(self, diff: ProductDiff, row_dict: dict, existing: dict) -> None:
        excel_val = _clean(row_dict.get("Caminho_Imagem"))
        diff.primary_excel_value = excel_val
        diff.primary_json_nas_path = existing.get("caminho_imagem")
        diff.primary_json_bucket_uri = existing.get("caminho_bucket_principal")

        if not _is_filename(excel_val):
            return  # já processado ou vazio — sem mudança

        if diff.primary_json_nas_path:
            diff.primary_is_changed = True
            self.logger.info(f"[Diff] Id {diff.product_id}: imagem principal TROCADA. Novo='{excel_val}'")
        else:
            diff.primary_is_new = True
            self.logger.info(f"[Diff] Id {diff.product_id}: imagem principal NOVA. Arquivo='{excel_val}'")

    def _build_secondaries(
        self, row_dict: dict, existing_json: Optional[dict]
    ) -> list[SecondaryImageDiff]:
        """
        Constrói a lista de SecondaryImageDiff para todos os slots.
        Funciona tanto para produto novo (existing_json=None) quanto existente.
        """
        existing = existing_json or {}
        secondaries = []

        for slot in SECONDARY_SLOTS:
            excel_val  = _clean(row_dict.get(SECONDARY_EXCEL_COLS[slot]))
            json_nas   = existing.get(SECONDARY_NAS_FIELDS[slot])
            json_bucket = existing.get(SECONDARY_BUCKET_FIELDS[slot])

            sec = SecondaryImageDiff(slot=slot, excel_value=excel_val,
                                     json_nas_path=json_nas, json_bucket_uri=json_bucket)

            if not excel_val and json_nas:
                sec.is_deleted = True
                self.logger.info(f"[Diff] Id ? Slot {slot}: DELETADO. NAS='{json_nas}'")
            elif not excel_val:
                sec.is_empty = True
            elif _is_processed(excel_val) and json_nas:
                sec.is_processed = True
            elif _is_filename(excel_val) and not json_nas:
                sec.is_new = True
                self.logger.info(f"[Diff] Id ? Slot {slot}: NOVA. Arquivo='{excel_val}'")
            elif _is_filename(excel_val) and json_nas:
                sec.is_changed = True
                self.logger.info(f"[Diff] Id ? Slot {slot}: TROCADA. Novo='{excel_val}'")
            else:
                sec.is_empty = True
                self.logger.warning(f"[Diff] Id ? Slot {slot}: valor não reconhecido '{excel_val}'. Ignorando.")

            secondaries.append(sec)

        return secondaries

    def _diff_nas_path(self, diff: ProductDiff, row_dict: dict, existing: dict) -> None:
        for excel_col, json_field in _NAS_ORGANIZER_FIELDS.items():
            if (_clean(row_dict.get(excel_col)) or "") != str(existing.get(json_field) or ""):
                diff.nas_path_changed = True
                self.logger.info(f"[Diff] Id {diff.product_id}: coluna organizadora '{excel_col}' mudou → mover pasta NAS.")
                return

    def _diff_data_fields(self, diff: ProductDiff, row_dict: dict, existing: dict) -> None:
        changed = [
            col for col, field in COLUMN_MAP.items()
            if field not in _JSON_ONLY_FIELDS
            and _normalize(row_dict.get(col)) != _normalize(existing.get(field))
        ]
        if changed:
            diff.data_fields_changed = True
            diff.changed_data_fields = changed
            self.logger.info(f"[Diff] Id {diff.product_id}: {len(changed)} campo(s) alterado(s): {changed}")
