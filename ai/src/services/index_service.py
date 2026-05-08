"""
IndexService — retreinamento incremental de embeddings CLIP + ST + BM25.

Fluxo por chamada:
  1. Carrega índices atuais do Blob (clip, text, metadata, bm25)
  2. Atualiza apenas as posições dos IDs informados
  3. Persiste os índices atualizados de volta no Blob

Os modelos CLIP e ST vêm do app_state (carregados no startup).
Os índices NÃO ficam em memória entre chamadas — cada retrain
parte do estado salvo no Blob.
"""

import json
import pickle
import re
import unicodedata
from io import BytesIO
from typing import Optional

import numpy as np

from services.filter_index_service import FilterIndexService

TEXT_FIELDS = [
    "nome_produto", "marca", "categoria_principal", "subcategoria",
    "ambiente", "forma",
    "material_principal", "material_estrutura", "material_revestimento",
    "faixa_preco", "descricao_tecnica",
]

TECHNICAL_FIELDS = {
    "altura_cm": "altura",
    "largura_cm": "largura",
    "profundidade_cm": "profundidade",
}


def _tokenize(text: str) -> list[str]:
    text = unicodedata.normalize("NFD", text.lower())
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    return re.findall(r"\b\w+\b", text)


def _build_text(data: dict, pid: str) -> str:
    parts = []
    for f in TEXT_FIELDS:
        v = data.get(f)
        if v:
            parts.append(str(v))
    for f, label in TECHNICAL_FIELDS.items():
        v = data.get(f)
        if v:
            parts.append(f"{label} {v}")
    return " | ".join(parts) if parts else f"produto {pid}"


def _clean(val) -> str:
    """Normaliza um valor de campo para string limpa (sem nan/None)."""
    if val is None:
        return ""
    s = str(val).strip()
    return "" if s.lower() in ("nan", "none", "") else s


