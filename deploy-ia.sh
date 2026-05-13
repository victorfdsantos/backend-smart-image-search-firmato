#!/usr/bin/env bash
# =============================================================================
# deploy-ai-vm.sh
# Executa na VM Azure para subir/atualizar o AI Service.
#
# Uso (da sua máquina local):
#   ssh usuario@IP_DA_VM 'bash -s' < deploy-ai-vm.sh
#
# Ou copie o script para a VM e execute lá:
#   scp deploy-ai-vm.sh usuario@IP_DA_VM:~/
#   ssh usuario@IP_DA_VM './deploy-ai-vm.sh'
# =============================================================================

set -euo pipefail

REPO_DIR="${HOME}/firmato"

echo "▶ Atualizando código..."
if [ -d "$REPO_DIR" ]; then
    cd "$REPO_DIR"
    git pull
else
    git clone <URL_DO_SEU_REPO> "$REPO_DIR"
    cd "$REPO_DIR"
fi

echo "▶ Verificando arquivo .env..."
if [ ! -f .env ]; then
    echo "ERRO: arquivo .env não encontrado em $REPO_DIR"
    echo "Crie o arquivo com AZURE_STORAGE_CONNECTION_STRING preenchido."
    exit 1
fi

echo "▶ Build e subida do AI Service..."
docker compose -f docker-compose.ai.yml build
docker compose -f docker-compose.ai.yml up -d

echo "▶ Aguardando healthcheck..."
sleep 10
docker compose -f docker-compose.ai.yml ps

echo ""
echo "✅ AI Service no ar!"
echo "   Health: http://$(hostname -I | awk '{print $1}'):9000/health"