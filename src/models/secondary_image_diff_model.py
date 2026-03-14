"""
Dataclasses que representam o resultado de uma comparação Excel vs JSON.
São o contrato de dados entre DiffService e CatalogService —
nenhum dos dois precisa conhecer os detalhes internos do outro.

SecondaryImageDiff  → estado de um slot de imagem secundária (1-3)
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class SecondaryImageDiff:
    """
    Representa o estado de um slot de imagem secundária após comparação.

    Flags mutuamente exclusivas (apenas uma será True por instância):
      is_new       → filename no Excel, sem caminho no JSON → processar pela 1ª vez
      is_changed   → filename no Excel, JSON já tem caminho → imagem foi trocada
      is_processed → caminho NAS no Excel, JSON confirma    → sem ação necessária
      is_deleted   → Excel vazio, JSON tem caminho          → remover NAS/bucket/JSON
      is_empty     → Excel vazio, JSON também vazio         → slot não utilizado
    """
    slot: int                     # 1, 2 ou 3
    excel_value: Optional[str]    # valor atual no Excel para este slot
    json_nas_path: Optional[str]  # caminho NAS gravado no JSON
    json_bucket_uri: Optional[str]# URI bucket gravado no JSON

    is_new: bool = False
    is_changed: bool = False
    is_processed: bool = False
    is_deleted: bool = False
    is_empty: bool = False