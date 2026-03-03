"""
DiffService
-----------
Responsável por comparar o estado atual do Excel com os JSONs em disco
e produzir um ProductDiff em memória para cada produto.

O diff é a fonte única de verdade para o CatalogService decidir
o que precisa ser feito: mover pasta no NAS, reprocessar imagem,
atualizar campos, etc.

Regras de comparação:
  - O Excel é a fonte de dados de produto (nome, marca, descrições, etc.)
  - O JSON é a fonte de verdade sobre o que já foi processado
    (caminhos NAS/bucket vivem apenas no JSON)
  - Campos de imagem no Excel (Caminho_Imagem, Caminho_Imagem_SecundariaX)
    contêm ou um filename original (processo pendente) ou "Processada"
  - Se o produto não tem JSON ainda → é um cadastro novo
"""

import logging
from dataclasses import dataclass, field
from typing import Optional

from models.product_model import (
    NAS_ORGANIZER_COLUMNS,
    SECONDARY_SLOTS,
    SECONDARY_EXCEL_COLS,
    SECONDARY_NAS_FIELDS,
    SECONDARY_BUCKET_FIELDS,
)
from services.json_service import JsonService

_PROCESSED_MARKER = "Processada"


# ---------------------------------------------------------------------------
# Estrutura de resultado do diff
# ---------------------------------------------------------------------------

@dataclass
class SecondaryImageDiff:
    """Diff de uma imagem secundária individual."""
    slot: int                          # 1, 2, 3 ou 4
    excel_value: Optional[str]         # valor atual no Excel para este slot
    json_nas_path: Optional[str]       # caminho NAS gravado no JSON
    json_bucket_uri: Optional[str]     # URI bucket gravado no JSON

    # Flags de decisão (preenchidas pelo DiffService)
    is_new: bool = False               # filename solto → precisa processar pela 1ª vez
    is_changed: bool = False           # filename diferente do que foi processado
    is_processed: bool = False         # já processado, sem mudança
    is_deleted: bool = False           # Excel vazio + JSON tem caminho → remover do NAS/bucket/JSON
    is_empty: bool = False             # slot vazio tanto no Excel quanto no JSON


@dataclass
class ProductDiff:
    """
    Resultado completo da comparação Excel vs JSON para um produto.
    É o contrato entre DiffService e CatalogService.
    """
    product_id: int
    row_dict: dict                     # linha completa do Excel (para uso no CatalogService)

    # --- Flags de estado geral ---
    is_new_product: bool = False       # JSON não existe → cadastro novo do zero

    # --- Imagem principal ---
    primary_excel_value: Optional[str] = None    # valor atual no Excel
    primary_json_nas_path: Optional[str] = None  # caminho NAS no JSON
    primary_json_bucket_uri: Optional[str] = None
    primary_is_new: bool = False        # filename solto → nunca foi processado
    primary_is_changed: bool = False    # filename diferente → imagem foi trocada

    # --- Imagens secundárias ---
    secondaries: list[SecondaryImageDiff] = field(default_factory=list)

    # --- Campos organizadores do NAS ---
    nas_path_changed: bool = False      # Marca/Linha/Categoria mudou → mover pasta

    # --- Campos de dados (non-image) ---
    data_fields_changed: bool = False   # qualquer campo de produto mudou
    changed_data_fields: list[str] = field(default_factory=list)  # quais campos mudaram

    # --- Helpers ---
    @property
    def has_any_change(self) -> bool:
        return (
            self.is_new_product
            or self.primary_is_new
            or self.primary_is_changed
            or self.nas_path_changed
            or self.data_fields_changed
            or any(
                s.is_new or s.is_changed or s.is_deleted
                for s in self.secondaries
            )
        )

    @property
    def secondary_changes(self) -> list[SecondaryImageDiff]:
        """Slots com imagem nova ou trocada (precisa processar arquivo)."""
        return [s for s in self.secondaries if s.is_new or s.is_changed]

    @property
    def secondary_deletions(self) -> list[SecondaryImageDiff]:
        """Slots que foram apagados no Excel mas ainda existem no JSON/NAS/bucket."""
        return [s for s in self.secondaries if s.is_deleted]


# ---------------------------------------------------------------------------
# DiffService
# ---------------------------------------------------------------------------

