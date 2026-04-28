"""
execution.py — Módulo 4: Ejecución y Riesgo.

Responsabilidades:
- Calcular tamaño de posición respetando el saldo T+1 disponible.
- Enviar Bracket Orders (entrada + Stop-Loss + Take-Profit en un solo paquete).
- Verificar si ya existe una posición abierta antes de comprar.
- Cerrar posiciones cuando la señal de análisis lo indique.

Reglas de riesgo inquebrantables:
    1. Nunca operar con fondos no liquidados (T+1).
    2. Toda compra lleva Stop-Loss y Take-Profit obligatorio (Bracket Order).
    3. Nunca abrir una segunda posición en el mismo símbolo si ya hay una abierta.
    4. No operar si el saldo disponible es menor al mínimo configurado.

Parámetros de riesgo (ajustables):
    RISK_PER_TRADE  : % del capital que se arriesga por operación.
    STOP_LOSS_PCT   : % de caída máxima aceptada desde el precio de entrada.
    TAKE_PROFIT_PCT : % de ganancia objetivo desde el precio de entrada.
    MIN_CASH        : Saldo mínimo para operar (protección de capital).
"""

from alpaca.trading.client import TradingClient
from alpaca.trading.requests import (
    MarketOrderRequest,
    TakeProfitRequest,
    StopLossRequest,
)
from alpaca.trading.enums import OrderSide, TimeInForce, OrderClass

# ─────────────────────────────────────────────
# Parámetros de gestión de riesgo
# ─────────────────────────────────────────────
RISK_PER_TRADE  = 0.10   # Arriesgar máximo 10% del saldo disponible por operación
STOP_LOSS_PCT   = 0.02   # Stop-Loss: 2% por debajo del precio de entrada
TAKE_PROFIT_PCT = 0.04   # Take-Profit: 4% por encima (ratio riesgo/beneficio 1:2)
MIN_CASH        = 10.0   # No operar si hay menos de $10 disponibles


def calcular_cantidad(precio: float, saldo_disponible: float) -> int:
    """
    Calcula cuántas acciones comprar respetando el riesgo por operación.

    Usa RISK_PER_TRADE para limitar la exposición. Retorna un entero
    porque Alpaca Cash Accounts solo admite acciones enteras.

    Args:
        precio:            Precio actual del activo.
        saldo_disponible:  Efectivo real disponible (T+1).

    Returns:
        int: Número de acciones a comprar (0 si no alcanza para 1).
    """
    capital_a_usar = saldo_disponible * RISK_PER_TRADE
    cantidad = int(capital_a_usar / precio)
    return cantidad


def tiene_posicion_abierta(trading_client: TradingClient, symbol: str) -> bool:
    """
    Verifica si ya existe una posición abierta para el símbolo dado.

    Evita duplicar posiciones en el mismo activo.

    Args:
        trading_client: Cliente de trading de Alpaca.
        symbol:         Ticker del activo.

    Returns:
        bool: True si hay una posición abierta para el símbolo.

    Raises:
        RuntimeError: Si la consulta a la API falla.
    """
    try:
        posiciones = trading_client.get_all_positions()
        simbolos_abiertos = {p.symbol for p in posiciones}
        return symbol in simbolos_abiertos
    except Exception as e:
        raise RuntimeError(f"Error al consultar posiciones abiertas: {e}") from e


def enviar_bracket_order(
    trading_client: TradingClient,
    symbol: str,
    cantidad: int,
    precio_entrada: float,
) -> dict | None:
    """
    Envía una Bracket Order: entrada de mercado + Stop-Loss + Take-Profit.

    Una Bracket Order es atómica: si la entrada se ejecuta, el broker
    coloca automáticamente las órdenes de salida. No requiere monitoreo
    manual del precio.

    Estructura:
        - Entrada:      Market Order (precio actual de mercado)
        - Stop-Loss:    precio_entrada * (1 - STOP_LOSS_PCT)
        - Take-Profit:  precio_entrada * (1 + TAKE_PROFIT_PCT)

    Args:
        trading_client: Cliente de trading de Alpaca.
        symbol:         Ticker del activo.
        cantidad:       Número de acciones a comprar.
        precio_entrada: Precio de referencia para calcular SL y TP.

    Returns:
        dict con {order_id, symbol, qty, stop_loss, take_profit} si se envió,
        None si la orden fue rechazada.

    Raises:
        RuntimeError: Si la llamada a la API falla por error de red.
    """
    stop_loss_price   = round(precio_entrada * (1 - STOP_LOSS_PCT), 2)
    take_profit_price = round(precio_entrada * (1 + TAKE_PROFIT_PCT), 2)

    try:
        orden = MarketOrderRequest(
            symbol=symbol,
            qty=cantidad,
            side=OrderSide.BUY,
            time_in_force=TimeInForce.DAY,
            order_class=OrderClass.BRACKET,
            take_profit=TakeProfitRequest(limit_price=take_profit_price),
            stop_loss=StopLossRequest(stop_price=stop_loss_price),
        )

        respuesta = trading_client.submit_order(orden)

        return {
            "order_id":   str(respuesta.id),
            "symbol":     symbol,
            "qty":        cantidad,
            "stop_loss":  stop_loss_price,
            "take_profit": take_profit_price,
            "status":     respuesta.status,
        }

    except Exception as e:
        # No relanzar como RuntimeError de red si es rechazo de la API
        # (fondos insuficientes, mercado cerrado, etc.)
        raise RuntimeError(f"Error al enviar bracket order para {symbol}: {e}") from e


