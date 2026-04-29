"""
main.py — Punto de entrada del Auto DayTrading Bot.

Ejecuta este archivo para iniciar el bot:
    python main.py

Módulos activos:
    [✓] Módulo 1: Setup y Conexión
    [✓] Módulo 2: Motor de Datos         (velas de 15 minutos)
    [✓] Módulo 3: Motor de Análisis      (EMA9/EMA21 + RSI14)
    [✓] Módulo 4: Ejecución y Riesgo     (fracciones + SL/TP manual)
    [✓] Módulo 5: Sentimiento de Noticias (Alpaca News + Claude Haiku)

Scheduler (hora ET, respeta horario de verano automáticamente):
    09:35 ET  → Análisis completo + posible compra (apertura de mercado)
    12:30 ET  → Análisis completo + posible compra o cierre (mediodía)
    cada 30 min → Solo monitoreo de SL/TP de posiciones abiertas

Razón de este diseño para cash account T+1:
    Con liquidación al día siguiente no tiene sentido operar cada 5 minutos.
    Dos ventanas de análisis al día son suficientes, y el monitoreo de
    SL/TP frecuente protege las posiciones entre esas ventanas.
"""

import sys
import time
import schedule
from datetime import datetime
from zoneinfo import ZoneInfo

from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

from src.broker    import get_clients, print_account_summary, get_available_cash, is_market_open
from src.data_feed import get_historical_bars, get_latest_bar, print_latest_bar
from src.analysis  import calculate_indicators, get_signal, print_analysis, Signal
from src.execution import ejecutar_senal, monitorear_sl_tp, get_posiciones_abiertas
from src.sentiment import get_sentiment, print_sentiment
from src.config    import get_config

# ─────────────────────────────────────────────
# CONFIGURACIÓN
# ─────────────────────────────────────────────
SYMBOLS   = ["SPY", "AAPL", "TSLA", "NVDA"]
TIMEFRAME = TimeFrame(15, TimeFrameUnit.Minute)   # Velas de 15 minutos
DAYS_BACK = 5                                      # ~130 velas (26 por día × 5 días)
ET        = ZoneInfo("America/New_York")           # Timezone del mercado (maneja DST solo)

# Horarios de análisis completo (hora ET)
ANALISIS_APERTURA = (9, 35)    # 9:35am — primeros minutos del mercado ya estabilizados
ANALISIS_MEDIODIA = (12, 30)   # 12:30pm — mitad del día de trading

# Registro de jobs ejecutados hoy (evita doble ejecución si el proceso hace tick varias veces en el mismo minuto)
_ejecutados_hoy: set = set()

# Clientes de sesión
trading_client = None
data_client    = None
config         = None


# ─────────────────────────────────────────────
# Inicialización
# ─────────────────────────────────────────────

def iniciar_sesion() -> bool:
    """Conecta con Alpaca y verifica la cuenta."""
    global trading_client, data_client, config
    try:
        print("  Conectando con Alpaca API...")
        config = get_config()
        trading_client, data_client = get_clients()
        print("  ✓ Conexión establecida.\n")
        print_account_summary(trading_client)

        import os
        if os.getenv("ANTHROPIC_API_KEY", "").strip():
            print("  🧠 Módulo 5 (Sentimiento) ACTIVO — usando Claude Haiku\n")
        else:
            print("  ℹ️  Módulo 5 (Sentimiento) inactivo — configura ANTHROPIC_API_KEY para activarlo\n")

        return True
    except (ValueError, ConnectionError, RuntimeError) as e:
        print(f"\n  ✗ ERROR de conexión: {e}")
        return False


# ─────────────────────────────────────────────
# Ciclo de monitoreo (SL/TP cada 30 minutos)
# ─────────────────────────────────────────────

def ciclo_monitoreo():
    """
    Verifica SL/TP de posiciones abiertas sin hacer análisis nuevo.
    Se ejecuta cada 30 minutos durante el horario de mercado.
    """
    posiciones = get_posiciones_abiertas()
    if not posiciones:
        return

    now_et = datetime.now(ET).strftime("%H:%M ET")
    print(f"\n  🔍 [{now_et}] Monitoreo de {len(posiciones)} posición(es):")

    try:
        if not is_market_open(trading_client):
            print("  💤 Mercado cerrado.\n")
            return

        precios = {}
        for symbol in posiciones:
            bar = get_latest_bar(data_client, symbol)
            if bar is not None:
                precios[symbol] = float(bar["close"])

        monitorear_sl_tp(trading_client, precios)

    except Exception as e:
        print(f"  ✗ Error en monitoreo: {e}")


# ─────────────────────────────────────────────
# Ciclo de análisis completo (2 veces al día)
# ─────────────────────────────────────────────

