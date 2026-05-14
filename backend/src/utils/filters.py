"""
Utilitário para parsear filtros de query params.

Usado por product_controller, search_controller e filter_controller
para evitar repetição do mesmo bloco de split/strip/filter.
"""

from typing import Optional


def parse_active_filters(
    marca:               Optional[str] = None,
    categoria_principal: Optional[str] = None,
    subcategoria:        Optional[str] = None,
    faixa_preco:         Optional[str] = None,
    ambiente:            Optional[str] = None,
    forma:               Optional[str] = None,
    material_principal:  Optional[str] = None,
) -> dict[str, list[str]]:
    """
    Converte query params de filtro em dict[field, list[values]].
    Aceita valores separados por vírgula. Ignora campos vazios.

    Exemplo:
        marca="Tok&Stok,Etna" → {"marca": ["Tok&Stok", "Etna"]}
    """
    raw = {
        "marca":               marca,
        "categoria_principal": categoria_principal,
        "subcategoria":        subcategoria,
        "faixa_preco":         faixa_preco,
        "ambiente":            ambiente,
        "forma":               forma,
        "material_principal":  material_principal,
    }
    return {
        k: [v.strip() for v in val.split(",") if v.strip()]
        for k, val in raw.items()
        if val and val.strip()
    }