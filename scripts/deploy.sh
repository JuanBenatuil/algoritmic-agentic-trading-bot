#!/bin/bash
# =============================================================
# deploy.sh — Actualizar el bot en el VPS
# =============================================================
# Ejecutar cada vez que hagas cambios en el código y quieras
# que el VPS los refleje.
#
# Uso (desde el VPS, dentro del directorio del proyecto):
#   bash scripts/deploy.sh
# =============================================================

set -e

APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$APP_DIR"

echo ""
echo "======================================================"
echo "  🔄  Actualizando Auto DayTrading Bot"
echo "======================================================"

# ── 1. Bajar el bot ────────────────────────────────────────
echo ""
echo "→ [1/4] Deteniendo bot..."
docker compose down tradingbot
echo "   ✓ Detenido."

# ── 2. Traer últimos cambios del repo ─────────────────────
echo ""
echo "→ [2/4] Descargando últimos cambios..."
git pull origin master
echo "   ✓ Código actualizado."

# ── 3. Rebuild de la imagen ───────────────────────────────
echo ""
echo "→ [3/4] Reconstruyendo imagen Docker..."
docker compose build tradingbot
echo "   ✓ Imagen lista."

# ── 4. Levantar el bot ────────────────────────────────────
echo ""
echo "→ [4/4] Levantando bot..."
docker compose up -d tradingbot
echo "   ✓ Bot en marcha."

echo ""
echo "======================================================"
echo "  ✅  Deploy completado."
echo "======================================================"
echo ""
echo "  Ver logs: docker logs -f tradingbot-tradingbot-1"
echo ""
