import logging
import shutil
from pathlib import Path
from typing import Optional

from config.settings import settings


class NasService:
    """
    Serviço responsável por operações no NAS.
    Atualmente usa sistema de arquivos local (caminho configurável em config.ini).
    No futuro pode ser adaptado para protocolos SMB/NFS/SFTP.
    """

    def __init__(self, logger: logging.Logger):
        self.logger = logger
        self.base_path = settings.nas.base_path
        self.organizer_columns = settings.nas.organizer_columns

    # ------------------------------------------------------------------
    # Construção de caminhos
    # ------------------------------------------------------------------

    def build_product_path(self, data_row: dict, product_id: int) -> Path:
        """
        Monta o caminho de destino no NAS a partir dos dados atuais da linha.
        Estrutura: {base}/{col1}/{col2}/.../{ID}/
        """
        parts = [
            self._sanitize(str(data_row.get(col, "desconhecido")))
            for col in self.organizer_columns
        ]
        return self.base_path.joinpath(*parts, str(product_id))

    def _sanitize(self, value: str) -> str:
        """Sanitiza nome de pasta: remove/substitui caracteres inválidos."""
        invalid = r'\/:*?"<>|'
        for ch in invalid:
            value = value.replace(ch, "_")
        return value.strip().strip(".")[:100]

    # ------------------------------------------------------------------
    # Busca por ID
    # ------------------------------------------------------------------

    def find_product_folder(self, product_id: int) -> Optional[Path]:
        """
        Busca recursivamente no NAS a pasta cujo nome seja o ID do produto.
        Retorna o Path encontrado ou None se não existir.

        Isso permite localizar o produto independente de qual estrutura
        de pastas organizadoras ele está atualmente (antes de mover).
        """
        try:
            target_name = str(product_id)
            for candidate in self.base_path.rglob(target_name):
                if candidate.is_dir():
                    self.logger.info(
                        f"[NAS] Pasta do produto {product_id} encontrada: {candidate}"
                    )
                    return candidate
            self.logger.info(
                f"[NAS] Pasta do produto {product_id} não encontrada no NAS."
            )
            return None
        except Exception as exc:
            self.logger.error(
                f"[NAS] Erro ao buscar pasta do produto {product_id}: {exc}",
                exc_info=True,
            )
            return None

    # ------------------------------------------------------------------
    # Mover produto (manutenção de caminho)
    # ------------------------------------------------------------------

    def move_product_folder(self, current_path: Path, new_path: Path) -> bool:
        """
        Move toda a pasta de um produto de current_path para new_path.
        Garante a remoção completa da pasta de origem após a movimentação,
        incluindo limpeza de pastas pai que ficaram vazias.
        Retorna True em sucesso.
        """
        try:
            if current_path.resolve() == new_path.resolve():
                self.logger.info(
                    f"[NAS] Pasta já está no caminho correto, nenhuma movimentação necessária: "
                    f"{current_path}"
                )
                return True

            if not current_path.exists():
                self.logger.warning(
                    f"[NAS] Caminho de origem não encontrado para mover: {current_path}"
                )
                return False

            new_path.parent.mkdir(parents=True, exist_ok=True)

            # Guarda o pai antes de mover para poder limpar depois
            origin_parent = current_path.parent

            if new_path.exists():
                # Destino já existe: copia cada arquivo e depois apaga a origem inteira
                self.logger.warning(
                    f"[NAS] Pasta de destino já existe. Mesclando e removendo origem: {new_path}"
                )
                for item in current_path.iterdir():
                    dest_item = new_path / item.name
                    if dest_item.exists():
                        dest_item.unlink()
                        self.logger.debug(f"[NAS] Sobrescrito no destino: {dest_item}")
                    shutil.move(str(item), str(dest_item))

                # Remove a pasta de origem (agora vazia) de forma garantida
                shutil.rmtree(str(current_path), ignore_errors=False)
                self.logger.info(f"[NAS] Origem removida após mesclagem: {current_path}")
            else:
                # Destino não existe: move diretamente (atômico no mesmo filesystem)
                shutil.move(str(current_path), str(new_path))

            self.logger.info(f"[NAS] Pasta movida com sucesso: {current_path} → {new_path}")

            # Remove pastas pai que ficaram vazias após a movimentação
            self._cleanup_empty_parents(origin_parent)
            return True

        except Exception as exc:
            self.logger.error(
                f"[NAS] Erro ao mover pasta '{current_path}' → '{new_path}': {exc}",
                exc_info=True,
            )
            return False

    def _cleanup_empty_parents(self, folder: Path) -> None:
        """
        Remove recursivamente pastas pai que ficaram vazias
        após uma movimentação, sem ultrapassar o base_path.
        """
        try:
            current = folder
            while current != self.base_path and current.exists():
                if not any(current.iterdir()):
                    current.rmdir()
                    self.logger.debug(f"[NAS] Pasta vazia removida: {current}")
                    current = current.parent
                else:
                    break
        except Exception as exc:
            self.logger.warning(
                f"[NAS] Aviso ao limpar pastas vazias em '{folder}': {exc}"
            )

    # ------------------------------------------------------------------
    # Salvar imagem
    # ------------------------------------------------------------------

    def save_image(self, source_path: Path, dest_folder: Path, filename: str) -> Optional[Path]:
        """
        Copia imagem para o NAS.
        Retorna o caminho final no NAS ou None em caso de erro.
        """
        try:
            dest_folder.mkdir(parents=True, exist_ok=True)
            dest_path = dest_folder / filename
            shutil.copy2(source_path, dest_path)
            self.logger.info(f"[NAS] Imagem salva: {dest_path}")
            return dest_path
        except Exception as exc:
            self.logger.error(
                f"[NAS] Erro ao salvar '{filename}' em '{dest_folder}': {exc}",
                exc_info=True,
            )
            return None

    # ------------------------------------------------------------------
    # Get / Delete (prontos para futura expansão)
    # ------------------------------------------------------------------

    def get_image(self, nas_path: str) -> Optional[Path]:
        """
        Retorna o Path de uma imagem no NAS se existir.
        Preparado para futura expansão (ex: acesso via protocolo SMB/NFS).
        """
        try:
            path = Path(nas_path)
            if path.exists():
                self.logger.debug(f"[NAS] Imagem encontrada: {path}")
                return path
            self.logger.warning(f"[NAS] Imagem não encontrada: {path}")
            return None
        except Exception as exc:
            self.logger.error(f"[NAS] Erro ao buscar '{nas_path}': {exc}", exc_info=True)
            return None

    def delete_image(self, nas_path: str) -> bool:
        """Remove imagem do NAS. Retorna True em sucesso."""
        try:
            path = Path(nas_path)
            if path.exists():
                path.unlink()
                self.logger.info(f"[NAS] Imagem removida: {path}")
                return True
            self.logger.warning(f"[NAS] Imagem não encontrada para remoção: {path}")
            return False
        except Exception as exc:
            self.logger.error(
                f"[NAS] Erro ao remover '{nas_path}': {exc}", exc_info=True
            )
            return False
