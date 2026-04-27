"""ProductController — rotas de listagem e detalhe de produtos."""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Response
from fastapi.responses import FileResponse, JSONResponse

from config.settings import settings
from services.filter_service import FilterService
from services.product_service import ProductService
from utils.logger import setup_logger

router = APIRouter(prefix="/products", tags=["Products"])

_DEFAULT_PAGE_SIZE = 12


@router.get("")
async def list_products(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=_DEFAULT_PAGE_SIZE, ge=1, le=100),
    # Filtros opcionais
    marca:               Optional[str] = Query(default=None),
    categoria_principal: Optional[str] = Query(default=None),
    subcategoria:        Optional[str] = Query(default=None),
    faixa_preco:         Optional[str] = Query(default=None),
    ambiente:            Optional[str] = Query(default=None),
    forma:               Optional[str] = Query(default=None),
    material_principal:  Optional[str] = Query(default=None),
) -> JSONResponse:
    logger = setup_logger("product_list")

    # Monta filtros ativos
    raw = {
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
        for k, val in raw.items()
        if val and val.strip()
    }
    logger.info(f"[Filter] active_filters={active_filters}")

    # Se há filtros, usa FilterService para obter IDs permitidos
    allowed_ids = None
    if active_filters:
        filter_service = FilterService(logger)
        allowed_ids = filter_service.get_filtered_ids(active_filters)
        logger.info(f"[Filter] allowed_ids={allowed_ids}")

    result = ProductService(logger).list_active(
        page=page,
        page_size=page_size,
        allowed_ids=allowed_ids,
    )
    return JSONResponse(content=result)


@router.get("/{product_id}")
async def get_product(product_id: int) -> JSONResponse:
    logger = setup_logger("product_detail")
    product = ProductService(logger).get_by_id(product_id)
    if product is None:
        raise HTTPException(status_code=404, detail=f"Produto {product_id} não encontrado.")
    return JSONResponse(content=product)


@router.get("/images/{filename}", tags=["Images"])
async def get_image(filename: str, response: Response) -> FileResponse:
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(status_code=400, detail="Nome de arquivo inválido.")
    image_path = settings.general.tmp_images_path / filename
    if not image_path.exists():
        raise HTTPException(status_code=404, detail=f"Imagem '{filename}' não encontrada.")
    return FileResponse(
        path=image_path,
        media_type="image/jpeg",
        headers={"Cache-Control": "public, max-age=86400", "ETag": str(image_path.stat().st_mtime)},
    )