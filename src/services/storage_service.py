import logging
from pathlib import Path
from typing import Optional

from config.settings import settings


class StorageService:
    """
    Serviço responsável por operações no Google Cloud Storage (GCS).
    Estrutura do bucket: images/{filename}  (ex: images/1.jpg, images/1A.jpg)
    Sem hierarquia organizacional — o bucket é um repositório flat acessado apenas pelo sistema.
    Requer a lib google-cloud-storage instalada e credenciais configuradas.
    """

    _IMAGES_PREFIX = "images"

    def __init__(self, logger: logging.Logger):
        self.logger = logger
        self.bucket_name = settings.gcs.bucket_name
        self.credentials_path = settings.gcs.credentials_path
        self._client = None
        self._bucket = None

    # ------------------------------------------------------------------
    # Conexão (lazy init)
    # ------------------------------------------------------------------

    def _get_client(self):
        """Inicializa o cliente GCS na primeira chamada (lazy)."""
        if self._client is not None:
            return self._client

        try:
            from google.cloud import storage as gcs
            from google.oauth2 import service_account

            if self.credentials_path.exists():
                credentials = service_account.Credentials.from_service_account_file(
                    str(self.credentials_path)
                )
                self._client = gcs.Client(credentials=credentials)
            else:
                # Tenta usar credenciais default do ambiente (GOOGLE_APPLICATION_CREDENTIALS)
                self._client = gcs.Client()

            self._bucket = self._client.bucket(self.bucket_name)
            self.logger.info(f"[GCS] Cliente inicializado. Bucket: {self.bucket_name}")
            return self._client

        except ImportError:
            self.logger.error(
                "[GCS] Biblioteca 'google-cloud-storage' não instalada. "
                "Execute: pip install google-cloud-storage"
            )
            raise
        except Exception as exc:
            self.logger.error(
                f"[GCS] Falha ao inicializar cliente: {exc}", exc_info=True
            )
            raise

    # ------------------------------------------------------------------
    # Utilitários
    # ------------------------------------------------------------------

    def build_blob_name(self, filename: str) -> str:
        """
        Monta o blob name dentro do bucket.
        Estrutura: images/{filename}  (ex: images/1.jpg)
        """
        return f"{self._IMAGES_PREFIX}/{filename}"

    # ------------------------------------------------------------------
    # Upload
    # ------------------------------------------------------------------

    def upload_image(self, local_path: Path, filename: str) -> Optional[str]:
        """
        Faz upload de imagem para o GCS em images/{filename}.
        Se já existir um blob com esse nome, sobrescreve.
        Retorna a URI gs:// em caso de sucesso, None em caso de erro.
        """
        blob_name = self.build_blob_name(filename)
        try:
            self._get_client()
            blob = self._bucket.blob(blob_name)
            blob.upload_from_filename(str(local_path), content_type="image/jpeg")
            uri = f"gs://{self.bucket_name}/{blob_name}"
            self.logger.info(f"[GCS] Upload concluído: {uri}")
            return uri
        except Exception as exc:
            self.logger.error(
                f"[GCS] Erro no upload de '{local_path}' para '{blob_name}': {exc}",
                exc_info=True,
            )
            return None

    # ------------------------------------------------------------------
    # Get
    # ------------------------------------------------------------------

    def get_image_url(self, filename: str) -> str:
        """
        Retorna a URI gs:// de uma imagem pelo nome do arquivo.
        Preparado para futura expansão (ex: signed URLs).
        """
        return f"gs://{self.bucket_name}/{self.build_blob_name(filename)}"

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    def delete_image(self, filename: str) -> bool:
        """
        Remove imagem do bucket pelo nome do arquivo.
        Retorna True em sucesso, False se não encontrado ou erro.
        """
        blob_name = self.build_blob_name(filename)
        try:
            self._get_client()
            blob = self._bucket.blob(blob_name)
            if not blob.exists():
                self.logger.warning(f"[GCS] Blob não encontrado para remoção: {blob_name}")
                return False
            blob.delete()
            self.logger.info(f"[GCS] Blob removido: {blob_name}")
            return True
        except Exception as exc:
            self.logger.error(
                f"[GCS] Erro ao remover blob '{blob_name}': {exc}", exc_info=True
            )
            return False

    def delete_images(self, filenames: list[str]) -> dict[str, bool]:
        """
        Remove múltiplas imagens do bucket de uma vez.
        Retorna dict filename → True/False indicando sucesso de cada remoção.
        Útil ao substituir imagem principal ou remover secundárias.
        """
        results: dict[str, bool] = {}
        for filename in filenames:
            results[filename] = self.delete_image(filename)
        return results
