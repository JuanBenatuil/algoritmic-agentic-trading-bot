"""
broker.py — Módulo 1: Setup y Conexión a Alpaca.

Responsabilidades:
- Inicializar los clientes de la API de Alpaca.
- Verificar el estado de la cuenta (saldo, estado, modo).
- Calcular el saldo disponible real considerando la liquidación T+1.
"""

from alpaca.trading.client import TradingClient
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.trading.models import TradeAccount
from src.config import get_config


def is_market_open(trading_client: TradingClient) -> bool:
    """
    Consulta el reloj de Alpaca para saber si el mercado está abierto.

    El mercado de EE. UU. opera de lunes a viernes de 9:30 a 16:00 ET.
    Esta función debe llamarse al inicio de cada ciclo para evitar intentar
    operar fuera de horario (las órdenes de mercado serían rechazadas).

    Args:
        trading_client: Cliente de trading de Alpaca ya inicializado.

    Returns:
        bool: True si el mercado está abierto ahora mismo.

    Raises:
        RuntimeError: Si la consulta a la API falla.
    """
    try:
        clock = trading_client.get_clock()
        return clock.is_open
    except Exception as e:
        raise RuntimeError(f"Error al consultar el estado del mercado: {e}") from e


def get_clients() -> tuple[TradingClient, StockHistoricalDataClient]:
    """
    Inicializa y retorna los clientes de Alpaca para trading y datos.

    Returns:
        tuple: (TradingClient, StockHistoricalDataClient)

    Raises:
        ConnectionError: Si no se puede establecer conexión con la API.
    """
    try:
        config = get_config()
        trading_client = TradingClient(
            api_key=config["api_key"],
            secret_key=config["secret_key"],
            paper=config["paper"],
        )
        data_client = StockHistoricalDataClient(
            api_key=config["api_key"],
            secret_key=config["secret_key"],
        )
        return trading_client, data_client
    except Exception as e:
        raise ConnectionError(f"No se pudo conectar con la API de Alpaca: {e}") from e


def get_account_info(trading_client: TradingClient) -> TradeAccount:
    """
    Consulta y retorna la información completa de la cuenta.

    Args:
        trading_client: Cliente de trading de Alpaca ya inicializado.

    Returns:
        TradeAccount: Objeto con todos los datos de la cuenta.

    Raises:
        RuntimeError: Si la consulta a la API falla.
    """
    try:
        account = trading_client.get_account()
        return account
    except Exception as e:
        raise RuntimeError(f"Error al consultar la cuenta: {e}") from e


def get_available_cash(trading_client: TradingClient) -> float:
    """
    Calcula el saldo de efectivo REAL disponible para operar.

    En una Cash Account, el dinero de ventas recientes tarda T+1 en
    liquidarse. Alpaca expone 'cash' (total) y 'cash_withdrawable'
    (ya liquidado). Usamos el más conservador para evitar operar
    con fondos no liquidados.

    Args:
        trading_client: Cliente de trading de Alpaca ya inicializado.

    Returns:
        float: Saldo disponible en dólares, respetando la liquidación T+1.
    """
    try:
        account = get_account_info(trading_client)
        # 'buying_power' en cash accounts equivale al efectivo disponible real
        # 'cash' puede incluir fondos pendientes de liquidar
        buying_power = float(account.buying_power)
        cash = float(account.cash)

        # Retornamos el menor de los dos como medida de seguridad
        available = min(buying_power, cash)
        return available
    except Exception as e:
        raise RuntimeError(f"Error al calcular saldo disponible: {e}") from e


def print_account_summary(trading_client: TradingClient) -> None:
    """
    Imprime en consola un resumen legible del estado de la cuenta.

    Args:
        trading_client: Cliente de trading de Alpaca ya inicializado.
    """
    account = get_account_info(trading_client)

    print("=" * 50)
    print("  ESTADO DE CUENTA — ALPACA PAPER TRADING")
    print("=" * 50)
    print(f"  Estado de la cuenta : {account.status.value}")
    print(f"  Valor del portafolio : ${float(account.portfolio_value):,.2f}")
    print(f"  Efectivo total       : ${float(account.cash):,.2f}")
    print(f"  Buying Power         : ${float(account.buying_power):,.2f}")
    print(f"  Acciones en cartera  : ${float(account.long_market_value):,.2f}")
    print(f"  Day trades (5 días)  : {account.daytrade_count}")
    print("=" * 50)
