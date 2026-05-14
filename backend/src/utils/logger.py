import logging
import sys
from datetime import datetime


def setup_logger(endpoint_name: str) -> logging.Logger:
    """
    Cria e retorna um logger nomeado para a execução atual.
    Loga apenas no stdout (sem dependência de disco).
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    name      = f"{endpoint_name}_{timestamp}"

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