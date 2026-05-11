"""SearchController — busca por texto e/ou imagem via CLIP + ST + BM25 com filtros."""

from typing import Optional

from fastapi import APIRouter, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import JSONResponse

from services.filter_service import FilterService
from services.search_service import SearchService
from utils.logger import setup_logger

router = APIRouter(prefix="/search", tags=["Search"])

_ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}

@router.post("")
async def search(
    request: Request,
    q:                   Optional[str]        = Query(default=None),
    top_k:               int                  = Query(default=20, ge=1, le=100),
    marca:               Optional[str]        = Query(default=None),
    categoria_principal: Optional[str]        = Query(default=None),
    subcategoria:        Optional[str]        = Query(default=None),
    faixa_preco:         Optional[str]        = Query(default=None),
    ambiente:            Optional[str]        = Query(default=None),
    forma:               Optional[str]        = Query(default=None),
    material_principal:  Optional[str]        = Query(default=None),
    image:               Optional[UploadFile] = File(default=None),
) -> JSONResponse:

    if not q and not image:
        raise HTTPException(status_code=400, detail="Envie texto ou imagem.")

    image_bytes = None
    if image:
        if image.content_type not in _ALLOWED_IMAGE_TYPES:
            raise HTTPException(status_code=400, detail=f"Formato inválido: {image.content_type}")
        image_bytes = await image.read()

    raw_filters = {
        "marca":               marca,
        "categoria_principal": categoria_principal,
        "subcategoria":        subcategoria,
        "faixa_preco":         faixa_preco,
        "ambiente":            ambiente,
        "forma":               forma,
        "material_principal":  material_principal,
    }
    active_filters = {
        k: [v.strip() for v in val.split(",") if v.strip()]
        for k, val in raw_filters.items()
        if val and val.strip()
    }

    logger = setup_logger("search")

    allowed_ids = None
    if active_filters:
        filter_service = FilterService(
            logger       = logger,
            filter_index = request.app.state.filter_index,
        )
        allowed_ids = filter_service.filter_product_ids(active_filters)
        logger.info(
            f"[Search] Filtros: {active_filters} → "
            f"{len(allowed_ids) if allowed_ids else 0} IDs"
        )

    service = SearchService(
        logger          = logger,
        clip_embeddings = request.app.state.clip_embeddings,
        text_embeddings = request.app.state.text_embeddings,
        metadata        = request.app.state.embeddings_metadata,
        clip_model      = request.app.state.clip_model,
        clip_processor  = request.app.state.clip_processor,
        clip_device     = request.app.state.clip_device,
        st_model        = request.app.state.st_model,
        bm25            = request.app.state.bm25,
        blob_repo       = request.app.state.blob_repo,   # ← passa o repo
    )

    results = await service.search(        
        query       = q,
        image_bytes = image_bytes,
        top_k       = top_k,
        allowed_ids = allowed_ids,
    )

    return JSONResponse(content={"total": len(results), "items": results})