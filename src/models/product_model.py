from dataclasses import dataclass, asdict
from typing import Optional


# ---------------------------------------------------------------------------
# Colunas do Excel que definem o caminho de pasta no NAS.
# Qualquer mudança nessas colunas exige mover a pasta do produto no NAS.
# ---------------------------------------------------------------------------
NAS_ORGANIZER_COLUMNS: list[str] = ["Marca", "Linha_Colecao", "Categoria_Principal"]

# ---------------------------------------------------------------------------
# Slots de imagens secundárias (índice 1-4).
# Cada slot tem uma coluna no Excel e um campo correspondente no model/JSON.
# ---------------------------------------------------------------------------
SECONDARY_SLOTS: list[int] = [1, 2, 3, 4]

# Colunas do Excel para imagens secundárias
SECONDARY_EXCEL_COLS: dict[int, str] = {
    i: f"Caminho_Imagem_Secundaria{i}" for i in SECONDARY_SLOTS
}

# Campos do model/JSON para caminhos NAS das secundárias
SECONDARY_NAS_FIELDS: dict[int, str] = {
    i: f"caminho_imagem_secundaria{i}" for i in SECONDARY_SLOTS
}

# Campos do model/JSON para URIs do bucket das secundárias
SECONDARY_BUCKET_FIELDS: dict[int, str] = {
    i: f"caminho_bucket_secundaria{i}" for i in SECONDARY_SLOTS
}


@dataclass
class ProductModel:
    """
    Representa um produto do catálogo com todos os seus atributos.

    Campos de imagem:
      - caminho_imagem          : caminho NAS da imagem principal (só no JSON)
      - caminho_bucket_principal: URI GCS da imagem principal    (só no JSON)
      - caminho_imagem_secundaria1..4 : caminhos NAS das secundárias (só no JSON)
      - caminho_bucket_secundaria1..4 : URIs GCS das secundárias    (só no JSON)

    O Excel contém apenas os nomes de arquivo originais (antes do processamento)
    ou o marcador "Processada" depois de processado. Os caminhos reais NAS/bucket
    vivem exclusivamente no JSON.
    """

    # --- Identificação ---
    chave_especial: Optional[str] = None
    id_produto: Optional[int] = None

    # --- Imagem principal (somente JSON, nunca gravado no Excel) ---
    caminho_imagem: Optional[str] = None
    caminho_bucket_principal: Optional[str] = None

    # --- Imagens secundárias NAS (somente JSON) ---
    caminho_imagem_secundaria1: Optional[str] = None
    caminho_imagem_secundaria2: Optional[str] = None
    caminho_imagem_secundaria3: Optional[str] = None
    caminho_imagem_secundaria4: Optional[str] = None

    # --- Imagens secundárias bucket (somente JSON) ---
    caminho_bucket_secundaria1: Optional[str] = None
    caminho_bucket_secundaria2: Optional[str] = None
    caminho_bucket_secundaria3: Optional[str] = None
    caminho_bucket_secundaria4: Optional[str] = None

    # --- Dados do produto ---
    nome_produto: Optional[str] = None
    linha_colecao: Optional[str] = None
    marca: Optional[str] = None
    status: Optional[str] = None
    categoria_principal: Optional[str] = None
    subcategoria: Optional[str] = None
    tipo: Optional[str] = None
    ambiente: Optional[str] = None
    estilo: Optional[str] = None
    forma: Optional[str] = None
    modular: Optional[str] = None
    uso: Optional[str] = None

    # --- Materiais ---
    material_principal: Optional[str] = None
    material_estrutura: Optional[str] = None
    material_revestimento: Optional[str] = None

    # --- Cores ---
    cor_principal: Optional[str] = None
    cores_disponiveis: Optional[str] = None

    # --- Dimensões ---
    peso_kg: Optional[str] = None
    altura_cm: Optional[str] = None
    largura_cm: Optional[str] = None
    profundidade_cm: Optional[str] = None
    suporta_peso_kg: Optional[str] = None

    # --- Conforto e usabilidade ---
    nivel_conforto: Optional[str] = None
    firmeza: Optional[str] = None
    complexidade_montagem: Optional[str] = None
    indicado_espacos_pequenos: Optional[str] = None
    possui_armazenamento: Optional[str] = None
    multifuncional: Optional[str] = None
    nivel_premium: Optional[str] = None
    faixa_preco: Optional[str] = None

    # --- Logística ---
    fornecedor: Optional[str] = None
    prazo_entrega: Optional[str] = None
    tipo_entrega: Optional[str] = None
    garantia_meses: Optional[str] = None

    # --- Conteúdo descritivo ---
    palavras_chave: Optional[str] = None
    descricao_curta: Optional[str] = None
    descricao_tecnica: Optional[str] = None
    tags: Optional[str] = None
    sinonimos: Optional[str] = None
    perfil_cliente: Optional[str] = None

    def to_dict(self) -> dict:
        """Serializa o model descartando campos None."""
        return {k: v for k, v in asdict(self).items() if v is not None}


