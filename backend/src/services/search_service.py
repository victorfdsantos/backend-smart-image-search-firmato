"""SearchService — busca híbrida CLIP + ST + BM25 com suporte a filtros em cascata.

Melhorias:
- Detecção de marca na query (fuzzy, case-insensitive, antes de traduzir)
- Threshold de similaridade 0.65
- Resultados paginados pelo caller
- Cache LRU de tradução PT→EN para evitar requests externos repetidos
- Resultados já enriquecidos com campos do metadata em memória
  (elimina N+1 de getProductDetail no frontend)
"""

import json
import logging
import re
import unicodedata
from functools import lru_cache
from io import BytesIO
from typing import Optional

import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image


# ---------------------------------------------------------------------------
# Helpers genéricos
# ---------------------------------------------------------------------------

def _minmax(scores: np.ndarray) -> np.ndarray:
    mn, mx = scores.min(), scores.max()
    if mx - mn < 1e-9:
        return np.zeros_like(scores)
    return (scores - mn) / (mx - mn)


def _tokenize(text: str) -> list[str]:
    text = unicodedata.normalize("NFD", text.lower())
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    return re.findall(r"\b\w+\b", text)


def _normalize(text: str) -> str:
    """Remove acentos e converte para minúsculas."""
    text = unicodedata.normalize("NFD", text.lower())
    return "".join(c for c in text if unicodedata.category(c) != "Mn")


# ---------------------------------------------------------------------------
# Cache de tradução PT → EN
# Evita um request HTTP externo a cada busca com a mesma query.
# lru_cache é thread-safe para leituras; o pior caso é um miss duplo
# em concorrência alta, o que é aceitável.
# ---------------------------------------------------------------------------

@lru_cache(maxsize=128)
def _translate_cached(text: str) -> str:
    """Traduz PT→EN com cache em memória. Retorna o original em caso de falha."""
    try:
        from deep_translator import GoogleTranslator
        return GoogleTranslator(source="pt", target="en").translate(text)
    except Exception:
        return text


# ---------------------------------------------------------------------------
# Detecção de marca na query
# ---------------------------------------------------------------------------

def _brand_similarity(query_token: str, brand_token: str) -> float:
    if query_token == brand_token:
        return 1.0
    if brand_token in query_token or query_token in brand_token:
        longer  = max(len(query_token), len(brand_token))
        shorter = min(len(query_token), len(brand_token))
        return shorter / longer
    a, b = query_token, brand_token
    if abs(len(a) - len(b)) > max(2, int(0.4 * max(len(a), len(b)))):
        return 0.0
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a):
        curr = [i + 1]
        for j, cb in enumerate(b):
            cost = 0 if ca == cb else 1
            curr.append(min(curr[j] + 1, prev[j + 1] + 1, prev[j] + cost))
        prev = curr
    dist    = prev[len(b)]
    max_len = max(len(a), len(b))
    return 1.0 - dist / max_len


def detect_brand_in_query(
    query: str,
    brands: list[str],
    threshold: float = 0.75,
) -> tuple[Optional[str], str]:
    """
    Procura por nomes de marca na query (fuzzy, sem case/acento).
    Retorna (marca_encontrada | None, query_sem_marca).
    """
    if not brands or not query.strip():
        return None, query

    norm_query   = _normalize(query)
    query_tokens = re.findall(r"\b\w+\b", norm_query)

    best_brand: Optional[str]    = None
    best_score: float            = 0.0
    best_span:  tuple[int, int]  = (0, 0)

    for brand in brands:
        norm_brand   = _normalize(brand)
        brand_tokens = re.findall(r"\b\w+\b", norm_brand)
        if not brand_tokens:
            continue

        n_bt = len(brand_tokens)
        for start in range(len(query_tokens) - n_bt + 1):
            window = query_tokens[start: start + n_bt]
            score  = sum(
                _brand_similarity(wt, bt)
                for wt, bt in zip(window, brand_tokens)
            ) / n_bt

            if score > best_score and score >= threshold:
                best_score = score
                best_brand = brand
                best_span  = (start, start + n_bt)

    if best_brand is None:
        return None, query

    remaining_tokens = query_tokens[: best_span[0]] + query_tokens[best_span[1]:]
    clean_query      = " ".join(remaining_tokens).strip()
    return best_brand, clean_query


