"""
AI Service — indexação incremental de embeddings CLIP + ST + BM25.
Endpoint principal: POST /training
"""

import logging
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from config.settings import settings
from controllers.training_controller import router as training_router
from services.startup_service import StartupService

# 🔥 IMPORTANTE
from repositories.blob_storage_repository import BlobStorageRepository
from utils.logger import setup_logger


# --------------------------------------------------
# LIFESPAN (STARTUP)
# --------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger = setup_logger("ai_startup")

    logger.info("[AI] Inicializando dependências...")

    try:
        # -------------------------
        # REPOSITORY (BLOB)
        # -------------------------
        app.state.blob_repo = BlobStorageRepository(
            connection_string=settings.azure.connection_string,
            logger=logger
        )

        # -------------------------
        # STARTUP SERVICE (models, embeddings em memória, etc)
        # -------------------------
        startup = StartupService(logger)
        startup.run(app.state.__dict__)

        logger.info("[AI] Aplicação pronta")

        yield

    except Exception as e:
        logger.error(f"[AI] Erro no startup: {e}", exc_info=True)
        raise

    finally:
        logger.info("[AI] Encerrando aplicação...")


# --------------------------------------------------
# APP
# --------------------------------------------------

app = FastAPI(
    title="Firmato AI Service",
    description="Serviço de indexação e retreinamento incremental de embeddings.",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(training_router)


# --------------------------------------------------
# HEALTH
# --------------------------------------------------

@app.get("/health", tags=["System"])
async def health_check() -> JSONResponse:
    return JSONResponse(content={"status": "ok", "service": "firmato-ai"})


# --------------------------------------------------
# RUN
# --------------------------------------------------

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=9000)