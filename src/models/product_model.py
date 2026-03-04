from dataclasses import dataclass, asdict
from typing import Optional

# Slots de imagens secundárias
SECONDARY_SLOTS: list[int] = [1, 2, 3, 4]

SECONDARY_EXCEL_COLS:  dict[int, str] = {i: f"Caminho_Imagem_Secundaria{i}" for i in SECONDARY_SLOTS}
SECONDARY_NAS_FIELDS:  dict[int, str] = {i: f"caminho_imagem_secundaria{i}" for i in SECONDARY_SLOTS}
SECONDARY_BUCKET_FIELDS: dict[int, str] = {i: f"caminho_bucket_secundaria{i}"  for i in SECONDARY_SLOTS}

# Colunas do Excel que, se mudarem, exigem mover a pasta do produto no NAS
NAS_ORGANIZER_COLUMNS: list[str] = ["Marca", "Linha_Colecao", "Categoria_Principal"]


@dataclass
class ProductModel:
    """
    Representa um produto do catálogo.

    Campos de caminho (NAS/bucket) vivem APENAS no JSON — nunca são lidos do Excel.
    O Excel fornece só os dados de produto e os filenames de imagem pendentes.
    """
    # Identificação
    chave_especial: Optional[str] = None
    id_produto: Optional[int] = None

    # Caminhos — preenchidos programaticamente, nunca vindos do Excel direto
    caminho_imagem: Optional[str] = None
    caminho_bucket_principal: Optional[str] = None
    caminho_imagem_secundaria1: Optional[str] = None
    caminho_imagem_secundaria2: Optional[str] = None
    caminho_imagem_secundaria3: Optional[str] = None
    caminho_imagem_secundaria4: Optional[str] = None
    caminho_bucket_secundaria1: Optional[str] = None
    caminho_bucket_secundaria2: Optional[str] = None
    caminho_bucket_secundaria3: Optional[str] = None
    caminho_bucket_secundaria4: Optional[str] = None

    # Dados do produto
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
    material_principal: Optional[str] = None
    material_estrutura: Optional[str] = None
    material_revestimento: Optional[str] = None
    cor_principal: Optional[str] = None
    cores_disponiveis: Optional[str] = None
    peso_kg: Optional[str] = None
    altura_cm: Optional[str] = None
    largura_cm: Optional[str] = None
    profundidade_cm: Optional[str] = None
    suporta_peso_kg: Optional[str] = None
    nivel_conforto: Optional[str] = None
    firmeza: Optional[str] = None
    complexidade_montagem: Optional[str] = None
    indicado_espacos_pequenos: Optional[str] = None
    possui_armazenamento: Optional[str] = None
    multifuncional: Optional[str] = None
    nivel_premium: Optional[str] = None
    faixa_preco: Optional[str] = None
    fornecedor: Optional[str] = None
    prazo_entrega: Optional[str] = None
    tipo_entrega: Optional[str] = None
    garantia_meses: Optional[str] = None
    palavras_chave: Optional[str] = None
    descricao_curta: Optional[str] = None
    descricao_tecnica: Optional[str] = None
    tags: Optional[str] = None
    sinonimos: Optional[str] = None
    perfil_cliente: Optional[str] = None

    def to_dict(self) -> dict:
        """Serializa descartando campos None — o JSON só terá o que foi preenchido."""
        return {k: v for k, v in asdict(self).items() if v is not None}


# Mapeamento Excel → model. Inclui APENAS campos de dados.
# Campos de caminho (NAS/bucket) são preenchidos pelo CatalogService diretamente.
COLUMN_MAP: dict[str, str] = {
    "Chave_Especial":            "chave_especial",
    "Id_produto":                "id_produto",
    "Nome_Produto":              "nome_produto",
    "Linha_Colecao":             "linha_colecao",
    "Marca":                     "marca",
    "Status":                    "status",
    "Categoria_Principal":       "categoria_principal",
    "Subcategoria":              "subcategoria",
    "Tipo":                      "tipo",
    "Ambiente":                  "ambiente",
    "Estilo":                    "estilo",
    "Forma":                     "forma",
    "Modular":                   "modular",
    "Uso":                       "uso",
    "Material_Principal":        "material_principal",
    "Material_Estrutura":        "material_estrutura",
    "Material_Revestimento":     "material_revestimento",
    "Cor_Principal":             "cor_principal",
    "Cores_Disponiveis":         "cores_disponiveis",
    "Peso_kg":                   "peso_kg",
    "Altura_cm":                 "altura_cm",
    "Largura_cm":                "largura_cm",
    "Profundidade_cm":           "profundidade_cm",
    "Suporta_Peso_kg":           "suporta_peso_kg",
    "Nivel_Conforto":            "nivel_conforto",
    "Firmeza":                   "firmeza",
    "Complexidade_Montagem":     "complexidade_montagem",
    "Indicado_Espacos_Pequenos": "indicado_espacos_pequenos",
    "Possui_Armazenamento":      "possui_armazenamento",
    "Multifuncional":            "multifuncional",
    "Nivel_Premium":             "nivel_premium",
    "Faixa_Preco":               "faixa_preco",
    "Fornecedor":                "fornecedor",
    "Prazo de Entrega":          "prazo_entrega",
    "Tipo de Entrega":           "tipo_entrega",
    "Garantia_Meses":            "garantia_meses",
    "Palavras_Chave":            "palavras_chave",
    "Descricao_Curta":           "descricao_curta",
    "Descricao_Tecnica":         "descricao_tecnica",
    "Tags":                      "tags",
    "Sinonimos":                 "sinonimos",
    "Perfil_Cliente":            "perfil_cliente",
}
