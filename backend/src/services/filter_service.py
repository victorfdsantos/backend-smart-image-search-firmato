"""
FilterService — lê o índice de filtros do app_state (filter_index),
que é construído pelo AI/FilterIndexService após cada treino e
carregado do Blob no startup do backend.

Estrutura do filter_index:
{
    "marca":               { "Tok&Stok": ["1","5","23"], "Etna": ["2","8"] },
    "categoria_principal": { "Sofás": ["1","2"], ... },
    "subcategoria":        { ... },
    "faixa_preco":         { ... },
    "ambiente":            { ... },
    "forma":               { ... },
    "material_principal":  { ... },
}
"""

import logging
from typing import Optional

FILTER_FIELDS = [
    "marca",
    "categoria_principal",
    "subcategoria",
    "faixa_preco",
    "ambiente",
    "forma",
    "material_principal",
]


class FilterService:

    def __init__(self, logger: logging.Logger, filter_index: Optional[dict] = None):
        self.logger = logger
        # filter_index vem do app_state (carregado no startup do Blob)
        self.index: dict = filter_index or {f: {} for f in FILTER_FIELDS}

    # --------------------------------------------------
    # GET FILTER OPTIONS (cascata)
    # --------------------------------------------------

    def get_options(self, active_filters: dict[str, list[str]]) -> dict[str, list[str]]:
        """
        Retorna os valores disponíveis para cada campo considerando
        os filtros já ativos (cascata).
        """
        current_ids = self._ids_for_filters(active_filters)

        if current_ids is None:
            # nenhum filtro ativo → retorna tudo
            return {f: sorted(self.index.get(f, {}).keys()) for f in FILTER_FIELDS}

        options = {}
        for field in FILTER_FIELDS:
            valid = [
                val for val, ids in self.index.get(field, {}).items()
                if current_ids.intersection(ids)
            ]
            options[field] = sorted(valid)

        return options

    # --------------------------------------------------
    # GET IDS (para ProductService e SearchService)
    # --------------------------------------------------

    def get_filtered_ids(self, active_filters: dict[str, list[str]]) -> set[str]:
        return self._ids_for_filters(active_filters) or set()

    # alias usado em search_controller
    def filter_product_ids(self, active_filters: dict[str, list[str]]) -> set[str]:
        return self.get_filtered_ids(active_filters)

    # --------------------------------------------------
    # INTERNAL
    # --------------------------------------------------

    def _ids_for_filters(self, active_filters: dict[str, list[str]]) -> Optional[set[str]]:
        """
        Intersecção dos IDs que satisfazem todos os filtros ativos.
        Retorna None se não há filtros ativos.
        """
        current_ids: Optional[set[str]] = None

        for field, values in active_filters.items():
            if not values:
                continue

            ids: set[str] = set()
            for v in values:
                ids.update(self.index.get(field, {}).get(v, []))

            current_ids = ids if current_ids is None else current_ids & ids

        return current_ids