def ciclo_analisis(momento: str):
    """
    Ciclo completo: datos → indicadores → sentimiento → ejecución.
    Se ejecuta a las 9:35am y 12:30pm ET.

    Args:
        momento: "apertura" o "mediodía" (para el log).
    """
    now_et = datetime.now(ET).strftime("%H:%M ET")
    print(f"\n{'='*52}")
    print(f"  ⏱  Ciclo de análisis — {momento.upper()} ({now_et})")
    print(f"{'='*52}")

    try:
        if not is_market_open(trading_client):
            print("  💤 Mercado cerrado — ciclo omitido.\n")
            return

        # — Saldo disponible —
        saldo = get_available_cash(trading_client)
        print(f"  💰 Saldo disponible (T+1): ${saldo:,.2f}")

        # — Monitoreo SL/TP previo al análisis —
        posiciones = get_posiciones_abiertas()
        if posiciones:
            print(f"  🔍 Revisando {len(posiciones)} posición(es) abierta(s):")
            precios = {}
            for symbol in posiciones:
                bar = get_latest_bar(data_client, symbol)
                if bar is not None:
                    precios[symbol] = float(bar["close"])
            monitorear_sl_tp(trading_client, precios)

        # — Análisis por símbolo —
        print("\n  📊 Análisis de señales (velas 15 min):")
        for symbol in SYMBOLS:

            # Módulo 2: datos históricos
            df = get_historical_bars(
                client=data_client,
                symbol=symbol,
                timeframe=TIMEFRAME,
                days_back=DAYS_BACK,
            )
            if df.empty:
                print(f"  🟡 [{symbol}] Sin datos disponibles.")
                continue

            print_latest_bar(symbol, df.iloc[-1])

            # Módulo 3: indicadores y señal técnica
            df_ind = calculate_indicators(df)
            result = get_signal(df_ind, symbol=symbol)
            print_analysis(result)

            # Módulo 5: sentimiento (solo si hay señal BUY)
            senal_final = result.signal
            if result.signal == Signal.BUY:
                sentiment = get_sentiment(
                    symbol=symbol,
                    alpaca_api_key=config["api_key"],
                    alpaca_secret_key=config["secret_key"],
                )
                print_sentiment(sentiment)
                if sentiment.available and sentiment.score < 0:
                    print(f"  ⚠️  [{symbol}] BUY bloqueado por sentimiento negativo.")
                    senal_final = Signal.HOLD

            # Módulo 4: ejecución
            ejecutar_senal(
                trading_client=trading_client,
                symbol=symbol,
                signal=senal_final,
                precio_actual=result.close,
                saldo_disponible=saldo,
            )

        print(f"\n  ✓ Ciclo {momento} completado.\n")

    except Exception as e:
        print(f"  ✗ Error en ciclo de análisis: {e}")


# ─────────────────────────────────────────────
# Tick principal (corre cada minuto)
# ─────────────────────────────────────────────

def tick():
    """
    Se ejecuta cada minuto. Decide qué acción tomar según la hora ET.

    Usa un registro diario (_ejecutados_hoy) para garantizar que cada
    ciclo de análisis corre exactamente una vez por día, aunque el
    proceso haga varios ticks en el mismo minuto.
    """
    global _ejecutados_hoy

    now_et   = datetime.now(ET)
    fecha    = now_et.date()
    hora     = now_et.hour
    minuto   = now_et.minute

    # Resetear registro al cambiar de día
    clave_fecha = str(fecha)
    if not any(k.startswith(clave_fecha) for k in _ejecutados_hoy):
        _ejecutados_hoy = set()

    # — Análisis de apertura: 9:35am ET —
    clave_apertura = f"{fecha}_apertura"
    if (hora, minuto) == ANALISIS_APERTURA and clave_apertura not in _ejecutados_hoy:
        _ejecutados_hoy.add(clave_apertura)
        ciclo_analisis("apertura")
        return

    # — Análisis de mediodía: 12:30pm ET —
    clave_mediodia = f"{fecha}_mediodia"
    if (hora, minuto) == ANALISIS_MEDIODIA and clave_mediodia not in _ejecutados_hoy:
        _ejecutados_hoy.add(clave_mediodia)
        ciclo_analisis("mediodía")
        return

    # — Monitoreo SL/TP: cada 30 minutos (en punto o y media) —
    if minuto in (0, 30):
        clave_monitor = f"{fecha}_{hora}_{minuto}_monitor"
        if clave_monitor not in _ejecutados_hoy:
            _ejecutados_hoy.add(clave_monitor)
            ciclo_monitoreo()


# ─────────────────────────────────────────────
# Punto de entrada
# ─────────────────────────────────────────────

def main():
    """Inicializa el bot y lanza el scheduler."""
    print("\n🤖 Iniciando Auto DayTrading Bot...")

    if not iniciar_sesion():
        sys.exit(1)

    now_et = datetime.now(ET)
    apertura_str = f"{ANALISIS_APERTURA[0]:02d}:{ANALISIS_APERTURA[1]:02d} ET"
    mediodia_str = f"{ANALISIS_MEDIODIA[0]:02d}:{ANALISIS_MEDIODIA[1]:02d} ET"

    print(f"  📅 Hora actual         : {now_et.strftime('%Y-%m-%d %H:%M ET')}")
    print(f"  🔔 Análisis apertura   : {apertura_str}")
    print(f"  🔔 Análisis mediodía   : {mediodia_str}")
    print(f"  🔄 Monitoreo SL/TP     : cada 30 minutos")
    print(f"  📊 Temporalidad velas  : 15 minutos")
    print(f"  📈 Símbolos            : {', '.join(SYMBOLS)}\n")

    # Monitoreo inmediato si hay posiciones abiertas al arrancar
    ciclo_monitoreo()

    # Tick cada minuto
    schedule.every(1).minutes.do(tick)
    print("  🕐 Scheduler activo. Ctrl+C para detener.\n")

    while True:
        schedule.run_pending()
        time.sleep(30)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n  🛑 Bot detenido manualmente.\n")
        sys.exit(0)
