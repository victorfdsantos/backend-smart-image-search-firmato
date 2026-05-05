from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
import time

from services.index_service import IndexService
from repositories.blob_storage_repository import BlobStorageRepository
from utils.logger import setup_logger

router = APIRouter(prefix="/training", tags=["Training"])


@router.post("")
async def train(request: Request, body: dict):

    if not body.get("image_ids") and not body.get("data_ids"):
        raise HTTPException(422, "IDs obrigatórios")

    logger = setup_logger("training")
    t0 = time.time()

    repo = request.app.state.blob_repo
    
    service = IndexService(
        logger=logger,
        app_state=request.app.state.__dict__,
        repo=repo
    )

    stats = service.retrain(
        image_ids=body.get("image_ids", []),
        data_ids=body.get("data_ids", [])
    )

    return JSONResponse({
        "status": "success" if not stats["errors"] else "partial",
        "elapsed": round(time.time() - t0, 2),
        **stats
    })