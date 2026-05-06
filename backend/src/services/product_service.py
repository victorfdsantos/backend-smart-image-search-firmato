"""
ProductService — listagem paginada, detalhe e download de imagens do Blob.

Caminhos no Blob:
  thumbnail/{id}.jpg   → imagem pequena servida no grid
  output/{id}.jpg      → imagem full-quality servida no preview
  data/{id}.json       → JSON com os campos do produto
"""

import asyncio
import json
import logging
import math
from typing import Optional

from repositories.blob_storage_repository import BlobStorageRepository

_CONTAINER = "firmato-catalogo"


class ProductService:

    def __init__(self, logger: logging.Logger, blob_repo: BlobStorageRepository):
        self.logger = logger
        self.blob   = blob_repo

    # ================================================================ LIST

    async def list_active(
        self,
        page:        int,
        page_size:   int,
        allowed_ids: Optional[set] = None,
    ) -> dict:
        """
        Lista produtos paginados.
        Retorna itens com imagem_url apontando para o endpoint de thumbnail.
        """
        # lista todos os blobs de data para descobrir IDs ativos
        blobs = await self.blob.list_blobs(_CONTAINER, "data/")
        json_blobs = [b for b in blobs if b.endswith(".json")]

        # filtra por IDs permitidos (filtros de categoria, marca, etc.)
        if allowed_ids is not None:
            json_blobs = [
                b for b in json_blobs
                if b.replace("data/", "").replace(".json", "") in allowed_ids
            ]

        total = len(json_blobs)
        total_pages = max(1, math.ceil(total / page_size))
        page = max(1, min(page, total_pages))

        start = (page - 1) * page_size
        page_blobs = json_blobs[start: start + page_size]

        # baixa os JSONs em paralelo
        items = await asyncio.gather(
            *[self._blob_to_summary(b) for b in page_blobs],
            return_exceptions=True,
        )

        valid_items = [i for i in items if isinstance(i, dict)]

        return {
            "page":        page,
            "page_size":   page_size,
            "total":       total,
            "total_pages": total_pages,
            "items":       valid_items,
        }

    # ================================================================ DETAIL

    async def get_by_id(self, product_id: int) -> Optional[dict]:
        blob_path = f"data/{product_id}.json"
        try:
            data = await self.blob.download(_CONTAINER, blob_path)
            return json.loads(data)
        except Exception as exc:
            self.logger.warning(f"[ProductService] get_by_id {product_id}: {exc}")
            return None

    # ============================================================= IMAGES

    async def get_thumbnail(self, filename: str) -> Optional[bytes]:
        """Baixa a thumbnail (imagem pequena) do Blob."""
        return await self._download_image(f"thumbnail/{filename}")

    async def get_image(self, filename: str) -> Optional[bytes]:
        """Baixa a imagem em alta qualidade (output) do Blob."""
        return await self._download_image(f"output/{filename}")

    # ================================================================ HELPERS

    async def _download_image(self, blob_path: str) -> Optional[bytes]:
        try:
            return await self.blob.download(_CONTAINER, blob_path)
        except Exception as exc:
            self.logger.warning(f"[ProductService] download {blob_path}: {exc}")
            return None

    async def _blob_to_summary(self, blob_path: str) -> dict:
        """Converte um blob data/{id}.json → dict resumido com imagem_url de thumbnail."""
        pid = blob_path.replace("data/", "").replace(".json", "")
        data = await self.blob.download(_CONTAINER, blob_path)
        product = json.loads(data)

        return {
            "id_produto":          product.get("id_produto", pid),
            "nome_produto":        product.get("nome_produto", ""),
            "marca":               product.get("marca", ""),
            "categoria_principal": product.get("categoria_principal", ""),
            "faixa_preco":         product.get("faixa_preco", ""),
            "altura_cm":           product.get("altura_cm"),
            "largura_cm":          product.get("largura_cm"),
            "profundidade_cm":     product.get("profundidade_cm"),
            # thumbnail usado no grid — endpoint dedicado
            "imagem_url":          f"/api/products/thumbnail/{pid}.jpg",
        }