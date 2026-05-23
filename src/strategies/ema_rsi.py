"""
ema_rsi.py — Estrategia EMA9/EMA21 + RSI14.
"""

import pandas as pd
import pandas_ta as ta

from src.domain.analysis_models import (
    AnalysisResult,
    DEFAULT_STRATEGY,
    Signal,
    StrategyConfig,
)


def calculate_indicators(
    df: pd.DataFrame,
    config: StrategyConfig = DEFAULT_STRATEGY,
) -> pd.DataFrame:
    if "close" not in df.columns:
        raise ValueError("El DataFrame debe tener columna 'close'.")

    df = df.copy()
    df[f"EMA_{config.ema_fast}"] = ta.ema(df["close"], length=config.ema_fast)
    df[f"EMA_{config.ema_slow}"] = ta.ema(df["close"], length=config.ema_slow)
    df[f"RSI_{config.rsi_period}"] = ta.rsi(df["close"], length=config.rsi_period)
    return df


def get_signal(
    df: pd.DataFrame,
    symbol: str = "",
    config: StrategyConfig = DEFAULT_STRATEGY,
) -> AnalysisResult:
    col_fast = f"EMA_{config.ema_fast}"
    col_slow = f"EMA_{config.ema_slow}"
    col_rsi = f"RSI_{config.rsi_period}"

    if len(df) < config.min_bars:
        return _hold_result(
            symbol,
            df,
            reason=f"Datos insuficientes ({len(df)} velas, minimo {config.min_bars})",
        )

    last = df.iloc[-1]
    prev = df.iloc[-2]

    close = float(last["close"])
    ema_fast = _safe_float(last[col_fast])
    ema_slow = _safe_float(last[col_slow])
    rsi = _safe_float(last[col_rsi])

    if any(v is None for v in (ema_fast, ema_slow, rsi)):
        return AnalysisResult(
            symbol=symbol,
            signal=Signal.HOLD,
            close=close,
            ema_fast=ema_fast,
            ema_slow=ema_slow,
            rsi=rsi,
            reason="Indicadores con NaN — pocas velas o alta volatilidad",
        )

    prev_fast = _safe_float(prev[col_fast])
    prev_slow = _safe_float(prev[col_slow])

    death_cross = _is_death_cross(prev_fast, prev_slow, ema_fast, ema_slow)

    # SELL: cruce bajista o RSI sobrecomprado
    if death_cross or rsi > config.rsi_ob:
        reason = (
            f"Death cross EMA{config.ema_fast}/EMA{config.ema_slow}"
            if death_cross
            else f"RSI sobrecomprado: {rsi:.1f} > {config.rsi_ob}"
        )
        return AnalysisResult(
            symbol=symbol,
            signal=Signal.SELL,
            close=close,
            ema_fast=ema_fast,
            ema_slow=ema_slow,
            rsi=rsi,
            reason=reason,
        )

    # BUY: tendencia alcista confirmada (EMA9 > EMA21) + RSI en zona sana
    # Antes se requería un cruce exacto en la última vela (demasiado estricto).
    # Ahora basta con que la tendencia esté establecida y el RSI tenga momentum.
    trending_up = ema_fast > ema_slow and prev_fast > prev_slow
    rsi_ok = config.rsi_buy_min <= rsi < config.rsi_ob
    if trending_up and rsi_ok:
        return AnalysisResult(
            symbol=symbol,
            signal=Signal.BUY,
            close=close,
            ema_fast=ema_fast,
            ema_slow=ema_slow,
            rsi=rsi,
            reason=(
                f"Tendencia alcista EMA{config.ema_fast}={ema_fast:.2f} > "
                f"EMA{config.ema_slow}={ema_slow:.2f}"
                f" + RSI {rsi:.1f} en zona sana ({config.rsi_buy_min}-{config.rsi_ob})"
            ),
        )

    direction = "alcista" if ema_fast > ema_slow else "bajista"
    return AnalysisResult(
        symbol=symbol,
        signal=Signal.HOLD,
        close=close,
        ema_fast=ema_fast,
        ema_slow=ema_slow,
        rsi=rsi,
        reason=f"Tendencia {direction} — RSI {rsi:.1f} fuera de rango o sin confirmacion",
    )


def print_analysis(result: AnalysisResult, config: StrategyConfig = DEFAULT_STRATEGY) -> None:
    icons = {Signal.BUY: "🟢", Signal.SELL: "🔴", Signal.HOLD: "🟡"}
    ema_f = f"{result.ema_fast:.2f}" if result.ema_fast is not None else "N/A"
    ema_s = f"{result.ema_slow:.2f}" if result.ema_slow is not None else "N/A"
    rsi = f"{result.rsi:.1f}" if result.rsi is not None else "N/A"

    print(
        f"  {icons[result.signal]} [{result.symbol}] {result.signal.value:4s} | "
        f"Close: ${result.close:.2f}  "
        f"EMA{config.ema_fast}: {ema_f}  EMA{config.ema_slow}: {ema_s}  "
        f"RSI: {rsi} | {result.reason}"
    )


def _safe_float(value) -> float | None:
    return float(value) if pd.notna(value) else None


def _hold_result(symbol: str, df: pd.DataFrame, reason: str) -> AnalysisResult:
    return AnalysisResult(
        symbol=symbol,
        signal=Signal.HOLD,
        close=float(df["close"].iloc[-1]),
        ema_fast=None,
        ema_slow=None,
        rsi=None,
        reason=reason,
    )


def _is_golden_cross(
    prev_fast: float | None,
    prev_slow: float | None,
    fast: float,
    slow: float,
) -> bool:
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
    return (
        prev_fast is not None
        and prev_slow is not None
        and prev_fast >= prev_slow
        and fast < slow
    )
