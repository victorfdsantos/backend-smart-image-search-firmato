"""StartupService — inicialização da API."""

import json
import logging
import pickle
import shutil
from pathlib import Path
import numpy as np
from PIL import Image
from config.settings import settings

class StartupService:

    def __init__(self, logger: logging.Logger):
        self.logger = logger

    def run(self, app_state: dict) -> None:
        self._load_embeddings(app_state)
        self._load_clip_model(app_state)
        self._load_st_model(app_state)
        self._load_bm25(app_state)
        self._rebuild_tmp_images()

    # ------------------------------------------------------------------
    # Embeddings
    # ------------------------------------------------------------------

    def _load_embeddings(self, app_state: dict) -> None:
        emb_dir = settings.embeddings.npy_path.parent

        app_state["clip_embeddings"]     = None
        app_state["text_embeddings"]     = None
        app_state["embeddings_metadata"] = None

        clip_path = emb_dir / "clip_embeddings.npy"
        if clip_path.exists():
            try:
                app_state["clip_embeddings"] = np.load(str(clip_path))
                self.logger.info(f"[Startup] CLIP embeddings: shape={app_state['clip_embeddings'].shape}")
            except Exception as exc:
                self.logger.warning(f"[Startup] Falha clip_embeddings: {exc}")
        else:
            self.logger.warning(f"[Startup] clip_embeddings.npy não encontrado: {clip_path}")

        text_path = emb_dir / "text_embeddings.npy"
        if text_path.exists():
            try:
                app_state["text_embeddings"] = np.load(str(text_path))
                self.logger.info(f"[Startup] Text embeddings: shape={app_state['text_embeddings'].shape}")
            except Exception as exc:
                self.logger.warning(f"[Startup] Falha text_embeddings: {exc}")
        else:
            self.logger.warning(f"[Startup] text_embeddings.npy não encontrado: {text_path}")

        meta_path = settings.embeddings.metadata_path
        if meta_path.exists():
            try:
                with open(meta_path, encoding="utf-8") as f:
                    app_state["embeddings_metadata"] = json.load(f)
                self.logger.info(f"[Startup] Metadata: {len(app_state['embeddings_metadata'])} entradas")
            except Exception as exc:
                self.logger.warning(f"[Startup] Falha metadata: {exc}")
        else:
            self.logger.warning(f"[Startup] metadata_index.json não encontrado: {meta_path}")

    # ------------------------------------------------------------------
    # CLIP
    # ------------------------------------------------------------------

    def _load_clip_model(self, app_state: dict) -> None:
        try:
            import torch
            from transformers import CLIPProcessor, CLIPModel

            model_name = "openai/clip-vit-large-patch14"
            device = "cuda" if torch.cuda.is_available() else "cpu"

            app_state["clip_model"] = CLIPModel.from_pretrained(model_name).to(device).eval()
            app_state["clip_processor"] = CLIPProcessor.from_pretrained(
                model_name, clean_up_tokenization_spaces=True
            )
            app_state["clip_device"] = device
            self.logger.info(f"[Startup] CLIP carregado: {model_name} | device={device}")
        except Exception as exc:
            self.logger.warning(f"[Startup] Falha CLIP: {exc}")
            app_state["clip_model"]     = None
            app_state["clip_processor"] = None
            app_state["clip_device"]    = "cpu"

    # ------------------------------------------------------------------
    # Sentence-Transformers
    # ------------------------------------------------------------------

    def _load_st_model(self, app_state: dict) -> None:
        try:
            from sentence_transformers import SentenceTransformer
            model_name = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
            app_state["st_model"] = SentenceTransformer(model_name)
            self.logger.info(f"[Startup] ST carregado: {model_name}")
        except Exception as exc:
            self.logger.warning(f"[Startup] Falha ST: {exc}")
            app_state["st_model"] = None

    # ------------------------------------------------------------------
    # BM25
    # ------------------------------------------------------------------

    def _load_bm25(self, app_state: dict) -> None:
        app_state["bm25"] = None
        bm25_path = settings.embeddings.npy_path.parent / "bm25_index.pkl"
        if not bm25_path.exists():
            self.logger.warning(f"[Startup] bm25_index.pkl não encontrado: {bm25_path}")
            return
        try:
            with open(bm25_path, "rb") as f:
                data = pickle.load(f)
            app_state["bm25"] = data["bm25"]
            self.logger.info(f"[Startup] BM25 carregado: {len(data['tokenized_corpus'])} documentos")
        except Exception as exc:
            self.logger.warning(f"[Startup] Falha BM25: {exc}")

    # ------------------------------------------------------------------
    # tmp_images
    # ------------------------------------------------------------------

    def _rebuild_tmp_images(self) -> None:
        tmp_dir = settings.general.tmp_images_path
        thumbnail_dir = settings.nas.thumbnail

        # limpa diretório temporário
        tmp_dir.mkdir(parents=True, exist_ok=True)
        for item in tmp_dir.iterdir():
            try:
                if item.is_file():
                    item.unlink()
                elif item.is_dir():
                    shutil.rmtree(item)
            except Exception as exc:
                self.logger.warning(f"[Startup] Não foi possível remover '{item}': {exc}")

        self.logger.info(f"[Startup] tmp_images limpo: {tmp_dir}")

        # valida existência da pasta de thumbnails
        if not thumbnail_dir.exists():
            self.logger.warning(f"[Startup] Pasta de thumbnails não encontrada: {thumbnail_dir}")
            return

        copied = 0
        conflicts: dict[str, Path] = {}

        for img_path in thumbnail_dir.rglob("*.jpg"):
            filename = img_path.name

            if filename in conflicts:
                self.logger.warning(f"[Startup] Conflito ignorado: '{filename}'")
                continue
            try:
                shutil.copy2(img_path, tmp_dir / filename)
                conflicts[filename] = img_path
                copied += 1
            except Exception as exc:
                self.logger.warning(f"[Startup] Falha ao copiar '{img_path}': {exc}")

        self.logger.info(f"[Startup] {copied} thumbnail(s) copiadas.")