"""
SharePointRepository — leitura e escrita na planilha Excel via Microsoft Graph.

Todos os métodos são SÍNCRONOS (requests). O catalog_service deve chamá-los
via asyncio.to_thread para não bloquear o event loop.
"""

import logging
import time
from typing import Optional

import requests

from config.settings import settings


class SharePointRepository:

    _TOKEN_URL  = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"
    _GRAPH_BASE = "https://graph.microsoft.com/v1.0"

    def __init__(self, logger: logging.Logger):
        self.logger = logger
        self._sp    = settings.sharepoint
        self._token: Optional[str] = None

    # ------------------------------------------------------------------ AUTH

    def _get_token(self) -> str:
        if self._token:
            return self._token

        self.logger.debug("[SP] Obtendo token de autenticação...")
        url  = self._TOKEN_URL.format(tenant=self._sp.tenant_id)
        resp = requests.post(
            url,
            data={
                "grant_type":    "client_credentials",
                "client_id":     self._sp.client_id,
                "client_secret": self._sp.client_secret,
                "scope":         "https://graph.microsoft.com/.default",
            },
            timeout=30,
        )
        resp.raise_for_status()
        self._token = resp.json()["access_token"]
        self.logger.info("[SP] Token obtido com sucesso.")
        return self._token

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self._get_token()}"}

    def _get(self, url: str) -> dict:
        self.logger.debug(f"[SP] GET {url}")
        r = requests.get(url, headers=self._headers(), timeout=30)
        r.raise_for_status()
        return r.json()

    # ------------------------------------------------------------ METADATA

    def _get_ids(self) -> tuple[str, str, str, str]:
        """Retorna (site_id, drive_id, item_id, table_name)."""
        self.logger.debug("[SP] Buscando IDs do site/drive/item/tabela...")

        site     = self._get(f"{self._GRAPH_BASE}/sites/{self._sp.host}:/{self._sp.site_path}")
        site_id  = site["id"]

        drive    = self._get(f"{self._GRAPH_BASE}/sites/{site_id}/drives")
        drive_id = drive["value"][0]["id"]

        item     = self._get(
            f"{self._GRAPH_BASE}/sites/{site_id}/drives/{drive_id}"
            f"/root:/{self._sp.file_name}"
        )
        item_id  = item["id"]

        tables   = self._get(
            f"{self._GRAPH_BASE}/sites/{site_id}/drives/{drive_id}"
            f"/items/{item_id}/workbook/tables"
        )
        table    = tables["value"][0]["name"]

        self.logger.debug(
            f"[SP] IDs resolvidos | site={site_id[:12]}... "
            f"drive={drive_id[:12]}... table={table}"
        )
        return site_id, drive_id, item_id, table

    # --------------------------------------------------------------- READ

    def list_rows(self) -> list[dict]:
        """Retorna todas as linhas da tabela como lista de dicts."""
        self.logger.info("[SP] Lendo linhas da planilha...")
        t0 = time.time()

        site_id, drive_id, item_id, table = self._get_ids()

        headers_data = self._get(
            f"{self._GRAPH_BASE}/sites/{site_id}/drives/{drive_id}"
            f"/items/{item_id}/workbook/tables/{table}/headerRowRange"
        )
        headers = headers_data["values"][0]

        rows: list[list] = []
        url: Optional[str] = (
            f"{self._GRAPH_BASE}/sites/{site_id}/drives/{drive_id}"
            f"/items/{item_id}/workbook/tables/{table}/rows"
        )

        page = 0
        while url:
            data = self._get(url)
            batch = data.get("value", [])
            rows.extend(r["values"][0] for r in batch)
            url = data.get("@odata.nextLink")
            page += 1
            self.logger.debug(f"[SP] list_rows: página {page} | {len(batch)} linhas | total acum. {len(rows)}")

        elapsed = round(time.time() - t0, 2)
        result  = [dict(zip(headers, r)) for r in rows]
        self.logger.info(f"[SP] list_rows concluído | {len(result)} linhas | {elapsed}s")
        return result

    # -------------------------------------------------------------- UPDATE

    def update_row(self, product_id: str, fields: dict) -> None:
        """Atualiza uma linha específica da planilha pelo Id_produto."""
        self.logger.info(f"[SP] update_row | pid={product_id} | fields={list(fields.keys())}")
        t0 = time.time()

        site_id, drive_id, item_id, table = self._get_ids()

        header_data = self._get(
            f"{self._GRAPH_BASE}/sites/{site_id}/drives/{drive_id}"
            f"/items/{item_id}/workbook/tables/{table}/headerRowRange"
        )
        headers    = header_data["values"][0]
        id_col_idx = headers.index("Id_produto")

        rows_data = self._get(
            f"{self._GRAPH_BASE}/sites/{site_id}/drives/{drive_id}"
            f"/items/{item_id}/workbook/tables/{table}/rows"
        )["value"]

        target_idx: Optional[int] = None
        for i, row in enumerate(rows_data):
            if str(row["values"][0][id_col_idx]) == str(product_id):
                target_idx = i
                break

        if target_idx is None:
            self.logger.warning(f"[SP] update_row | pid={product_id} não encontrado na planilha — ignorando.")
            return

        row_values = list(rows_data[target_idx]["values"][0])
        for k, v in fields.items():
            if k in headers:
                col_idx = headers.index(k)
                old_val = row_values[col_idx]
                row_values[col_idx] = v
                self.logger.debug(f"[SP] update_row | pid={product_id} | {k}: {old_val!r} → {v!r}")
            else:
                self.logger.warning(f"[SP] update_row | coluna '{k}' não encontrada nos headers — ignorando.")

        patch_url = (
            f"{self._GRAPH_BASE}/sites/{site_id}/drives/{drive_id}"
            f"/items/{item_id}/workbook/tables/{table}"
            f"/rows/itemAt(index={target_idx})"
        )

        resp = requests.patch(
            patch_url,
            headers={**self._headers(), "Content-Type": "application/json"},
            json={"values": [row_values]},
            timeout=30,
        )
        resp.raise_for_status()

        elapsed = round(time.time() - t0, 2)
        self.logger.info(f"[SP] update_row concluído | pid={product_id} | {elapsed}s")