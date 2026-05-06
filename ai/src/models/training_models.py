"""
Modelos Pydantic para o endpoint POST /training do AI Service.
"""

from pydantic import BaseModel, Field, model_validator


class TrainingRequest(BaseModel):
    """
    Payload para retreinamento incremental.

    Você pode passar os IDs em dois grupos independentes:

    - **image_ids** → produtos com imagem nova ou alterada.
      Regenera o embedding CLIP a partir da imagem no Blob (thumbnail_staging/{id}.jpg).

    - **data_ids** → produtos com JSON de metadados novo ou alterado.
      Regenera o embedding de texto (ST) e atualiza o BM25.

    Um produto pode aparecer nos dois grupos simultaneamente (ex: a
    imagem E os metadados foram atualizados na mesma operação).

    Exemplo — só imagem alterada:
        { "image_ids": ["42", "77"] }

    Exemplo — só metadados alterados:
        { "data_ids": ["42", "77"] }

    Exemplo — ambos:
        { "image_ids": ["42"], "data_ids": ["42", "100", "101"] }
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

    @model_validator(mode="after")
    def at_least_one_id(self) -> "TrainingRequest":
        if not self.image_ids and not self.data_ids:
            raise ValueError("Informe ao menos um ID em image_ids ou data_ids.")
        return self


class TrainingResponse(BaseModel):
    status:          str
    elapsed:         float
    total_requested: int
    clip_updated:    int
    text_updated:    int
    bm25_rebuilt:    bool
    errors:          list[str]