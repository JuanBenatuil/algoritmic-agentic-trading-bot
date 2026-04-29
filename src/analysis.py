"""
analysis.py — Módulo 3: Motor de Análisis (Cerebro).

Estrategia: Doble EMA + RSI con doble confirmación.

Lógica de señales:
    BUY  → EMA9 cruza por encima de EMA21 (golden cross) Y RSI < 70
    SELL → EMA9 cruza por debajo de EMA21 (death cross)  O RSI > 70
    HOLD → No se cumplen condiciones de entrada/salida

Principios SOLID aplicados:
    SRP — Cada función tiene una responsabilidad única: calcular, evaluar o mostrar.
    OCP — StrategyConfig permite ajustar parámetros sin modificar la lógica de señales.
"""

from dataclasses import dataclass
from enum import Enum

import pandas as pd
import pandas_ta as ta


# ─── Tipos de dominio ────────────────────────────────────────────────────────

class Signal(Enum):
    """Señales posibles que puede emitir el motor de análisis."""
    BUY  = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


@dataclass(frozen=True)
class StrategyConfig:
    """Parámetros de la estrategia técnica (inmutables).

    Encapsular los parámetros en un dataclass permite:
    - Cambiarlos en un solo lugar sin tocar la lógica de señales (OCP).
    - Pasarlos entre funciones con type-checking explícito.
    - Documentar cada parámetro con su propósito.
    """
    ema_fast:    int = 9    # EMA rápida — sensible a movimientos recientes
    ema_slow:    int = 21   # EMA lenta  — tendencia más estable
    rsi_period:  int = 14   # Estándar de la industria
    rsi_ob:      int = 70   # Overbought — zona de venta
    rsi_os:      int = 30   # Oversold   — zona de posible compra
    min_bars:    int = 30   # Mínimo de velas para resultados confiables


@dataclass
class AnalysisResult:
    """Resultado completo del análisis para un símbolo."""
    symbol:   str
    signal:   Signal
    close:    float
    ema_fast: float | None  # EMA rápida (ej. EMA 9)
    ema_slow: float | None  # EMA lenta  (ej. EMA 21)
    rsi:      float | None  # RSI 14
    reason:   str           # Explicación legible de la señal


# Configuración por defecto (puede sobreescribirse instanciando StrategyConfig)
DEFAULT_STRATEGY = StrategyConfig()


# ─── Cálculo de indicadores ──────────────────────────────────────────────────

def calculate_indicators(
    df: pd.DataFrame,
    config: StrategyConfig = DEFAULT_STRATEGY,
) -> pd.DataFrame:
    """Calcula indicadores técnicos sobre un DataFrame OHLCV.

    Agrega las columnas EMA_{fast}, EMA_{slow} y RSI_{period} al DataFrame.

    Args:
        df:     DataFrame con columnas [open, high, low, close, volume].
        config: Parámetros de estrategia. Usa DEFAULT_STRATEGY si se omite.

    Returns:
        Copia del DataFrame con las columnas de indicadores añadidas.

    Raises:
        ValueError: Si el DataFrame no contiene la columna 'close'.
    """
    if "close" not in df.columns:
        raise ValueError("El DataFrame debe tener columna 'close'.")

    df = df.copy()
    df[f"EMA_{config.ema_fast}"]   = ta.ema(df["close"], length=config.ema_fast)
    df[f"EMA_{config.ema_slow}"]   = ta.ema(df["close"], length=config.ema_slow)
    df[f"RSI_{config.rsi_period}"] = ta.rsi(df["close"], length=config.rsi_period)
    return df


# ─── Evaluación de señal ─────────────────────────────────────────────────────

