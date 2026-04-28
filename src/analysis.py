"""
analysis.py — Módulo 3: Motor de Análisis (Cerebro).

Estrategia: Doble EMA + RSI con doble confirmación.

Lógica de señales:
    BUY  → EMA9 cruza por encima de EMA21 (momentum alcista)
            Y RSI < 70 (no sobrecomprado)
    SELL → EMA9 cruza por debajo de EMA21 (momentum bajista)
            O RSI > 70 (sobrecomprado — salir de posición larga)
    HOLD → No se cumplen condiciones de entrada/salida

Parámetros:
    EMA rápida  : 9 períodos  (sensible a movimientos recientes)
    EMA lenta   : 21 períodos (tendencia más estable)
    RSI         : 14 períodos (estándar de la industria)
    RSI overbought: 70
    RSI oversold  : 30

Requisito mínimo de datos:
    Se necesitan al menos 30 velas para que EMA21 y RSI14 sean válidos.
    Con menos velas los indicadores producen NaN y la señal será HOLD.
"""

import pandas as pd
import pandas_ta as ta
from dataclasses import dataclass
from enum import Enum


class Signal(Enum):
    """Señales posibles que puede emitir el motor de análisis."""
    BUY  = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


@dataclass
class AnalysisResult:
    """Resultado completo del análisis para un símbolo."""
    symbol:     str
    signal:     Signal
    close:      float
    ema_fast:   float | None   # EMA 9
    ema_slow:   float | None   # EMA 21
    rsi:        float | None   # RSI 14
    reason:     str            # Explicación legible de la señal


# ─────────────────────────────────────────────
# Parámetros de la estrategia (ajustables)
# ─────────────────────────────────────────────
EMA_FAST    = 9
EMA_SLOW    = 21
RSI_PERIOD  = 14
RSI_OB      = 70   # Overbought — zona de venta
RSI_OS      = 30   # Oversold   — zona de posible compra
MIN_BARS    = 30   # Mínimo de velas para resultados confiables