class DiffService:
    """
    Compara o estado do Excel com os JSONs em disco e produz ProductDiff.
    Não executa nenhuma ação — apenas observa e reporta diferenças.
    """

    # Campos de produto que, se mudarem, definem o caminho de pasta no NAS
    _NAS_ORGANIZER_FIELDS = {
        "Marca": "marca",
        "Linha_Colecao": "linha_colecao",
        "Categoria_Principal": "categoria_principal",
    }

    # Campos de dados (non-image, non-path) que existem apenas no JSON
    # e não estão no Excel — ignorados na comparação de dados
    _JSON_ONLY_FIELDS = {
        "caminho_imagem",
        "caminho_bucket_principal",
        "caminho_imagem_secundaria1", "caminho_imagem_secundaria2",
        "caminho_imagem_secundaria3", "caminho_imagem_secundaria4",
        "caminho_bucket_secundaria1", "caminho_bucket_secundaria2",
        "caminho_bucket_secundaria3", "caminho_bucket_secundaria4",
    }

    def __init__(self, logger: logging.Logger, json_service: JsonService):
        self.logger = logger
        self.json_service = json_service

    # ------------------------------------------------------------------
    # Ponto de entrada
    # ------------------------------------------------------------------

    def build(self, product_id: int, row_dict: dict) -> ProductDiff:
        """
        Constrói o ProductDiff para um produto a partir da linha do Excel
        e do JSON em disco (se existir).

        Args:
            product_id: ID numérico do produto.
            row_dict:   Dicionário da linha do Excel (colunas → valores).

        Returns:
            ProductDiff com todas as flags preenchidas.
        """
        self.logger.debug(f"[Diff] Iniciando diff para Id {product_id}.")

        diff = ProductDiff(product_id=product_id, row_dict=row_dict)
        existing_json = self.json_service.load(product_id)

        if existing_json is None:
            # ---- Produto novo: sem JSON ----
            self.logger.info(
                f"[Diff] Id {product_id}: JSON não encontrado → cadastro novo."
            )
            diff.is_new_product = True
            diff.primary_excel_value = self._clean(row_dict.get("Caminho_Imagem"))
            diff.primary_is_new = self._is_filename(diff.primary_excel_value)
            self._fill_secondary_diffs_new(diff, row_dict)
            return diff

        # ---- Produto existente: comparar Excel vs JSON ----
        self.logger.debug(
            f"[Diff] Id {product_id}: JSON encontrado. Comparando campos."
        )

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
            f"data_changed={diff.data_fields_changed} "
            f"({diff.changed_data_fields})"
        )

        return diff

    # ------------------------------------------------------------------
    # Diff da imagem principal
    # ------------------------------------------------------------------

    def _diff_primary_image(
        self, diff: ProductDiff, row_dict: dict, existing_json: dict
    ) -> None:
        """
        Compara o valor de Caminho_Imagem no Excel com o que está no JSON.

        Casos:
          - Excel tem filename solto + JSON tem caminho → imagem foi trocada
          - Excel tem filename solto + JSON não tem caminho → nova (não deveria
            acontecer se o produto já tem JSON, mas tratamos por segurança)
          - Excel tem caminho completo ou vazio → já processado, sem mudança de imagem
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
                # JSON existe mas sem caminho → tratar como novo
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
    # Diff das imagens secundárias
    # ------------------------------------------------------------------

    def _diff_secondary_images(
        self, diff: ProductDiff, row_dict: dict, existing_json: dict
    ) -> None:
        """
        Compara cada slot de imagem secundária (1-4) entre Excel e JSON.
        """
        for slot in SECONDARY_SLOTS:
            excel_col = SECONDARY_EXCEL_COLS[slot]
            nas_field = SECONDARY_NAS_FIELDS[slot]
            bucket_field = SECONDARY_BUCKET_FIELDS[slot]

            excel_val = self._clean(row_dict.get(excel_col))
            json_nas = existing_json.get(nas_field)
            json_bucket = existing_json.get(bucket_field)

            sec = SecondaryImageDiff(
                slot=slot,
                excel_value=excel_val,
                json_nas_path=json_nas,
                json_bucket_uri=json_bucket,
            )

            if not excel_val and json_nas:
                # Excel apagado + JSON tem caminho → remoção solicitada
                sec.is_deleted = True
                self.logger.info(
                    f"[Diff] Id {diff.product_id}: Slot secundária {slot} DELETADO. "
                    f"NAS='{json_nas}'"
                )
            elif not excel_val and not json_nas:
                sec.is_empty = True
                self.logger.debug(
                    f"[Diff] Id {diff.product_id}: Slot secundária {slot} vazio."
                )
            elif self._is_processed(excel_val) and json_nas:
                sec.is_processed = True
                self.logger.debug(
                    f"[Diff] Id {diff.product_id}: Slot secundária {slot} já processado."
                )
            elif self._is_filename(excel_val) and not json_nas:
                sec.is_new = True
                self.logger.info(
                    f"[Diff] Id {diff.product_id}: Slot secundária {slot} NOVA. "
                    f"Excel='{excel_val}'"
                )
            elif self._is_filename(excel_val) and json_nas:
                sec.is_changed = True
                self.logger.info(
                    f"[Diff] Id {diff.product_id}: Slot secundária {slot} TROCADA. "
                    f"Excel='{excel_val}' | JSON NAS='{json_nas}'"
                )
            else:
                # Caso residual: excel tem algo mas não é filename limpo
                sec.is_empty = True
                self.logger.debug(
                    f"[Diff] Id {diff.product_id}: Slot secundária {slot} — "
                    f"valor não reconhecido: '{excel_val}'. Tratando como vazio."
                )

            diff.secondaries.append(sec)

    def _fill_secondary_diffs_new(
        self, diff: ProductDiff, row_dict: dict
    ) -> None:
        """
        Preenche os slots secundários para produtos novos (sem JSON).
        Todo slot com filename é marcado como is_new.
        """
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
                    f"[Diff] Id {diff.product_id}: Slot secundária {slot} NOVA (produto novo). "
                    f"Excel='{excel_val}'"
                )
            else:
                sec.is_empty = True

            diff.secondaries.append(sec)

    # ------------------------------------------------------------------
    # Diff do caminho NAS (colunas organizadoras)
    # ------------------------------------------------------------------

    def _diff_nas_path(
        self, diff: ProductDiff, row_dict: dict, existing_json: dict
    ) -> None:
        """
        Verifica se as colunas que definem a estrutura de pasta no NAS
        (Marca, Linha_Colecao, Categoria_Principal) mudaram em relação ao JSON.
        """
        for excel_col, json_field in self._NAS_ORGANIZER_FIELDS.items():
            excel_val = self._clean(row_dict.get(excel_col)) or ""
            json_val = str(existing_json.get(json_field) or "")

            if excel_val != json_val:
                diff.nas_path_changed = True
                self.logger.info(
                    f"[Diff] Id {diff.product_id}: Campo organizador NAS mudou: "
                    f"'{excel_col}' Excel='{excel_val}' → JSON='{json_val}'"
                )
                return  # basta um campo diferente para confirmar mudança

        self.logger.debug(
            f"[Diff] Id {diff.product_id}: Colunas organizadoras NAS sem mudança."
        )

    # ------------------------------------------------------------------
    # Diff dos campos de dados
    # ------------------------------------------------------------------

    def _diff_data_fields(
        self, diff: ProductDiff, row_dict: dict, existing_json: dict
    ) -> None:
        """
        Compara todos os campos de dados (non-image) entre Excel e JSON.
        Campos exclusivos do JSON (caminhos) são ignorados nesta comparação.
        """
        from models.product_model import COLUMN_MAP

        changed = []
        for excel_col, model_field in COLUMN_MAP.items():
            if model_field in self._JSON_ONLY_FIELDS:
                continue

            excel_val = self._normalize(row_dict.get(excel_col))
            json_val = self._normalize(existing_json.get(model_field))

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
                f"[Diff] Id {diff.product_id}: {len(changed)} campo(s) de dados alterado(s): "
                f"{changed}"
            )

    # ------------------------------------------------------------------
    # Utilitários
    # ------------------------------------------------------------------

    def _clean(self, value) -> Optional[str]:
        """Normaliza célula: None/NaN/vazio vira None."""
        if value is None:
            return None
        s = str(value).strip()
        return s if s and s.lower() not in ("nan", "none") else None

    def _normalize(self, value) -> str:
        """Normaliza para comparação: None e string vazia são equivalentes."""
        if value is None:
            return ""
        return str(value).strip()

    def _is_filename(self, value: Optional[str]) -> bool:
        """
        Retorna True se o valor é um filename solto (sem separador de pasta),
        indicando que ainda precisa ser processado.
        Valores com separador (caminho NAS já processado) retornam False naturalmente.
        """
        if not value:
            return False
        return "/" not in value and "\\" not in value

    def _is_processed(self, value: Optional[str]) -> bool:
        """
        Retorna True se o slot já foi processado.
        Novo comportamento: detecta caminho NAS (contém '/' ou '\\').
        Mantém compatibilidade com o marcador legado 'Processada' para
        planilhas antigas que ainda usem esse valor.
        """
        if not value:
            return False
        if "/" in value or "\\" in value:
            return True
        return value.strip().lower() == _PROCESSED_MARKER.lower()
