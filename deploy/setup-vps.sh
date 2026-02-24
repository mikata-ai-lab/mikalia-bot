#!/bin/bash
# ============================================================
# setup-vps.sh — Script de setup para VPS (Hetzner CX22)
# ============================================================
# Uso: scp este archivo al VPS y ejecuta:
#   chmod +x setup-vps.sh && sudo ./setup-vps.sh
# ============================================================

set -euo pipefail

echo "=== Mikalia VPS Setup ==="

# 1. Actualizar sistema
echo "[1/6] Actualizando sistema..."
apt-get update && apt-get upgrade -y

# 2. Instalar Docker
echo "[2/6] Instalando Docker..."
if ! command -v docker &> /dev/null; then
    curl -fsSL https://get.docker.com -o get-docker.sh
    sh get-docker.sh
    rm get-docker.sh
    systemctl enable docker
    systemctl start docker
fi

# 3. Instalar Docker Compose plugin
echo "[3/6] Verificando Docker Compose..."
docker compose version || {
    apt-get install -y docker-compose-plugin
}

# 4. Instalar Nginx
echo "[4/6] Instalando Nginx..."
apt-get install -y nginx

# 5. Instalar Certbot
echo "[5/6] Instalando Certbot..."
apt-get install -y certbot python3-certbot-nginx

# 6. Crear directorio de la app
echo "[6/6] Preparando directorio..."
mkdir -p /opt/mikalia
chown $SUDO_USER:$SUDO_USER /opt/mikalia

echo ""
echo "=== Setup completo ==="
echo ""
echo "Siguientes pasos:"
echo "  1. cd /opt/mikalia"
echo "  2. git clone https://github.com/mikata-ai-lab/mikalia-bot.git ."
echo "  3. cp .env.example .env && nano .env  (agregar API keys)"
echo "  4. docker compose up -d"
echo "  5. Configurar DNS: mikalia.mikata-ai-lab.com -> IP del VPS"
echo "  6. cp deploy/nginx.conf /etc/nginx/sites-available/mikalia"
echo "     ln -s /etc/nginx/sites-available/mikalia /etc/nginx/sites-enabled/"
echo "     certbot --nginx -d mikalia.mikata-ai-lab.com"
echo "     systemctl reload nginx"
echo ""
echo "Verificar: docker compose logs -f mikalia"
