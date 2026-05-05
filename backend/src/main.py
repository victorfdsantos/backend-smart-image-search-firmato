"""Catalog Processor API"""

from contextlib import asynccontextmanager
import logging
import os

import uvicorn
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from config.settings import settings

# Controllers
from controllers.catalog_controller import router as catalog_router
from controllers.product_controller import router as product_router
from controllers.search_controller import router as search_router
from controllers.filter_controller import router as filter_router

# Services
from services.startup_service import StartupService
from services.image_service import ImageProcessingService
from services.product_data_service import ProductDataService
from services.filter_service import FilterService

# Repositories
from repositories.blob_storage_repository import BlobStorageRepository
from repositories.sharepoint_repository import SharePointRepository

from utils.logger import setup_logger


# --------------------------------------------------
# LIFESPAN (STARTUP)
# --------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger = setup_logger("startup")

    logger.info("[Startup] Inicializando dependências...")

    try:
        # -------------------------
        # VALIDA CONFIG
        # -------------------------
        if not hasattr(settings, "azure") or not settings.azure.connection_string:
            raise ValueError("Azure connection_string não configurada")

        # -------------------------
        # REPOSITORIES
        # -------------------------
        logger.info("[Startup] Criando BlobRepository...")
        app.state.blob_repo = BlobStorageRepository(
            connection_string=settings.azure.connection_string,
            logger=logger
        )

        logger.info("[Startup] Criando SharePointRepository...")
        app.state.sp_repo = SharePointRepository(
            logger
        )

        # -------------------------
        # SERVICES
        # -------------------------
        logger.info("[Startup] Criando services...")
        app.state.image_service = ImageProcessingService(logger)
        app.state.data_service = ProductDataService(logger)
        app.state.filter_service = FilterService(logger)

        # -------------------------
        # STARTUP SERVICE
        # -------------------------
        logger.info("[Startup] Rodando StartupService...")
        startup = StartupService(
            logger=logger,
            blob_repo=app.state.blob_repo
        )
        startup.run(app.state.__dict__)

        logger.info("[Startup] Aplicação pronta ✔")

    except Exception as e:
        logger.error(f"[Startup] ERRO REAL: {e}", exc_info=True)
        raise  # ESSENCIAL → mostra erro no uvicorn

    yield

    logger.info("[Shutdown] Encerrando aplicação...")


# --------------------------------------------------
# APP
# --------------------------------------------------

app = FastAPI(
    title="Catalog Processor API",
    description="API para processamento e cadastro de catálogo de produtos Firmato Móveis.",
    version="1.0.0",
    lifespan=lifespan,
)

# --------------------------------------------------
# STATIC
# --------------------------------------------------

app.mount(
    "/static/images",
    StaticFiles(directory=str(settings.general.tmp_images_path)),
    name="images",
)

# --------------------------------------------------
# CORS
# --------------------------------------------------

origins = os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --------------------------------------------------
# ROUTERS
# --------------------------------------------------

app.include_router(catalog_router)
app.include_router(product_router)
app.include_router(search_router)
app.include_router(filter_router)

# --------------------------------------------------
# HEALTH
# --------------------------------------------------

@app.get("/health", tags=["System"])
async def health_check() -> JSONResponse:
    return JSONResponse(content={"status": "ok", "service": "catalog-processor"})


# --------------------------------------------------
# RUN
# --------------------------------------------------

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000)