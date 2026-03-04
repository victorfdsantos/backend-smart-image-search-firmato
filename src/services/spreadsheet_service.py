"""SpreadsheetService — leitura e escrita da planilha Excel do catálogo."""

import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd

from config.settings import settings
from models.product_model import ProductModel, COLUMN_MAP


class SpreadsheetService:

    SHEET_NAME = "Catalogo_Produtos"

    def __init__(self, logger: logging.Logger):
        self.logger = logger

    def load(self, xlsx_path: Path) -> pd.DataFrame:
        self.logger.info(f"[Spreadsheet] Carregando: {xlsx_path}")
        df = pd.read_excel(xlsx_path, sheet_name=self.SHEET_NAME, dtype=str)
        df = df.where(pd.notna(df), None)
        self.logger.info(f"[Spreadsheet] {len(df)} linhas carregadas.")
        return df

    def save(self, df: pd.DataFrame, original_path: Path) -> Optional[Path]:
        nas_dir = settings.nas.base_path / "planilhas"
        nas_dir.mkdir(parents=True, exist_ok=True)
        dest = nas_dir / original_path.name
        try:
            df.to_excel(dest, index=False, sheet_name=self.SHEET_NAME)
            self.logger.info(f"[Spreadsheet] Salva em: {dest}")
            return dest
        except Exception as exc:
            self.logger.warning(f"[Spreadsheet] Falha ao salvar em '{dest}': {exc}. Tentando fallback.")
            return self._save_fallback(df, nas_dir, original_path)

    def row_to_model(self, row_dict: dict) -> ProductModel:
        """Converte linha do Excel → ProductModel. Preenche apenas dados (não caminhos)."""
        model = ProductModel()
        for excel_col, model_field in COLUMN_MAP.items():
            val = row_dict.get(excel_col)
            if val is not None and str(val).lower() not in ("nan", "none", ""):
                setattr(model, model_field, val)
        return model

    def parse_id(self, value) -> Optional[int]:
        try:
            return int(float(str(value)))
        except (ValueError, TypeError):
            return None

    def _save_fallback(self, df: pd.DataFrame, nas_dir: Path, original_path: Path) -> Optional[Path]:
        try:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            fallback = nas_dir / f"{original_path.stem}_{ts}{original_path.suffix}"
            df.to_excel(fallback, index=False, sheet_name=self.SHEET_NAME)
            self.logger.info(f"[Spreadsheet] Salva (fallback): {fallback}")
            return fallback
        except Exception as exc:
            self.logger.error(f"[Spreadsheet] Falha crítica ao salvar: {exc}", exc_info=True)
            return None
