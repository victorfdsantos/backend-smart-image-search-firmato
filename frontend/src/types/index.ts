export interface ProductSummary {
  id_produto: number | string;
  imagem_url: string;
  nome_produto: string;
  marca: string;
  categoria_principal: string;
  faixa_preco: string;
  altura_cm?: string;
  largura_cm?: string;
  profundidade_cm?: string;
}

export interface ProductDetail {
  id_produto: number | string;
  nome_produto: string;
  marca: string;
  status: string;
  categoria_principal: string;
  subcategoria?: string;
  tipo?: string;
  ambiente?: string;
  estilo?: string;
  forma?: string;
  modular?: string;
  uso?: string;
  material_principal?: string;
  material_estrutura?: string;
  material_revestimento?: string;
  cor_principal?: string;
  cores_disponiveis?: string;
  peso_kg?: string;
  altura_cm?: string;
  largura_cm?: string;
  profundidade_cm?: string;
  suporta_peso_kg?: string;
  nivel_conforto?: string;
  firmeza?: string;
  complexidade_montagem?: string;
  indicado_espacos_pequenos?: string;
  possui_armazenamento?: string;
  multifuncional?: string;
  nivel_premium?: string;
  faixa_preco?: string;
  fornecedor?: string;
  prazo_entrega?: string;
  tipo_entrega?: string;
  garantia_meses?: string;
  palavras_chave?: string;
  descricao_curta?: string;
  descricao_tecnica?: string;
  tags?: string;
  sinonimos?: string;
  perfil_cliente?: string;
  caminho_imagem?: string;
  caminho_imagem_secundaria1?: string;
  caminho_imagem_secundaria2?: string;
  caminho_imagem_secundaria3?: string;
  caminho_imagem_secundaria4?: string;
}

export interface PaginatedProducts {
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
  items: ProductSummary[];
}

export interface SearchResult {
  total: number;
  items: ProductSummary[];
}

export interface FilterOptions {
  fields: string[];
  labels: Record<string, string>;
  options: Record<string, string[]>;
  active_filters: Record<string, string[]>;
}

export type FilterMap = Record<string, string[]>;

/**
 * Resposta do endpoint POST /catalog/register
 */
export interface UploadStats {
  status: string;
  elapsed_seconds: number;
  processed: number;
  skipped: number;
  errors: number;
  updated_ids: string[];
}