class IndexService:

    def __init__(self, logger, app_state: dict, repo):
        self.logger = logger
        self.state  = app_state   # apenas para modelos CLIP/ST
        self.repo   = repo

    # ------------------------------------------------------------------
    # ENTRYPOINT
    # ------------------------------------------------------------------

    def retrain(self, image_ids: list[str], data_ids: list[str]) -> dict:
        image_set = set(image_ids)
        data_set  = set(data_ids)
        all_ids   = sorted(image_set | data_set)

        self.logger.info(
            f"[Index] Retrain iniciado | total_ids={len(all_ids)} "
            f"| image_ids={len(image_set)} | data_ids={len(data_set)}"
        )

        # ── valida modelos antes de processar ─────────────────────────
        if image_set and self.state.get("clip_model") is None:
            raise RuntimeError(
                "Modelo CLIP não carregado — verifique os logs do startup."
            )
        if data_set and self.state.get("st_model") is None:
            raise RuntimeError(
                "Modelo ST não carregado — verifique os logs do startup."
            )

        stats = {
            "total_requested": len(all_ids),
            "clip_updated":    0,
            "text_updated":    0,
            "bm25_rebuilt":    False,
            "errors":          [],
        }

        # ── carrega índices atuais do Blob ─────────────────────────────
        clip_arr, text_arr, metadata, bm25_corpus = self._load_indices()

        self.logger.debug(
            f"[Index] Índices carregados | "
            f"clip={None if clip_arr is None else clip_arr.shape} | "
            f"text={None if text_arr is None else text_arr.shape} | "
            f"metadata={len(metadata)} | bm25_corpus={len(bm25_corpus)}"
        )

        id_to_pos: dict[str, int] = {m["id"]: i for i, m in enumerate(metadata)}

        # ── processa cada ID ───────────────────────────────────────────
        for pid in all_ids:
            try:
                clip_arr, text_arr = self._process(
                    pid         = pid,
                    image_set   = image_set,
                    data_set    = data_set,
                    clip_arr    = clip_arr,
                    text_arr    = text_arr,
                    metadata    = metadata,
                    bm25_corpus = bm25_corpus,
                    id_to_pos   = id_to_pos,
                    stats       = stats,
                )
            except Exception as e:
                self.logger.error(f"[Index] Erro no PID {pid}: {e}", exc_info=True)
                stats["errors"].append(f"{pid}: {e}")

        # ── reconstrói BM25 se algum texto mudou ──────────────────────
        if stats["text_updated"]:
            self._rebuild_bm25(bm25_corpus, stats)

        # ── persiste no Blob ───────────────────────────────────────────
        self.logger.info("[Index] Persistindo...")
        self._persist(clip_arr, text_arr, metadata, bm25_corpus)

        # ── reconstrói índice de filtros e salva no Blob ───────────────
        filter_svc = FilterIndexService(logger=self.logger, repo=self.repo)
        filter_index = filter_svc.rebuild(metadata)
        self.state["filter_index"] = filter_index

        self.logger.info(f"[Index] Finalizado | stats={stats}")
        return stats

    # ------------------------------------------------------------------
    # LOAD INDICES FROM BLOB
    # ------------------------------------------------------------------

    def _load_indices(self) -> tuple[
        Optional[np.ndarray],
        Optional[np.ndarray],
        list[dict],
        list[list[str]],
    ]:
        clip_arr    = None
        text_arr    = None
        metadata    = []
        bm25_corpus = []

        try:
            data     = self.repo.download_sync("firmato-catalogo", "embeddings/clip_embeddings.npy")
            clip_arr = np.load(BytesIO(data))
            self.logger.info(f"[Index] clip_embeddings carregado: shape={clip_arr.shape}")
        except Exception as e:
            self.logger.warning(f"[Index] clip_embeddings ausente ({e}) — será criado.")

        try:
            data     = self.repo.download_sync("firmato-catalogo", "embeddings/text_embeddings.npy")
            text_arr = np.load(BytesIO(data))
            self.logger.info(f"[Index] text_embeddings carregado: shape={text_arr.shape}")
        except Exception as e:
            self.logger.warning(f"[Index] text_embeddings ausente ({e}) — será criado.")

        try:
            data     = self.repo.download_sync("firmato-catalogo", "embeddings/metadata.json")
            metadata = json.loads(data)
            self.logger.info(f"[Index] metadata carregado: {len(metadata)} entradas")
        except Exception as e:
            self.logger.warning(f"[Index] metadata ausente ({e}) — será criado.")

        try:
            data        = self.repo.download_sync("firmato-catalogo", "embeddings/bm25.pkl")
            obj         = pickle.loads(data)
            bm25_corpus = obj["corpus"]
            self.logger.info(f"[Index] bm25_corpus carregado: {len(bm25_corpus)} docs")
        except Exception as e:
            self.logger.warning(f"[Index] bm25 ausente ({e}) — será criado.")

        return clip_arr, text_arr, metadata, bm25_corpus

    # ------------------------------------------------------------------
    # PROCESS (um produto por vez)
    # ------------------------------------------------------------------

    def _process(
        self,
        pid:         str,
        image_set:   set[str],
        data_set:    set[str],
        clip_arr:    Optional[np.ndarray],
        text_arr:    Optional[np.ndarray],
        metadata:    list[dict],
        bm25_corpus: list[list[str]],
        id_to_pos:   dict[str, int],
        stats:       dict,
    ) -> tuple[Optional[np.ndarray], Optional[np.ndarray]]:

        self.logger.debug(f"[Index] Processando PID={pid}")

        data = self.repo.get_json(pid)
        if not data:
            raise ValueError(f"JSON não encontrado no Blob para pid={pid}")

        text = _build_text(data, pid)

        # upsert no metadata
        is_new     = pid not in id_to_pos
        meta_entry = {
            "id":                  pid,
            "imagem":              f"{pid}.jpg",
            "json":                f"{pid}.json",
            "text_corpus":         text,
            # campos de filtro — usados pelo FilterIndexService
            "marca":               _clean(data.get("marca")),
            "categoria_principal": _clean(data.get("categoria_principal")),
            "subcategoria":        _clean(data.get("subcategoria")),
            "faixa_preco":         _clean(data.get("faixa_preco")),
            "ambiente":            _clean(data.get("ambiente")),
            "forma":               _clean(data.get("forma")),
            "material_principal":  _clean(data.get("material_principal")),
        }

        if is_new:
            metadata.append(meta_entry)
            pos            = len(metadata) - 1
            id_to_pos[pid] = pos
        else:
            pos            = id_to_pos[pid]
            metadata[pos]  = meta_entry

        total = len(metadata)

        # CLIP
        if pid in image_set:
            img_bytes = self.repo.get_image(pid)
            if not img_bytes:
                self.logger.warning(f"[Index] Imagem ausente no Blob | pid={pid}")
            else:
                clip_arr = self._upsert(clip_arr, pos, self._encode_image(img_bytes), total)
                stats["clip_updated"] += 1

        # ST + BM25
        if pid in data_set:
            text_arr = self._upsert(text_arr, pos, self._encode_text(text), total)
            stats["text_updated"] += 1

            while len(bm25_corpus) <= pos:
                bm25_corpus.append([])
            bm25_corpus[pos] = _tokenize(text)

        return clip_arr, text_arr

    # ------------------------------------------------------------------
    # UPSERT
    # ------------------------------------------------------------------

    def _upsert(self, arr: Optional[np.ndarray], pos: int, vec: np.ndarray, total: int) -> np.ndarray:
        dim = len(vec)

        if arr is None:
            arr = np.zeros((total, dim), dtype=np.float32)

        if pos >= len(arr):
            needed = max(total, pos + 1)
            arr    = np.vstack([arr, np.zeros((needed - len(arr), dim), dtype=np.float32)])

        arr[pos] = vec
        return arr

    # ------------------------------------------------------------------
    # ENCODERS
    # ------------------------------------------------------------------

    def _encode_image(self, image_bytes: bytes) -> np.ndarray:
        import torch
        import torch.nn.functional as F
        from PIL import Image

        img    = Image.open(BytesIO(image_bytes)).convert("RGB")
        proc   = self.state["clip_processor"]
        model  = self.state["clip_model"]
        device = self.state["clip_device"]

        inputs = proc(images=img, return_tensors="pt").to(device)
        with torch.no_grad():
            emb = F.normalize(model.get_image_features(**inputs), dim=-1)
        return emb.cpu().numpy()[0]

    def _encode_text(self, text: str) -> np.ndarray:
        return self.state["st_model"].encode(text, normalize_embeddings=True)

    # ------------------------------------------------------------------
    # BM25
    # ------------------------------------------------------------------

    def _rebuild_bm25(self, corpus: list[list[str]], stats: dict) -> None:
        from rank_bm25 import BM25Okapi

        clean = [tokens if tokens else ["_"] for tokens in corpus]
        self.state["bm25"] = BM25Okapi(clean)
        stats["bm25_rebuilt"] = True
        self.logger.info(f"[Index] BM25 rebuild | docs={len(clean)}")

    # ------------------------------------------------------------------
    # PERSIST → Blob
    # ------------------------------------------------------------------

    def _persist(
        self,
        clip:    Optional[np.ndarray],
        text:    Optional[np.ndarray],
        meta:    list[dict],
        corpus:  list[list[str]],
    ) -> None:
        errors = []

        if clip is not None:
            try:
                buf = BytesIO()
                np.save(buf, clip)
                self.repo.save_clip_embeddings(buf.getvalue())
                self.logger.info(f"[Index] CLIP salvo | shape={clip.shape}")
            except Exception as e:
                errors.append(f"clip: {e}")

        if text is not None:
            try:
                buf = BytesIO()
                np.save(buf, text)
                self.repo.save_text_embeddings(buf.getvalue())
                self.logger.info(f"[Index] TEXT salvo | shape={text.shape}")
            except Exception as e:
                errors.append(f"text: {e}")

        try:
            self.repo.save_metadata(json.dumps(meta, ensure_ascii=False).encode("utf-8"))
            self.logger.info(f"[Index] Metadata salvo | total={len(meta)}")
        except Exception as e:
            errors.append(f"metadata: {e}")

        bm25_obj = self.state.get("bm25")
        if bm25_obj is not None:
            try:
                self.repo.save_bm25(pickle.dumps({"bm25": bm25_obj, "corpus": corpus}))
                self.logger.info("[Index] BM25 salvo")
            except Exception as e:
                errors.append(f"bm25: {e}")

        if errors:
            raise RuntimeError(f"Falhas na persistência: {'; '.join(errors)}")