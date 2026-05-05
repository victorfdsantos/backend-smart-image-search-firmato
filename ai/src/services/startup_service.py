"""StartupService — carrega modelos CLIP, ST e índices na inicialização."""

import json
import logging
import pickle
from pathlib import Path

import numpy as np

from config.settings import settings


class StartupService:

    def __init__(self, logger: logging.Logger):
        self.logger = logger

    def run(self, app_state: dict) -> None:
        """Carrega todos os recursos na inicialização da API."""
        self._load_indices(app_state)
        self._load_clip(app_state)
        self._load_st(app_state)
        self.logger.info("[Startup] AI Service pronto.")

    # ------------------------------------------------------------------
    # Índices (embeddings + metadata + BM25)
    # ------------------------------------------------------------------

    def _load_indices(self, app_state: dict) -> None:
        emb = settings.embeddings

        # Defaults
        app_state["clip_embeddings"] = None
        app_state["text_embeddings"] = None
        app_state["metadata"] = []
        app_state["bm25"] = None
        app_state["bm25_corpus"] = []

        # CLIP embeddings
        if emb.clip_npy.exists():
            try:
                app_state["clip_embeddings"] = np.load(str(emb.clip_npy))
                self.logger.info(
                    f"[Startup] clip_embeddings carregado: shape={app_state['clip_embeddings'].shape}"
                )
            except Exception as e:
                self.logger.warning(f"[Startup] Falha ao carregar clip_embeddings: {e}")
        else:
            self.logger.warning(f"[Startup] clip_embeddings.npy não encontrado em {emb.clip_npy}")

        # Text embeddings
        if emb.text_npy.exists():
            try:
                app_state["text_embeddings"] = np.load(str(emb.text_npy))
                self.logger.info(
                    f"[Startup] text_embeddings carregado: shape={app_state['text_embeddings'].shape}"
                )
            except Exception as e:
                self.logger.warning(f"[Startup] Falha ao carregar text_embeddings: {e}")
        else:
            self.logger.warning(f"[Startup] text_embeddings.npy não encontrado em {emb.text_npy}")

        # Metadata
        if emb.metadata_json.exists():
            try:
                with open(emb.metadata_json, encoding="utf-8") as f:
                    app_state["metadata"] = json.load(f)
                self.logger.info(
                    f"[Startup] metadata carregado: {len(app_state['metadata'])} entradas"
                )
            except Exception as e:
                self.logger.warning(f"[Startup] Falha ao carregar metadata: {e}")
        else:
            self.logger.warning(f"[Startup] metadata_index.json não encontrado em {emb.metadata_json}")

        # BM25
        if emb.bm25_pkl.exists():
            try:
                with open(emb.bm25_pkl, "rb") as f:
                    data = pickle.load(f)
                app_state["bm25"] = data["bm25"]
                app_state["bm25_corpus"] = data["corpus"]
                self.logger.info(
                    f"[Startup] BM25 carregado: {len(app_state['bm25_corpus'])} documentos"
                )
            except Exception as e:
                self.logger.warning(f"[Startup] Falha ao carregar BM25: {e}")
        else:
            self.logger.warning(f"[Startup] bm25_index.pkl não encontrado em {emb.bm25_pkl}")

    # ------------------------------------------------------------------
    # CLIP
    # ------------------------------------------------------------------

    def _load_clip(self, app_state: dict) -> None:
        try:
            import torch
            from transformers import CLIPModel, CLIPProcessor

            model_name = settings.models.clip_model_name
            device_cfg = settings.models.device
            import torch
            device = "cuda" if (device_cfg == "cuda" and torch.cuda.is_available()) else "cpu"

            app_state["clip_model"] = (
                CLIPModel.from_pretrained(model_name).to(device).eval()
            )
            app_state["clip_processor"] = CLIPProcessor.from_pretrained(
                model_name, clean_up_tokenization_spaces=True
            )
            app_state["clip_device"] = device
            self.logger.info(f"[Startup] CLIP carregado: {model_name} | device={device}")

        except Exception as e:
            self.logger.warning(f"[Startup] Falha ao carregar CLIP: {e}")
            app_state["clip_model"] = None
            app_state["clip_processor"] = None
            app_state["clip_device"] = "cpu"

    # ------------------------------------------------------------------
    # Sentence-Transformers
    # ------------------------------------------------------------------

    def _load_st(self, app_state: dict) -> None:
        try:
            from sentence_transformers import SentenceTransformer
            import torch

            model_name = settings.models.st_model_name
            device_cfg = settings.models.device
            device = "cuda" if (device_cfg == "cuda" and torch.cuda.is_available()) else "cpu"

            app_state["st_model"] = SentenceTransformer(model_name, device=device)

            self.logger.info(f"[Startup] ST carregado: {model_name} | device={device}")

        except Exception as e:
            self.logger.warning(f"[Startup] Falha ao carregar ST: {e}")
            app_state["st_model"] = None