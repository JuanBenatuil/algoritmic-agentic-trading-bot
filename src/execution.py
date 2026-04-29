"""
execution.py — Módulo 4: Ejecución y Riesgo (Fracciones de Acciones).

Estrategia de ejecución:
    - Las compras usan 'notional' (monto en dólares), no 'qty' (acciones enteras).
      Esto permite comprar fracciones: $45 de SPY ≈ 0.063 acciones.
    - Alpaca no admite Bracket Orders en órdenes fraccionarias, por lo que
      el Stop-Loss y Take-Profit se monitoran manualmente en cada ciclo.
    - El estado de posiciones abiertas se persiste en JSON para sobrevivir
      reinicios del proceso.

Principios SOLID aplicados:
    SRP — Cada función tiene una única responsabilidad: persistir, calcular,
          abrir, cerrar o monitorear. La lógica de despacho está separada.
    OCP — RiskConfig agrupa los parámetros; cambiarlos no requiere tocar la lógica.
    DIP — Signal se importa al nivel del módulo (no dentro de la función),
          eliminando la dependencia oculta que existía antes.
"""

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.trading.requests import MarketOrderRequest

from src.analysis import Signal


# ─── Configuración de riesgo ─────────────────────────────────────────────────

@dataclass(frozen=True)
class RiskConfig:
    """Parámetros de gestión de riesgo (inmutables).

    Centralizar aquí facilita ajustar el riesgo sin tocar la lógica (OCP).
    """
    risk_per_trade:  float = 0.10  # 10% del saldo disponible por operación
    stop_loss_pct:   float = 0.02  # SL: 2% por debajo del precio de entrada
    take_profit_pct: float = 0.04  # TP: 4% por encima (ratio riesgo/beneficio 1:2)
    min_notional:    float = 1.0   # Mínimo $1 por orden (límite de Alpaca)


DEFAULT_RISK = RiskConfig()

# Archivo donde se guarda el estado de posiciones abiertas
_STATE_FILE = Path(os.getenv("STATE_FILE", "logs/posiciones.json"))


# ─── Persistencia de estado ──────────────────────────────────────────────────

