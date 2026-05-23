"""
analysis_models.py — Modelos de dominio para analisis tecnico.
"""

from dataclasses import dataclass
from enum import Enum


class Signal(Enum):
    """Senales posibles que puede emitir el motor de analisis."""

    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


@dataclass(frozen=True)
class StrategyConfig:
    """Parametros de la estrategia tecnica (inmutables)."""

    ema_fast: int = 9
    ema_slow: int = 21
    rsi_period: int = 14
    rsi_ob: int = 70
    rsi_os: int = 30
    min_bars: int = 30
    # RSI mínimo para BUY (evita entrar en caída libre)
    rsi_buy_min: int = 40


@dataclass
class AnalysisResult:
    """Resultado completo del analisis para un simbolo."""

    symbol: str
    signal: Signal
    close: float
    ema_fast: float | None
    ema_slow: float | None
    rsi: float | None
    reason: str


DEFAULT_STRATEGY = StrategyConfig()
