import json
import re
import unicodedata
from io import BytesIO

import numpy as np

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


class IndexService:

    def __init__(self, logger, app_state, repo):
        self.logger = logger
        self.state = app_state
        self.repo = repo

    # --------------------------------------------------
    # ENTRYPOINT
    # --------------------------------------------------

    def retrain(self, image_ids, data_ids):

        all_ids = sorted(set(image_ids) | set(data_ids))

        self.logger.info(
            f"[Index] Retrain iniciado | total_ids={len(all_ids)} "
            f"| image_ids={len(image_ids)} | data_ids={len(data_ids)}"
        )

        stats = {
            "total_requested": len(all_ids),
            "clip_updated": 0,
            "text_updated": 0,
            "bm25_rebuilt": False,
            "errors": [],
        }

        clip_arr = self.state.get("clip_embeddings")
        text_arr = self.state.get("text_embeddings")
        metadata = self.state.get("metadata", [])
        bm25_corpus = self.state.get("bm25_corpus", [])

        self.logger.debug(
            f"[Index] Estado inicial | clip={None if clip_arr is None else clip_arr.shape} "
            f"| text={None if text_arr is None else text_arr.shape} "
            f"| metadata={len(metadata)}"
        )

        id_to_pos = {m["id"]: i for i, m in enumerate(metadata)}

        for pid in all_ids:
            try:
                clip_arr, text_arr = self._process(
                    pid, image_ids, data_ids,
                    clip_arr, text_arr,
                    metadata, bm25_corpus,
                    id_to_pos, stats
                )
            except Exception as e:
                self.logger.error(f"[Index] Erro no PID {pid}: {e}", exc_info=True)
                stats["errors"].append(f"{pid}: {str(e)}")

        # BM25
        if stats["text_updated"]:
            self.logger.info("[Index] Rebuild BM25 iniciado")
            self._rebuild_bm25(bm25_corpus, stats)

        # Persistência
        self.logger.info("[Index] Persistindo embeddings...")
        self._persist(clip_arr, text_arr, metadata, bm25_corpus)

        # Atualiza memória
        self.state.update({
            "clip_embeddings": clip_arr,
            "text_embeddings": text_arr,
            "metadata": metadata,
            "bm25_corpus": bm25_corpus,
        })

        self.logger.info(f"[Index] Finalizado | stats={stats}")

        return stats

    # --------------------------------------------------
    # PROCESS
    # --------------------------------------------------

    def _process(self, pid, image_ids, data_ids,
                clip_arr, text_arr,
                metadata, bm25_corpus,
                id_to_pos, stats):

        self.logger.debug(f"[Index] Processando PID {pid}")

        data = self.repo.get_json(pid)
        if not data:
            raise Exception("JSON não encontrado")

        pos = id_to_pos.get(pid)
        is_new = pos is None

        text = _build_text(data, pid)

        meta = {
            "id": pid,
            "imagem": f"{pid}.jpg",
            "json": f"{pid}.json",
            "text_corpus": text,
        }

        # metadata
        if is_new:
            metadata.append(meta)
            pos = len(metadata) - 1
            id_to_pos[pid] = pos
        else:
            metadata[pos] = meta

        # IMAGE
        if pid in image_ids:
            img = self.repo.get_image(pid)

            if not img:
                self.logger.warning(f"[Index] Imagem não encontrada | pid={pid}")
            else:
                vec = self._encode_image(img)
                clip_arr = self._upsert(clip_arr, pos, vec, len(metadata))
                stats["clip_updated"] += 1

        # TEXT
        if pid in data_ids:
            vec = self._encode_text(text)
            text_arr = self._upsert(text_arr, pos, vec, len(metadata))
            stats["text_updated"] += 1

            tokens = _tokenize(text)

            if pos < len(bm25_corpus):
                bm25_corpus[pos] = tokens
            else:
                bm25_corpus.append(tokens)

        return clip_arr, text_arr

    # --------------------------------------------------
    # UPSERT
    # --------------------------------------------------

    def _upsert(self, arr, pos, vec, total):
        if arr is None:
            self.logger.debug("[Index] Inicializando array embeddings")
            arr = np.zeros((total, len(vec)), dtype=np.float32)

        if pos >= len(arr):
            self.logger.debug(f"[Index] Expandindo array | pos={pos}")
            pad = np.zeros((pos - len(arr) + 1, len(vec)), dtype=np.float32)
            arr = np.vstack([arr, pad])

        arr[pos] = vec
        return arr

    # --------------------------------------------------
    # ENCODE
    # --------------------------------------------------

    def _encode_image(self, image_bytes):
        import torch
        import torch.nn.functional as F
        from PIL import Image

        img = Image.open(BytesIO(image_bytes)).convert("RGB")

        proc = self.state["clip_processor"]
        model = self.state["clip_model"]
        device = self.state["clip_device"]

        inputs = proc(images=img, return_tensors="pt").to(device)

        with torch.no_grad():
            emb = model.get_image_features(**inputs)
            emb = F.normalize(emb, dim=-1)

        return emb.cpu().numpy()[0]

    def _encode_text(self, text):
        model = self.state["st_model"]
        return model.encode(text, normalize_embeddings=True)

    # --------------------------------------------------
    # BM25
    # --------------------------------------------------

    def _rebuild_bm25(self, corpus, stats):
        from rank_bm25 import BM25Okapi

        self.logger.debug(f"[Index] BM25 corpus size={len(corpus)}")

        self.state["bm25"] = BM25Okapi(corpus)
        stats["bm25_rebuilt"] = True

        self.logger.info("[Index] BM25 rebuild concluído")

    # --------------------------------------------------
    # PERSIST
    # --------------------------------------------------

    def _persist(self, clip, text, meta, corpus):
        import pickle

        try:
            if clip is not None:
                buf = BytesIO()
                np.save(buf, clip)
                self.repo.save_clip_embeddings(buf.getvalue())
                self.logger.info("[Index] CLIP salvo")

            if text is not None:
                buf = BytesIO()
                np.save(buf, text)
                self.repo.save_text_embeddings(buf.getvalue())
                self.logger.info("[Index] TEXT salvo")

            self.repo.save_metadata(json.dumps(meta).encode())
            self.logger.info(f"[Index] Metadata salvo | total={len(meta)}")

            bm25 = self.state.get("bm25")
            if bm25:
                self.repo.save_bm25(
                    pickle.dumps({"bm25": bm25, "corpus": corpus})
                )
                self.logger.info("[Index] BM25 salvo")

        except Exception as e:
            self.logger.error(f"[Index] Erro ao persistir: {e}", exc_info=True)
            raise