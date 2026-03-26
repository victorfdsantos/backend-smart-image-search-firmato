"""
IndexService — retreinamento incremental de embeddings.

Fluxo por produto:
  1. Localiza a imagem no NAS (busca recursiva em nas/output/)
  2. Lê o JSON de metadados em nas/data/{id}.json
  3. Remove a entrada antiga dos arrays numpy e do metadata
  4. Gera novos embeddings (CLIP e/ou texto)
  5. Faz append nos arrays e reconstrói o BM25
  6. Persiste tudo em disco
"""

import json
import logging
import pickle
import re
import unicodedata
from pathlib import Path
from typing import Optional

import numpy as np

from config.settings import settings


# ------------------------------------------------------------------ #
# Campos de texto — mesmos usados no indexer.py original
# ------------------------------------------------------------------ #
TEXT_FIELDS = [
    "nome_produto", "marca", "categoria_principal", "subcategoria",
    "ambiente", "forma",
    "material_principal", "material_estrutura", "material_revestimento",
    "faixa_preco", "descricao_tecnica",
]
TECHNICAL_FIELDS = {
    "altura_cm":       "altura",
    "largura_cm":      "largura",
    "profundidade_cm": "profundidade",
}
BLOCKED_FIELDS = {"id_produto", "caminho_imagem", "status"}


def _tokenize(text: str) -> list[str]:
    text = unicodedata.normalize("NFD", text.lower())
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    return re.findall(r"\b\w+\b", text)


def _build_text_corpus(data: dict, pid: str) -> str:
    parts = []
    for field in TEXT_FIELDS:
        val = data.get(field)
        if val and str(val).strip().lower() not in ("none", "nan", ""):
            parts.append(str(val).strip())
    for field, label in TECHNICAL_FIELDS.items():
        val = data.get(field)
        if val and str(val).strip().lower() not in ("none", "nan", ""):
            parts.append(f"{label} {str(val).strip()}")
    return " | ".join(parts) if parts else f"produto {pid}"


def _build_meta_entry(data: dict, pid: str) -> dict:
    text_corpus = _build_text_corpus(data, pid)
    entry = {
        "id":          pid,
        "imagem":      f"{pid}.jpg",
        "json":        f"{pid}.json",
        "text_corpus": text_corpus,
        "nome_produto": "",
        "marca": "",
        "categoria_principal": "",
        "faixa_preco": "",
    }
    for key, val in data.items():
        if key not in BLOCKED_FIELDS and val is not None:
            s = str(val).strip()
            if s.lower() not in ("none", "nan", ""):
                entry[key] = s
    return entry


