import logging
import sys
from datetime import datetime
from io import StringIO


def setup_logger(endpoint_name: str) -> logging.Logger:
    """
    Cria e retorna um logger nomeado para a execução atual.
    Loga apenas no stdout (sem dependência de disco).
    Para persistir logs no Blob, use BlobLogHandler abaixo.
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    name = f"{endpoint_name}_{timestamp}"

    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)

    if logger.handlers:
        return logger

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.DEBUG)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    return logger


class BlobLogHandler(logging.Handler):
    """
    Handler que acumula logs em memória e faz upload para o Blob
    ao ser fechado (flush/close).

    Uso (no final de uma operação):
        handler = BlobLogHandler(blob_repo, "firmato-catalogo", f"logs/catalog_{ts}.log")
        logger.addHandler(handler)
        ...
        await handler.upload()   # ou handler.upload_sync()
        logger.removeHandler(handler)
    """

    def __init__(self, blob_repo, container: str, blob_path: str):
        super().__init__()
        self.blob_repo  = blob_repo
        self.container  = container
        self.blob_path  = blob_path
        self._buffer    = StringIO()
        self.setFormatter(logging.Formatter(
            fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        ))

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self._buffer.write(self.format(record) + "\n")
        except Exception:
            self.handleError(record)

    async def upload(self) -> None:
        """Faz upload assíncrono do buffer para o Blob."""
        try:
            data = self._buffer.getvalue().encode("utf-8")
            await self.blob_repo.upload(self.container, self.blob_path, data, "text/plain")
        except Exception as exc:
            # não propaga — log de log não deve derrubar a app
            print(f"[BlobLogHandler] Falha ao salvar log no Blob: {exc}", file=sys.stderr)

    def upload_sync(self) -> None:
        """Faz upload síncrono (para uso no AI service)."""
        try:
            data = self._buffer.getvalue().encode("utf-8")
            self.blob_repo._upload(self.blob_path, data)
        except Exception as exc:
            print(f"[BlobLogHandler] Falha ao salvar log no Blob: {exc}", file=sys.stderr)