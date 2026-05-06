"""
TrainingController — endpoint POST /training

Recebe image_ids e/ou data_ids e delega ao IndexService para
retreinamento incremental (apenas os produtos informados).
"""

import time

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from models.training_models import TrainingRequest
from services.index_service import IndexService
from utils.logger import setup_logger

router = APIRouter(prefix="/training", tags=["Training"])


@router.post("")
async def train(request: Request, body: TrainingRequest) -> JSONResponse:
    """
    Retreina embeddings apenas para os IDs informados.

    - **image_ids**: produtos com imagem nova ou alterada (regenera CLIP)
    - **data_ids**: produtos com metadados novos ou alterados (regenera ST + BM25)

    Um produto pode aparecer nos dois grupos simultaneamente.
    """
    if not body.image_ids and not body.data_ids:
        raise HTTPException(
            status_code=422,
            detail="Informe ao menos um ID em image_ids ou data_ids.",
        )

    logger = setup_logger("training")
    t0     = time.time()

    logger.info(
        f"[Training] Requisição recebida | "
        f"image_ids={len(body.image_ids)} | data_ids={len(body.data_ids)}"
    )

    try:
        service = IndexService(
            logger    = logger,
            app_state = request.app.state.__dict__,
            repo      = request.app.state.blob_repo,
        )

        stats = service.retrain(
            image_ids = body.image_ids,
            data_ids  = body.data_ids,
        )

        status  = "success" if not stats["errors"] else "partial"
        elapsed = round(time.time() - t0, 2)

        logger.info(f"[Training] Concluído | status={status} | elapsed={elapsed}s")

        return JSONResponse(
            status_code=200,
            content={
                "status":  status,
                "elapsed": elapsed,
                **stats,
            },
        )

    except Exception as exc:
        elapsed = round(time.time() - t0, 2)
        logger.error(f"[Training] Falha crítica: {exc}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={"message": str(exc), "elapsed": elapsed},
        )