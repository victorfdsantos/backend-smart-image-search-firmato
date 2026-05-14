"""ProductController — listagem, detalhe e imagens de produtos."""

from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse

from services.filter_service import FilterService
from services.product_service import ProductService
from utils.filters import parse_active_filters
from utils.logger import setup_logger

router = APIRouter(prefix="/products", tags=["Products"])

_DEFAULT_PAGE_SIZE = 12


# ================================================================== LIST

@router.get("")
async def list_products(
    request: Request,
    page:                int           = Query(default=1,                  ge=1),
    page_size:           int           = Query(default=_DEFAULT_PAGE_SIZE, ge=1, le=100),
    marca:               Optional[str] = Query(default=None),
    categoria_principal: Optional[str] = Query(default=None),
    subcategoria:        Optional[str] = Query(default=None),
    faixa_preco:         Optional[str] = Query(default=None),
    ambiente:            Optional[str] = Query(default=None),
    forma:               Optional[str] = Query(default=None),
    material_principal:  Optional[str] = Query(default=None),
) -> JSONResponse:

    logger = setup_logger("product_list")

    active_filters = parse_active_filters(
        marca               = marca,
        categoria_principal = categoria_principal,
        subcategoria        = subcategoria,
        faixa_preco         = faixa_preco,
        ambiente            = ambiente,
        forma               = forma,
        material_principal  = material_principal,
    )

    allowed_ids: Optional[set] = None
    if active_filters:
        filter_service = FilterService(
            logger       = logger,
            filter_index = request.app.state.filter_index,
        )
        allowed_ids = filter_service.get_filtered_ids(active_filters)
        logger.info(f"[Products] Filtros={active_filters} → {len(allowed_ids)} ids")

    service = ProductService(logger=logger, blob_repo=request.app.state.blob_repo)
    result  = await service.list_active(
        page        = page,
        page_size   = page_size,
        allowed_ids = allowed_ids,
    )

    return JSONResponse(content=result)


# ================================================================= DETAIL

@router.get("/{product_id}")
async def get_product(request: Request, product_id: int) -> JSONResponse:
    logger  = setup_logger("product_detail")
    service = ProductService(logger=logger, blob_repo=request.app.state.blob_repo)

    product = await service.get_by_id(product_id)
    if product is None:
        raise HTTPException(status_code=404, detail=f"Produto {product_id} não encontrado.")

    return JSONResponse(content=product)


# ============================================================= THUMBNAIL

@router.get("/thumbnail/{filename}", tags=["Images"])
async def get_thumbnail(request: Request, filename: str) -> Response:
    _validate_filename(filename)
    logger  = setup_logger("product_thumbnail")
    service = ProductService(logger=logger, blob_repo=request.app.state.blob_repo)

    data = await service.get_thumbnail(filename)
    if not data:
        raise HTTPException(status_code=404, detail="Thumbnail não encontrada.")

    return Response(
        content    = data,
        media_type = "image/jpeg",
        headers    = {"Cache-Control": "public, max-age=86400"},
    )


# =============================================================== OUTPUT

@router.get("/images/{filename}", tags=["Images"])
async def get_output_image(request: Request, filename: str) -> Response:
    _validate_filename(filename)
    logger  = setup_logger("product_image")
    service = ProductService(logger=logger, blob_repo=request.app.state.blob_repo)

    data = await service.get_image(filename)
    if not data:
        raise HTTPException(status_code=404, detail="Imagem não encontrada.")

    return Response(
        content    = data,
        media_type = "image/jpeg",
        headers    = {"Cache-Control": "public, max-age=86400"},
    )


# ---------------------------------------------------------------- HELPER

def _validate_filename(filename: str) -> None:
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(status_code=400, detail="Nome de arquivo inválido.")