# Despliegue en Google Cloud Platform (Gratis)

## Por qué GCP e2-micro

Google Cloud ofrece una instancia **e2-micro permanentemente gratuita** (no expira).
- 1 vCPU compartida, 1 GB RAM
- 30 GB de disco HDD
- 1 GB de egreso de red mensual
- Regiones elegibles: `us-west1`, `us-central1`, `us-east1`

Suficiente para este bot que apenas consume ~250 MB de RAM.

---

## Paso 1 — Crear cuenta en GCP

1. Ve a [cloud.google.com](https://cloud.google.com) e inicia sesión con tu cuenta de Google.
2. Activa la cuenta (pide tarjeta de crédito para verificación, **no te cobra nada**).
3. Crea un nuevo proyecto: menú superior → "Seleccionar proyecto" → "Nuevo proyecto" → llámalo `tradingbot`.

---

## Paso 2 — Crear la VM gratuita

1. En el menú lateral: **Compute Engine → Instancias de VM → Crear instancia**
2. Configura así:

| Campo | Valor |
|-------|-------|
| Nombre | `tradingbot` |
| Región | `us-central1` (Iowa) |
| Zona | `us-central1-a` |
| Serie | `E2` |
| Tipo de máquina | `e2-micro` ← **importante para que sea gratis** |
| Sistema operativo | Ubuntu 22.04 LTS |
| Disco de arranque | 30 GB HDD estándar |
| Firewall | ✅ Permitir tráfico HTTP (no es necesario pero no hace daño) |

3. Haz clic en **Crear**. En ~1 minuto estará lista.

> ⚠️ Verifica que aparezca el mensaje "Tu instancia es parte del nivel gratuito" antes de crearla.

---

## Paso 3 — Subir el código a GitHub

El bot vive en Git. Antes de conectarte al VPS, sube tu código:

```bash
# En tu máquina local (PowerShell o terminal)
cd "C:\Users\jdben\OneDrive\Documents\AAa Mis Cosas\A Proyectos varios\TradingBot"
git remote add origin https://github.com/TU_USUARIO/TradingBot.git
git push -u origin master
```

> El `.env` está en `.gitignore` — tus credenciales nunca se subirán al repo.

---

## Paso 4 — Conectarte al VPS

En la página de tu VM en GCP, haz clic en **SSH** (abre una terminal en el navegador).

También puedes usar la terminal local si tienes `gcloud` instalado:
```bash
gcloud compute ssh tradingbot --zone=us-central1-a
```

---

## Paso 5 — Instalar Docker y desplegar el bot

Una vez dentro del VPS, ejecuta el script de setup:

```bash
# Descarga y ejecuta el script de instalación
curl -fsSL https://raw.githubusercontent.com/TU_USUARIO/TradingBot/master/scripts/setup_vps.sh | bash
```

El script hará automáticamente:
1. Actualizar el sistema
2. Instalar Docker y Docker Compose
3. Clonar tu repositorio
4. Pedirte que configures el `.env` con tus credenciales
5. Construir la imagen y levantar el bot

---

## Paso 6 — Configurar credenciales en el VPS

El script abre `nano` para que edites el `.env`. Si lo cerraste sin editar:

```bash
nano ~/tradingbot/.env
```

Rellena:
```
ALPACA_API_KEY=tu_key_real_aqui
ALPACA_SECRET_KEY=tu_secret_real_aqui
ALPACA_MODE=paper
ANTHROPIC_API_KEY=tu_key_de_anthropic  # opcional
```

Guardar en nano: `Ctrl+O` → `Enter` → `Ctrl+X`

Luego reinicia el bot:
```bash
cd ~/tradingbot && docker compose up -d tradingbot
```

---

## Comandos de operación diaria

```bash
# Ver logs en tiempo real
docker logs -f tradingbot-tradingbot-1

# Ver últimas 50 líneas de log
docker logs --tail=50 tradingbot-tradingbot-1

# Ver estado del contenedor
docker compose ps

# Detener el bot
docker compose down

# Reiniciar el bot
docker compose restart tradingbot

# Actualizar el bot con nuevos cambios del código
cd ~/tradingbot && bash scripts/deploy.sh
```

---

## El bot sobrevive reinicios automáticamente

Gracias a `restart: unless-stopped` en `docker-compose.yml`, si el VPS se reinicia (por mantenimiento de GCP, por ejemplo), el bot vuelve a arrancar solo sin que tengas que hacer nada.

---

## Monitoreo de logs (qué verás cada día)

```
🤖 Iniciando Auto DayTrading Bot...
  ✓ Conexión establecida.
  Estado de la cuenta : ACTIVE
  Valor del portafolio : $450.00
  ...
  🔔 Análisis apertura   : 09:35 ET
  🔔 Análisis mediodía   : 12:30 ET

# A las 9:35am ET:
==================================================
  ⏱  Ciclo de análisis — APERTURA (09:35 ET)
==================================================
  💰 Saldo disponible (T+1): $450.00
  📊 Análisis de señales (velas 15 min):
  [SPY] 2026-05-01 13:35 UTC | O:710.20  C:711.80  Vol:12,450
  🟢 [SPY] BUY | EMA9: 711.50  EMA21: 710.80  RSI: 52.3 | Golden cross
  📰🟢 [SPY] Sentimiento: ALCISTA | datos de empleo superan expectativas
  ✅ [SPY] COMPRA fraccionaria — $45.00 (~0.0633 acc) × $710.80 | SL: $696.58 | TP: $739.23

# A las 10:00am ET (monitoreo SL/TP):
  🔍 Monitoreando 1 posición(es):
  📌 [SPY] entrada: $710.80 | actual: $712.50 | P&L: +0.24% | SL: $696.58 | TP: $739.23
```

---

## Costos estimados

| Recurso | Costo |
|---------|-------|
| VM e2-micro (us-central1) | **$0/mes** (free tier) |
| Disco 30 GB HDD | **$0/mes** (incluido en free tier) |
| Egreso de red | **$0/mes** (bien bajo del límite de 1 GB) |
| Llamadas a Anthropic (Claude Haiku) | ~$0.001 por ciclo × 2/día ≈ **$0.06/mes** |
| **Total** | **~$0.06/mes** |
