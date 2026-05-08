import json
import logging
import pickle
from io import BytesIO

import numpy as np
from config.settings import settings


class StartupService:

    def __init__(self, logger: logging.Logger, blob_repo):
        self.logger = logger
        self.blob = blob_repo

    # --------------------------------------------------
    # ENTRYPOINT
    # --------------------------------------------------

    async def run(self, app_state: dict) -> None:
        await self._load_embeddings(app_state)
        self._load_clip_model(app_state)
        self._load_st_model(app_state)
        await self._load_bm25(app_state)
        await self._load_filter_index(app_state)

        self.logger.info("[Startup] Service pronto.")

    # --------------------------------------------------
    # EMBEDDINGS (BLOB)
    # --------------------------------------------------

    async def _load_embeddings(self, app_state: dict) -> None:
        container = "firmato-catalogo"

        app_state["clip_embeddings"]    = None
        app_state["text_embeddings"]    = None
        app_state["embeddings_metadata"] = None

        try:
            clip_bytes = await self.blob.download(container, "embeddings/clip_embeddings.npy")
            app_state["clip_embeddings"] = np.load(BytesIO(clip_bytes))
            self.logger.info(f"[Startup] CLIP embeddings: {app_state['clip_embeddings'].shape}")
        except Exception as e:
            self.logger.warning(f"[Startup] Falha CLIP embeddings: {e}")

        try:
            text_bytes = await self.blob.download(container, "embeddings/text_embeddings.npy")
            app_state["text_embeddings"] = np.load(BytesIO(text_bytes))
            self.logger.info(f"[Startup] TEXT embeddings: {app_state['text_embeddings'].shape}")
        except Exception as e:
            self.logger.warning(f"[Startup] Falha TEXT embeddings: {e}")

        try:
            meta_bytes = await self.blob.download(container, "embeddings/metadata.json")
            app_state["embeddings_metadata"] = json.loads(meta_bytes)
            self.logger.info(f"[Startup] Metadata: {len(app_state['embeddings_metadata'])}")
        except Exception as e:
            self.logger.warning(f"[Startup] Falha metadata: {e}")

    # --------------------------------------------------
    # CLIP MODEL
    # --------------------------------------------------

    def _load_clip_model(self, app_state: dict) -> None:
        try:
            import torch
            from transformers import CLIPProcessor, CLIPModel

            model_name = settings.models.clip_model_name
            device = "cuda" if torch.cuda.is_available() else "cpu"

            app_state["clip_model"]     = CLIPModel.from_pretrained(model_name).to(device).eval()
            app_state["clip_processor"] = CLIPProcessor.from_pretrained(model_name, use_fast=True)
            app_state["clip_device"]    = device

            self.logger.info(f"[Startup] CLIP carregado: {model_name} | device={device}")

        except Exception as exc:
            self.logger.warning(f"[Startup] Falha CLIP: {exc}")
            app_state["clip_model"]     = None
            app_state["clip_processor"] = None
            app_state["clip_device"]    = "cpu"

    # --------------------------------------------------
    # ST MODEL
    # --------------------------------------------------

    def _load_st_model(self, app_state: dict) -> None:
        try:
            from sentence_transformers import SentenceTransformer

            model_name = settings.models.st_model_name
            app_state["st_model"] = SentenceTransformer(model_name)

            self.logger.info(f"[Startup] ST carregado: {model_name}")

        except Exception as exc:
            self.logger.warning(f"[Startup] Falha ST: {exc}")
            app_state["st_model"] = None

    # --------------------------------------------------
    # BM25
    # --------------------------------------------------

    async def _load_bm25(self, app_state: dict) -> None:
        container = "firmato-catalogo"

        app_state["bm25"]        = None
        app_state["bm25_corpus"] = None

        try:
            data = await self.blob.download(container, "embeddings/bm25.pkl")
            obj  = pickle.loads(data)

            app_state["bm25"]        = obj["bm25"]
            app_state["bm25_corpus"] = obj["corpus"]

            self.logger.info(f"[Startup] BM25 carregado: {len(obj['corpus'])}")

        except Exception as e:
            self.logger.warning(f"[Startup] Falha BM25: {e}")

    # --------------------------------------------------
    # FILTER INDEX (construído pelo AI após cada treino)
    # --------------------------------------------------

    async def _load_filter_index(self, app_state: dict) -> None:
        """
        Carrega o filter_index.json do Blob.
        Estrutura: { "marca": { "Tok&Stok": ["1","5"], ... }, ... }

        Produzido pelo AI/FilterIndexService após cada treino.
        Se não existir ainda (primeira execução), define como None —
        os filtros retornarão vazios até o primeiro treino.
        """
        app_state["filter_index"] = None

        try:
            data = await self.blob.download("firmato-catalogo", "embeddings/filter_index.json")
            app_state["filter_index"] = json.loads(data)
            total = sum(len(v) for v in app_state["filter_index"].values())
            self.logger.info(f"[Startup] filter_index carregado: {total} valores únicos")
        except Exception as e:
            self.logger.warning(
                f"[Startup] filter_index não encontrado ({e}) "
                "— filtros indisponíveis até o próximo treino."
            )