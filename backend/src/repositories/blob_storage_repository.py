import logging
from azure.storage.blob.aio import BlobServiceClient
from azure.storage.blob import ContentSettings
import asyncio


class BlobStorageRepository:

    def __init__(self, connection_string: str, logger: logging.Logger):
        self.logger = logger
        self.client = BlobServiceClient.from_connection_string(connection_string)

    # --------------------------------------------------
    # URL
    # --------------------------------------------------
    def get_blob_url(self, container: str, blob_name: str) -> str:
        blob_client = self.client.get_blob_client(container, blob_name)
        return blob_client.url

    # --------------------------------------------------
    # LIST
    # --------------------------------------------------
    async def list_blobs(self, container: str, prefix: str = "") -> list[str]:
        try:
            container_client = self.client.get_container_client(container)

            blobs = []
            async for b in container_client.list_blobs(name_starts_with=prefix):
                blobs.append(b.name)

            return blobs

        except Exception as e:
            self.logger.error(f"[Blob] Erro list_blobs: {e}")
            return []

    # --------------------------------------------------
    # DOWNLOAD
    # --------------------------------------------------
    async def download(self, container: str, blob_name: str) -> bytes:
        try:
            blob_client = self.client.get_blob_client(container, blob_name)

            stream = await blob_client.download_blob()
            data = await stream.readall()

            self.logger.info(f"[Blob] Download OK: {container}/{blob_name}")
            return data

        except Exception as exc:
            self.logger.error(f"[Blob] Erro download {container}/{blob_name}: {exc}")
            raise

    # --------------------------------------------------
    # UPLOAD
    # --------------------------------------------------
    async def upload(self, container: str, blob_name: str, data: bytes, content_type="application/octet-stream"):
        try:
            blob_client = self.client.get_blob_client(container, blob_name)

            await blob_client.upload_blob(
                data,
                overwrite=True,
                content_settings=ContentSettings(content_type=content_type),
            )

            self.logger.info(f"[Blob] Upload OK: {container}/{blob_name}")

        except Exception as exc:
            self.logger.error(f"[Blob] Erro upload {container}/{blob_name}: {exc}")
            raise

    # --------------------------------------------------
    # EXISTS
    # --------------------------------------------------
    async def exists(self, container: str, blob_name: str) -> bool:
        try:
            blob_client = self.client.get_blob_client(container, blob_name)
            return await blob_client.exists()
        except Exception as exc:
            self.logger.warning(f"[Blob] Erro exists {container}/{blob_name}: {exc}")
            return False

    # --------------------------------------------------
    # DELETE
    # --------------------------------------------------
    async def delete(self, container: str, blob_name: str):
        try:
            blob_client = self.client.get_blob_client(container, blob_name)
            await blob_client.delete_blob()

            self.logger.info(f"[Blob] Delete OK: {container}/{blob_name}")

        except Exception as exc:
            self.logger.warning(f"[Blob] Erro delete {container}/{blob_name}: {exc}")

    # --------------------------------------------------
    # COPY
    # --------------------------------------------------
    async def copy(self, container: str, src_blob: str, dst_blob: str):
        try:
            src = self.client.get_blob_client(container, src_blob)
            dst = self.client.get_blob_client(container, dst_blob)

            await dst.start_copy_from_url(src.url)

            self.logger.info(f"[Blob] Copy OK: {src_blob} → {dst_blob}")

        except Exception as exc:
            self.logger.error(f"[Blob] Erro copy {src_blob}: {exc}")
            raise