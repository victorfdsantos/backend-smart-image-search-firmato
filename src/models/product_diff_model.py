"""
Dataclasses que representam o resultado de uma comparação Excel vs JSON.
São o contrato de dados entre DiffService e CatalogService —
nenhum dos dois precisa conhecer os detalhes internos do outro.

ProductDiff         → estado completo de um produto após o diff
"""

from dataclasses import dataclass, field
from models.secondary_image_diff_model import SecondaryImageDiff
from typing import Optional

@dataclass
class ProductDiff:
    """
    Resultado completo da comparação Excel vs JSON para um produto.
    Preenchido pelo DiffService e consumido pelo CatalogService.
    """
    product_id: int
    row_dict: dict  # linha completa do Excel, repassada ao CatalogService

    # --- Estado geral ---
    is_new_product: bool = False   # JSON não existe → cadastro novo do zero

    # --- Imagem principal ---
    primary_excel_value: Optional[str] = None     # valor atual no Excel
    primary_json_nas_path: Optional[str] = None   # caminho NAS no JSON
    primary_json_bucket_uri: Optional[str] = None # URI bucket no JSON
    primary_is_new: bool = False      # filename solto, JSON sem caminho → processar
    primary_is_changed: bool = False  # filename solto, JSON tem caminho → trocar

    # --- Imagens secundárias ---
    secondaries: list[SecondaryImageDiff] = field(default_factory=list)

    # --- Colunas organizadoras do NAS ---
    nas_path_changed: bool = False  # Marca/Linha/Categoria mudou → mover pasta NAS

    # --- Campos de dados (non-image) ---
    data_fields_changed: bool = False
    changed_data_fields: list[str] = field(default_factory=list)

    # ------------------------------------------------------------------
    # Helpers de consulta
    # ------------------------------------------------------------------

    @property
    def has_any_change(self) -> bool:
        """True se há qualquer ação a executar para este produto."""
        return (
            self.is_new_product
            or self.primary_is_new
            or self.primary_is_changed
            or self.nas_path_changed
            or self.data_fields_changed
            or any(s.is_new or s.is_changed or s.is_deleted for s in self.secondaries)
        )

    @property
    def secondary_changes(self) -> list[SecondaryImageDiff]:
        """Slots com imagem nova ou trocada — requerem processamento de arquivo."""
        return [s for s in self.secondaries if s.is_new or s.is_changed]

    @property
    def secondary_deletions(self) -> list[SecondaryImageDiff]:
        """Slots apagados no Excel que ainda existem no JSON/NAS/bucket."""
        return [s for s in self.secondaries if s.is_deleted]
