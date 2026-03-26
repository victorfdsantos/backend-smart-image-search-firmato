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


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger = logging.getLogger("ai.startup")
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    startup = StartupService(logger)
    startup.run(app.state.__dict__)
    yield


app = FastAPI(
    title="Firmato AI Service",
    description="Serviço de indexação e retreinamento incremental de embeddings.",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(training_router)


@app.get("/health", tags=["System"])
async def health_check() -> JSONResponse:
    return JSONResponse(content={"status": "ok", "service": "firmato-ai"})


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=9000, reload=True)