"""ProductController — rotas de listagem e detalhe de produtos."""

import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse

from config.settings import settings
from services.product_service import ProductService
from utils.logger import setup_logger

router = APIRouter(prefix="/products", tags=["Products"])

_DEFAULT_PAGE_SIZE = 20


def _service(logger: logging.Logger) -> ProductService:
    return ProductService(logger)


@router.get(
    "",
    summary="Galeria de produtos ativos",
    description="Retorna produtos com status=Ativo, paginados. Usado pela galeria do frontend.",
)
async def list_products(
    page: int = Query(default=1, ge=1, description="Número da página"),
    page_size: int = Query(default=_DEFAULT_PAGE_SIZE, ge=1, le=100),
) -> JSONResponse:
    logger = setup_logger("product_list")
    result = _service(logger).list_active(page=page, page_size=page_size)
    return JSONResponse(content=result)


@router.get(
    "/{product_id}",
    summary="Detalhe completo do produto",
    description="Retorna todos os campos do data/{id}.json para exibição no modal/detalhe.",
)
async def get_product(product_id: int) -> JSONResponse:
    logger = setup_logger("product_detail")
    product = _service(logger).get_by_id(product_id)
    if product is None:
        raise HTTPException(status_code=404, detail=f"Produto {product_id} não encontrado.")
    return JSONResponse(content=product)


@router.get(
    "/images/{filename}",
    summary="Servir imagem da galeria",
    description="Serve imagens diretamente do tmp_images/ (flat).",
    tags=["Images"],
)
async def get_image(filename: str) -> FileResponse:
    # Sanitização básica — evita path traversal
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(status_code=400, detail="Nome de arquivo inválido.")

    image_path = settings.general.tmp_images_path / filename
    if not image_path.exists():
        raise HTTPException(status_code=404, detail=f"Imagem '{filename}' não encontrada.")

    return FileResponse(path=image_path, media_type="image/jpeg")