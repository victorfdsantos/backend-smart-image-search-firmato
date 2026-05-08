"""
FilterIndexService — constrói e mantém em memória o índice de filtros
a partir do metadata.json que já está no Blob.

Estrutura do índice:
{
    "marca": {
        "Tok&Stok": [1, 5, 23, 77],
        "Etna":     [2, 8, 31],
        ...
    },
    "categoria_principal": { ... },
    "subcategoria":        { ... },
    "faixa_preco":         { ... },
    "ambiente":            { ... },
    "forma":               { ... },
    "material_principal":  { ... },
}

O índice é salvo no Blob como embeddings/filter_index.json para
sobreviver a restarts sem precisar reconstruir do zero.
"""

import json
import logging
import re
from io import BytesIO
from typing import Optional

FILTER_FIELDS = [
    "marca",
    "categoria_principal",
    "subcategoria",
    "faixa_preco",
    "ambiente",
    "forma",
    "material_principal",
]

_CONTAINER = "firmato-catalogo"
_BLOB_PATH = "embeddings/filter_index.json"


def _clean(val) -> str:
    if val is None:
        return ""
    s = str(val).strip()
    return "" if s.lower() in ("nan", "none", "") else s


def _split(raw: str) -> list[str]:
    """Separa valores compostos tipo 'Sala / Escritório' em ['Sala', 'Escritório']."""
    return [p.strip() for p in re.split(r"\s*/\s*", raw) if p.strip()]


def build_filter_index(metadata: list[dict]) -> dict[str, dict[str, list[str]]]:
    """
    Recebe a lista de metadados (igual ao metadata.json) e retorna
    o índice de filtros.

    Cada produto no metadata tem campos como:
        { "id": "42", "imagem": "42.jpg", "text_corpus": "...", ... }

    Os campos de filtro vêm diretamente do JSON do produto via text_corpus,
    mas como o metadata só guarda o corpus de texto, precisamos que o
    metadata também guarde os campos individuais.

    NOTA: o IndexService já salva os campos completos do produto no metadata.
    Se não estiver salvando, ajustamos ali também.
    """
    index: dict[str, dict[str, list[str]]] = {f: {} for f in FILTER_FIELDS}

    for entry in metadata:
        pid = str(entry.get("id", ""))
        if not pid:
            continue

        for field in FILTER_FIELDS:
            raw = _clean(entry.get(field))
            if not raw:
                continue

            for val in _split(raw):
                index[field].setdefault(val, [])
                if pid not in index[field][val]:
                    index[field][val].append(pid)

    # ordena as listas de IDs para consistência
    for field in index:
        for val in index[field]:
            index[field][val].sort()

    return index


class FilterIndexService:

    def __init__(self, logger: logging.Logger, repo):
        self.logger = logger
        self.repo   = repo

    # ------------------------------------------------------------------
    # BUILD + PERSIST
    # ------------------------------------------------------------------

    def rebuild(self, metadata: list[dict]) -> dict[str, dict[str, list[str]]]:
        """
        Reconstrói o índice a partir do metadata, salva no Blob e retorna.
        Chamado após cada treino pelo IndexService.
        """
        self.logger.info(f"[FilterIndex] Rebuilding | entries={len(metadata)}")
        index = build_filter_index(metadata)
        self._persist(index)
        self.logger.info(
            "[FilterIndex] OK | "
            + ", ".join(f"{f}={len(index[f])}" for f in FILTER_FIELDS)
        )
        return index

    # ------------------------------------------------------------------
    # LOAD FROM BLOB (usado no startup)
    # ------------------------------------------------------------------

    def load(self) -> Optional[dict[str, dict[str, list[str]]]]:
        """
        Tenta carregar o índice já construído do Blob.
        Retorna None se não existir (primeira execução).
        """
        try:
            data = self.repo.download_sync(_CONTAINER, _BLOB_PATH)
            index = json.loads(data)
            self.logger.info(
                "[FilterIndex] Carregado do Blob | "
                + ", ".join(f"{f}={len(index.get(f, {}))}" for f in FILTER_FIELDS)
            )
            return index
        except Exception as e:
            self.logger.warning(
                f"[FilterIndex] Não encontrado no Blob ({e}) "
                "— será construído no próximo treino."
            )
            return None

    # ------------------------------------------------------------------
    # PERSIST
    # ------------------------------------------------------------------

    def _persist(self, index: dict) -> None:
        try:
            data = json.dumps(index, ensure_ascii=False).encode("utf-8")
            self.repo._upload(_BLOB_PATH, data)
            self.logger.info("[FilterIndex] Salvo no Blob")
        except Exception as e:
            self.logger.error(f"[FilterIndex] Falha ao salvar: {e}", exc_info=True)