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


class NasSettings:
    # Pasta raiz do NAS — imagens ficam em output/ de forma recursiva
    base_path: Path = _resolve(_cfg.get("nas", "base_path"))
    # Pasta data/ com os JSONs de metadados
    data_path: Path = _resolve(_cfg.get("nas", "data_path"))


class EmbeddingsSettings:
    # Pasta onde ficam os arquivos .npy, .pkl e metadata_index.json
    output_path: Path = _resolve(_cfg.get("embeddings", "output_path"))

    @property
    def clip_npy(self) -> Path:
        return self.output_path / "clip_embeddings.npy"

    @property
    def text_npy(self) -> Path:
        return self.output_path / "text_embeddings.npy"

    @property
    def bm25_pkl(self) -> Path:
        return self.output_path / "bm25_index.pkl"

    @property
    def metadata_json(self) -> Path:
        return self.output_path / "metadata_index.json"


class ModelSettings:
    clip_model_name: str = _cfg.get("models", "clip_model_name",
                                     fallback="openai/clip-vit-large-patch14")
    st_model_name: str = _cfg.get("models", "st_model_name",
                                   fallback="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")
    device: str = _cfg.get("models", "device", fallback="cpu")


class LogsSettings:
    path: Path = _resolve(_cfg.get("logs", "path", fallback="./logs"))


class Settings:
    nas = NasSettings()
    embeddings = EmbeddingsSettings()
    models = ModelSettings()
    logs = LogsSettings()


settings = Settings()