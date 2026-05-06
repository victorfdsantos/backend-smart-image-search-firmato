"""
AI Service — retreinamento incremental de embeddings CLIP + ST + BM25.
Endpoint: POST /training
"""

from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from config.settings import settings
from controllers.training_controller import router as training_router
from repositories.blob_storage_repository import BlobStorageRepository
from services.startup_service import StartupService
from utils.logger import setup_logger


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger = setup_logger("ai_startup")
    logger.info("[AI] Inicializando...")

    try:
        app.state.blob_repo = BlobStorageRepository(
            connection_string=settings.azure.connection_string,
            logger=logger,
        )

        # só carrega modelos — índices são gerenciados pelo IndexService
        StartupService(logger).run(app.state.__dict__)

        logger.info("[AI] Pronto.")
        yield

    except Exception as e:
        logger.error(f"[AI] Erro no startup: {e}", exc_info=True)
        raise

    finally:
        logger.info("[AI] Encerrando...")


app = FastAPI(
    title="Firmato AI Service",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(training_router)


@app.get("/health", tags=["System"])
async def health_check() -> JSONResponse:
    return JSONResponse({"status": "ok", "service": "firmato-ai"})


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=9000)