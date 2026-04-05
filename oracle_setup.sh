#!/bin/bash
# ============================================================
# Script de Setup: Docker + WAHA no Oracle Cloud (Ubuntu 22.04)
# Uso: bash oracle_setup.sh
# ============================================================

set -e

echo "=== [1/4] Atualizando sistema ==="
sudo apt-get update -y && sudo apt-get upgrade -y

echo "=== [2/4] Instalando Docker ==="
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker "$USER"

echo "=== [3/4] Configurando firewall (porta 3000) ==="
sudo ufw allow OpenSSH
sudo ufw allow 3000/tcp
sudo ufw --force enable

echo "=== [4/4] Iniciando container WAHA ==="
# Usa newgrp para aplicar grupo docker sem precisar de logout
newgrp docker <<DOCKERCMD
docker run -d \
  --name waha \
  --restart always \
  -p 3000:3000 \
  devlikeapro/waha

echo ""
echo "✅ WAHA rodando!"
docker ps --filter name=waha --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
DOCKERCMD

echo ""
echo "============================================================"
echo "  WAHA instalado com sucesso!"
echo ""
echo "  Próximos passos:"
echo "  1. Acesse no browser: http://$(curl -s ifconfig.me):3000"
echo "  2. Clique em 'Start' para iniciar a sessão WhatsApp"
echo "  3. Escaneie o QR code com seu WhatsApp"
echo "  4. Adicione nas secrets do GitHub:"
echo "     WAHA_URL = http://$(curl -s ifconfig.me):3000"
echo "     WAHA_SESSION = default"
echo "     WAHA_API_KEY = (deixar vazio ou definir no dashboard)"
echo "============================================================"
