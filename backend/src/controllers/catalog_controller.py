"""CatalogController — endpoints de sincronização e retreino do catálogo."""

import time

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

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

            # ---- 4. RELOAD EMBEDDINGS + FILTER INDEX IN MEMORY ----
            # O AI retreinou e salvou novos embeddings no Blob.
            # reload_indices() recarrega clip_embeddings, text_embeddings,
            # metadata, bm25 e filter_index em uma única passagem.
            startup = StartupService(logger=logger, blob_repo=request.app.state.blob_repo)
            await startup.reload_indices(request.app.state.__dict__)

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