class IndexService:

    def __init__(self, logger: logging.Logger, app_state: dict):
        self.logger = logger
        self.state = app_state

    # ------------------------------------------------------------------
    # Ponto de entrada: retreinar lista de produtos
    # ------------------------------------------------------------------

    def retrain(
        self,
        image_ids: list[str],
        data_ids: list[str],
    ) -> dict:
        """
        Retreina embeddings para os produtos informados.

        image_ids : produtos com imagem nova/alterada → regenera embedding CLIP
        data_ids  : produtos com JSON novo/alterado   → regenera embedding de texto

        Um mesmo produto pode aparecer nos dois. Os processamentos são
        independentes por tipo de embedding.

        Retorna dict com estatísticas da operação.
        """
        all_ids = sorted(set(image_ids) | set(data_ids))

        stats = {
            "total_requested": len(all_ids),
            "clip_updated": 0,
            "text_updated": 0,
            "bm25_rebuilt": False,
            "errors": [],
        }

        if not all_ids:
            return stats

        # Carrega os arrays atuais (pode estar None se ainda não existirem)
        clip_arr  = self.state.get("clip_embeddings")   # shape (N, D) ou None
        text_arr  = self.state.get("text_embeddings")   # shape (N, D) ou None
        metadata: list[dict] = self.state.get("metadata", [])
        bm25_corpus: list[list[str]] = self.state.get("bm25_corpus", [])

        # Índice rápido: id → posição na lista de metadata
        id_to_pos: dict[str, int] = {m["id"]: i for i, m in enumerate(metadata)}

        # ── Processa cada produto ──────────────────────────────────────
        for pid in all_ids:
            try:
                self._process_product(
                    pid=pid,
                    do_clip=pid in set(image_ids),
                    do_text=pid in set(data_ids),
                    clip_arr=clip_arr,
                    text_arr=text_arr,
                    metadata=metadata,
                    bm25_corpus=bm25_corpus,
                    id_to_pos=id_to_pos,
                    stats=stats,
                )
            except Exception as e:
                msg = f"Erro ao processar produto {pid}: {e}"
                self.logger.error(msg, exc_info=True)
                stats["errors"].append(msg)

        # ── Reconstrói BM25 se houve mudança de texto ─────────────────
        if stats["text_updated"] > 0:
            self._rebuild_bm25(bm25_corpus, stats)

        # ── Persiste tudo em disco ─────────────────────────────────────
        self._persist(clip_arr, text_arr, metadata, bm25_corpus)

        # Atualiza app_state para o próximo request sem restart
        self.state["clip_embeddings"] = clip_arr
        self.state["text_embeddings"] = text_arr
        self.state["metadata"] = metadata
        self.state["bm25_corpus"] = bm25_corpus

        return stats

    # ------------------------------------------------------------------
    # Processa um único produto
    # ------------------------------------------------------------------

    def _process_product(
        self,
        pid: str,
        do_clip: bool,
        do_text: bool,
        clip_arr,
        text_arr,
        metadata: list,
        bm25_corpus: list,
        id_to_pos: dict,
        stats: dict,
    ) -> None:
        self.logger.info(f"[Index] Produto {pid} | clip={do_clip} | text={do_text}")

        # Carrega JSON
        json_data = self._load_json(pid)
        if json_data is None:
            raise FileNotFoundError(f"JSON não encontrado para produto {pid}")

        # Localiza imagem no NAS (busca recursiva)
        image_path: Optional[Path] = None
        if do_clip:
            image_path = self._find_image(pid)
            if image_path is None:
                raise FileNotFoundError(
                    f"Imagem {pid}.jpg não encontrada em {settings.nas.base_path}"
                )

        # Posição atual no array (None = produto novo)
        pos = id_to_pos.get(pid)

        # Monta/atualiza entrada de metadata
        new_meta = _build_meta_entry(json_data, pid)

        if pos is not None:
            # Atualiza metadata in-place
            metadata[pos] = new_meta
        else:
            # Produto novo — será appended
            metadata.append(new_meta)
            new_pos = len(metadata) - 1
            id_to_pos[pid] = new_pos
            pos = new_pos

        # ── Embedding CLIP ──────────────────────────────────────────
        if do_clip and image_path is not None:
            new_clip_vec = self._encode_image(image_path)
            if new_clip_vec is not None:
                clip_arr = self._upsert_row(
                    arr=clip_arr,
                    pos=pos,
                    vec=new_clip_vec,
                    total_expected=len(metadata),
                )
                self.state["clip_embeddings"] = clip_arr
                stats["clip_updated"] += 1
                self.logger.info(f"[Index] CLIP atualizado para {pid}")

        # ── Embedding de texto ─────────────────────────────────────
        if do_text:
            text_corpus_str = new_meta["text_corpus"]
            new_text_vec = self._encode_text(text_corpus_str)
            if new_text_vec is not None:
                text_arr = self._upsert_row(
                    arr=text_arr,
                    pos=pos,
                    vec=new_text_vec,
                    total_expected=len(metadata),
                )
                self.state["text_embeddings"] = text_arr
                stats["text_updated"] += 1
                self.logger.info(f"[Index] Text embedding atualizado para {pid}")

            # Atualiza corpus BM25
            tokenized = _tokenize(text_corpus_str)
            if pos < len(bm25_corpus):
                bm25_corpus[pos] = tokenized
            else:
                # Garante que o corpus tem entradas suficientes
                while len(bm25_corpus) < pos:
                    bm25_corpus.append([])
                bm25_corpus.append(tokenized)

    # ------------------------------------------------------------------
    # Helpers — upsert em array numpy
    # ------------------------------------------------------------------

    def _upsert_row(
        self,
        arr: Optional[np.ndarray],
        pos: int,
        vec: np.ndarray,
        total_expected: int,
    ) -> np.ndarray:
        """
        Substitui a linha `pos` por `vec`.
        Se arr=None ou pos >= len(arr), faz append/pad.
        """
        dim = vec.shape[0]

        if arr is None:
            # Primeiro embedding — inicializa array com zeros
            arr = np.zeros((total_expected, dim), dtype=np.float32)
            arr[pos] = vec
            return arr

        current_rows = arr.shape[0]

        if pos < current_rows:
            arr[pos] = vec
            return arr

        # Produto novo além do tamanho atual → expande com zeros
        extra = pos - current_rows + 1
        pad = np.zeros((extra, dim), dtype=np.float32)
        arr = np.vstack([arr, pad])
        arr[pos] = vec
        return arr

    # ------------------------------------------------------------------
    # Helpers — encoders
    # ------------------------------------------------------------------

    def _encode_image(self, image_path: Path) -> Optional[np.ndarray]:
        clip_model = self.state.get("clip_model")
        clip_proc  = self.state.get("clip_processor")
        device     = self.state.get("clip_device", "cpu")

        if clip_model is None or clip_proc is None:
            self.logger.warning("[Index] CLIP não disponível para encode de imagem.")
            return None

        try:
            import torch
            import torch.nn.functional as F
            from PIL import Image

            img = Image.open(image_path).convert("RGB")
            img.thumbnail((768, 768), Image.LANCZOS)

            inputs = clip_proc(images=img, return_tensors="pt").to(device)
            with torch.no_grad():
                emb = clip_model.get_image_features(**inputs)
                emb = F.normalize(emb, p=2, dim=-1)
            return emb.cpu().numpy()[0]

        except Exception as e:
            self.logger.error(f"[Index] Falha ao encodar imagem {image_path}: {e}", exc_info=True)
            return None

    def _encode_text(self, text: str) -> Optional[np.ndarray]:
        st_model = self.state.get("st_model")

        if st_model is None:
            self.logger.warning("[Index] ST não disponível para encode de texto.")
            return None

        try:
            vec = st_model.encode(text, normalize_embeddings=True)
            return vec.astype(np.float32)
        except Exception as e:
            self.logger.error(f"[Index] Falha ao encodar texto: {e}", exc_info=True)
            return None

    # ------------------------------------------------------------------
    # Helpers — BM25
    # ------------------------------------------------------------------

    def _rebuild_bm25(self, bm25_corpus: list, stats: dict) -> None:
        try:
            from rank_bm25 import BM25Okapi

            bm25 = BM25Okapi(bm25_corpus)
            self.state["bm25"] = bm25
            stats["bm25_rebuilt"] = True
            self.logger.info(
                f"[Index] BM25 reconstruído com {len(bm25_corpus)} documentos."
            )
        except Exception as e:
            msg = f"Falha ao reconstruir BM25: {e}"
            self.logger.error(msg, exc_info=True)
            stats["errors"].append(msg)

    # ------------------------------------------------------------------
    # Helpers — NAS
    # ------------------------------------------------------------------

    def _find_image(self, pid: str) -> Optional[Path]:
        """Busca recursiva por {pid}.jpg dentro de nas/output/."""
        base = settings.nas.base_path
        for candidate in base.rglob(f"{pid}.jpg"):
            if candidate.is_file():
                return candidate
        return None

    def _load_json(self, pid: str) -> Optional[dict]:
        path = settings.nas.data_path / f"{pid}.json"
        if not path.exists():
            return None
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            self.logger.error(f"[Index] Erro ao ler {path}: {e}", exc_info=True)
            return None

    # ------------------------------------------------------------------
    # Persistência
    # ------------------------------------------------------------------

    def _persist(
        self,
        clip_arr: Optional[np.ndarray],
        text_arr: Optional[np.ndarray],
        metadata: list,
        bm25_corpus: list,
    ) -> None:
        emb = settings.embeddings
        emb.output_path.mkdir(parents=True, exist_ok=True)

        if clip_arr is not None:
            np.save(str(emb.clip_npy), clip_arr)
            self.logger.info(f"[Index] clip_embeddings.npy salvo | shape={clip_arr.shape}")

        if text_arr is not None:
            np.save(str(emb.text_npy), text_arr)
            self.logger.info(f"[Index] text_embeddings.npy salvo | shape={text_arr.shape}")

        with open(emb.metadata_json, "w", encoding="utf-8") as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)
        self.logger.info(f"[Index] metadata_index.json salvo | {len(metadata)} entradas")

        bm25_obj = self.state.get("bm25")
        if bm25_obj is not None:
            with open(emb.bm25_pkl, "wb") as f:
                pickle.dump(
                    {"bm25": bm25_obj, "tokenized_corpus": bm25_corpus}, f
                )
            self.logger.info("[Index] bm25_index.pkl salvo")