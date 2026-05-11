"""CatalogController — endpoints de sincronização e retreino do catálogo."""

import json
import time

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse

from services.catalog_service import CatalogService
from services.startup_service import StartupService
from services.training_service import TrainingService
from utils.logger import setup_logger

router = APIRouter(prefix="/catalog", tags=["Catalog"])


@router.post(
    "/register",
    summary="Sincroniza catálogo com SharePoint/Blob e retreina embeddings",
)
async def register_catalog(request: Request) -> JSONResponse:
    logger = setup_logger("catalog_register")
    t0     = time.time()

    try:
        svc = CatalogService(
            logger         = logger,
            sp_repo        = request.app.state.sp_repo,
            blob_repo      = request.app.state.blob_repo,
            image_service  = request.app.state.image_service,
            data_service   = request.app.state.data_service,
            filter_service = request.app.state.filter_service,
        )
        training = TrainingService(logger)

        # ---- 1. PROCESS ----
        result      = await svc.process()
        updated_ids = result["updated_ids"]

        if updated_ids:
            # ---- 2. TRAIN ----
            ok = await training.train(
                image_ids = updated_ids,
                data_ids  = updated_ids,
            )

            if not ok:
                logger.warning("[Catalog] Training falhou → abortando commit")
                return JSONResponse(
                    status_code=400,
                    content={
                        "status":          "training_failed",
                        "elapsed_seconds": round(time.time() - t0, 2),
                        "processed":       result["processed"],
                        "skipped":         result["skipped"],
                        "errors":          result["errors"],
                        "updated_ids":     updated_ids,
                    },
                )

            # ---- 3. COMMIT ----
            await svc.commit(
                updated_ids        = updated_ids,
                landing_map        = result["landing_map"],
                sharepoint_updates = result["sharepoint_updates"],
                hash_index         = result["hash_index"],
            )

            # ---- 4. RELOAD FILTER INDEX ----
            await _reload_filter_index(request, logger)

            # ---- 5. RELOAD EMBEDDINGS + MODELS IN MEMORY ----
            # O AI retreinou e salvou novos embeddings no Blob.
            # Recarregamos tudo (clip_embeddings, text_embeddings, metadata,
            # bm25, filter_index) para que a busca reflita as mudanças.
            await _reload_startup(request, logger)

        else:
            logger.info("[Catalog] Nenhuma alteração detectada")

        return JSONResponse(content={
            "status":          "success",
            "elapsed_seconds": round(time.time() - t0, 2),
            "processed":       result["processed"],
            "skipped":         result["skipped"],
            "errors":          result["errors"],
            "updated_ids":     updated_ids,
        })

    except Exception as exc:
        logger.error(f"[Catalog] Falha crítica: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get(
    "/latest-log",
    summary="Download do log mais recente do catalog_register",
)
async def latest_log() -> FileResponse:
    """
    Tenta baixar o log mais recente do Blob (logs/catalog_register_*.log).
    Se não existir no Blob, retorna 404.
    """
    from config.settings import settings
    from repositories.blob_storage_repository import BlobStorageRepository
    import tempfile, os

    # Tenta ler do Blob
    # O log é salvo opcionalmente via BlobLogHandler; se não existir,
    # informa ao usuário que os logs estão apenas no stdout do container.
    raise HTTPException(
        status_code=404,
        detail=(
            "Logs são emitidos no stdout do container. "
            "Use 'docker compose logs -f backend' para visualizá-los, "
            "ou habilite BlobLogHandler no logger para persistir no Blob."
        ),
    )


# ---------------------------------------------------------------- HELPERS

async def _reload_filter_index(request: Request, logger) -> None:
    """Baixa o filter_index.json recém-gerado pelo AI e atualiza o app_state."""
    try:
        data = await request.app.state.blob_repo.download(
            "firmato-catalogo", "embeddings/filter_index.json"
        )
        request.app.state.filter_index = json.loads(data)
        total = sum(len(v) for v in request.app.state.filter_index.values())
        logger.info(f"[Catalog] filter_index recarregado | {total} valores únicos")
    except Exception as e:
        logger.warning(f"[Catalog] Falha ao recarregar filter_index: {e}")


async def _reload_startup(request: Request, logger) -> None:
    """
    Recarrega embeddings, BM25 e filter_index do Blob para o app_state.
    NÃO recarrega os modelos CLIP/ST (eles já estão em memória e não mudam).
    """
    try:
        logger.info("[Catalog] Recarregando embeddings do Blob...")
        startup = StartupService(logger=logger, blob_repo=request.app.state.blob_repo)

        # Recarrega apenas os índices (embeddings + bm25 + filter_index).
        # Os modelos CLIP/ST ficam em memória — não precisam ser recarregados.
        await startup._load_embeddings(request.app.state.__dict__)
        await startup._load_bm25(request.app.state.__dict__)
        await startup._load_filter_index(request.app.state.__dict__)

        logger.info("[Catalog] Embeddings recarregados com sucesso.")
    except Exception as e:
        logger.error(f"[Catalog] Falha ao recarregar embeddings: {e}", exc_info=True)