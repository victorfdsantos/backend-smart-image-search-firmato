"""SearchController — busca por texto e/ou imagem via CLIP."""

from fastapi import APIRouter, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import JSONResponse
from typing import Optional

from services.search_service import SearchService
from utils.logger import setup_logger

router = APIRouter(prefix="/search", tags=["Search"])

_ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}


@router.post(
    "",
    summary="Busca por texto e/ou imagem via CLIP",
)
async def search(
    request: Request,
    q: Optional[str] = Query(default=None, description="Texto de busca"),
    top_k: int = Query(default=20, ge=1, le=100),
    image: Optional[UploadFile] = File(default=None),
) -> JSONResponse:
    if not q and not image:
        raise HTTPException(status_code=400, detail="Envie texto ou imagem.")

    image_bytes = None
    if image:
        if image.content_type not in _ALLOWED_IMAGE_TYPES:
            raise HTTPException(status_code=400, detail=f"Formato inválido: {image.content_type}")
        image_bytes = await image.read()

    logger = setup_logger("search")
    service = SearchService(
        logger=logger,
        embeddings=request.app.state.embeddings,
        metadata=request.app.state.embeddings_metadata,
        clip_model=request.app.state.clip_model,
        clip_processor=request.app.state.clip_processor,
        clip_device=request.app.state.clip_device,
    )

    results = service.search(query=q, image_bytes=image_bytes, top_k=top_k)
    return JSONResponse(content={"total": len(results), "items": results})