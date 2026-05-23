"""
risk.py — Modelos y calculos de riesgo.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class RiskConfig:
    """Parametros de gestion de riesgo (inmutables)."""

    risk_per_trade: float = 0.10
    stop_loss_pct: float = 0.02
    take_profit_pct: float = 0.04
    min_notional: float = 1.0


DEFAULT_RISK = RiskConfig()


def calcular_notional(saldo_disponible: float, config: RiskConfig = DEFAULT_RISK) -> float:
    """Calcula el monto a invertir segun el porcentaje de riesgo."""
    return round(saldo_disponible * config.risk_per_trade, 2)


def calcular_sl_tp(precio_entrada: float, config: RiskConfig = DEFAULT_RISK) -> tuple[float, float]:
    """Calcula niveles de stop-loss y take-profit para un precio de entrada."""
    sl_price = round(precio_entrada * (1 - config.stop_loss_pct), 4)
    tp_price = round(precio_entrada * (1 + config.take_profit_pct), 4)
    return sl_price, tp_price
