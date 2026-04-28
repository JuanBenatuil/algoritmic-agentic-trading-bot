"""
main.py — Punto de entrada del Auto DayTrading Bot.

Ejecuta este archivo para iniciar el bot:
    python main.py

Módulos activos:
    [✓] Módulo 1: Setup y Conexión
    [✓] Módulo 2: Motor de Datos
    [✓] Módulo 3: Motor de Análisis
    [✓] Módulo 4: Ejecución y Riesgo
    [ ] Módulo 5: Sentimiento de Noticias
"""

import sys
import time
import schedule
from alpaca.data.timeframe import TimeFrame

from src.broker    import get_clients, print_account_summary, get_available_cash, is_market_open
from src.data_feed import get_historical_bars, get_latest_quote, print_latest_bar
from src.analysis  import calculate_indicators, get_signal, print_analysis, Signal
from src.execution import ejecutar_senal

# ─────────────────────────────────────────────
# CONFIGURACIÓN
# ─────────────────────────────────────────────
SYMBOLS    = ["SPY", "AAPL", "TSLA"]
TIMEFRAME  = TimeFrame.Minute
DAYS_BACK  = 2       # Histórico para indicadores

# Clientes de sesión (se inicializan una vez al arrancar)
trading_client = None
data_client    = None


def iniciar_sesion() -> bool:
    """
    Conecta con Alpaca y verifica la cuenta.
    Retorna True si la conexión fue exitosa.
    """
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

    Flujo completo:
        1. Verificar si el mercado está abierto → si no, saltar.
        2. [Módulo 1] Leer saldo disponible (T+1).
        3. Por cada símbolo en SYMBOLS:
           a. [Módulo 2] Obtener velas históricas.
           b. [Módulo 3] Calcular indicadores y generar señal.
           c. [Módulo 4] Ejecutar acción según señal (BUY/SELL/HOLD).
    """
    print("\n  ⏱  Ejecutando ciclo de trading...")

    try:
        # — Paso 1: Verificar horario de mercado —
        if not is_market_open(trading_client):
            print("  💤 Mercado cerrado — ciclo omitido.\n")
            return

        # — Paso 2: Saldo disponible (Módulo 1) —
        saldo = get_available_cash(trading_client)
        print(f"  💰 Saldo disponible (T+1): ${saldo:,.2f}")

        print("  📊 Análisis y ejecución:")
        for symbol in SYMBOLS:
            # — Paso 3a: Datos históricos (Módulo 2) —
            df = get_historical_bars(
                client=data_client,
                symbol=symbol,
                timeframe=TIMEFRAME,
                days_back=DAYS_BACK,
            )

            if df.empty:
                print(f"  🟡 [{symbol}] Sin datos históricos disponibles.")
                continue

            # Mostrar última vela
            print_latest_bar(symbol, df.iloc[-1])

            # — Paso 3b: Calcular indicadores y señal (Módulo 3) —
            df_ind = calculate_indicators(df)
            result = get_signal(df_ind, symbol=symbol)
            print_analysis(result)

            # — Paso 3c: Ejecutar según señal (Módulo 4) —
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

    # Ejecutar un ciclo inmediato al arrancar
    ciclo_de_trading()

    # Programar ciclos cada 5 minutos
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
