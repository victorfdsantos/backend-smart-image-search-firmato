"""
SharePointRepository — leitura e escrita na planilha Excel via Microsoft Graph.

Todos os métodos são SÍNCRONOS (requests). O catalog_service deve chamá-los
via asyncio.to_thread para não bloquear o event loop.

Inclui retry com exponential backoff para erros de cota (429 / 503).
"""

import logging
import time
from typing import Optional

import requests

from config.settings import settings

# ── Retry config ──────────────────────────────────────────────────────────────
_RETRY_STATUS = {429, 503}   # códigos que disparam retry
_MAX_RETRIES  = 6             # máximo de tentativas por chamada
_BACKOFF_BASE = 2.0           # segundos base (dobra a cada tentativa)
_BACKOFF_MAX  = 120.0         # teto de espera por tentativa (segundos)


def _with_retry(fn, logger: logging.Logger, label: str):
    """Executa fn() com retry + exponential backoff em erros de cota."""
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            return fn()
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else 0

            if status not in _RETRY_STATUS or attempt == _MAX_RETRIES:
                raise

            # Respeita o header Retry-After se presente
            retry_after = exc.response.headers.get("Retry-After")
            wait = float(retry_after) if retry_after else min(
                _BACKOFF_BASE * (2 ** (attempt - 1)), _BACKOFF_MAX
            )

            logger.warning(
                f"[SP] {label} | HTTP {status} (throttle/cota) | "
                f"tentativa {attempt}/{_MAX_RETRIES} | aguardando {wait:.1f}s..."
            )
            time.sleep(wait)

    raise RuntimeError(f"[SP] {label}: todas as {_MAX_RETRIES} tentativas falharam.")


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

        def do():
            resp = requests.post(
                self._TOKEN_URL.format(tenant=self._sp.tenant_id),
                data={
                    "grant_type":    "client_credentials",
                    "client_id":     self._sp.client_id,
                    "client_secret": self._sp.client_secret,
                    "scope":         "https://graph.microsoft.com/.default",
                },
                timeout=30,
            )
            resp.raise_for_status()
            return resp.json()["access_token"]

        self._token = _with_retry(do, self.logger, "get_token")
        self.logger.info("[SP] Token obtido com sucesso.")
        return self._token

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self._get_token()}"}

    def _get(self, url: str) -> dict:
        self.logger.debug(f"[SP] GET {url}")

        def do():
            r = requests.get(url, headers=self._headers(), timeout=30)
            r.raise_for_status()
            return r.json()

        return _with_retry(do, self.logger, f"GET ...{url[-60:]}")

    def _patch(self, url: str, payload: dict) -> None:
        self.logger.debug(f"[SP] PATCH {url}")

        def do():
            r = requests.patch(
                url,
                headers={**self._headers(), "Content-Type": "application/json"},
                json=payload,
                timeout=30,
            )
            r.raise_for_status()

        _with_retry(do, self.logger, f"PATCH ...{url[-60:]}")

    # ------------------------------------------------------------ METADATA

    def _get_ids(self) -> tuple[str, str, str, str]:
        """Retorna (site_id, drive_id, item_id, table_name)."""
        self.logger.debug("[SP] Buscando IDs do site/drive/item/tabela...")

        site     = self._get(f"{self._GRAPH_BASE}/sites/{self._sp.host}:/{self._sp.site_path}")
        site_id  = site["id"]

        drive    = self._get(f"{self._GRAPH_BASE}/sites/{site_id}/drives")
        drive_id = drive["value"][0]["id"]

        item = self._get(
            f"{self._GRAPH_BASE}/sites/{site_id}/drives/{drive_id}"
            f"/root:/{self._sp.file_name}"
        )
        item_id = item["id"]

        tables = self._get(
            f"{self._GRAPH_BASE}/sites/{site_id}/drives/{drive_id}"
            f"/items/{item_id}/workbook/tables"
        )
        table = tables["value"][0]["name"]

        self.logger.debug(
            f"[SP] IDs resolvidos | site={site_id[:12]}... drive={drive_id[:12]}... table={table}"
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
            data  = self._get(url)
            batch = data.get("value", [])
            rows.extend(r["values"][0] for r in batch)
            url = data.get("@odata.nextLink")
            page += 1
            self.logger.debug(
                f"[SP] list_rows: página {page} | {len(batch)} linhas | total {len(rows)}"
            )

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
            self.logger.warning(
                f"[SP] update_row | pid={product_id} não encontrado na planilha — ignorando."
            )
            return

        row_values = list(rows_data[target_idx]["values"][0])
        for k, v in fields.items():
            if k in headers:
                col_idx = headers.index(k)
                old_val = row_values[col_idx]
                row_values[col_idx] = v
                self.logger.debug(
                    f"[SP] update_row | pid={product_id} | {k}: {old_val!r} → {v!r}"
                )
            else:
                self.logger.warning(
                    f"[SP] update_row | coluna '{k}' não encontrada — ignorando."
                )

        patch_url = (
            f"{self._GRAPH_BASE}/sites/{site_id}/drives/{drive_id}"
            f"/items/{item_id}/workbook/tables/{table}"
            f"/rows/itemAt(index={target_idx})"
        )

        self._patch(patch_url, {"values": [row_values]})

        elapsed = round(time.time() - t0, 2)
        self.logger.info(f"[SP] update_row concluído | pid={product_id} | {elapsed}s")