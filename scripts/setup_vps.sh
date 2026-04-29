#!/bin/bash
# =============================================================
# setup_vps.sh — Instalación del Auto DayTrading Bot en VPS
# =============================================================
# Ejecutar UNA SOLA VEZ en un VPS Ubuntu 22.04 / Debian 12 limpio.
#
# Uso:
#   curl -fsSL <URL_RAW_GITHUB>/scripts/setup_vps.sh | bash
#   o bien:
#   bash scripts/setup_vps.sh
# =============================================================

set -e  # Detener si cualquier comando falla

REPO_URL="https://github.com/TU_USUARIO/TradingBot.git"   # <-- cambia esto
APP_DIR="$HOME/tradingbot"
COMPOSE_FILE="$APP_DIR/docker-compose.yml"

echo ""
echo "======================================================"
echo "  🤖  Setup Auto DayTrading Bot — VPS"
echo "======================================================"

# ── 1. Actualizar sistema ──────────────────────────────────
echo ""
echo "→ [1/6] Actualizando sistema..."
sudo apt-get update -q && sudo apt-get upgrade -y -q

# ── 2. Instalar Docker ─────────────────────────────────────
echo ""
echo "→ [2/6] Instalando Docker..."
if command -v docker &>/dev/null; then
    echo "   Docker ya está instalado: $(docker --version)"
else
    curl -fsSL https://get.docker.com | sudo sh
    sudo usermod -aG docker "$USER"
    echo "   ✓ Docker instalado."
fi

# ── 3. Verificar Docker Compose ────────────────────────────
echo ""
echo "→ [3/6] Verificando Docker Compose..."
if docker compose version &>/dev/null; then
    echo "   ✓ $(docker compose version)"
else
    sudo apt-get install -y -q docker-compose-plugin
    echo "   ✓ Docker Compose instalado."
fi

# ── 4. Clonar repositorio ──────────────────────────────────
echo ""
echo "→ [4/6] Clonando repositorio..."
if [ -d "$APP_DIR" ]; then
    echo "   Directorio ya existe — haciendo git pull..."
    cd "$APP_DIR" && git pull
else
    git clone "$REPO_URL" "$APP_DIR"
    echo "   ✓ Repositorio clonado en $APP_DIR"
fi

# ── 5. Crear archivo .env ──────────────────────────────────
echo ""
echo "→ [5/6] Configurando variables de entorno..."
if [ -f "$APP_DIR/.env" ]; then
    echo "   .env ya existe — no se sobreescribe."
else
    cp "$APP_DIR/.env.example" "$APP_DIR/.env"
    echo ""
    echo "   ⚠️  IMPORTANTE: debes rellenar el archivo .env con tus credenciales."
    echo "   Edítalo con:"
    echo "       nano $APP_DIR/.env"
    echo ""
    echo "   Necesitas:"
    echo "     ALPACA_API_KEY    → tu key de Paper Trading en app.alpaca.markets"
    echo "     ALPACA_SECRET_KEY → tu secret de Paper Trading"
    echo "     ALPACA_MODE       → paper"
    echo "     ANTHROPIC_API_KEY → opcional, para el módulo de sentimiento"
    echo ""
    read -p "   ¿Quieres editar el .env ahora? [s/N]: " respuesta
    if [[ "$respuesta" =~ ^[sS]$ ]]; then
        nano "$APP_DIR/.env"
    fi
fi

# ── 6. Construir y levantar el bot ─────────────────────────
echo ""
echo "→ [6/6] Construyendo imagen Docker y levantando el bot..."
cd "$APP_DIR"

# Aplicar permisos de Docker sin cerrar sesión (newgrp crea subshell)
sg docker -c "docker compose up -d --build tradingbot"

echo ""
echo "======================================================"
echo "  ✅  Bot desplegado correctamente."
echo "======================================================"
echo ""
echo "  Comandos útiles:"
echo "    Ver logs en vivo   : docker logs -f tradingbot-tradingbot-1"
echo "    Detener el bot     : docker compose -f $COMPOSE_FILE down"
echo "    Actualizar el bot  : cd $APP_DIR && bash scripts/deploy.sh"
echo ""
echo "  El bot correrá automáticamente si el servidor se reinicia"
echo "  gracias a la política restart: unless-stopped en docker-compose.yml"
echo ""