def get_signal(
    df: pd.DataFrame,
    symbol: str = "",
    config: StrategyConfig = DEFAULT_STRATEGY,
) -> AnalysisResult:
    """Evalúa la última vela del DataFrame y retorna la señal de trading.

    Requiere que el DataFrame ya tenga los indicadores calculados
    (llamar a calculate_indicators() primero).

    Detecta cruce de EMAs comparando la penúltima y última fila:
        - Golden cross: EMA rápida cruza de abajo hacia arriba EMA lenta → BUY
        - Death cross:  EMA rápida cruza de arriba hacia abajo EMA lenta → SELL

    Args:
        df:     DataFrame con indicadores calculados.
        symbol: Ticker del activo (para el resultado).
        config: Parámetros de estrategia. Usa DEFAULT_STRATEGY si se omite.

    Returns:
        AnalysisResult con la señal, valores de indicadores y razón.
    """
    col_fast = f"EMA_{config.ema_fast}"
    col_slow = f"EMA_{config.ema_slow}"
    col_rsi  = f"RSI_{config.rsi_period}"

    if len(df) < config.min_bars:
        return _hold_result(
            symbol, df,
            reason=f"Datos insuficientes ({len(df)} velas, mínimo {config.min_bars})",
        )

    last = df.iloc[-1]
    prev = df.iloc[-2]

    close    = float(last["close"])
    ema_fast = _safe_float(last[col_fast])
    ema_slow = _safe_float(last[col_slow])
    rsi      = _safe_float(last[col_rsi])

    if any(v is None for v in (ema_fast, ema_slow, rsi)):
        return AnalysisResult(
            symbol=symbol, signal=Signal.HOLD,
            close=close, ema_fast=ema_fast, ema_slow=ema_slow, rsi=rsi,
            reason="Indicadores con NaN — pocas velas o alta volatilidad",
        )

    prev_fast = _safe_float(prev[col_fast])
    prev_slow = _safe_float(prev[col_slow])

    golden_cross = _is_golden_cross(prev_fast, prev_slow, ema_fast, ema_slow)
    death_cross  = _is_death_cross(prev_fast, prev_slow, ema_fast, ema_slow)

    if golden_cross and rsi < config.rsi_ob:
        return AnalysisResult(
            symbol=symbol, signal=Signal.BUY,
            close=close, ema_fast=ema_fast, ema_slow=ema_slow, rsi=rsi,
            reason=(
                f"Golden cross EMA{config.ema_fast}/EMA{config.ema_slow}"
                f" + RSI {rsi:.1f} < {config.rsi_ob}"
            ),
        )

    if death_cross or rsi > config.rsi_ob:
        reason = (
            f"Death cross EMA{config.ema_fast}/EMA{config.ema_slow}"
            if death_cross
            else f"RSI sobrecomprado: {rsi:.1f} > {config.rsi_ob}"
        )
        return AnalysisResult(
            symbol=symbol, signal=Signal.SELL,
            close=close, ema_fast=ema_fast, ema_slow=ema_slow, rsi=rsi,
            reason=reason,
        )

    direction = "alcista" if ema_fast > ema_slow else "bajista"
    return AnalysisResult(
        symbol=symbol, signal=Signal.HOLD,
        close=close, ema_fast=ema_fast, ema_slow=ema_slow, rsi=rsi,
        reason=f"Tendencia {direction} sin cruce — mantener",
    )


# ─── Display ─────────────────────────────────────────────────────────────────

def print_analysis(result: AnalysisResult, config: StrategyConfig = DEFAULT_STRATEGY) -> None:
    """Imprime el resultado del análisis de forma legible en consola.

    Args:
        result: AnalysisResult con todos los datos del análisis.
        config: Parámetros de estrategia (para mostrar los períodos correctos).
    """
    icons = {Signal.BUY: "🟢", Signal.SELL: "🔴", Signal.HOLD: "🟡"}
    ema_f = f"{result.ema_fast:.2f}" if result.ema_fast is not None else "N/A"
    ema_s = f"{result.ema_slow:.2f}" if result.ema_slow is not None else "N/A"
    rsi   = f"{result.rsi:.1f}"      if result.rsi      is not None else "N/A"

    print(
        f"  {icons[result.signal]} [{result.symbol}] {result.signal.value:4s} | "
        f"Close: ${result.close:.2f}  "
        f"EMA{config.ema_fast}: {ema_f}  EMA{config.ema_slow}: {ema_s}  "
        f"RSI: {rsi} | {result.reason}"
    )


# ─── Helpers privados ────────────────────────────────────────────────────────

def _safe_float(value) -> float | None:
    """Convierte un valor a float o retorna None si es NaN."""
    return float(value) if pd.notna(value) else None


def _hold_result(symbol: str, df: pd.DataFrame, reason: str) -> AnalysisResult:
    """Construye un AnalysisResult de HOLD con datos mínimos."""
    return AnalysisResult(
        symbol=symbol, signal=Signal.HOLD,
        close=float(df["close"].iloc[-1]),
        ema_fast=None, ema_slow=None, rsi=None,
        reason=reason,
    )


def _is_golden_cross(
    prev_fast: float | None,
    prev_slow: float | None,
    fast: float,
    slow: float,
) -> bool:
    """EMA rápida cruzó de abajo hacia arriba la EMA lenta."""
    return (
        prev_fast is not None
        and prev_slow is not None
        and prev_fast <= prev_slow
        and fast > slow
    )


def _is_death_cross(
    prev_fast: float | None,
    prev_slow: float | None,
    fast: float,
    slow: float,
) -> bool:
    """EMA rápida cruzó de arriba hacia abajo la EMA lenta."""
    return (
        prev_fast is not None
        and prev_slow is not None
        and prev_fast >= prev_slow
        and fast < slow
    )