# ---------------------------------------------------------------------------
# Mapeamento das colunas do Excel → campos do ProductModel
# Não inclui campos exclusivos do JSON (caminhos NAS/bucket):
# esses são preenchidos programaticamente durante o processamento.
# ---------------------------------------------------------------------------
COLUMN_MAP: dict[str, str] = {
    "Chave_Especial":              "chave_especial",
    "Id_produto":                  "id_produto",
    # Secundárias do Excel → campos do model (valor original / "Processada")
    "Caminho_Imagem_Secundaria1":  "caminho_imagem_secundaria1",
    "Caminho_Imagem_Secundaria2":  "caminho_imagem_secundaria2",
    "Caminho_Imagem_Secundaria3":  "caminho_imagem_secundaria3",
    "Caminho_Imagem_Secundaria4":  "caminho_imagem_secundaria4",
    # Dados do produto
    "Nome_Produto":                "nome_produto",
    "Linha_Colecao":               "linha_colecao",
    "Marca":                       "marca",
    "Status":                      "status",
    "Categoria_Principal":         "categoria_principal",
    "Subcategoria":                "subcategoria",
    "Tipo":                        "tipo",
    "Ambiente":                    "ambiente",
    "Estilo":                      "estilo",
    "Forma":                       "forma",
    "Modular":                     "modular",
    "Uso":                         "uso",
    "Material_Principal":          "material_principal",
    "Material_Estrutura":          "material_estrutura",
    "Material_Revestimento":       "material_revestimento",
    "Cor_Principal":               "cor_principal",
    "Cores_Disponiveis":           "cores_disponiveis",
    "Peso_kg":                     "peso_kg",
    "Altura_cm":                   "altura_cm",
    "Largura_cm":                  "largura_cm",
    "Profundidade_cm":             "profundidade_cm",
    "Suporta_Peso_kg":             "suporta_peso_kg",
    "Nivel_Conforto":              "nivel_conforto",
    "Firmeza":                     "firmeza",
    "Complexidade_Montagem":       "complexidade_montagem",
    "Indicado_Espacos_Pequenos":   "indicado_espacos_pequenos",
    "Possui_Armazenamento":        "possui_armazenamento",
    "Multifuncional":              "multifuncional",
    "Nivel_Premium":               "nivel_premium",
    "Faixa_Preco":                 "faixa_preco",
    "Fornecedor":                  "fornecedor",
    "Prazo de Entrega":            "prazo_entrega",
    "Tipo de Entrega":             "tipo_entrega",
    "Garantia_Meses":              "garantia_meses",
    "Palavras_Chave":              "palavras_chave",
    "Descricao_Curta":             "descricao_curta",
    "Descricao_Tecnica":           "descricao_tecnica",
    "Tags":                        "tags",
    "Sinonimos":                   "sinonimos",
    "Perfil_Cliente":              "perfil_cliente",
}
