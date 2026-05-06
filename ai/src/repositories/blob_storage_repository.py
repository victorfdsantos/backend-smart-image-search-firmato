import json
import logging
from typing import Optional

from azure.storage.blob import BlobServiceClient


class BlobStorageRepository:

    _CONTAINER = "firmato-catalogo"

    def __init__(self, connection_string: str, logger: logging.Logger):
        self.logger = logger
        self.client = BlobServiceClient.from_connection_string(connection_string)

    # ------------------------------------------------------------------
    # READ
    # ------------------------------------------------------------------

    def download_sync(self, container: str, blob_path: str) -> bytes:
        blob = self.client.get_blob_client(container, blob_path)
        return blob.download_blob().readall()

    def get_json(self, pid: str) -> Optional[dict]:
        try:
            data = self.download_sync(self._CONTAINER, f"data_staging/{pid}.json")
            return json.loads(data)
        except Exception as e:
            self.logger.warning(f"[AIRepo] JSON não encontrado | pid={pid}: {e}")
            return None

    def get_image(self, pid: str) -> Optional[bytes]:
        try:
            return self.download_sync(self._CONTAINER, f"thumbnail_staging/{pid}.jpg")
        except Exception as e:
            self.logger.warning(f"[AIRepo] Imagem não encontrada | pid={pid}: {e}")
            return None

    # ------------------------------------------------------------------
    # WRITE
    # ------------------------------------------------------------------

    def save_clip_embeddings(self, data: bytes) -> None:
        self._upload("embeddings/clip_embeddings.npy", data)

    def save_text_embeddings(self, data: bytes) -> None:
        self._upload("embeddings/text_embeddings.npy", data)

    def save_metadata(self, data: bytes) -> None:
        self._upload("embeddings/metadata.json", data)

    def save_bm25(self, data: bytes) -> None:
        self._upload("embeddings/bm25.pkl", data)

    def _upload(self, blob_path: str, data: bytes) -> None:
        blob = self.client.get_blob_client(self._CONTAINER, blob_path)
        blob.upload_blob(data, overwrite=True)
        self.logger.info(f"[AIRepo] Upload OK: {blob_path}")