import configparser
import os
from pathlib import Path

_BASE_DIR = Path(__file__).resolve().parent.parent
_CONFIG_PATH = _BASE_DIR / "config.ini"


def _load() -> configparser.ConfigParser:
    cfg = configparser.ConfigParser()
    if not _CONFIG_PATH.exists():
        raise FileNotFoundError(f"Arquivo de configuração não encontrado: {_CONFIG_PATH}")
    cfg.read(_CONFIG_PATH, encoding="utf-8")
    return cfg


_cfg = _load()


def _resolve(path: str) -> Path:
    """Resolve caminho relativo a partir do diretório raiz do projeto."""
    p = Path(path)
    if not p.is_absolute():
        p = _BASE_DIR / p
    return p


class GeneralSettings:
    landing_path: Path = _resolve(_cfg.get("general", "landing_path"))
    data_path: Path = _resolve(_cfg.get("general", "data_path"))
    logs_path: Path = _resolve(_cfg.get("general", "logs_path"))
    tmp_images_path: Path = _resolve(_cfg.get("general", "tmp_images_path"))


class ImageSettings:
    resize_width: int = _cfg.getint("image", "resize_width")
    resize_height: int = _cfg.getint("image", "resize_height")
    jpeg_quality: int = _cfg.getint("image", "jpeg_quality")
    allowed_extensions: list[str] = [
        e.strip().lower() for e in _cfg.get("image", "allowed_extensions").split(",")
    ]


class NasSettings:
    base_path: Path = _resolve(_cfg.get("nas", "base_path"))
    organizer_columns: list[str] = [
        c.strip() for c in _cfg.get("nas", "organizer_columns").split(",")
    ]


class GcsSettings:
    bucket_name: str = _cfg.get("gcs", "bucket_name")
    credentials_path: Path = _resolve(_cfg.get("gcs", "credentials_path"))


class HashSettings:
    hash_columns: list[str] = [
        c.strip() for c in _cfg.get("hash", "hash_columns").split(",")
    ]


class EmbeddingsSettings:
    npy_path: Path = _resolve(_cfg.get("embeddings", "npy_path"))
    metadata_path: Path = _resolve(_cfg.get("embeddings", "metadata_path"))


class Settings:
    general = GeneralSettings()
    image = ImageSettings()
    nas = NasSettings()
    gcs = GcsSettings()
    hash = HashSettings()
    embeddings = EmbeddingsSettings()

settings = Settings()
