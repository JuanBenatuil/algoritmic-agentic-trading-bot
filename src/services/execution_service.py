"""
execution_service.py — Orquestacion de ejecucion y riesgo.
"""

from datetime import datetime, timezone

from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.trading.requests import MarketOrderRequest

from src.domain.analysis_models import Signal
from src.domain.risk import DEFAULT_RISK, RiskConfig, calcular_notional, calcular_sl_tp
from src.notifier import notify_buy, notify_sell, notify_stop_loss, notify_take_profit
from src.services.position_store import PositionStore


def get_posiciones_abiertas(store: PositionStore | None = None) -> dict:
    store = store or PositionStore()
    return store.get_all()


def tiene_posicion_abierta(symbol: str, store: PositionStore | None = None) -> bool:
    store = store or PositionStore()
    return store.has(symbol)


def abrir_posicion(
    trading_client: TradingClient,
    symbol: str,
    notional: float,
    precio_entrada: float,
    config: RiskConfig = DEFAULT_RISK,
    store: PositionStore | None = None,
) -> None:
    sl_price, tp_price = calcular_sl_tp(precio_entrada, config)

    try:
        orden = MarketOrderRequest(
            symbol=symbol,
            notional=notional,
            side=OrderSide.BUY,
            time_in_force=TimeInForce.DAY,
        )
        respuesta = trading_client.submit_order(orden)
    except Exception as exc:
        raise RuntimeError(f"Error al abrir posicion en {symbol}: {exc}") from exc

    store = store or PositionStore()
    store.upsert(
        symbol,
        {
            "entry_price": precio_entrada,
            "sl_price": sl_price,
            "tp_price": tp_price,
            "notional": notional,
            "order_id": str(respuesta.id),
            "opened_at": datetime.now(timezone.utc).isoformat(),
        },
    )


def cerrar_posicion(
    trading_client: TradingClient,
    symbol: str,
    motivo: str = "senal de venta",
    store: PositionStore | None = None,
) -> None:
    try:
        trading_client.close_position(symbol)
    except Exception as exc:
        raise RuntimeError(f"Error al cerrar posicion de {symbol}: {exc}") from exc

    store = store or PositionStore()
    store.remove(symbol)
    print(f"  ✅ [{symbol}] POSICION CERRADA — motivo: {motivo}")
    notify_sell(symbol, motivo)


def monitorear_sl_tp(
    trading_client: TradingClient,
    precios_actuales: dict[str, float],
    store: PositionStore | None = None,
) -> None:
    store = store or PositionStore()
    estado = store.get_all()
    for symbol, datos in list(estado.items()):
        precio = precios_actuales.get(symbol)
        if precio is None:
            continue
        _evaluar_posicion(trading_client, symbol, precio, datos, store)


def ejecutar_senal(
    trading_client: TradingClient,
    symbol: str,
    signal: Signal,
    precio_actual: float,
    saldo_disponible: float,
    config: RiskConfig = DEFAULT_RISK,
    store: PositionStore | None = None,
) -> None:
    handlers = {
        Signal.BUY: lambda: _handle_buy(
            trading_client, symbol, precio_actual, saldo_disponible, config, store
        ),
        Signal.SELL: lambda: _handle_sell(trading_client, symbol, store),
        Signal.HOLD: lambda: None,
    }
    handler = handlers.get(signal)
    if handler:
        handler()


def _evaluar_posicion(
    trading_client: TradingClient,
    symbol: str,
    precio: float,
    datos: dict,
    store: PositionStore,
) -> None:
    sl = datos["sl_price"]
    tp = datos["tp_price"]
    entrada = datos["entry_price"]
    pnl_pct = (precio - entrada) / entrada * 100

    if precio <= sl:
        print(
            f"  🔴 [{symbol}] Stop-Loss tocado — "
            f"entrada: ${entrada:.2f} | actual: ${precio:.2f} | P&L: {pnl_pct:.2f}%"
        )
        notify_stop_loss(symbol, entrada, precio, pnl_pct)
        _intentar_cierre(trading_client, symbol, motivo=f"stop-loss ${sl:.2f}", store=store)
        return

    if precio >= tp:
        print(
            f"  🟢 [{symbol}] Take-Profit alcanzado — "
            f"entrada: ${entrada:.2f} | actual: ${precio:.2f} | P&L: +{pnl_pct:.2f}%"
        )
        notify_take_profit(symbol, entrada, precio, pnl_pct)
        _intentar_cierre(trading_client, symbol, motivo=f"take-profit ${tp:.2f}", store=store)
        return

    print(
        f"  📌 [{symbol}] Posicion activa — "
        f"entrada: ${entrada:.2f} | actual: ${precio:.2f} | "
        f"P&L: {pnl_pct:+.2f}% | SL: ${sl:.2f} | TP: ${tp:.2f}"
    )


def _intentar_cierre(
    trading_client: TradingClient,
    symbol: str,
    motivo: str,
    store: PositionStore,
) -> None:
    try:
        cerrar_posicion(trading_client, symbol, motivo=motivo, store=store)
    except RuntimeError as exc:
        print(f"  ✗  [{symbol}] Error cerrando posicion: {exc}")


def _handle_buy(
    trading_client: TradingClient,
    symbol: str,
    precio_actual: float,
    saldo_disponible: float,
    config: RiskConfig,
    store: PositionStore | None,
) -> None:
    store = store or PositionStore()
    if tiene_posicion_abierta(symbol, store):
        print(f"  ⚠️  [{symbol}] BUY ignorado — ya hay posicion abierta.")
        return

    notional = calcular_notional(saldo_disponible, config)
    if notional < config.min_notional:
        print(f"  ⚠️  [{symbol}] BUY ignorado — monto insuficiente (${notional:.2f})")
        return

    try:
        abrir_posicion(trading_client, symbol, notional, precio_actual, config, store)
        fracciones = notional / precio_actual
        sl, tp = calcular_sl_tp(precio_actual, config)
        print(
            f"  ✅ [{symbol}] COMPRA fraccionaria — "
            f"${notional:.2f} (~{fracciones:.4f} acc) x ${precio_actual:.2f} | "
            f"SL: ${sl:.2f} | TP: ${tp:.2f}"
        )
        notify_buy(symbol, notional, precio_actual, sl, tp)
    except RuntimeError as exc:
        print(f"  ✗  [{symbol}] Error al comprar: {exc}")


def _handle_sell(
    trading_client: TradingClient,
    symbol: str,
    store: PositionStore | None,
) -> None:
    store = store or PositionStore()
    if not tiene_posicion_abierta(symbol, store):
        print(f"  ℹ️  [{symbol}] SELL — sin posicion abierta, nada que cerrar.")
        return
    _intentar_cierre(trading_client, symbol, motivo="senal de venta (analisis)", store=store)
