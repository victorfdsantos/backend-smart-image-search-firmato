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

    def list_active(
        self,
        page: int = 1,
        page_size: int = 12,
        allowed_ids: Optional[set] = None,
    ) -> dict:
        start = (page - 1) * page_size
        end   = start + page_size

        items = []

        # CASO COM FILTRO
        if allowed_ids is not None:
            sorted_ids = sorted(int(i) for i in allowed_ids)
            total = len(sorted_ids)

            for pid in sorted_ids[start:end]:
                path = self.data_dir / f"{pid}.json"
                product = self._load(path)
                if product and self._is_active(product):
                    items.append(self._to_summary(product))

        # SEM FILTRO
        else:
            all_paths = sorted(
                self.data_dir.glob("*.json"),
                key=lambda p: int(p.stem) if p.stem.isdigit() else 0,
            )

            total = len(all_paths)

            for json_path in all_paths[start:end]:
                product = self._load(json_path)
                if product and self._is_active(product):
                    items.append(self._to_summary(product))

        return {
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": max(1, -(-total // page_size)),
            "items": items,
        }

    def get_by_id(self, product_id: int) -> Optional[dict]:
        path = self.data_dir / f"{product_id}.json"
        if not path.exists():
            self.logger.warning(f"[Product] JSON não encontrado: {path}")
            return None
        return self._load(path)

    def _load(self, path: Path) -> Optional[dict]:
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except Exception as exc:
            self.logger.warning(f"[Product] Erro ao ler {path}: {exc}")
            return None

    def _is_active(self, product: dict) -> bool:
        return str(product.get("status", "")).strip().lower() == "ativo"

    def _to_summary(self, product: dict) -> dict:
        pid = product.get("id_produto")
        return {
            "id_produto":          pid,
            "nome_produto":        product.get("nome_produto"),
            "marca":               product.get("marca"),
            "categoria_principal": product.get("categoria_principal"),
            "faixa_preco":         product.get("faixa_preco"),
            "altura_cm":           product.get("altura_cm"),
            "largura_cm":          product.get("largura_cm"),
            "profundidade_cm":     product.get("profundidade_cm"),
            "imagem_url":          f"/static/images/{pid}.jpg",
        }