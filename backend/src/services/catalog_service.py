"""
CatalogService — orquestra processamento do catálogo com Azure Blob + SharePoint.

Regras de async:
  - BlobStorageRepository  → async  (usa azure-storage-blob async)
  - SharePointRepository   → sync   (usa requests)  → chamado com asyncio.to_thread
  - ImageProcessingService → sync
  - ProductDataService     → sync
  - FilterService          → sync
"""

import asyncio
import json
from pathlib import Path

from config.settings import settings

_HASH_COLUMNS = settings.hash.hash_columns
_CONTAINER = "firmato-catalogo"


class CatalogService:

    def __init__(self, logger, sp_repo, blob_repo, image_service, data_service, filter_service):
        self.logger       = logger
        self.sp           = sp_repo          # síncrono
        self.blob         = blob_repo        # assíncrono
        self.image        = image_service    # síncrono
        self.data         = data_service     # síncrono
        self.filter       = filter_service   # síncrono

    # ================================================================ PROCESS

    async def process(self) -> dict:
        stats = {
            "processed":   0,
            "skipped":     0,
            "errors":      0,
            "updated_ids": [],
        }
        sharepoint_updates: list[dict] = []
        landing_map:        dict[str, str] = {}

        # ----- carrega hash index e linhas do SP em paralelo -----
        hash_index, rows, blobs = await asyncio.gather(
            self._load_hash_index(),
            asyncio.to_thread(self.sp.list_rows),
            self.blob.list_blobs(_CONTAINER, "landing/"),
        )

        # monta índice de blobs por stem (sem extensão, lower)
        blob_index: dict[str, list[str]] = {}
        for b in blobs:
            key = Path(b).stem.lower()
            blob_index.setdefault(key, []).append(b)

        for row in rows:
            try:
                raw_id = row.get("Id_produto")
                if not raw_id:
                    continue
                pid = str(int(float(raw_id)))

                new_hash = self.image.generate_hash(row, _HASH_COLUMNS)

                if hash_index.get(pid) == new_hash:
                    stats["skipped"] += 1
                    continue

                img_raw = row.get("Caminho_Imagem")
                if not img_raw:
                    self.logger.warning(f"[Catalog] {pid}: sem Caminho_Imagem")
                    stats["errors"] += 1
                    continue

                base_name = Path(str(img_raw)).stem.lower()
                candidates = blob_index.get(base_name)

                if not candidates:
                    self.logger.warning(
                        f"[Catalog] {pid}: imagem não encontrada no landing ({base_name}.*)"
                    )
                    stats["errors"] += 1
                    continue

                img_name = candidates[0]
                img_bytes = await self.blob.download(_CONTAINER, img_name)

                # processamento síncrono → thread pool
                output_bytes, thumb_bytes = await asyncio.to_thread(
                    self.image.process, img_bytes, pid
                )

                fname = f"{pid}.jpg"

                # uploads em paralelo
                product = await asyncio.to_thread(self.data.row_to_model, row)
                product.chave_especial   = new_hash
                product.caminho_output   = f"output/{fname}"
                product.caminho_thumbnail = f"thumbnail/{fname}"

                product_json = json.dumps(product.model_dump()).encode()

                await asyncio.gather(
                    self.blob.upload(_CONTAINER, f"output_staging/{fname}",    output_bytes, "image/jpeg"),
                    self.blob.upload(_CONTAINER, f"thumbnail_staging/{fname}", thumb_bytes,  "image/jpeg"),
                    self.blob.upload(_CONTAINER, f"data_staging/{pid}.json",   product_json, "application/json"),
                )

                landing_map[pid] = img_name
                sharepoint_updates.append({
                    "pid":    pid,
                    "fields": {
                        "Caminho_Imagem": fname,
                        "Chave_Especial": new_hash,
                    },
                })
                hash_index[pid] = new_hash

                stats["processed"] += 1
                stats["updated_ids"].append(pid)

            except Exception as exc:
                self.logger.error(f"[Catalog] erro na linha {row}: {exc}", exc_info=True)
                stats["errors"] += 1

        stats["updated_ids"] = list(dict.fromkeys(stats["updated_ids"]))

        return {
            **stats,
            "landing_map":        landing_map,
            "sharepoint_updates": sharepoint_updates,
            "hash_index":         hash_index,
        }

    # ================================================================ COMMIT

    async def commit(
        self,
        updated_ids:        list[str],
        landing_map:        dict[str, str],
        sharepoint_updates: list[dict],
        hash_index:         dict,
    ) -> None:
        try:
            # move staging → produção + deleta landing em paralelo por produto
            move_tasks = []
            for pid in updated_ids:
                fname = f"{pid}.jpg"
                move_tasks.append(self._promote_product(pid, fname, landing_map.get(pid)))

            await asyncio.gather(*move_tasks)

            # atualiza SharePoint (síncrono) em thread pool
            for item in sharepoint_updates:
                await asyncio.to_thread(self.sp.update_row, item["pid"], item["fields"])

            # persiste hash index
            await self._save_hash_index(hash_index)

            # limpa staging
            await self._clear_staging(updated_ids)

            # reconstrói índice de filtros
            rows = await asyncio.to_thread(self.sp.list_rows)
            await asyncio.to_thread(self.filter.build, rows)

        except Exception as exc:
            self.logger.error(f"[Catalog] Commit falhou: {exc}", exc_info=True)
            raise

    # ================================================================ HELPERS

    async def _promote_product(self, pid: str, fname: str, original_blob: str | None) -> None:
        """Move output/thumbnail/data de staging para produção e apaga landing."""
        tasks = [
            self._move("output_staging",    "output",    fname),
            self._move("thumbnail_staging", "thumbnail", fname),
            self._move("data_staging",      "data",      f"{pid}.json"),
        ]
        if original_blob:
            tasks.append(self.blob.delete(_CONTAINER, original_blob))

        await asyncio.gather(*tasks)

    async def _move(self, src_path: str, dst_path: str, blob_name: str) -> None:
        src = f"{src_path}/{blob_name}"
        dst = f"{dst_path}/{blob_name}"
        await self.blob.copy(_CONTAINER, src, dst)

    async def _clear_staging(self, ids: list[str]) -> None:
        tasks = []
        for pid in ids:
            fname = f"{pid}.jpg"
            tasks += [
                self.blob.delete(_CONTAINER, f"output_staging/{fname}"),
                self.blob.delete(_CONTAINER, f"thumbnail_staging/{fname}"),
                self.blob.delete(_CONTAINER, f"data_staging/{pid}.json"),
            ]
        await asyncio.gather(*tasks)

    async def _load_hash_index(self) -> dict:
        try:
            data = await self.blob.download(_CONTAINER, "utils/hash_index.json")
            return json.loads(data)
        except Exception:
            return {}

    async def _save_hash_index(self, hash_index: dict) -> None:
        await self.blob.upload(
            _CONTAINER,
            "utils/hash_index.json",
            json.dumps(hash_index).encode(),
            "application/json",
        )