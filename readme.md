# Firmato — Guia de Deploy

## Visão geral

O projeto tem três ambientes que funcionam com os mesmos arquivos:

| Ambiente | Onde roda | Comando |
|---|---|---|
| **Local completo** | Sua máquina | `docker compose up -d` |
| **App Service** | Azure (frontend + backend) | `deploy-azure.sh` |
| **AI VM** | Azure VM GPU/CPU | `deploy-ai-vm.sh` |

O AI Service sempre fica separado porque precisa de GPU e muito mais memória.
O backend se comunica com ele via variável de ambiente `AI_SERVICE_URL`.

---

## Arquivos de deploy

```
docker-compose.yml          → local (todos os serviços incluindo AI)
docker-compose.azure.yml    → App Service (frontend + backend + nginx)
docker-compose.ai.yml       → VM Azure ou local isolado do AI
deploy-azure.sh             → script de build/push/restart para App Service
deploy-ai-vm.sh             → script para atualizar a VM
.env.local.example          → template de variáveis para local
.env.azure.example          → template de variáveis para App Service
training_service.py         → versão atualizada (lê AI_SERVICE_URL do ambiente)
backend.Dockerfile          → versão corrigida (sem --reload em produção)
```

---

## Rodando localmente

### 1. Configurar variáveis

```bash
cp .env.local.example .env
# edite .env e preencha AZURE_STORAGE_CONNECTION_STRING e SHAREPOINT_CLIENT_SECRET
```

### 2. Subir todos os serviços

```bash
docker compose up -d
```

Acesse: http://localhost (nginx) ou http://localhost:3000 (frontend direto)

### 3. Subir sem o AI Service local (usando a VM Azure)

```bash
# No .env, aponte AI_SERVICE_URL para o IP da sua VM:
# AI_SERVICE_URL=http://20.1.2.3:9000

# Suba apenas frontend, backend e nginx — sem o serviço ai:
docker compose up -d frontend backend nginx
```

---

## Deploy no Azure App Service

### Pré-requisitos

- Azure CLI instalado (`az login` feito)
- Docker instalado
- Um Azure Container Registry criado

### 1. Ajustar o script

Edite `deploy-azure.sh` e preencha as três variáveis no topo:

```bash
ACR_NAME="seuacr"
RESOURCE_GROUP="firmato-rg"
APP_SERVICE_NAME="firmato-app"
```

### 2. Rodar o deploy

```bash
chmod +x deploy-azure.sh
./deploy-azure.sh
```

O script faz:
1. `az acr login` — autentica no seu Container Registry
2. Build das imagens do backend e frontend
3. Push das imagens para o ACR
4. Reinicia o App Service

### 3. Configurar variáveis no App Service

No portal Azure: **App Service → Configuration → Application settings**

Adicione as variáveis do arquivo `.env.azure.example`:

| Chave | Valor |
|---|---|
| `AZURE_STORAGE_CONNECTION_STRING` | sua connection string do Blob Storage |
| `SHAREPOINT_CLIENT_SECRET` | secret do app registration |
| `AI_SERVICE_URL` | `http://<IP_DA_VM>:9000` |
| `CORS_ORIGINS` | `https://seu-app.azurewebsites.net` |
| `WEBSITES_PORT` | `80` |

### 4. Configurar o compose no App Service

No portal: **App Service → Deployment Center → Container**
- Source: **Azure Container Registry**
- Config type: **Docker Compose**
- Cole o conteúdo de `docker-compose.azure.yml` (com o nome do ACR preenchido)

> **Nota sobre volumes:** O App Service não suporta volumes locais como o Docker Desktop.
> O `clip_cache` foi removido do `docker-compose.azure.yml` — os modelos Hugging Face
> são baixados na primeira inicialização (~900MB CLIP) e ficam dentro do container.
> Se quiser persistência, monte um Azure File Share em `/app/.cache/huggingface`.

---

## Deploy do AI Service na VM Azure

### 1. Preparar a VM

```bash
# Na VM (Ubuntu 22.04+ recomendado):
sudo apt update && sudo apt install -y docker.io docker-compose-plugin git
sudo usermod -aG docker $USER
# Faça logout e login para aplicar o grupo
```

Para GPU NVIDIA, instale também o `nvidia-container-toolkit`:
```bash
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | \
  sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
  sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
sudo apt update && sudo apt install -y nvidia-container-toolkit
sudo systemctl restart docker
```

### 2. Criar o .env na VM

```bash
cat > ~/firmato/.env << 'EOF'
AZURE_STORAGE_CONNECTION_STRING=DefaultEndpointsProtocol=https;AccountName=...;...
EOF
```

### 3. Executar o script de deploy

Da sua máquina local:
```bash
# Edite a URL do repo no script primeiro
scp deploy-ai-vm.sh usuario@IP_DA_VM:~/
ssh usuario@IP_DA_VM './deploy-ai-vm.sh'
```

### 4. Configurar o NSG (firewall Azure)

No portal: **VM → Networking → Add inbound port rule**
- Port: `9000`
- Source: IP ou range de IPs do seu App Service (pegue em App Service → Outbound IPs)
- Action: Allow

**Nunca deixe a porta 9000 aberta para `0.0.0.0/0`.**

---

## Mudanças necessárias no código existente

### 1. `backend/Dockerfile`

Substitua pelo arquivo `backend.Dockerfile` gerado aqui.
A única mudança é remover o `--reload` do CMD — ele é para desenvolvimento e
não deve rodar em produção (faz o uvicorn reiniciar ao detectar alterações de arquivo).

### 2. `backend/src/services/training_service.py`

Substitua pelo arquivo `training_service.py` gerado aqui.
A mudança é fazer a URL do AI Service ser lida de `AI_SERVICE_URL` no ambiente,
em vez de ser hardcoded como `http://ai:9000`.

Isso permite que o mesmo código funcione localmente (Docker network) e na Azure
(apontando para o IP da VM), sem alteração.

### 3. `.gitignore`

Adicione ao seu `.gitignore` existente:
```
.env
.env.local
.env.azure
```

---

## Fluxo completo de desenvolvimento

```
Máquina local
  └─ docker compose up -d          ← tudo rodando, incluindo AI
  └─ docker compose up -d frontend backend nginx  ← sem AI local,
                                                     usa VM Azure

Azure App Service
  └─ frontend :3000  ─┐
  └─ backend :8000   ─┤─ nginx :80 → exposto como HTTPS pelo App Service
  └─ nginx :80       ─┘

Azure VM
  └─ ai :9000  ← acessado pelo backend via AI_SERVICE_URL

Azure Blob Storage
  └─ firmato-catalogo  ← compartilhado por backend e AI
```