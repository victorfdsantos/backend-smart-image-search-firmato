from typing import Optional
from pydantic import BaseModel, Field


class TrainingRequest(BaseModel):
    """
    Payload para retreinamento incremental.

    Você pode passar os IDs em dois grupos independentes:

    - image_ids  → produtos com imagem nova ou alterada.
                   Regenera o embedding CLIP a partir da imagem
                   encontrada recursivamente em nas/output/{id}.jpg

    - data_ids   → produtos com JSON de metadados novo ou alterado.
                   Regenera o embedding de texto (ST) e atualiza o BM25.

    Um produto pode aparecer nos dois grupos simultaneamente (ex: a
    imagem E os metadados foram atualizados na mesma operação).

    Exemplo mínimo — só imagem alterada:
        { "image_ids": ["42", "77"] }

    Exemplo mínimo — só metadados alterados:
        { "data_ids": ["42", "77"] }

    Exemplo completo — ambos:
        {
          "image_ids": ["42"],
          "data_ids":  ["42", "100", "101"]
        }
    """

    image_ids: list[str] = Field(
        default_factory=list,
        description="IDs dos produtos com imagem nova ou alterada.",
        examples=[["42", "77"]],
    )
    data_ids: list[str] = Field(
        default_factory=list,
        description="IDs dos produtos com JSON de metadados novo ou alterado.",
        examples=[["42", "100", "101"]],
    )


class TrainingResponse(BaseModel):
    status: str
    total_requested: int
    clip_updated: int
    text_updated: int
    bm25_rebuilt: bool
    errors: list[str]