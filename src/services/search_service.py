"""SearchService — encode de texto/imagem CLIP + busca por similaridade."""

import json
import logging
from io import BytesIO

import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image

from config.settings import settings


class SearchService:

    def __init__(self, logger, embeddings, metadata, clip_model, clip_processor, clip_device):
        self.logger = logger
        self.embeddings = embeddings
        self.metadata = metadata
        self.clip_model = clip_model
        self.clip_processor = clip_processor
        self.clip_device = clip_device
        self.data_dir = settings.general.data_path

    # ------------------------------------------------------------------
    # Ponto de entrada
    # ------------------------------------------------------------------

    def search(self, query: str = None, image_bytes: bytes = None, top_k: int = 20) -> list[dict]:
        """
        query=texto, image_bytes=None → só texto
        query=None, image_bytes=bytes → só imagem
        query=texto, image_bytes=bytes → combinado 50/50
        """
        if self.embeddings is None or self.clip_model is None:
            self.logger.warning("[Search] Embeddings ou CLIP não disponíveis.")
            return []

        text_emb = self._encode_text(query) if query and query.strip() else None
        image_emb = self._encode_image(image_bytes) if image_bytes else None

        if text_emb is None and image_emb is None:
            return []

        # Combinação 50/50 se ambos presentes
        if text_emb is not None and image_emb is not None:
            combined = (text_emb + image_emb) / 2
            query_emb = combined / np.linalg.norm(combined)  # renormaliza
            self.logger.info("[Search] Modo: texto + imagem (50/50)")
        elif text_emb is not None:
            query_emb = text_emb
            self.logger.info(f"[Search] Modo: só texto → '{query}'")
        else:
            query_emb = image_emb
            self.logger.info("[Search] Modo: só imagem")

        return self._similarity_search(query_emb, top_k)

    # ------------------------------------------------------------------
    # Encode
    # ------------------------------------------------------------------

    def _encode_text(self, text: str) -> np.ndarray | None:
        try:
            from deep_translator import GoogleTranslator
            translated = GoogleTranslator(source="pt", target="en").translate(text)
            self.logger.info(f"[Search] Traduzido: '{text}' → '{translated}'")
        except Exception:
            translated = text

        try:
            inputs = self.clip_processor(
                text=[translated], return_tensors="pt", padding=True
            ).to(self.clip_device)
            with torch.no_grad():
                emb = self.clip_model.get_text_features(**inputs)
                return F.normalize(emb, p=2, dim=-1).cpu().numpy()[0]  # (768,)
        except Exception as exc:
            self.logger.warning(f"[Search] Falha ao encodar texto: {exc}")
            return None

    def _encode_image(self, image_bytes: bytes) -> np.ndarray | None:
        try:
            img = Image.open(BytesIO(image_bytes)).convert("RGB")
            inputs = self.clip_processor(images=img, return_tensors="pt").to(self.clip_device)
            with torch.no_grad():
                emb = self.clip_model.get_image_features(**inputs)
                return F.normalize(emb, p=2, dim=-1).cpu().numpy()[0]  # (768,)
        except Exception as exc:
            self.logger.warning(f"[Search] Falha ao encodar imagem: {exc}")
            return None

    # ------------------------------------------------------------------
    # Similaridade
    # ------------------------------------------------------------------

    def _similarity_search(self, query_emb: np.ndarray, top_k: int) -> list[dict]:
        scores = self.embeddings @ query_emb  # (N,)
        top_indices = np.argsort(scores)[::-1]

        results = []
        for idx in top_indices:
            if len(results) >= top_k:
                break
            meta = self.metadata[idx]
            product_id = meta.get("id")
            product_data = self._load_json(product_id)
            if product_data is None:
                continue
            if str(product_data.get("status", "")).strip().lower() != "ativo":
                continue
            results.append({
                "id_produto": product_id,
                "score": float(scores[idx]),
                "imagem_url": f"/static/images/{product_id}.jpg",
            })

        return results

    def _load_json(self, product_id) -> dict | None:
        path = self.data_dir / f"{product_id}.json"
        if not path.exists():
            return None
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None