def cerrar_posicion(trading_client: TradingClient, symbol: str) -> bool:
    """
    Cierra la posición abierta de un símbolo al precio de mercado.

    Se usa cuando el Módulo 3 emite señal SELL y hay una posición activa.
    Alpaca cancelará automáticamente las órdenes SL/TP pendientes de esa posición.

    Args:
        trading_client: Cliente de trading de Alpaca.
        symbol:         Ticker del activo a cerrar.

    Returns:
        bool: True si el cierre se solicitó correctamente.

    Raises:
        RuntimeError: Si la llamada a la API falla.
    """
    try:
        trading_client.close_position(symbol)
        return True
    except Exception as e:
        raise RuntimeError(f"Error al cerrar posición de {symbol}: {e}") from e


def ejecutar_senal(
    trading_client: TradingClient,
    symbol: str,
    signal,                 # Signal enum de analysis.py
    precio_actual: float,
    saldo_disponible: float,
) -> None:
    """
    Punto de entrada principal del Módulo 4.

    Evalúa la señal del Módulo 3 y ejecuta la acción correspondiente,
    aplicando todas las validaciones de riesgo antes de operar.

    Args:
        trading_client:    Cliente de trading de Alpaca.
        symbol:            Ticker del activo.
        signal:            Señal emitida por el Módulo 3 (Signal enum).
        precio_actual:     Último precio de cierre del activo.
        saldo_disponible:  Efectivo real disponible (T+1).
    """
    from src.analysis import Signal  # importación local para evitar ciclos

    # ── Señal de COMPRA ──────────────────────────────────────────────
    if signal == Signal.BUY:

        # 1. Validar saldo mínimo
        if saldo_disponible < MIN_CASH:
            print(f"  ⚠️  [{symbol}] BUY ignorado — saldo insuficiente (${saldo_disponible:.2f} < ${MIN_CASH})")
            return

        # 2. No duplicar posición
        if tiene_posicion_abierta(trading_client, symbol):
            print(f"  ⚠️  [{symbol}] BUY ignorado — ya hay posición abierta.")
            return

        # 3. Calcular cantidad
        cantidad = calcular_cantidad(precio_actual, saldo_disponible)
        if cantidad < 1:
            print(f"  ⚠️  [{symbol}] BUY ignorado — capital insuficiente para 1 acción "
                  f"(${precio_actual:.2f} × {RISK_PER_TRADE*100:.0f}% = ${saldo_disponible*RISK_PER_TRADE:.2f})")
            return

        # 4. Enviar Bracket Order
        try:
            resultado = enviar_bracket_order(trading_client, symbol, cantidad, precio_actual)
            if resultado:
                sl  = resultado["stop_loss"]
                tp  = resultado["take_profit"]
                print(f"  ✅ [{symbol}] COMPRA enviada — "
                      f"{cantidad} acc × ${precio_actual:.2f} | "
                      f"SL: ${sl:.2f} | TP: ${tp:.2f} | "
                      f"ID: {resultado['order_id'][:8]}...")
        except RuntimeError as e:
            print(f"  ✗  [{symbol}] Error al comprar: {e}")

    # ── Señal de VENTA ───────────────────────────────────────────────
    elif signal == Signal.SELL:

        if not tiene_posicion_abierta(trading_client, symbol):
            print(f"  ℹ️  [{symbol}] SELL — sin posición abierta, nada que cerrar.")
            return

        try:
            cerrar_posicion(trading_client, symbol)
            print(f"  ✅ [{symbol}] POSICIÓN CERRADA al precio de mercado.")
        except RuntimeError as e:
            print(f"  ✗  [{symbol}] Error al cerrar: {e}")

    # ── HOLD: no hacer nada ──────────────────────────────────────────
    # (el ciclo de análisis ya imprimió el estado)