def calculate_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calcula indicadores técnicos sobre un DataFrame OHLCV.

    Agrega las columnas: EMA_9, EMA_21, RSI_14 al DataFrame.

    Args:
        df: DataFrame con columnas [open, high, low, close, volume]
            indexado por timestamp. Mínimo MIN_BARS filas.

    Returns:
        DataFrame original con las columnas de indicadores añadidas.

    Raises:
        ValueError: Si el DataFrame no tiene la columna 'close'.
    """
    if "close" not in df.columns:
        raise ValueError("El DataFrame debe tener columna 'close'.")

    df = df.copy()

    # EMA rápida y lenta
    df[f"EMA_{EMA_FAST}"] = ta.ema(df["close"], length=EMA_FAST)
    df[f"EMA_{EMA_SLOW}"] = ta.ema(df["close"], length=EMA_SLOW)

    # RSI
    df[f"RSI_{RSI_PERIOD}"] = ta.rsi(df["close"], length=RSI_PERIOD)

    return df


def get_signal(df: pd.DataFrame, symbol: str = "") -> AnalysisResult:
    """
    Evalúa la última vela del DataFrame e imprime la señal de trading.

    Requiere que el DataFrame ya tenga los indicadores calculados
    (llamar a calculate_indicators() primero).

    Detecta cruce de EMAs comparando la penúltima y última fila:
        - Cruce alcista (golden cross): EMA_fast cruza de abajo hacia arriba EMA_slow
        - Cruce bajista (death cross):  EMA_fast cruza de arriba hacia abajo EMA_slow

    Args:
        df:     DataFrame con indicadores ya calculados.
        symbol: Ticker del activo (para el resultado).

    Returns:
        AnalysisResult con la señal, valores de indicadores y razón.
    """
    ema_fast_col = f"EMA_{EMA_FAST}"
    rsi_col      = f"RSI_{RSI_PERIOD}"
    ema_slow_col = f"EMA_{EMA_SLOW}"

    # Verificar datos suficientes
    if len(df) < MIN_BARS:
        return AnalysisResult(
            symbol=symbol, signal=Signal.HOLD,
            close=float(df["close"].iloc[-1]),
            ema_fast=None, ema_slow=None, rsi=None,
            reason=f"Datos insuficientes ({len(df)} velas, mínimo {MIN_BARS})"
        )

    # Valores de la última y penúltima vela
    last = df.iloc[-1]
    prev = df.iloc[-2]

    close    = float(last["close"])
    ema_fast = float(last[ema_fast_col]) if pd.notna(last[ema_fast_col]) else None
    ema_slow = float(last[ema_slow_col]) if pd.notna(last[ema_slow_col]) else None
    rsi      = float(last[rsi_col])      if pd.notna(last[rsi_col])      else None

    # Sin indicadores válidos → HOLD
    if ema_fast is None or ema_slow is None or rsi is None:
        return AnalysisResult(
            symbol=symbol, signal=Signal.HOLD,
            close=close, ema_fast=ema_fast, ema_slow=ema_slow, rsi=rsi,
            reason="Indicadores con NaN — pocas velas o alta volatilidad"
        )

    prev_ema_fast = float(prev[ema_fast_col]) if pd.notna(prev[ema_fast_col]) else None
    prev_ema_slow = float(prev[ema_slow_col]) if pd.notna(prev[ema_slow_col]) else None

    # Detectar cruce alcista: EMA rápida cruza por ENCIMA de EMA lenta
    golden_cross = (
        prev_ema_fast is not None and prev_ema_slow is not None
        and prev_ema_fast <= prev_ema_slow   # antes: rápida debajo
        and ema_fast > ema_slow              # ahora: rápida encima
    )

    # Detectar cruce bajista: EMA rápida cruza por DEBAJO de EMA lenta
    death_cross = (
        prev_ema_fast is not None and prev_ema_slow is not None
        and prev_ema_fast >= prev_ema_slow   # antes: rápida encima
        and ema_fast < ema_slow              # ahora: rápida debajo
    )

    # ─── Lógica de señales ───
    if golden_cross and rsi < RSI_OB:
        return AnalysisResult(
            symbol=symbol, signal=Signal.BUY,
            close=close, ema_fast=ema_fast, ema_slow=ema_slow, rsi=rsi,
            reason=f"Golden cross EMA{EMA_FAST}/EMA{EMA_SLOW} + RSI {rsi:.1f} < {RSI_OB}"
        )

    if death_cross or rsi > RSI_OB:
        reason = (
            f"Death cross EMA{EMA_FAST}/EMA{EMA_SLOW}" if death_cross
            else f"RSI sobrecomprado: {rsi:.1f} > {RSI_OB}"
        )
        return AnalysisResult(
            symbol=symbol, signal=Signal.SELL,
            close=close, ema_fast=ema_fast, ema_slow=ema_slow, rsi=rsi,
            reason=reason
        )

    # Sin cruce → HOLD
    direction = "alcista" if ema_fast > ema_slow else "bajista"
    return AnalysisResult(
        symbol=symbol, signal=Signal.HOLD,
        close=close, ema_fast=ema_fast, ema_slow=ema_slow, rsi=rsi,
        reason=f"Tendencia {direction} sin cruce — mantener"
    )


def print_analysis(result: AnalysisResult) -> None:
    """
    Imprime en consola el resultado del análisis de forma legible.

    Args:
        result: AnalysisResult con todos los datos del análisis.
    """
    signal_icons = {Signal.BUY: "🟢", Signal.SELL: "🔴", Signal.HOLD: "🟡"}
    icon = signal_icons[result.signal]

    ema_f = f"{result.ema_fast:.2f}" if result.ema_fast else "N/A"
    ema_s = f"{result.ema_slow:.2f}" if result.ema_slow else "N/A"
    rsi   = f"{result.rsi:.1f}"      if result.rsi      else "N/A"

    print(
        f"  {icon} [{result.symbol}] {result.signal.value:4s} | "
        f"Close: ${result.close:.2f}  "
        f"EMA{EMA_FAST}: {ema_f}  EMA{EMA_SLOW}: {ema_s}  "
        f"RSI: {rsi} | {result.reason}"
    )
