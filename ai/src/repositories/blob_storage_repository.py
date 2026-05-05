import json
import logging
from typing import Optional
from azure.storage.blob import BlobServiceClient


class BlobStorageRepository:

    def __init__(self, connection_string: str, logger: logging.Logger):
        self.logger = logger
        self.client = BlobServiceClient.from_connection_string(connection_string)

    # --------------------------------------------------
    # READ
    # --------------------------------------------------

    def get_json(self, pid: str) -> Optional[dict]:
        try:
            blob = self.client.get_blob_client("firmato-catalogo", f"data_staging/{pid}.json")
            data = blob.download_blob().readall()
            return json.loads(data)

        except Exception as e:
            self.logger.warning(f"[AIRepo] JSON não encontrado {pid}: {e}")
            return None

    def get_image(self, pid: str) -> Optional[bytes]:
        try:
            blob = self.client.get_blob_client("firmato-catalogo", f"thumbnail_staging/{pid}.jpg")
            return blob.download_blob().readall()

        except Exception as e:
            self.logger.warning(f"[AIRepo] Imagem não encontrada {pid}: {e}")
            return None

    # --------------------------------------------------
    # WRITE (embeddings)
    # --------------------------------------------------

    def save_clip_embeddings(self, data: bytes):
        blob = self.client.get_blob_client("firmato-catalogo", "embeddings/clip_embeddings.npy")
        blob.upload_blob(data, overwrite=True)

    def save_text_embeddings(self, data: bytes):
        blob = self.client.get_blob_client("firmato-catalogo", "embeddings/text_embeddings.npy")
        blob.upload_blob(data, overwrite=True)

    def save_metadata(self, data: bytes):
        blob = self.client.get_blob_client("firmato-catalogo", "embeddings/metadata.json")
        blob.upload_blob(data, overwrite=True)

    def save_bm25(self, data: bytes):
        blob = self.client.get_blob_client("firmato-catalogo", "embeddings/bm25.pkl")
        blob.upload_blob(data, overwrite=True)