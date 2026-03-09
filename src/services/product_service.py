"""ProductService — leitura e listagem de produtos a partir dos data/*.json."""

import json
import logging
from pathlib import Path
from typing import Optional

from config.settings import settings


class ProductService:

    def __init__(self, logger: logging.Logger):
        self.logger = logger
        self.data_dir = settings.general.data_path

    def list_active(self, page: int = 1, page_size: int = 20) -> dict:
        """
        Retorna produtos com status=Ativo, paginados.
        Lê todos os .json do data_dir, filtra ativos e pagina.
        """
        all_products = []

        for json_path in sorted(self.data_dir.glob("*.json"), key=lambda p: int(p.stem) if p.stem.isdigit() else 0):
            product = self._load(json_path)
            if product and self._is_active(product):
                all_products.append(self._to_summary(product))

        total = len(all_products)
        start = (page - 1) * page_size
        end = start + page_size

        return {
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": max(1, -(-total // page_size)),  # ceil division
            "items": all_products[start:end],
        }

    def get_by_id(self, product_id: int) -> Optional[dict]:
        """Retorna o JSON completo de um produto pelo ID, ou None se não encontrar."""
        path = self.data_dir / f"{product_id}.json"
        if not path.exists():
            self.logger.warning(f"[Product] JSON não encontrado: {path}")
            return None
        return self._load(path)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _load(self, path: Path) -> Optional[dict]:
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except Exception as exc:
            self.logger.warning(f"[Product] Erro ao ler {path}: {exc}")
            return None

    def _is_active(self, product: dict) -> bool:
        status = str(product.get("status", "")).strip().lower()
        return status == "ativo"

    def _to_summary(self, product: dict) -> dict:
        """Retorna apenas os campos necessários para a galeria."""
        pid = product.get("id_produto")
        return {
            "id_produto": pid,
            "nome_produto": product.get("nome_produto"),
            "marca": product.get("marca"),
            "categoria_principal": product.get("categoria_principal"),
            "faixa_preco": product.get("faixa_preco"),
            "imagem_url": f"/images/{pid}.jpg",
        }