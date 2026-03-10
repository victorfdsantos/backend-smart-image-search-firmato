"""StartupService — inicialização da API: carrega embeddings e reconstrói tmp_images."""

import logging
import shutil
from pathlib import Path
from typing import Optional

import numpy as np
from PIL import Image

from config.settings import settings

_THUMBNAIL_SIZE = (400, 400)


class StartupService:

    def __init__(self, logger: logging.Logger):
        self.logger = logger

    # ------------------------------------------------------------------
    # Ponto de entrada
    # ------------------------------------------------------------------

    def run(self, app_state: dict) -> None:
        """
        Executado uma vez ao subir a API.
        Popula app_state com os recursos carregados.
        """
        self._load_embeddings(app_state)
        self._load_clip_model(app_state)
        self._rebuild_tmp_images()

    # ------------------------------------------------------------------
    # Embeddings
    # ------------------------------------------------------------------

    def _load_embeddings(self, app_state: dict) -> None:
        npy_path = settings.embeddings.npy_path
        metadata_path = settings.embeddings.metadata_path

        app_state["embeddings"] = None
        app_state["embeddings_metadata"] = None

        if not npy_path.exists():
            self.logger.warning(f"[Startup] embeddings.npy não encontrado: {npy_path}")
        else:
            try:
                app_state["embeddings"] = np.load(str(npy_path))
                self.logger.info(
                    f"[Startup] Embeddings carregados: shape={app_state['embeddings'].shape}"
                )
            except Exception as exc:
                self.logger.warning(f"[Startup] Falha ao carregar embeddings: {exc}")

        if not metadata_path.exists():
            self.logger.warning(f"[Startup] metadata_index.json não encontrado: {metadata_path}")
        else:
            try:
                import json
                with open(metadata_path, encoding="utf-8") as f:
                    app_state["embeddings_metadata"] = json.load(f)
                self.logger.info(
                    f"[Startup] Metadata carregado: {len(app_state['embeddings_metadata'])} entradas"
                )
            except Exception as exc:
                self.logger.warning(f"[Startup] Falha ao carregar metadata: {exc}")

    # ------------------------------------------------------------------
    # tmp_images — thumbnails 400x400 mantendo proporção
    # ------------------------------------------------------------------

    def _rebuild_tmp_images(self) -> None:
        tmp_dir = settings.general.tmp_images_path
        nas_base = settings.nas.base_path

        if tmp_dir.exists():
            shutil.rmtree(tmp_dir)
        tmp_dir.mkdir(parents=True)
        self.logger.info(f"[Startup] tmp_images limpo e recriado: {tmp_dir}")

        if not nas_base.exists():
            self.logger.warning(f"[Startup] Diretório NAS não encontrado: {nas_base}. tmp_images ficará vazio.")
            return

        copied = 0
        conflicts: dict[str, Path] = {}

        for img_path in nas_base.rglob("*.jpg"):
            filename = img_path.name
            if filename in conflicts:
                self.logger.warning(
                    f"[Startup] Conflito de nome ignorado: '{filename}' "
                    f"(mantido de {conflicts[filename]}, ignorado de {img_path})"
                )
                continue

            try:
                with Image.open(img_path) as img:
                    img = img.convert("RGB")
                    img.thumbnail(_THUMBNAIL_SIZE, Image.LANCZOS)
                    img.save(tmp_dir / filename, "JPEG", quality=82, optimize=True)

                conflicts[filename] = img_path
                copied += 1
            except Exception as exc:
                self.logger.warning(f"[Startup] Falha ao processar '{img_path}': {exc}")

        self.logger.info(f"[Startup] {copied} thumbnail(s) gerada(s) em tmp_images.")

    # ------------------------------------------------------------------
    # CLIP
    # ------------------------------------------------------------------

    def _load_clip_model(self, app_state: dict) -> None:
        """Carrega o modelo CLIP para encoding de queries em runtime."""
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
            self.logger.warning(f"[Startup] Falha ao carregar CLIP: {exc}. Busca por similaridade indisponível.")
            app_state["clip_model"] = None
            app_state["clip_processor"] = None