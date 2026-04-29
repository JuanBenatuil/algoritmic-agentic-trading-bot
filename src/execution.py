"""
execution.py — Módulo 4: Ejecución y Riesgo (Fracciones de Acciones).

Estrategia de ejecución:
    - Las compras usan 'notional' (monto en dólares), no 'qty' (acciones enteras).
      Esto permite comprar fracciones: $45 de SPY = ~0.063 acciones.
    - Alpaca no admite Bracket Orders en órdenes fraccionarias, por lo que
      el Stop-Loss y Take-Profit se monitorean manualmente en cada ciclo.
    - El estado de posiciones abiertas (precio de entrada, SL, TP) se persiste
      en un archivo JSON para sobrevivir reinicios del bot.

Parámetros de riesgo:
    RISK_PER_TRADE  : % del saldo disponible a invertir por operación.
    STOP_LOSS_PCT   : % de caída máxima aceptada desde el precio de entrada.
    TAKE_PROFIT_PCT : % de ganancia objetivo desde el precio de entrada.
    MIN_NOTIONAL    : Monto mínimo en dólares para abrir una posición (límite de Alpaca).
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce

# ─────────────────────────────────────────────
# Parámetros de gestión de riesgo
# ─────────────────────────────────────────────
RISK_PER_TRADE  = 0.10   # 10% del saldo disponible por operación
STOP_LOSS_PCT   = 0.02   # Stop-Loss: 2% por debajo del precio de entrada
TAKE_PROFIT_PCT = 0.04   # Take-Profit: 4% por encima (ratio riesgo/beneficio 1:2)
MIN_NOTIONAL    = 1.0    # Mínimo $1 por orden (límite de Alpaca para fracciones)

# Archivo donde se guarda el estado de posiciones abiertas
STATE_FILE = Path(os.getenv("STATE_FILE", "logs/posiciones.json"))


# ─────────────────────────────────────────────
# Gestión de estado persistente
# ─────────────────────────────────────────────

def _cargar_estado() -> dict:
    """
    Carga el estado de posiciones abiertas desde el archivo JSON.

    Returns:
        dict: {symbol: {entry_price, sl_price, tp_price, notional, opened_at}}
              Diccionario vacío si el archivo no existe.
    """
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return {}
    return {}


def _guardar_estado(estado: dict) -> None:
    """
    Persiste el estado de posiciones abiertas en el archivo JSON.

    Args:
        estado: Diccionario con el estado actual de posiciones.
    """
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(estado, f, indent=2)


def get_posiciones_abiertas() -> dict:
    """
    Retorna el estado de las posiciones abiertas rastreadas por el bot.

    Returns:
        dict: {symbol: {entry_price, sl_price, tp_price, notional, opened_at}}
    """
    return _cargar_estado()


# ─────────────────────────────────────────────
# Cálculo de tamaño de posición
# ─────────────────────────────────────────────

def calcular_notional(saldo_disponible: float) -> float:
    """
    Calcula el monto en dólares a invertir en la siguiente operación.

    Args:
        saldo_disponible: Efectivo real disponible (T+1) en dólares.

    Returns:
        float: Monto en dólares a invertir (redondeado a 2 decimales).
    """
    return round(saldo_disponible * RISK_PER_TRADE, 2)


# ─────────────────────────────────────────────
# Verificación de posiciones
# ─────────────────────────────────────────────

def tiene_posicion_abierta(symbol: str) -> bool:
    """
    Verifica si el bot tiene registrada una posición abierta para el símbolo.

    Usa el estado local (JSON) en lugar de consultar la API en cada ciclo.

    Args:
        symbol: Ticker del activo.

    Returns:
        bool: True si hay una posición registrada para este símbolo.
    """
    estado = _cargar_estado()
    return symbol in estado


# ─────────────────────────────────────────────
# Apertura de posiciones (compra fraccionaria)
# ─────────────────────────────────────────────

def abrir_posicion(
    trading_client: TradingClient,
    symbol: str,
    notional: float,
    precio_entrada: float,
) -> bool:
    """
    Abre una posición fraccionaria enviando una Market Order por monto en dólares.

    Calcula y registra los niveles de Stop-Loss y Take-Profit automáticamente.
    Al no poder usar Bracket Orders, estos niveles se monitoran en cada ciclo.

    Args:
        trading_client:  Cliente de trading de Alpaca.
        symbol:          Ticker del activo.
        notional:        Monto en dólares a invertir.
        precio_entrada:  Precio actual de referencia para calcular SL y TP.

    Returns:
        bool: True si la orden se envió correctamente.

    Raises:
        RuntimeError: Si la llamada a la API falla por error de red.
    """
    sl_price = round(precio_entrada * (1 - STOP_LOSS_PCT), 4)
    tp_price = round(precio_entrada * (1 + TAKE_PROFIT_PCT), 4)

    try:
        orden = MarketOrderRequest(
            symbol=symbol,
            notional=notional,
            side=OrderSide.BUY,
            time_in_force=TimeInForce.DAY,
        )
        respuesta = trading_client.submit_order(orden)

        # Registrar posición en el estado local
        estado = _cargar_estado()
        estado[symbol] = {
            "entry_price": precio_entrada,
            "sl_price":    sl_price,
            "tp_price":    tp_price,
            "notional":    notional,
            "order_id":    str(respuesta.id),
            "opened_at":   datetime.now(timezone.utc).isoformat(),
        }
        _guardar_estado(estado)
        return True

    except Exception as e:
        raise RuntimeError(f"Error al abrir posición en {symbol}: {e}") from e


# ─────────────────────────────────────────────
# Cierre de posiciones
# ─────────────────────────────────────────────

def cerrar_posicion(
    trading_client: TradingClient,
    symbol: str,
    motivo: str = "señal de venta",
) -> bool:
    """
    Cierra la posición abierta de un símbolo al precio de mercado
    y elimina su registro del estado local.

    Args:
        trading_client: Cliente de trading de Alpaca.
        symbol:         Ticker del activo a cerrar.
        motivo:         Razón del cierre (para el log).

    Returns:
        bool: True si el cierre se solicitó correctamente.

    Raises:
        RuntimeError: Si la llamada a la API falla.
    """
    try:
        trading_client.close_position(symbol)

        # Eliminar del estado local
        estado = _cargar_estado()
        estado.pop(symbol, None)
        _guardar_estado(estado)

        print(f"  ✅ [{symbol}] POSICIÓN CERRADA — motivo: {motivo}")
        return True

    except Exception as e:
        raise RuntimeError(f"Error al cerrar posición de {symbol}: {e}") from e


# ─────────────────────────────────────────────
# Monitoreo de SL/TP (reemplaza al Bracket Order)
# ─────────────────────────────────────────────

def monitorear_sl_tp(
    trading_client: TradingClient,
    precios_actuales: dict[str, float],
) -> None:
    """
    Verifica si alguna posición abierta ha tocado su Stop-Loss o Take-Profit
    y la cierra automáticamente si es el caso.

    Debe llamarse al inicio de cada ciclo, antes de buscar nuevas entradas.

    Args:
        trading_client:   Cliente de trading de Alpaca.
        precios_actuales: {symbol: precio_cierre_actual} para cada posición abierta.
    """
    estado = _cargar_estado()
    if not estado:
        return

    for symbol, datos in list(estado.items()):
        precio = precios_actuales.get(symbol)
        if precio is None:
            continue

        sl = datos["sl_price"]
        tp = datos["tp_price"]
        entrada = datos["entry_price"]
        pnl_pct = (precio - entrada) / entrada * 100

        if precio <= sl:
            print(f"  🔴 [{symbol}] Stop-Loss tocado — "
                  f"entrada: ${entrada:.2f} | actual: ${precio:.2f} | "
                  f"P&L: {pnl_pct:.2f}%")
            try:
                cerrar_posicion(trading_client, symbol, motivo=f"stop-loss ${sl:.2f}")
            except RuntimeError as e:
                print(f"  ✗  [{symbol}] Error cerrando SL: {e}")

        elif precio >= tp:
            print(f"  🟢 [{symbol}] Take-Profit alcanzado — "
                  f"entrada: ${entrada:.2f} | actual: ${precio:.2f} | "
                  f"P&L: +{pnl_pct:.2f}%")
            try:
                cerrar_posicion(trading_client, symbol, motivo=f"take-profit ${tp:.2f}")
            except RuntimeError as e:
                print(f"  ✗  [{symbol}] Error cerrando TP: {e}")

        else:
            print(f"  📌 [{symbol}] Posición activa — "
                  f"entrada: ${entrada:.2f} | actual: ${precio:.2f} | "
                  f"P&L: {pnl_pct:+.2f}% | "
                  f"SL: ${sl:.2f} | TP: ${tp:.2f}")


# ─────────────────────────────────────────────
# Punto de entrada principal del Módulo 4
# ─────────────────────────────────────────────

def ejecutar_senal(
    trading_client: TradingClient,
    symbol: str,
    signal,
    precio_actual: float,
    saldo_disponible: float,
) -> None:
    """
    Evalúa la señal del Módulo 3 y ejecuta la acción correspondiente,
    aplicando todas las validaciones de riesgo antes de operar.

    Args:
        trading_client:    Cliente de trading de Alpaca.
        symbol:            Ticker del activo.
        signal:            Señal emitida por el Módulo 3 (Signal enum).
        precio_actual:     Último precio de cierre del activo.
        saldo_disponible:  Efectivo real disponible (T+1).
    """
    from src.analysis import Signal

    if signal == Signal.BUY:
        # 1. No duplicar posición
        if tiene_posicion_abierta(symbol):
            print(f"  ⚠️  [{symbol}] BUY ignorado — ya hay posición abierta.")
            return

        # 2. Calcular monto a invertir
        notional = calcular_notional(saldo_disponible)
        if notional < MIN_NOTIONAL:
            print(f"  ⚠️  [{symbol}] BUY ignorado — monto insuficiente (${notional:.2f})")
            return

        # 3. Abrir posición fraccionaria
        try:
            abrir_posicion(trading_client, symbol, notional, precio_actual)
            fracciones = notional / precio_actual
            sl = round(precio_actual * (1 - STOP_LOSS_PCT), 2)
            tp = round(precio_actual * (1 + TAKE_PROFIT_PCT), 2)
            print(f"  ✅ [{symbol}] COMPRA fraccionaria — "
                  f"${notional:.2f} (~{fracciones:.4f} acc) × ${precio_actual:.2f} | "
                  f"SL: ${sl:.2f} | TP: ${tp:.2f}")
        except RuntimeError as e:
            print(f"  ✗  [{symbol}] Error al comprar: {e}")

    elif signal == Signal.SELL:
        if not tiene_posicion_abierta(symbol):
            print(f"  ℹ️  [{symbol}] SELL — sin posición abierta, nada que cerrar.")
            return
        try:
            cerrar_posicion(trading_client, symbol, motivo="señal de venta (análisis)")
        except RuntimeError as e:
            print(f"  ✗  [{symbol}] Error al cerrar: {e}")
