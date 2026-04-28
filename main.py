"""
main.py — Punto de entrada del Auto DayTrading Bot.

Ejecuta este archivo para iniciar el bot:
    python main.py

Módulos activos:
    [✓] Módulo 1: Setup y Conexión
    [ ] Módulo 2: Motor de Datos
    [ ] Módulo 3: Motor de Análisis
    [ ] Módulo 4: Ejecución y Riesgo
    [ ] Módulo 5: Sentimiento de Noticias
"""

import sys
import time
import schedule
from src.broker import get_clients, print_account_summary, get_available_cash

# Clientes globales de sesión (se inicializan una vez al arrancar)
trading_client = None
data_client = None


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
    Aquí se irán agregando los módulos 2, 3 y 4 progresivamente.
    """
    print("\n  ⏱  Ejecutando ciclo de trading...")

    try:
        saldo = get_available_cash(trading_client)
        print(f"  💰 Saldo disponible (T+1): ${saldo:,.2f}")

        # — Módulo 2: Motor de Datos      (próximamente) —
        # — Módulo 3: Motor de Análisis   (próximamente) —
        # — Módulo 4: Ejecución y Riesgo  (próximamente) —

        print("  ✓ Ciclo completado.\n")

    except Exception as e:
        print(f"  ✗ Error en el ciclo: {e}")


def main():
    """Función principal: inicializa el bot y lanza el scheduler."""
    print("\n🤖 Iniciando Auto DayTrading Bot...")

    if not iniciar_sesion():
        sys.exit(1)

    # Programar el ciclo cada 5 minutos
    # (el intervalo se ajustará cuando implementemos la estrategia real)
    schedule.every(5).minutes.do(ciclo_de_trading)
    print("  🕐 Scheduler activo — ciclo cada 5 minutos. Ctrl+C para detener.\n")

    # Loop principal: mantiene el proceso vivo y dispara las tareas programadas
    while True:
        schedule.run_pending()
        time.sleep(10)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n  🛑 Bot detenido manualmente.\n")
        sys.exit(0)
