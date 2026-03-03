import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd

from config.settings import settings
from models.product_model import ProductModel, COLUMN_MAP


class SpreadsheetService:
    """
    Responsável por todas as operações de leitura e escrita
    da planilha Excel do catálogo.
    """

    SHEET_NAME = "Catalogo_Produtos"

    def __init__(self, logger: logging.Logger):
        self.logger = logger

    # ------------------------------------------------------------------
    # Leitura
    # ------------------------------------------------------------------

    def load(self, xlsx_path: Path) -> pd.DataFrame:
        """
        Lê a planilha e retorna um DataFrame limpo.
        Todos os campos são lidos como string; NaN vira None.
        Lança exceção em caso de falha (deixa o controller tratar).
        """
        self.logger.info(f"[Spreadsheet] Carregando planilha: {xlsx_path}")
        df = pd.read_excel(xlsx_path, sheet_name=self.SHEET_NAME, dtype=str)
        df = df.where(pd.notna(df), None)
        self.logger.info(f"[Spreadsheet] {len(df)} linhas carregadas.")
        return df

    # ------------------------------------------------------------------
    # Escrita
    # ------------------------------------------------------------------

    def save(self, df: pd.DataFrame, original_path: Path) -> Optional[Path]:
        """
        Salva o DataFrame no NAS (pasta planilhas/).
        Se falhar, tenta salvar com sufixo de data/hora para não perder dados.
        Retorna o caminho onde foi salvo, ou None em falha total.
        """
        nas_dir = settings.nas.base_path / "planilhas"
        nas_dir.mkdir(parents=True, exist_ok=True)
        dest_path = nas_dir / original_path.name

        try:
            df.to_excel(dest_path, index=False, sheet_name=self.SHEET_NAME)
            self.logger.info(f"[Spreadsheet] Planilha salva: {dest_path}")
            return dest_path
        except Exception as exc:
            self.logger.error(
                f"[Spreadsheet] Erro ao salvar em '{dest_path}': {exc}. "
                "Tentando salvar com sufixo de data/hora.",
                exc_info=True,
            )
            return self._save_fallback(df, nas_dir, original_path)

    def _save_fallback(
        self, df: pd.DataFrame, nas_dir: Path, original_path: Path
    ) -> Optional[Path]:
        """Salva com sufixo de data/hora como fallback."""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            fallback_path = nas_dir / f"{original_path.stem}_{timestamp}{original_path.suffix}"
            df.to_excel(fallback_path, index=False, sheet_name=self.SHEET_NAME)
            self.logger.info(f"[Spreadsheet] Planilha salva (fallback): {fallback_path}")
            return fallback_path
        except Exception as exc2:
            self.logger.error(
                f"[Spreadsheet] Falha crítica ao salvar planilha fallback: {exc2}",
                exc_info=True,
            )
            return None

    # ------------------------------------------------------------------
    # Conversão de linha → Model
    # ------------------------------------------------------------------

    def row_to_model(self, row_dict: dict) -> ProductModel:
        """
        Converte um dicionário de linha do Excel para ProductModel.
        Apenas preenche os campos mapeados em COLUMN_MAP (dados do produto).
        Campos exclusivos do JSON (caminhos NAS/bucket) devem ser preenchidos
        pelo CatalogService após o processamento.
        """
        model = ProductModel()
        for excel_col, model_field in COLUMN_MAP.items():
            val = row_dict.get(excel_col)
            if val is not None and str(val).lower() not in ("nan", "none", ""):
                setattr(model, model_field, val)
        return model

    # ------------------------------------------------------------------
    # Utilitários
    # ------------------------------------------------------------------

    def parse_id(self, value) -> Optional[int]:
        """Converte valor de Id_produto para int. Retorna None se inválido."""
        try:
            return int(float(str(value)))
        except (ValueError, TypeError):
            return None

    def clean_str(self, value) -> Optional[str]:
        """Normaliza célula de string: None/NaN/vazio vira None."""
        if value is None:
            return None
        s = str(value).strip()
        return s if s and s.lower() not in ("nan", "none") else None
