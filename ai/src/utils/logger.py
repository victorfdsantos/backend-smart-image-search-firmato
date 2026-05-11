import logging
import sys
from datetime import datetime
from io import StringIO


def setup_logger(endpoint_name: str) -> logging.Logger:
    """
    Cria e retorna um logger nomeado para a execução atual.
    Loga apenas no stdout (sem dependência de disco).
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    name = f"ai.{endpoint_name}_{timestamp}"

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
    Handler que acumula logs em memória e faz upload síncrono para o Blob
    ao final de uma operação (ex: fim do /training).

    Uso:
        handler = BlobLogHandler(repo, f"logs/training_{ts}.log")
        logger.addHandler(handler)
        ...
        handler.upload_sync()
        logger.removeHandler(handler)
    """

    def __init__(self, blob_repo, blob_path: str):
        super().__init__()
        self.blob_repo = blob_repo
        self.blob_path = blob_path
        self._buffer   = StringIO()
        self.setFormatter(logging.Formatter(
            fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        ))

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self._buffer.write(self.format(record) + "\n")
        except Exception:
            self.handleError(record)

    def upload_sync(self) -> None:
        """Faz upload síncrono do buffer para o Blob (firmato-catalogo/logs/)."""
        try:
            data = self._buffer.getvalue().encode("utf-8")
            self.blob_repo._upload(self.blob_path, data)
        except Exception as exc:
            print(f"[BlobLogHandler] Falha ao salvar log no Blob: {exc}", file=sys.stderr)