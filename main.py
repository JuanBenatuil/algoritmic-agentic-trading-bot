"""
main.py — Punto de entrada del Auto DayTrading Bot.

Ejecuta este archivo para iniciar el bot:
    python main.py

Módulos activos:
    [✓] Módulo 1: Setup y Conexión
    [✓] Módulo 2: Motor de Datos
    [✓] Módulo 3: Motor de Análisis
    [ ] Módulo 4: Ejecución y Riesgo
    [ ] Módulo 5: Sentimiento de Noticias
"""

import sys
import time
import schedule
from alpaca.data.timeframe import TimeFrame

from src.broker   import get_clients, print_account_summary, get_available_cash, is_market_open
from src.data_feed import get_historical_bars, get_latest_quote, print_latest_bar
from src.analysis  import calculate_indicators, get_signal, print_analysis, Signal

# ─────────────────────────────────────────────
# CONFIGURACIÓN
# ─────────────────────────────────────────────
SYMBOLS    = ["SPY", "AAPL", "TSLA"]
TIMEFRAME  = TimeFrame.Minute   # Velas de 1 minuto
DAYS_BACK  = 2                  # Histórico para calcular indicadores (2 días = ~780 velas de 1 min)

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

    Flujo:
        1. Verificar si el mercado está abierto → si no, saltar.
        2. [Módulo 1] Leer saldo disponible (T+1).
        3. [Módulo 2] Obtener velas históricas y cotización de cada símbolo.
        4. [Módulo 3] Calcular indicadores y generar señal BUY/SELL/HOLD.
        5. [Módulo 4] Ejecutar órdenes según señal (próximamente).
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

        print("  📊 Análisis de señales:")
        for symbol in SYMBOLS:
            # — Paso 3: Obtener datos históricos (Módulo 2) —
            df = get_historical_bars(
                client=data_client,
                symbol=symbol,
                timeframe=TIMEFRAME,
                days_back=DAYS_BACK,
            )

            if df.empty:
                print(f"  🟡 [{symbol}] Sin datos históricos disponibles.")
                continue

            # Mostrar última vela (timestamp es el índice — bar.name)
            last = df.iloc[-1]
            print_latest_bar(symbol, last)

            # — Paso 4: Calcular indicadores y señal (Módulo 3) —
            df_ind = calculate_indicators(df)
            result = get_signal(df_ind, symbol=symbol)
            print_analysis(result)

            # — Paso 5: Ejecutar orden (Módulo 4 — próximamente) —
            if result.signal == Signal.BUY:
                print(f"  ℹ️  [{symbol}] Señal BUY detectada — ejecución pendiente (Módulo 4)")
            elif result.signal == Signal.SELL:
                print(f"  ℹ️  [{symbol}] Señal SELL detectada — ejecución pendiente (Módulo 4)")

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