def _cargar_estado() -> dict:
    """Carga el estado de posiciones desde el archivo JSON.

    Returns:
        dict con estructura {symbol: {entry_price, sl_price, tp_price, ...}}.
        Retorna diccionario vacío si el archivo no existe o está corrupto.
    """
    if _STATE_FILE.exists():
        try:
            with open(_STATE_FILE, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return {}
    return {}


def _guardar_estado(estado: dict) -> None:
    """Persiste el estado de posiciones en el archivo JSON.

    Args:
        estado: Diccionario actualizado con posiciones abiertas.
    """
    _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(_STATE_FILE, "w") as f:
        json.dump(estado, f, indent=2)


# ─── Consulta de posiciones ──────────────────────────────────────────────────

def get_posiciones_abiertas() -> dict:
    """Retorna el estado de posiciones abiertas rastreadas por el bot.

    Returns:
        dict con estructura {symbol: {entry_price, sl_price, tp_price, ...}}.
    """
    return _cargar_estado()


def tiene_posicion_abierta(symbol: str) -> bool:
    """Verifica si hay una posición registrada para el símbolo.

    Usa el estado local (JSON) en vez de consultar la API en cada ciclo.

    Args:
        symbol: Ticker del activo.

    Returns:
        True si hay una posición registrada para este símbolo.
    """
    return symbol in _cargar_estado()


# ─── Cálculo de tamaño de posición ──────────────────────────────────────────

def calcular_notional(saldo_disponible: float, config: RiskConfig = DEFAULT_RISK) -> float:
    """Calcula el monto en dólares a invertir en la siguiente operación.

    Args:
        saldo_disponible: Efectivo real disponible (T+1) en dólares.
        config:           Parámetros de riesgo. Usa DEFAULT_RISK si se omite.

    Returns:
        Monto en dólares a invertir, redondeado a 2 decimales.
    """
    return round(saldo_disponible * config.risk_per_trade, 2)


# ─── Apertura de posición (compra fraccionaria) ──────────────────────────────

def abrir_posicion(
    trading_client: TradingClient,
    symbol: str,
    notional: float,
    precio_entrada: float,
    config: RiskConfig = DEFAULT_RISK,
) -> None:
    """Abre una posición fraccionaria enviando una Market Order por monto en dólares.

    Calcula los niveles de SL/TP y los registra en el estado local para
    monitoreo manual (Alpaca no admite Bracket Orders en órdenes fraccionarias).

    Args:
        trading_client: Cliente de trading de Alpaca.
        symbol:         Ticker del activo.
        notional:       Monto en dólares a invertir.
        precio_entrada: Precio actual de referencia para calcular SL y TP.
        config:         Parámetros de riesgo.

    Raises:
        RuntimeError: Si la llamada a la API falla.
    """
    sl_price = round(precio_entrada * (1 - config.stop_loss_pct),   4)
    tp_price = round(precio_entrada * (1 + config.take_profit_pct), 4)

    try:
        orden = MarketOrderRequest(
            symbol=symbol,
            notional=notional,
            side=OrderSide.BUY,
            time_in_force=TimeInForce.DAY,
        )
        respuesta = trading_client.submit_order(orden)
    except Exception as e:
        raise RuntimeError(f"Error al abrir posición en {symbol}: {e}") from e

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


# ─── Cierre de posición ──────────────────────────────────────────────────────

def cerrar_posicion(
    trading_client: TradingClient,
    symbol: str,
    motivo: str = "señal de venta",
) -> None:
    """Cierra la posición abierta de un símbolo al precio de mercado.

    Elimina el registro del estado local una vez confirmado el cierre.

    Args:
        trading_client: Cliente de trading de Alpaca.
        symbol:         Ticker del activo a cerrar.
        motivo:         Razón del cierre (para el log).

    Raises:
        RuntimeError: Si la llamada a la API falla.
    """
    try:
        trading_client.close_position(symbol)
    except Exception as e:
        raise RuntimeError(f"Error al cerrar posición de {symbol}: {e}") from e

    estado = _cargar_estado()
    estado.pop(symbol, None)
    _guardar_estado(estado)
    print(f"  ✅ [{symbol}] POSICIÓN CERRADA — motivo: {motivo}")


# ─── Monitoreo de SL/TP ──────────────────────────────────────────────────────

def monitorear_sl_tp(
    trading_client: TradingClient,
    precios_actuales: dict[str, float],
) -> None:
    """Verifica posiciones abiertas y cierra las que tocaron SL o TP.

    Reemplaza el Bracket Order de Alpaca, que no está disponible para
    órdenes fraccionarias. Debe llamarse antes de buscar nuevas entradas.

    Args:
        trading_client:   Cliente de trading de Alpaca.
        precios_actuales: {symbol: precio_cierre_actual} para cada posición.
    """
    estado = _cargar_estado()
    for symbol, datos in list(estado.items()):
        precio = precios_actuales.get(symbol)
        if precio is None:
            continue
        _evaluar_posicion(trading_client, symbol, precio, datos)


def _evaluar_posicion(
    trading_client: TradingClient,
    symbol: str,
    precio: float,
    datos: dict,
) -> None:
    """Evalúa una posición individual y actúa si tocó SL o TP.

    Args:
        trading_client: Cliente de trading de Alpaca.
        symbol:         Ticker del activo.
        precio:         Precio de cierre actual.
        datos:          Datos de la posición (entry_price, sl_price, tp_price).
    """
    sl      = datos["sl_price"]
    tp      = datos["tp_price"]
    entrada = datos["entry_price"]
    pnl_pct = (precio - entrada) / entrada * 100

    if precio <= sl:
        print(
            f"  🔴 [{symbol}] Stop-Loss tocado — "
            f"entrada: ${entrada:.2f} | actual: ${precio:.2f} | P&L: {pnl_pct:.2f}%"
        )
        _intentar_cierre(trading_client, symbol, motivo=f"stop-loss ${sl:.2f}")

    elif precio >= tp:
        print(
            f"  🟢 [{symbol}] Take-Profit alcanzado — "
            f"entrada: ${entrada:.2f} | actual: ${precio:.2f} | P&L: +{pnl_pct:.2f}%"
        )
        _intentar_cierre(trading_client, symbol, motivo=f"take-profit ${tp:.2f}")

    else:
        print(
            f"  📌 [{symbol}] Posición activa — "
            f"entrada: ${entrada:.2f} | actual: ${precio:.2f} | "
            f"P&L: {pnl_pct:+.2f}% | SL: ${sl:.2f} | TP: ${tp:.2f}"
        )


def _intentar_cierre(trading_client: TradingClient, symbol: str, motivo: str) -> None:
    """Intenta cerrar una posición y captura errores sin detener el proceso.

    Args:
        trading_client: Cliente de trading de Alpaca.
        symbol:         Ticker del activo.
        motivo:         Razón del cierre para el log.
    """
    try:
        cerrar_posicion(trading_client, symbol, motivo=motivo)
    except RuntimeError as e:
        print(f"  ✗  [{symbol}] Error cerrando posición: {e}")


# ─── Punto de entrada del Módulo 4 ──────────────────────────────────────────

def ejecutar_senal(
    trading_client: TradingClient,
    symbol: str,
    signal: Signal,
    precio_actual: float,
    saldo_disponible: float,
    config: RiskConfig = DEFAULT_RISK,
) -> None:
    """Evalúa la señal del Módulo 3 y ejecuta la acción correspondiente.

    Aplica todas las validaciones de riesgo antes de operar. Usa un
    dispatch dict para manejar cada señal sin if/elif anidados (OCP):
    agregar una nueva señal solo requiere añadir una función y registrarla.

    Args:
        trading_client:   Cliente de trading de Alpaca.
        symbol:           Ticker del activo.
        signal:           Señal emitida por el Módulo 3.
        precio_actual:    Último precio de cierre del activo.
        saldo_disponible: Efectivo real disponible (T+1).
        config:           Parámetros de riesgo.
    """
    handlers = {
        Signal.BUY:  lambda: _handle_buy(trading_client, symbol, precio_actual, saldo_disponible, config),
        Signal.SELL: lambda: _handle_sell(trading_client, symbol),
        Signal.HOLD: lambda: None,
    }
    handler = handlers.get(signal)
    if handler:
        handler()


def _handle_buy(
    trading_client: TradingClient,
    symbol: str,
    precio_actual: float,
    saldo_disponible: float,
    config: RiskConfig,
) -> None:
    """Gestiona la señal BUY: valida, calcula notional y abre la posición."""
    if tiene_posicion_abierta(symbol):
        print(f"  ⚠️  [{symbol}] BUY ignorado — ya hay posición abierta.")
        return

    notional = calcular_notional(saldo_disponible, config)
    if notional < config.min_notional:
        print(f"  ⚠️  [{symbol}] BUY ignorado — monto insuficiente (${notional:.2f})")
        return

    try:
        abrir_posicion(trading_client, symbol, notional, precio_actual, config)
        fracciones = notional / precio_actual
        sl = round(precio_actual * (1 - config.stop_loss_pct),   2)
        tp = round(precio_actual * (1 + config.take_profit_pct), 2)
        print(
            f"  ✅ [{symbol}] COMPRA fraccionaria — "
            f"${notional:.2f} (~{fracciones:.4f} acc) × ${precio_actual:.2f} | "
            f"SL: ${sl:.2f} | TP: ${tp:.2f}"
        )
    except RuntimeError as e:
        print(f"  ✗  [{symbol}] Error al comprar: {e}")


def _handle_sell(trading_client: TradingClient, symbol: str) -> None:
    """Gestiona la señal SELL: cierra la posición si existe."""
    if not tiene_posicion_abierta(symbol):
        print(f"  ℹ️  [{symbol}] SELL — sin posición abierta, nada que cerrar.")
        return
    _intentar_cierre(trading_client, symbol, motivo="señal de venta (análisis)")
