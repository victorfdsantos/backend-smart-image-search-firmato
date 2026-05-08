"""CatalogController — endpoints de sincronização e retreino do catálogo."""

import json
import time

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse

from services.catalog_service import CatalogService
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

        # ---- 2. TRAIN ----
        if updated_ids:
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
            # O AI reconstruiu o filter_index.json no Blob durante o treino.
            # Recarregamos em memória para que os filtros reflitam os dados novos.
            await _reload_filter_index(request, logger)

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
    from config.settings import settings

    logs_dir = settings.general.logs_path
    logs     = sorted(
        logs_dir.glob("catalog_register_*.log"),
        key     = lambda p: p.stat().st_mtime,
        reverse = True,
    )

    if not logs:
        raise HTTPException(status_code=404, detail="Nenhum log encontrado.")

    latest = logs[0]
    return FileResponse(
        path        = latest,
        media_type  = "text/plain",
        filename    = latest.name,
        headers     = {"Content-Disposition": f"attachment; filename={latest.name}"},
    )


# ---------------------------------------------------------------- HELPER

async def _reload_filter_index(request: Request, logger) -> None:
    """
    Baixa o filter_index.json recém-gerado pelo AI e atualiza o app_state.
    Assim os filtros ficam atualizados sem precisar reiniciar o backend.
    """
    try:
        data = await request.app.state.blob_repo.download(
            "firmato-catalogo", "embeddings/filter_index.json"
        )
        request.app.state.filter_index = json.loads(data)
        total = sum(len(v) for v in request.app.state.filter_index.values())
        logger.info(f"[Catalog] filter_index recarregado | {total} valores únicos")
    except Exception as e:
        logger.warning(f"[Catalog] Falha ao recarregar filter_index: {e}")