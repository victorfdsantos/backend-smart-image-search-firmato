"""TrainingController — endpoint /training para retreinamento incremental."""

import logging
import time

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from models.training_models import TrainingRequest, TrainingResponse
from services.index_service import IndexService
from utils.logger import setup_logger

router = APIRouter(prefix="/training", tags=["Training"])


@router.post(
    "",
    response_model=TrainingResponse,
    summary="Retreinamento incremental de embeddings",
    description="""
Recebe listas de IDs de produtos cujos dados foram alterados e regenera
apenas os embeddings afetados, sem reprocessar o catálogo inteiro.

**image_ids** → produtos com imagem nova/trocada → regenera embedding CLIP  
**data_ids**  → produtos com JSON alterado → regenera embedding de texto (ST) + BM25  

Um mesmo ID pode aparecer nos dois grupos.
""",
)
async def train(request: Request, body: TrainingRequest) -> JSONResponse:
    if not body.image_ids and not body.data_ids:
        raise HTTPException(
            status_code=422,
            detail="Informe ao menos um ID em image_ids ou data_ids.",
        )

    logger = setup_logger("training")
    logger.info(
        f"[Training] Requisição recebida | "
        f"image_ids={body.image_ids} | data_ids={body.data_ids}"
    )

    # Verifica se os modelos estão carregados
    if request.app.state.clip_model is None:
        logger.warning("[Training] Modelo CLIP não disponível — embeddings visuais não serão gerados.")

    if request.app.state.st_model is None:
        logger.warning("[Training] Modelo ST não disponível — embeddings de texto não serão gerados.")

    t0 = time.time()

    service = IndexService(logger=logger, app_state=request.app.state.__dict__)

    try:
        stats = service.retrain(
            image_ids=body.image_ids,
            data_ids=body.data_ids,
        )
    except Exception as exc:
        logger.error(f"[Training] Falha crítica: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))

    elapsed = round(time.time() - t0, 2)
    logger.info(f"[Training] Concluído em {elapsed}s | stats={stats}")

    status = "success" if not stats["errors"] else "partial"

    return JSONResponse(
        content={
            "status": status,
            "elapsed_seconds": elapsed,
            **stats,
        }
    )