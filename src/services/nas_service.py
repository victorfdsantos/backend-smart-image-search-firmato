"""
NasService — operações no sistema de arquivos NAS.
Atualmente usa filesystem local; adaptável para SMB/NFS/SFTP.
"""

import logging
import shutil
from pathlib import Path
from typing import Optional

from config.settings import settings


class NasService:

    def __init__(self, logger: logging.Logger):
        self.logger = logger
        self.base_path = settings.nas.base_path
        self.organizer_columns = settings.nas.organizer_columns

    def build_product_path(self, data_row: dict, product_id: int) -> Path:
        """Monta o caminho esperado: {base}/{col1}/{col2}/.../{ID}/"""
        parts = [self._sanitize(str(data_row.get(col, "desconhecido"))) for col in self.organizer_columns]
        return self.base_path.joinpath(*parts, str(product_id))

    def find_product_folder(self, product_id: int) -> Optional[Path]:
        """Busca recursivamente a pasta do produto no NAS pelo ID."""
        try:
            for candidate in self.base_path.rglob(str(product_id)):
                if candidate.is_dir():
                    return candidate
            return None
        except Exception as exc:
            self.logger.error(f"[NAS] Erro ao buscar pasta do produto {product_id}: {exc}", exc_info=True)
            return None

    def move_product_folder(self, current: Path, new: Path) -> bool:
        """Move pasta do produto, mesclando se destino já existir. Limpa pastas pai vazias."""
        try:
            if current.resolve() == new.resolve():
                return True
            if not current.exists():
                self.logger.warning(f"[NAS] Origem não encontrada: {current}")
                return False

            new.parent.mkdir(parents=True, exist_ok=True)
            origin_parent = current.parent

            if new.exists():
                for item in current.iterdir():
                    dest = new / item.name
                    if dest.exists():
                        dest.unlink()
                    shutil.move(str(item), str(dest))
                shutil.rmtree(str(current))
            else:
                shutil.move(str(current), str(new))

            self.logger.info(f"[NAS] Pasta movida: {current} → {new}")
            self._cleanup_empty_parents(origin_parent)
            return True

        except Exception as exc:
            self.logger.error(f"[NAS] Erro ao mover '{current}' → '{new}': {exc}", exc_info=True)
            return False

    def save_image(self, source: Path, dest_folder: Path, filename: str) -> Optional[Path]:
        """Copia imagem para o NAS. Retorna o path final ou None em erro."""
        try:
            dest_folder.mkdir(parents=True, exist_ok=True)
            dest = dest_folder / filename
            shutil.copy2(source, dest)
            self.logger.info(f"[NAS] Imagem salva: {dest}")
            return dest
        except Exception as exc:
            self.logger.error(f"[NAS] Erro ao salvar '{filename}': {exc}", exc_info=True)
            return None

    def delete_image(self, nas_path: str) -> bool:
        """Remove imagem do NAS. Retorna True em sucesso."""
        try:
            path = Path(nas_path)
            if path.exists():
                path.unlink()
                self.logger.info(f"[NAS] Removido: {path}")
                return True
            self.logger.warning(f"[NAS] Não encontrado para remoção: {path}")
            return False
        except Exception as exc:
            self.logger.error(f"[NAS] Erro ao remover '{nas_path}': {exc}", exc_info=True)
            return False

    def _sanitize(self, value: str) -> str:
        for ch in r'\/:*?"<>|':
            value = value.replace(ch, "_")
        return value.strip().strip(".")[:100]

    def _cleanup_empty_parents(self, folder: Path) -> None:
        current = folder
        while current != self.base_path and current.exists():
            if not any(current.iterdir()):
                current.rmdir()
                current = current.parent
            else:
                break