# ---------------------------------------------------------------------------
# SearchService
# ---------------------------------------------------------------------------

SIMILARITY_THRESHOLD = 0.65


class SearchService:

    _CONTAINER = "firmato-catalogo"

    def __init__(
        self,
        logger: logging.Logger,
        clip_embeddings,
        text_embeddings,
        metadata,
        clip_model,
        clip_processor,
        clip_device,
        st_model  = None,
        bm25      = None,
        blob_repo = None,
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
        self.blob        = blob_repo

    # ------------------------------------------------------------------
    # Ponto de entrada
    # ------------------------------------------------------------------

    async def search(
        self,
        query: str                    = None,
        image_bytes: bytes            = None,
        top_k: int                    = 200,
        allowed_ids: Optional[set]   = None,
        page: int                     = 1,
        page_size: int                = 20,
        similarity_threshold: float   = SIMILARITY_THRESHOLD,
    ) -> dict:
        """
        Retorna um dict com:
          {
            "total": int,
            "page": int,
            "page_size": int,
            "total_pages": int,
            "items": [ ... ]   ← já enriquecidos com campos do metadata
          }
        """
        if self.clip_emb is None or self.clip_model is None:
            self.logger.warning("[Search] Embeddings ou CLIP não disponíveis.")
            return self._empty_page(page, page_size)

        has_text  = bool(query and query.strip())
        has_image = bool(image_bytes)

        if not has_text and not has_image:
            return self._empty_page(page, page_size)

        n            = len(self.metadata)
        clip_scores  = np.zeros(n)
        st_scores    = np.zeros(n)
        bm25_scores  = np.zeros(n)
        brand_filter: Optional[set[str]] = None

        # ── Fase 1: detecção de marca ──────────────────────────────────
        remaining_query = query or ""
        if has_text:
            brands         = self._collect_brands()
            detected_brand, remaining_query = detect_brand_in_query(query, brands)
            if detected_brand:
                self.logger.info(
                    f"[Search] Marca detectada: '{detected_brand}' "
                    f"| query restante: '{remaining_query}'"
                )
                brand_filter = self._ids_for_brand(detected_brand)
                self.logger.info(
                    f"[Search] Produtos filtrados pela marca: {len(brand_filter)}"
                )

        # ── Fase 2: scoring semântico ──────────────────────────────────
        text_for_scoring  = remaining_query.strip() or None
        effective_has_text = bool(text_for_scoring)

        # CLIP
        if has_image and effective_has_text:
            img_vec = self._encode_image(image_bytes)
            txt_vec = self._encode_text_clip(text_for_scoring)
            if img_vec is not None and txt_vec is not None:
                combined  = (img_vec + txt_vec) / 2
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

        elif effective_has_text:
            txt_vec = self._encode_text_clip(text_for_scoring)
            if txt_vec is not None:
                clip_scores = self.clip_emb @ txt_vec

        # ST
        if effective_has_text and self.text_emb is not None and self.st_model is not None:
            st_vec    = self.st_model.encode(text_for_scoring, normalize_embeddings=True)
            st_scores = self.text_emb @ st_vec

        # BM25
        if effective_has_text and self.bm25 is not None:
            tokens      = _tokenize(text_for_scoring)
            bm25_scores = np.array(self.bm25.get_scores(tokens))

        # ── Pesos ─────────────────────────────────────────────────────
        if has_image and effective_has_text:
            w_clip, w_st, w_bm25 = 0.50, 0.30, 0.20
        elif has_image:
            w_clip, w_st, w_bm25 = 1.0, 0.0, 0.0
        elif effective_has_text:
            w_clip, w_st, w_bm25 = 0.40, 0.35, 0.25
        else:
            w_clip, w_st, w_bm25 = 0.40, 0.35, 0.25

        final = (
            w_clip  * _minmax(clip_scores)
            + w_st  * _minmax(st_scores)
            + w_bm25 * _minmax(bm25_scores)
        )

        # ── Filtragem e threshold ──────────────────────────────────────
        order = np.argsort(final)[::-1]

        effective_ids: Optional[set[str]] = None
        if brand_filter is not None and allowed_ids is not None:
            effective_ids = brand_filter & {str(x) for x in allowed_ids}
        elif brand_filter is not None:
            effective_ids = brand_filter
        elif allowed_ids is not None:
            effective_ids = {str(x) for x in allowed_ids}

        apply_threshold = effective_has_text or has_image

        candidates = []
        for idx in order:
            if len(candidates) >= top_k:
                break
            score = float(final[idx])
            if apply_threshold and score < similarity_threshold:
                break

            meta = self.metadata[idx]
            pid  = str(meta.get("id", ""))

            if effective_ids is not None and pid not in effective_ids:
                continue

            if str(meta.get("status", "ativo")).strip().lower() != "ativo":
                continue

            # Enriquece com campos básicos do metadata já em memória —
            # evita que o frontend precise chamar /products/{id} para cada item.
            candidates.append({
                "id_produto":          pid,
                "score":               score,
                "score_clip":          float(clip_scores[idx]),
                "score_st":            float(st_scores[idx]),
                "score_bm25":          float(bm25_scores[idx]),
                "imagem_url":          f"/api/products/thumbnail/{pid}.jpg",
                # campos de exibição — vindos do metadata em memória
                "nome_produto":        meta.get("text_corpus", "").split(" | ")[0] if meta.get("text_corpus") else "",
                "marca":               meta.get("marca", ""),
                "categoria_principal": meta.get("categoria_principal", ""),
                "faixa_preco":         meta.get("faixa_preco", ""),
            })

        # ── Paginação ─────────────────────────────────────────────────
        total       = len(candidates)
        total_pages = max(1, -(-total // page_size))
        page        = max(1, min(page, total_pages))
        start       = (page - 1) * page_size
        page_items  = candidates[start: start + page_size]

        self.logger.info(
            f"[Search] total_candidates={total} "
            f"page={page}/{total_pages} items={len(page_items)}"
        )

        return {
            "total":       total,
            "page":        page,
            "page_size":   page_size,
            "total_pages": total_pages,
            "items":       page_items,
        }

    # ------------------------------------------------------------------
    # Brand helpers
    # ------------------------------------------------------------------

    def _collect_brands(self) -> list[str]:
        seen:   set[str]  = set()
        brands: list[str] = []
        for entry in self.metadata:
            b = (entry.get("marca") or "").strip()
            if b and b not in seen:
                seen.add(b)
                brands.append(b)
        return brands

    def _ids_for_brand(self, brand: str) -> set[str]:
        norm_brand = _normalize(brand)
        result: set[str] = set()
        for entry in self.metadata:
            if _normalize((entry.get("marca") or "")) == norm_brand:
                pid = str(entry.get("id", ""))
                if pid:
                    result.add(pid)
        return result

    # ------------------------------------------------------------------
    # Encoders
    # ------------------------------------------------------------------

    def _encode_text_clip(self, text: str) -> Optional[np.ndarray]:
        translated = _translate_cached(text)
        if translated != text:
            self.logger.info(f"[Search] CLIP: '{text}' → '{translated}'")
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
            img    = Image.open(BytesIO(image_bytes)).convert("RGB")
            inputs = self.clip_proc(images=img, return_tensors="pt").to(self.clip_device)
            with torch.no_grad():
                emb = self.clip_model.get_image_features(**inputs)
                return F.normalize(emb, p=2, dim=-1).cpu().numpy()[0]
        except Exception as exc:
            self.logger.warning(f"[Search] Falha encode imagem: {exc}")
            return None

    # ------------------------------------------------------------------
    # Util
    # ------------------------------------------------------------------

    @staticmethod
    def _empty_page(page: int, page_size: int) -> dict:
        return {
            "total":       0,
            "page":        page,
            "page_size":   page_size,
            "total_pages": 1,
            "items":       [],
        }