#!/usr/bin/env bash
# =============================================================================
# deploy-azure.sh
# Faz build das imagens, sobe para o ACR e reinicia o App Service.
#
# Pré-requisitos:
#   - Azure CLI instalado e autenticado (az login)
#   - Docker instalado e rodando
#   - Variáveis abaixo preenchidas
#
# Uso:
#   chmod +x deploy-azure.sh
#   ./deploy-azure.sh
# =============================================================================

set -euo pipefail

# ── Configurações — ajuste para o seu ambiente ────────────────────────────────
ACR_NAME="seuacr"                          # nome do Azure Container Registry (sem .azurecr.io)
RESOURCE_GROUP="firmato-rg"               # Resource Group do App Service
APP_SERVICE_NAME="firmato-app"            # nome do App Service
# ─────────────────────────────────────────────────────────────────────────────

ACR_LOGIN_SERVER="${ACR_NAME}.azurecr.io"

echo "▶ Autenticando no ACR..."
az acr login --name "$ACR_NAME"

echo "▶ Build das imagens..."
docker build -t "${ACR_LOGIN_SERVER}/firmato-backend:latest" \
    -f backend/Dockerfile --target runtime ./backend

docker build -t "${ACR_LOGIN_SERVER}/firmato-frontend:latest" \
    -f frontend/Dockerfile ./frontend

echo "▶ Push para o ACR..."
docker push "${ACR_LOGIN_SERVER}/firmato-backend:latest"
docker push "${ACR_LOGIN_SERVER}/firmato-frontend:latest"

echo "▶ Atualizando docker-compose.azure.yml com o nome do ACR..."
sed -i "s|<YOUR_ACR>|${ACR_NAME}|g" docker-compose.azure.yml

echo "▶ Reiniciando o App Service..."
az webapp restart \
    --name "$APP_SERVICE_NAME" \
    --resource-group "$RESOURCE_GROUP"

echo ""
echo "✅ Deploy concluído!"
echo "   App Service: https://${APP_SERVICE_NAME}.azurewebsites.net"