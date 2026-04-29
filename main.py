"""
main.py — Punto de entrada del Auto DayTrading Bot.

Ejecuta este archivo para iniciar el bot:
    python main.py

Módulos activos:
    [✓] Módulo 1: Setup y Conexión
    [✓] Módulo 2: Motor de Datos
    [✓] Módulo 3: Motor de Análisis
    [✓] Módulo 4: Ejecución y Riesgo (fracciones + SL/TP manual)
    [ ] Módulo 5: Sentimiento de Noticias
"""

import sys
import time
import schedule
from alpaca.data.timeframe import TimeFrame

from src.broker    import get_clients, print_account_summary, get_available_cash, is_market_open
from src.data_feed import get_historical_bars, get_latest_bar, print_latest_bar
from src.analysis  import calculate_indicators, get_signal, print_analysis, Signal
from src.execution import (
    ejecutar_senal, monitorear_sl_tp,
    get_posiciones_abiertas, tiene_posicion_abierta,
)

# ─────────────────────────────────────────────
# CONFIGURACIÓN
# ─────────────────────────────────────────────
SYMBOLS   = ["SPY", "AAPL", "TSLA", "NVDA"]
TIMEFRAME = TimeFrame.Minute
DAYS_BACK = 2

# Clientes de sesión (se inicializan una vez al arrancar)
trading_client = None
data_client    = None


def iniciar_sesion() -> bool:
    """Conecta con Alpaca y verifica la cuenta."""
    global trading_client, data_client
    try:
        print("  Conectando con Alpaca API...")
        trading_client, data_client = get_clients()
        print("  ✓ Conexión establecida.\n")
        print_account_summary(trading_client)
        return True
    except (ValueError, ConnectionError, RuntimeError) as e:
        print(f"\n  ✗ ERROR de conexión: {e}")
        return False


def ciclo_de_trading():
    """
    Ciclo principal del bot. Se ejecuta en cada intervalo programado.

    Flujo:
        1. Verificar horario de mercado.
        2. [Módulo 1] Saldo disponible (T+1).
        3. [Módulo 4] Monitorear SL/TP de posiciones ya abiertas.
        4. Por cada símbolo:
           a. [Módulo 2] Obtener datos históricos.
           b. [Módulo 3] Calcular indicadores y señal.
           c. [Módulo 4] Ejecutar acción (compra fraccionaria o cierre).
    """
    print("\n  ⏱  Ejecutando ciclo de trading...")

    try:
        # — Paso 1: Horario de mercado —
        if not is_market_open(trading_client):
            print("  💤 Mercado cerrado — ciclo omitido.\n")
            return

        # — Paso 2: Saldo disponible —
        saldo = get_available_cash(trading_client)
        print(f"  💰 Saldo disponible (T+1): ${saldo:,.2f}")

        # — Paso 3: Monitoreo de SL/TP de posiciones abiertas —
        posiciones = get_posiciones_abiertas()
        if posiciones:
            print(f"  🔍 Monitoreando {len(posiciones)} posición(es) abierta(s):")
            # Obtener precio actual de cada posición abierta
            precios = {}
            for symbol in posiciones:
                bar = get_latest_bar(data_client, symbol)
                if bar is not None:
                    precios[symbol] = float(bar["close"])
            monitorear_sl_tp(trading_client, precios)

        # — Paso 4: Análisis y ejecución por símbolo —
        print("  📊 Análisis de señales:")
        for symbol in SYMBOLS:
            # a. Datos históricos
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

            # b. Indicadores y señal
            df_ind = calculate_indicators(df)
            result = get_signal(df_ind, symbol=symbol)
            print_analysis(result)

            # c. Ejecución (solo si no tiene ya posición abierta para BUY)
            ejecutar_senal(
                trading_client=trading_client,
                symbol=symbol,
                signal=result.signal,
                precio_actual=result.close,
                saldo_disponible=saldo,
            )

        print("  ✓ Ciclo completado.\n")

    except Exception as e:
        print(f"  ✗ Error en el ciclo: {e}")


def main():
    """Función principal: inicializa el bot y lanza el scheduler."""
    print("\n🤖 Iniciando Auto DayTrading Bot...")

    if not iniciar_sesion():
        sys.exit(1)

    ciclo_de_trading()

    schedule.every(5).minutes.do(ciclo_de_trading)
    print("  🕐 Scheduler activo — ciclo cada 5 minutos. Ctrl+C para detener.\n")

    while True:
        schedule.run_pending()
        time.sleep(10)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n  🛑 Bot detenido manualmente.\n")
        sys.exit(0)
