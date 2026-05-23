"""
execution.py — Fachada del Modulo 4: Ejecucion y Riesgo.

Este archivo mantiene la API publica original y delega la logica a
servicios especializados para mejorar SRP y facilitar pruebas.
"""

from alpaca.trading.client import TradingClient

from src.analysis import Signal
from src.domain.risk import DEFAULT_RISK, RiskConfig, calcular_notional as _calcular_notional
from src.services.execution_service import (
    abrir_posicion as _abrir_posicion,
    cerrar_posicion as _cerrar_posicion,
    ejecutar_senal as _ejecutar_senal,
    get_posiciones_abiertas as _get_posiciones_abiertas,
    monitorear_sl_tp as _monitorear_sl_tp,
    tiene_posicion_abierta as _tiene_posicion_abierta,
)
from src.services.position_store import PositionStore


# ─── API publica compatible ─────────────────────────────────────────────────-

def get_posiciones_abiertas(store: PositionStore | None = None) -> dict:
    return _get_posiciones_abiertas(store)


def tiene_posicion_abierta(symbol: str, store: PositionStore | None = None) -> bool:
    return _tiene_posicion_abierta(symbol, store)


def calcular_notional(saldo_disponible: float, config: RiskConfig = DEFAULT_RISK) -> float:
    return _calcular_notional(saldo_disponible, config)


def abrir_posicion(
    trading_client: TradingClient,
    symbol: str,
    notional: float,
    precio_entrada: float,
    config: RiskConfig = DEFAULT_RISK,
    store: PositionStore | None = None,
) -> None:
    _abrir_posicion(trading_client, symbol, notional, precio_entrada, config, store)


def cerrar_posicion(
    trading_client: TradingClient,
    symbol: str,
    motivo: str = "senal de venta",
    store: PositionStore | None = None,
) -> None:
    _cerrar_posicion(trading_client, symbol, motivo=motivo, store=store)


def monitorear_sl_tp(
    trading_client: TradingClient,
    precios_actuales: dict[str, float],
    store: PositionStore | None = None,
) -> None:
    _monitorear_sl_tp(trading_client, precios_actuales, store)


def ejecutar_senal(
    trading_client: TradingClient,
    symbol: str,
    signal: Signal,
    precio_actual: float,
    saldo_disponible: float,
    config: RiskConfig = DEFAULT_RISK,
    store: PositionStore | None = None,
) -> None:
    _ejecutar_senal(
        trading_client,
        symbol,
        signal,
        precio_actual,
        saldo_disponible,
        config,
        store,
    )
