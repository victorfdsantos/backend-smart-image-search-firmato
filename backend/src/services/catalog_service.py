import json
from pathlib import Path
from config.settings import settings

_HASH_COLUMNS = settings.hash.hash_columns

class CatalogService:

    def __init__(self, logger, sp_repo, blob_repo, image_service, data_service, filter_service):
        self.logger = logger
        self.sp = sp_repo
        self.blob = blob_repo
        self.image = image_service
        self.data = data_service
        self.filter = filter_service

    # --------------------------------------------------
    # PROCESS
    # --------------------------------------------------

    def process(self) -> dict:
        stats = {
            "processed": 0,
            "skipped": 0,
            "errors": 0,
            "updated_ids": [],
        }

        sharepoint_updates = []
        landing_map = {}

        hash_index = self._load_hash_index()

        rows = self.sp.list_rows()

        blobs = self.blob.list_blobs("firmato-catalogo", "landing/")
        blob_index = {}
        for b in blobs:
            key = Path(b).stem.lower()
            blob_index.setdefault(key, []).append(b)

        for row in rows:
            try:
                pid = str(int(float(row.get("Id_produto"))))
                if not pid:
                    continue

                new_hash = self.image.generate_hash(row, _HASH_COLUMNS)

                if hash_index.get(pid) == new_hash:
                    self.logger.debug(f"[Catalog] {pid}: sem alteração")
                    stats["skipped"] += 1
                    continue

                img_raw = row.get("Caminho_Imagem")
                if not img_raw:
                    continue

                base_name = Path(str(img_raw)).stem.lower()

                candidates = blob_index.get(base_name)

                if not candidates:
                    self.logger.warning(f"[Catalog] {pid}: imagem não encontrada ({base_name}.*)")
                    stats["errors"] += 1
                    continue

                # pega a primeira (ou pode priorizar extensão depois)
                img_name = candidates[0]

                img_bytes = self.blob.download("firmato-catalogo", img_name)

                output_bytes, thumb_bytes = self.image.process(img_bytes, pid)

                fname = f"{pid}.jpg"

                self.blob.upload("firmato-catalogo", f"output_staging/{fname}", output_bytes, "image/jpeg")
                self.blob.upload("firmato-catalogo", f"thumbnail_staging/{fname}", thumb_bytes, "image/jpeg")

                product = self.data.row_to_model(row)
                product.chave_especial = new_hash
                product.caminho_output = f"output/{fname}"
                product.caminho_thumbnail = f"thumbnail/{fname}"

                self.blob.upload("firmato-catalogo",f"data_staging/{pid}.json",json.dumps(product.model_dump()).encode(),"application/json")

                landing_map[pid] = img_name

                sharepoint_updates.append({
                    "pid": pid,\
                    "fields": {
                        "Caminho_Imagem": fname,
                        "Chave_Especial": new_hash
                    }
                })

                hash_index[pid] = new_hash

                stats["processed"] += 1
                stats["updated_ids"].append(pid)

            except Exception as e:
                self.logger.error(f"[Catalog] erro {row}: {e}", exc_info=True)
                stats["errors"] += 1

        stats["updated_ids"] = list(dict.fromkeys(stats["updated_ids"]))

        return {
            **stats,
            "landing_map": landing_map,
            "sharepoint_updates": sharepoint_updates,
            "hash_index": hash_index,  # 🔥 NOVO
        }

    # --------------------------------------------------
    # COMMIT
    # --------------------------------------------------

    def commit(self, updated_ids, landing_map, sharepoint_updates, hash_index):
        try:
            for pid in updated_ids:
                fname = f"{pid}.jpg"

                self._move("output_staging", "output", fname)
                self._move("thumbnail_staging", "thumbnail", fname)
                self._move("data_staging", "data", f"{pid}.json")

                original_name = landing_map.get(pid)
                if original_name:
                    self.blob.delete("firmato-catalogo", original_name)

            for item in sharepoint_updates:
                self.sp.update_row(item["pid"], item["fields"])

            self._save_hash_index(hash_index)

            self._clear_staging(updated_ids)

            rows = self.sp.list_rows()
            self.filter.build(rows)

        except Exception as e:
            self.logger.error(f"[Catalog] Commit falhou: {e}", exc_info=True)
            raise

    # --------------------------------------------------
    # HELPERS
    # --------------------------------------------------
    
    def _move(self, src_path, dst_path, blob_name):
        CONTAINER = "firmato-catalogo"
        src_blob = f"{src_path}/{blob_name}"
        dst_blob = f"{dst_path}/{blob_name}"

        self.blob.copy(CONTAINER, src_blob, dst_blob)

    def _clear_staging(self, ids):
        for pid in ids:
            fname = f"{pid}.jpg"

            self.blob.delete("firmato-catalogo", f"output_staging/{fname}")
            self.blob.delete("firmato-catalogo", f"thumbnail_staging/{fname}")
            self.blob.delete("firmato-catalogo", f"data_staging/{pid}.json")
        
    def _load_hash_index(self):
        try:
            data = self.blob.download("firmato-catalogo", "utils/hash_index.json")
            return json.loads(data)
        except Exception:
            return {}

    def _save_hash_index(self, hash_index: dict):
        self.blob.upload(
            "firmato-catalogo",
            "utils/hash_index.json",
            json.dumps(hash_index).encode(),
            "application/json"
        )