# smart-image-search-firmato

API de processamento e busca inteligente do catálogo de produtos Firmato Móveis.

Recebe uma planilha Excel com os dados dos produtos, processa as imagens (resize, conversão para JPEG, hash), organiza no NAS e no GCS, salva um JSON por produto, e expõe endpoints de listagem, detalhe e busca semântica por texto ou imagem via CLIP.

---

## O que o sistema faz

- **`POST /catalog/register`** — recebe uma planilha `.xlsx`, compara com o estado atual (JSON em disco), processa imagens novas/trocadas, deleta imagens removidas, move pastas no NAS quando a organização muda, e devolve estatísticas da execução.
- **`GET /products`** — lista produtos ativos com paginação.
- **`GET /products/{id}`** — retorna o JSON completo de um produto.
- **`POST /search`** — busca semântica por texto e/ou imagem usando o modelo CLIP (`openai/clip-vit-large-patch14`). Suporta busca só por texto, só por imagem, ou combinada 50/50.

---

## Estrutura de pastas esperada

```
projeto/
├── src/
│   ├── main.py
│   ├── config.ini
│   ├── config/
│   ├── controllers/
│   ├── models/
│   ├── services/
│   └── utils/
├── landing/          # imagens brutas recebidas para processamento
├── data/             # JSONs gerados por produto (ex: 42.json)
├── output/nas/       # imagens processadas organizadas por Marca/Linha/Categoria/ID
├── embeddings/       # embeddings.npy + metadata_index.json
├── logs/
├── tmp_images/       # thumbnails 400x400 servidos pela API (gerado no startup)
├── tmp_uploads/      # upload temporário da planilha (apagado após uso)
└── requirements.txt
```

---

## Pré-requisitos

- Python **3.12**
- `venv` disponível (já vem com o Python 3.12)

---

## Como rodar localmente

### 1. Clonar o repositório

```bash
git clone https://github.com/seu-usuario/smart-image-search-firmato.git
cd smart-image-search-firmato
```

### 2. Criar o ambiente virtual

```bash
python3.12 -m venv .venv
```

### 3. Ativar o ambiente virtual

**Linux / macOS:**
```bash
source .venv/bin/activate
```

**Windows (PowerShell):**
```powershell
.venv\Scripts\Activate.ps1
```

### 4. Instalar as dependências

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

> **Atenção com o torch:** o `torch==2.5.1` do PyPI instala a versão CPU por padrão.
> Se quiser GPU (CUDA), instale manualmente antes de rodar o comando acima:
> ```bash
> pip install torch==2.5.1 --index-url https://download.pytorch.org/whl/cu121
> ```

### 5. Configurar o `config.ini`

O arquivo `src/config.ini` já vem com valores padrão apontando para pastas locais relativas.
Ajuste conforme necessário, principalmente:

```ini
[nas]
base_path = ./output/nas

[gcs]
bucket_name = firmato-moveis-catalog
credentials_path = ./config/gcs_credentials.json
```

> Se não for usar o GCS agora, pode deixar como está — o upload para o bucket está comentado no código.

### 6. Criar as pastas necessárias

```bash
mkdir -p landing data output/nas embeddings logs tmp_images tmp_uploads src/config
```

### 7. Rodar a API

```bash
cd src
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

A API estará disponível em: `http://localhost:8000`

Documentação interativa: `http://localhost:8000/docs`

---

## Notas

- Na primeira inicialização o modelo CLIP (~900 MB) é baixado automaticamente pelo `transformers` e cacheado em `~/.cache/huggingface`. Isso pode levar alguns minutos.
- Se os arquivos `embeddings/embeddings.npy` e `embeddings/metadata_index.json` não existirem, a API sobe normalmente mas a rota `/search` retorna lista vazia.
- As thumbnails em `tmp_images/` são regeradas do zero toda vez que a API é iniciada, varrendo o NAS.

---

## Como subir em produção (Docker)

### Pré-requisitos

- Docker Engine 24+
- Docker Compose v2 (`docker compose` sem hífen)

### 1. Clonar e entrar na pasta

```bash
git clone https://github.com/seu-usuario/smart-image-search-firmato.git
cd smart-image-search-firmato
```

### 2. Criar as pastas de dados no servidor

```bash
mkdir -p landing data output/nas embeddings logs src/config
```

### 3. Colocar as credenciais do GCS

Copie o arquivo de service account para dentro de `src/config/`:

```bash
cp /caminho/para/gcs_credentials.json src/config/gcs_credentials.json
```

### 4. Revisar o `src/config.ini`

Em produção os caminhos são relativos ao container — os padrões já funcionam com os volumes mapeados no `docker-compose.yml`. Verifique apenas:

```ini
[gcs]
bucket_name = firmato-moveis-catalog
credentials_path = ./config/gcs_credentials.json
```

### 5. Build e subir

```bash
docker compose build
docker compose up -d
```

A rede `firmato-net` é criada automaticamente pelo Compose se ainda não existir. Nenhum passo manual de `docker network create` é necessário.

### 6. Verificar se subiu

```bash
docker compose ps
docker compose logs -f api
```

A API estará disponível em `http://seu-servidor:8000`.  
Documentação interativa: `http://seu-servidor:8000/docs`

### Comandos úteis do dia a dia

```bash
# Rebuild após mudança de código
docker compose build && docker compose up -d

# Ver logs em tempo real
docker compose logs -f api

# Parar tudo
docker compose down

# Parar e apagar os volumes (cuidado — apaga o cache do CLIP)
docker compose down -v
```

### Observação sobre o modelo CLIP

Na primeira vez que o container sobe, o modelo `openai/clip-vit-large-patch14` (~900 MB) é baixado do Hugging Face e salvo no volume `clip_cache`. Nos próximos restarts ele é reutilizado sem re-download. Isso significa que o **primeiro startup pode demorar vários minutos** — o healthcheck tem `start_period: 90s` para dar essa margem.

Se preferir embutir o modelo na própria imagem (startup instantâneo, imagem maior), descomente o bloco `RUN python -c ...` no `Dockerfile` antes de fazer o build.
