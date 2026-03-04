"""JsonService — salva e carrega os arquivos data/{ID}.json de cada produto."""

import json
import logging
from pathlib import Path
from typing import Optional

from config.settings import settings
from models.product_model import ProductModel


class JsonService:

    def __init__(self, logger: logging.Logger):
        self.logger = logger
        self.data_dir = settings.general.data_path

    def save(self, model: ProductModel, product_id: int) -> bool:
        try:
            self.data_dir.mkdir(parents=True, exist_ok=True)
            path = self.data_dir / f"{product_id}.json"
            with open(path, "w", encoding="utf-8") as f:
                json.dump(model.to_dict(), f, ensure_ascii=False, indent=2)
            self.logger.info(f"[JSON] Salvo: {path}")
            return True
        except Exception as exc:
            self.logger.error(f"[JSON] Erro ao salvar {product_id}: {exc}", exc_info=True)
            return False

    def load(self, product_id: int) -> Optional[dict]:
        path = self.data_dir / f"{product_id}.json"
        if not path.exists():
            return None
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except Exception as exc:
            self.logger.error(f"[JSON] Erro ao carregar {product_id}: {exc}", exc_info=True)
            return None
