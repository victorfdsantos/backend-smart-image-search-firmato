import json
import logging
from typing import Optional
import asyncio


class ProductService:

    def __init__(self, logger: logging.Logger, blob_repo):
        self.logger = logger
        self.blob = blob_repo
        self.container = "firmato-catalogo"

    # --------------------------------------------------
    # LISTAGEM
    # --------------------------------------------------
    async def list_active(
        self,
        page: int = 1,
        page_size: int = 12,
        allowed_ids: Optional[set] = None,
    ) -> dict:

        start = (page - 1) * page_size
        end = start + page_size

        items = []

        # 🔥 pega todos os jsons do blob
        blobs = await self.blob.list_blobs(self.container, "data/")
        all_ids = sorted(
            int(b.split("/")[-1].replace(".json", ""))
            for b in blobs
        )

        # filtro
        if allowed_ids is not None:
            all_ids = [i for i in all_ids if str(i) in allowed_ids]

        total = len(all_ids)

        page_ids = all_ids[start:end]

        # 🔥 paralelo (importante)
        tasks = [self._load_product(pid) for pid in page_ids]
        products = await asyncio.gather(*tasks)

        for product in products:
            if product and self._is_active(product):
                items.append(self._to_summary(product))

        return {
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": max(1, -(-total // page_size)),
            "items": items,
        }

    # --------------------------------------------------
    # DETALHE
    # --------------------------------------------------
    async def get_by_id(self, product_id: int) -> Optional[dict]:
        return await self._load_product(product_id)

    # --------------------------------------------------
    # LOAD JSON (BLOB)
    # --------------------------------------------------
    async def _load_product(self, pid: int) -> Optional[dict]:
        try:
            data = await self.blob.download(
                self.container,
                f"data/{pid}.json"
            )
            return json.loads(data)

        except Exception as exc:
            self.logger.warning(f"[Product] JSON não encontrado {pid}: {exc}")
            return None

    # --------------------------------------------------
    # HELPERS
    # --------------------------------------------------
    def _is_active(self, product: dict) -> bool:
        return str(product.get("status", "")).strip().lower() == "ativo"

    def _to_summary(self, product: dict) -> dict:
        pid = product.get("id_produto")

        return {
            "id_produto": pid,
            "nome_produto": product.get("nome_produto"),
            "marca": product.get("marca"),
            "categoria_principal": product.get("categoria_principal"),
            "faixa_preco": product.get("faixa_preco"),
            "altura_cm": product.get("altura_cm"),
            "largura_cm": product.get("largura_cm"),
            "profundidade_cm": product.get("profundidade_cm"),

            # 🔥 agora correto
            "thumbnail_url": f"/products/thumbnail/{pid}",
        }