# src/controllers/catalog_controller.py
import shutil
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from services.catalog_service import CatalogService
from utils.logger import setup_logger

_TEMP_UPLOAD_DIR = Path("./tmp_uploads")
_TEMP_UPLOAD_DIR.mkdir(exist_ok=True)

router = APIRouter(prefix="/catalog", tags=["Catalog"])

ENDPOINT_NAME = "catalog_register"


@router.post(
    "/register",
    summary="Cadastrar produtos a partir de planilha",
    description=(
        "Recebe um arquivo .xlsx com o catálogo de produtos, executa o fluxo de "
        "processamento de imagens (redimensionamento, conversão, hash, NAS e GCS) e "
        "atualiza os dados da planilha. Retorna estatísticas da execução."
    ),
    response_description="Estatísticas do processamento",
)
async def register_catalog(file: UploadFile = File(...)) -> JSONResponse:
    if not file.filename.endswith((".xlsx", ".xlsm")):
        raise HTTPException(
            status_code=400,
            detail=f"Formato inválido: '{file.filename}'. Apenas .xlsx ou .xlsm são aceitos.",
        )

    logger = setup_logger(ENDPOINT_NAME)
    logger.info(f"Planilha recebida: {file.filename}")

    temp_path = _TEMP_UPLOAD_DIR / file.filename
    try:
        with temp_path.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        path = Path(temp_path)
        if not path.exists():
            raise HTTPException(status_code=422, detail=f"Arquivo não encontrado após upload: {temp_path}")

        service = CatalogService(logger)
        stats = service.process_spreadsheet(path)

        logger.info("Processamento finalizado com sucesso.")
        return JSONResponse(content={"status": "success", "stats": stats}, status_code=200)

    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Erro inesperado: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))

    finally:
        if temp_path.exists():
            temp_path.unlink()