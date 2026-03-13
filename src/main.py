"""Catalog Processor API"""

from contextlib import asynccontextmanager
import logging
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from config.settings import settings
from controllers.catalog_controller import router as catalog_router
from controllers.product_controller import router as product_router
from controllers.search_controller import router as search_router
from services.startup_service import StartupService


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger = logging.getLogger("startup")
    logging.basicConfig(level=logging.INFO)

    # Garante que tmp_images existe antes de montar o StaticFiles
    tmp_path = settings.general.tmp_images_path
    tmp_path.mkdir(parents=True, exist_ok=True)

    startup = StartupService(logger)
    startup.run(app.state.__dict__)

    yield


app = FastAPI(
    title="Catalog Processor API",
    description="API para processamento e cadastro de catálogo de produtos Firmato Móveis.",
    version="1.0.0",
    lifespan=lifespan,
)

app.mount(
    "/static/images",
    StaticFiles(directory=str(settings.general.tmp_images_path)),
    name="images",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(catalog_router)
app.include_router(product_router)
app.include_router(search_router)


@app.get("/health", tags=["System"], summary="Health check")
async def health_check() -> JSONResponse:
    return JSONResponse(content={"status": "ok", "service": "catalog-processor"})


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)