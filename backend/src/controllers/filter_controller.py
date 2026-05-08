"""FilterController — endpoint para opções de filtro em cascata."""

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse
from typing import Optional

from services.filter_service import FilterService, FILTER_FIELDS
from utils.logger import setup_logger

router = APIRouter(prefix="/filters", tags=["Filters"])


@router.get(
    "/options",
    summary="Opções de filtro em cascata",
    description=(
        "Retorna os valores disponíveis para cada campo de filtro, "
        "considerando apenas os produtos que satisfazem os filtros já ativos. "
        "Cada campo aceita múltiplos valores separados por vírgula."
    ),
)
async def get_filter_options(
    request: Request,
    marca:               Optional[str] = Query(default=None),
    categoria_principal: Optional[str] = Query(default=None),
    subcategoria:        Optional[str] = Query(default=None),
    faixa_preco:         Optional[str] = Query(default=None),
    ambiente:            Optional[str] = Query(default=None),
    forma:               Optional[str] = Query(default=None),
    material_principal:  Optional[str] = Query(default=None),
) -> JSONResponse:
    logger = setup_logger("filter_options")

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

    # lê o índice já construído do app_state (carregado no startup do Blob)
    service = FilterService(
        logger       = logger,
        filter_index = request.app.state.filter_index,
    )
    options = service.get_options(active_filters)

    return JSONResponse(content={
        "fields":         FILTER_FIELDS,
        "options":        options,
        "active_filters": active_filters,
    })