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
    p = Path(path)
    if not p.is_absolute():
        p = _BASE_DIR / p
    return p


class SharePointSettings:
    tenant_id:     str = _cfg.get("sharepoint", "tenant_id")
    client_id:     str = _cfg.get("sharepoint", "client_id")
    client_secret: str = os.getenv("SHAREPOINT_CLIENT_SECRET", "")
    host:          str = _cfg.get("sharepoint", "host")
    site_path:     str = _cfg.get("sharepoint", "site_path")
    file_name:     str = _cfg.get("sharepoint", "file_name")
    sheet_name:    str = _cfg.get("sharepoint", "sheet_name")


class GeneralSettings:
    landing_path:    Path = _resolve(_cfg.get("general", "landing_path"))
    data_path:       Path = _resolve(_cfg.get("general", "data_path"))
    tmp_images_path: Path = _resolve(_cfg.get("general", "tmp_images_path"))


class ImageSettings:
    thumb_width:  int = _cfg.getint("image", "thumb_width")
    thumb_height: int = _cfg.getint("image", "thumb_height")
    output_width:  int = _cfg.getint("image", "output_width")
    output_height: int = _cfg.getint("image", "output_height")
    jpeg_quality:  int = _cfg.getint("image", "jpeg_quality")
    allowed_extensions: list[str] = [
        e.strip().lower()
        for e in _cfg.get("image", "allowed_extensions").split(",")
    ]


class NasSettings:
    base_path: Path = _resolve(_cfg.get("nas", "base_path"))

    @property
    def landing(self) -> Path:
        return self.base_path / "landing"

    @property
    def output(self) -> Path:
        return self.base_path / "output"

    @property
    def thumbnail(self) -> Path:
        return self.base_path / "thumbnail"

    @property
    def data(self) -> Path:
        return self.base_path / "data"

    @property
    def utils(self) -> Path:
        return self.base_path / "utils"


class HashSettings:
    hash_columns: list[str] = [
        c.strip() for c in _cfg.get("hash", "hash_columns").split(",")
    ]


class AzureSettings:
    connection_string: str = os.getenv("AZURE_STORAGE_CONNECTION_STRING", "")


class EmbeddingsSettings:
    npy_path:      Path = _resolve(_cfg.get("embeddings", "npy_path"))
    metadata_path: Path = _resolve(_cfg.get("embeddings", "metadata_path"))


class ModelSettings:
    clip_model_name: str = _cfg.get(
        "models", "clip_model_name",
        fallback="openai/clip-vit-large-patch14"
    )
    st_model_name: str = _cfg.get(
        "models", "st_model_name",
        fallback="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    )
    device: str = _cfg.get("models", "device", fallback="cpu")


class Settings:
    general    = GeneralSettings()
    sharepoint = SharePointSettings()
    image      = ImageSettings()
    nas        = NasSettings()
    hash       = HashSettings()
    embeddings = EmbeddingsSettings()
    azure      = AzureSettings()
    models     = ModelSettings()


settings = Settings()