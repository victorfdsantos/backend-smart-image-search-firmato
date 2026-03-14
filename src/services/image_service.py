import hashlib
import logging
import string
from pathlib import Path
from typing import Optional

from PIL import Image

from config.settings import settings


class ImageService:
    """Responsável por operações de manipulação de imagem."""

    SECONDARY_SUFFIX = list(string.ascii_uppercase)  # A, B, C, ...

    def __init__(self, logger: logging.Logger):
        self.logger = logger
        self.allowed_extensions = settings.image.allowed_extensions
        self.resize_width = settings.image.resize_width
        self.resize_height = settings.image.resize_height
        self.jpeg_quality = settings.image.jpeg_quality

    # ------------------------------------------------------------------
    # Validação
    # ------------------------------------------------------------------

    def file_exists_in_landing(self, filename_without_ext: str) -> Optional[Path]:
        """
        Recebe apenas o nome base do arquivo (sem extensão).
        Procura na landing por qualquer extensão permitida.
        Retorna o Path completo se encontrar.
        """
        landing = settings.general.landing_path

        for ext in self.allowed_extensions:
            candidate = landing / f"{filename_without_ext}{ext}"
            if candidate.exists():
                self.logger.debug(f"Arquivo encontrado: {candidate}")
                return candidate

        self.logger.warning(
            f"Arquivo '{filename_without_ext}' não encontrado "
            f"com extensões permitidas: {self.allowed_extensions}"
        )
        return None

    # ------------------------------------------------------------------
    # Processamento
    # ------------------------------------------------------------------

    def process_image(self, source_path: Path, dest_path: Path) -> bool:
        """
        Redimensiona e converte a imagem para JPG.
        Salva no destino informado.
        Retorna True em caso de sucesso.
        """
        try:
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            with Image.open(source_path) as img:
                # Garante modo RGB para salvar como JPEG
                if img.mode in ("RGBA", "P", "LA"):
                    img = img.convert("RGBA")
                    background = Image.new("RGB", img.size, (255, 255, 255))
                    background.paste(img, mask=img.split()[3])
                    img = background
                elif img.mode != "RGB":
                    img = img.convert("RGB")

                # Redimensiona mantendo proporção dentro do bounding box
                target_w = self.resize_width
                target_h = self.resize_height
                if target_w > 0 and target_h > 0:
                    img.thumbnail((target_w, target_h), Image.LANCZOS)

                img.save(dest_path, "JPEG", quality=self.jpeg_quality, optimize=True)

            self.logger.info(
                f"Imagem processada com sucesso: {source_path} → {dest_path}"
            )
            return True

        except Exception as exc:
            self.logger.error(
                f"Erro ao processar imagem '{source_path}': {exc}", exc_info=True
            )
            return False

    # ------------------------------------------------------------------
    # Nomenclatura
    # ------------------------------------------------------------------

    def primary_image_name(self, product_id: int) -> str:
        """Retorna o nome da imagem principal: {ID}.jpg"""
        return f"{product_id}.jpg"

    def secondary_image_name(self, product_id: int, index: int) -> str:
        """
        Retorna o nome da imagem secundária com sufixo alfabético.
        index=0 → {ID}A.jpg, index=1 → {ID}B.jpg, ...
        """
        if index >= len(self.SECONDARY_SUFFIX):
            self.logger.warning(
                f"Índice secundário {index} excede o alfabeto. Usando fallback."
            )
            suffix = f"_{index}"
        else:
            suffix = self.SECONDARY_SUFFIX[index]
        return f"{product_id}{suffix}.jpg"

    # ------------------------------------------------------------------
    # Hash / Chave Especial
    # ------------------------------------------------------------------

    def generate_hash(self, data_row: dict) -> str:
        """
        Gera SHA-256 a partir dos valores das colunas configuradas em hash_columns.
        Retorna a string hexadecimal do hash.
        """
        hash_columns = settings.hash.hash_columns
        raw = "|".join(
            str(data_row.get(col, "")).strip() for col in hash_columns
        )
        digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        self.logger.debug(f"Hash gerado para colunas {hash_columns}: {digest[:16]}...")
        return digest