"""
StartupService do AI Service.

Única responsabilidade: carregar os modelos CLIP e ST na memória.
Índices (embeddings, metadata, bm25) são gerenciados pelo IndexService
a cada chamada de /training — não precisam ser carregados no startup.
"""

import logging

from services.filter_index_service import FilterIndexService


class StartupService:

    def __init__(self, logger: logging.Logger):
        self.logger = logger

    def run(self, app_state: dict) -> None:
        """
        Levanta RuntimeError se qualquer modelo não carregar —
        a API não deve subir com modelos None.
        """
        self._load_clip(app_state)
        self._load_st(app_state)

        missing = [
            name for name in ("clip_model", "clip_processor", "st_model")
            if app_state.get(name) is None
        ]
        if missing:
            raise RuntimeError(
                f"Modelos não carregaram: {', '.join(missing)}. "
                "Verifique conectividade com Hugging Face e espaço em disco."
            )

        self._load_filter_index(app_state)
        self.logger.info("[Startup] AI Service pronto — CLIP, ST e filter_index carregados.")

    def _load_filter_index(self, app_state: dict) -> None:
        """
        Tenta carregar o índice de filtros já construído do Blob.
        Se não existir (primeira execução) define como None —
        será populado após o primeiro treino.
        """
        repo = app_state.get("blob_repo")
        if repo is None:
            self.logger.warning("[Startup] blob_repo não disponível no app_state — filter_index não carregado.")
            app_state["filter_index"] = None
            return

        svc = FilterIndexService(logger=self.logger, repo=repo)
        app_state["filter_index"] = svc.load()

    # ------------------------------------------------------------------
    # CLIP
    # ------------------------------------------------------------------

    def _load_clip(self, app_state: dict) -> None:
        app_state.update({"clip_model": None, "clip_processor": None, "clip_device": "cpu"})

        try:
            import torch
            from transformers import CLIPModel, CLIPProcessor
            from config.settings import settings

            model_name = settings.models.clip_model_name
            device     = "cuda" if (settings.models.device == "cuda" and torch.cuda.is_available()) else "cpu"

            self.logger.info(f"[Startup] Carregando CLIP: {model_name} | device={device}")

            model     = CLIPModel.from_pretrained(model_name).to(device).eval()
            processor = CLIPProcessor.from_pretrained(model_name, clean_up_tokenization_spaces=True)

            # smoke test
            from PIL import Image as PILImage
            dummy = processor(images=PILImage.new("RGB", (224, 224)), return_tensors="pt").to(device)
            with torch.no_grad():
                model.get_image_features(**dummy)

            app_state["clip_model"]     = model
            app_state["clip_processor"] = processor
            app_state["clip_device"]    = device

            self.logger.info(f"[Startup] CLIP OK | device={device}")

        except Exception as e:
            self.logger.error(f"[Startup] FALHA ao carregar CLIP: {e}", exc_info=True)

    # ------------------------------------------------------------------
    # SENTENCE-TRANSFORMERS
    # ------------------------------------------------------------------

    def _load_st(self, app_state: dict) -> None:
        app_state["st_model"] = None

        try:
            from sentence_transformers import SentenceTransformer
            from config.settings import settings
            import torch

            model_name = settings.models.st_model_name
            device     = "cuda" if (settings.models.device == "cuda" and torch.cuda.is_available()) else "cpu"

            self.logger.info(f"[Startup] Carregando ST: {model_name} | device={device}")

            model = SentenceTransformer(model_name, device=device)
            model.encode("teste", normalize_embeddings=True)  # smoke test

            app_state["st_model"] = model
            self.logger.info(f"[Startup] ST OK | model={model_name}")

        except Exception as e:
            self.logger.error(f"[Startup] FALHA ao carregar ST: {e}", exc_info=True)