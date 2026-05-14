import logging
from typing import Optional
from models.product_model import Product

# Colunas da planilha → chaves no JSON
COLUMN_MAP: dict[str, str] = {
    "Id_produto":              "id_produto",
    "Chave_Especial":          "chave_especial",
    "Nome_Produto":            "nome_produto",
    "Marca":                   "marca",
    "Status":                  "status",
    "Categoria_Principal":     "categoria_principal",
    "Subcategoria":            "subcategoria",
    "Ambiente":                "ambiente",
    "Forma":                   "forma",
    "Material_Principal":      "material_principal",
    "Material_Estrutura":      "material_estrutura",
    "Material_Revestimento":   "material_revestimento",
    "Altura_cm":               "altura_cm",
    "Largura_cm":              "largura_cm",
    "Profundidade_cm":         "profundidade_cm",
    "Faixa_Preco":             "faixa_preco",
    "Descricao_Tecnica":       "descricao_tecnica",
}


def _clean(val) -> Optional[str]:
    if val is None:
        return None
    s = str(val).strip()
    return s if s and s.lower() not in ("nan", "none", "") else None


class ProductDataService:

    def __init__(self, logger: logging.Logger):
        self.logger = logger

    # --------------------------------------------------
    # BUILD MODEL
    # --------------------------------------------------

    def row_to_model(self, row: dict) -> Product:
        data = {}

        for col, key in COLUMN_MAP.items():
            val = _clean(row.get(col))
            if val is not None:
                data[key] = val

        return Product(**data)