"""SearchService — busca híbrida CLIP + ST + BM25 com suporte a filtros em cascata."""

import json
import logging
import re
import unicodedata
from io import BytesIO
from typing import Optional

import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image


def _minmax(scores: np.ndarray) -> np.ndarray:
    mn, mx = scores.min(), scores.max()
    if mx - mn < 1e-9:
        return np.zeros_like(scores)
    return (scores - mn) / (mx - mn)

def _tokenize(text: str) -> list[str]:
    text = unicodedata.normalize("NFD", text.lower())
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    return re.findall(r'\b\w+\b', text)

class SearchService:

    _CONTAINER = "firmato-catalogo"

    def __init__(
        self, logger: logging.Logger,
        clip_embeddings, text_embeddings, metadata,
        clip_model, clip_processor, clip_device,
        st_model=None,
        bm25=None,
        blob_repo=None,
    ):
        self.logger      = logger
        self.clip_emb    = clip_embeddings
        self.text_emb    = text_embeddings
        self.metadata    = metadata
        self.clip_model  = clip_model
        self.clip_proc   = clip_processor
        self.clip_device = clip_device
        self.st_model    = st_model
        self.bm25        = bm25
        self.blob        = blob_repo  # BlobStorageRepository (async)

    # ------------------------------------------------------------------
    # Ponto de entrada
    # ------------------------------------------------------------------

    async def search(
        self,
        query: str = None,
        image_bytes: bytes = None,
        top_k: int = 20,
        allowed_ids: Optional[set] = None,
    ) -> list[dict]:
        if self.clip_emb is None or self.clip_model is None:
            self.logger.warning("[Search] Embeddings ou CLIP não disponíveis.")
            return []

        has_text  = bool(query and query.strip())
        has_image = bool(image_bytes)

        if not has_text and not has_image:
            return []

        n = len(self.metadata)
        clip_scores = np.zeros(n)
        st_scores   = np.zeros(n)
        bm25_scores = np.zeros(n)

        # ── CLIP ──────────────────────────────────────────────────────
        if has_image and has_text:
            img_vec = self._encode_image(image_bytes)
            txt_vec = self._encode_text_clip(query)
            if img_vec is not None and txt_vec is not None:
                combined = (img_vec + txt_vec) / 2
                query_vec = combined / (np.linalg.norm(combined) + 1e-9)
            elif img_vec is not None:
                query_vec = img_vec
            else:
                query_vec = txt_vec
            if query_vec is not None:
                clip_scores = self.clip_emb @ query_vec

        elif has_image:
            img_vec = self._encode_image(image_bytes)
            if img_vec is not None:
                clip_scores = self.clip_emb @ img_vec

        elif has_text:
            txt_vec = self._encode_text_clip(query)
            if txt_vec is not None:
                clip_scores = self.clip_emb @ txt_vec

        # ── ST ────────────────────────────────────────────────────────
        if has_text and self.text_emb is not None and self.st_model is not None:
            st_vec    = self.st_model.encode(query, normalize_embeddings=True)
            st_scores = self.text_emb @ st_vec

        # ── BM25 ──────────────────────────────────────────────────────
        if has_text and self.bm25 is not None:
            tokens      = _tokenize(query)
            bm25_scores = np.array(self.bm25.get_scores(tokens))

        # ── Pesos ─────────────────────────────────────────────────────
        if has_image and has_text:
            w_clip, w_st, w_bm25 = 0.50, 0.30, 0.20
        elif has_image:
            w_clip, w_st, w_bm25 = 1.0, 0.0, 0.0
        else:
            w_clip, w_st, w_bm25 = 0.40, 0.35, 0.25

        final = (
            w_clip * _minmax(clip_scores) +
            w_st   * _minmax(st_scores)   +
            w_bm25 * _minmax(bm25_scores)
        )

        # ── Filtra allowed_ids e retorna top_k ────────────────────────
        order = np.argsort(final)[::-1]
        results = []
        for idx in order:
            if len(results) >= top_k:
                break
            meta = self.metadata[idx]
            pid  = str(meta.get("id", ""))

            if allowed_ids is not None and pid not in {str(x) for x in allowed_ids}:
                continue

            product = await self._load_json(pid)
            if product is None:
                continue
            if str(product.get("status", "")).strip().lower() != "ativo":
                continue

            results.append({
                "id_produto": pid,
                "score":      float(final[idx]),
                "score_clip": float(clip_scores[idx]),
                "score_st":   float(st_scores[idx]),
                "score_bm25": float(bm25_scores[idx]),
                "imagem_url": f"/api/products/thumbnail/{pid}.jpg",
            })

        return results

    # ------------------------------------------------------------------
    # Encoders
    # ------------------------------------------------------------------

    def _encode_text_clip(self, text: str) -> Optional[np.ndarray]:
        try:
            from deep_translator import GoogleTranslator
            translated = GoogleTranslator(source="pt", target="en").translate(text)
            self.logger.info(f"[Search] CLIP: '{text}' → '{translated}'")
        except Exception:
            translated = text
        try:
            inputs = self.clip_proc(
                text=[translated], return_tensors="pt", padding=True
            ).to(self.clip_device)
            with torch.no_grad():
                emb = self.clip_model.get_text_features(**inputs)
                return F.normalize(emb, p=2, dim=-1).cpu().numpy()[0]
        except Exception as exc:
            self.logger.warning(f"[Search] Falha encode CLIP texto: {exc}")
            return None

    def _encode_image(self, image_bytes: bytes) -> Optional[np.ndarray]:
        try:
            img = Image.open(BytesIO(image_bytes)).convert("RGB")
            inputs = self.clip_proc(images=img, return_tensors="pt").to(self.clip_device)
            with torch.no_grad():
                emb = self.clip_model.get_image_features(**inputs)
                return F.normalize(emb, p=2, dim=-1).cpu().numpy()[0]
        except Exception as exc:
            self.logger.warning(f"[Search] Falha encode imagem: {exc}")
            return None

    # ------------------------------------------------------------------
    # Helper — lê JSON do produto diretamente do Blob
    # ------------------------------------------------------------------

    async def _load_json(self, product_id: str) -> Optional[dict]:
        if self.blob is None:
            self.logger.warning("[Search] blob_repo não disponível — não foi possível carregar JSON do produto.")
            return None
        try:
            data = await self.blob.download(self._CONTAINER, f"data/{product_id}.json")
            return json.loads(data)
        except Exception as exc:
            self.logger.warning(f"[Search] JSON não encontrado no Blob | pid={product_id}: {exc}")
            return None