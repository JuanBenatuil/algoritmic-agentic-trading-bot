"""
data_feed.py — Módulo 2: Motor de Datos (Data Feed).

Responsabilidades:
- Extraer velas OHLCV históricas para análisis técnico.
- Obtener la última vela y cotización en tiempo real.
- Retornar siempre DataFrames de pandas limpios y listos para análisis.

Nota sobre feeds de datos:
    La cuenta gratuita de Alpaca da acceso al feed IEX (Investors Exchange).
    El feed SIP (consolidado de todos los exchanges) requiere suscripción paga.
    Para daytrading con cuenta small, IEX es suficiente.
"""

import pandas as pd
from datetime import datetime, timedelta, timezone

from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import (
    StockBarsRequest,
    StockLatestBarRequest,
    StockLatestQuoteRequest,
)
from alpaca.data.timeframe import TimeFrame
from alpaca.data.enums import DataFeed


def get_historical_bars(
    client: StockHistoricalDataClient,
    symbol: str,
    timeframe: TimeFrame = TimeFrame.Minute,
    days_back: int = 5,
    feed: DataFeed = DataFeed.IEX,
) -> pd.DataFrame:
    """
    Obtiene velas OHLCV históricas para un símbolo.

    Args:
        client:    Cliente de datos históricos de Alpaca.
        symbol:    Ticker del activo (ej. "AAPL", "SPY").
        timeframe: Temporalidad de las velas (por defecto: 1 minuto).
        days_back: Cuántos días hacia atrás traer datos (por defecto: 5).
        feed:      Feed de datos a usar (IEX para cuenta gratuita).

    Returns:
        DataFrame con columnas [open, high, low, close, volume, vwap, trade_count],
        indexado por timestamp en UTC. Retorna DataFrame vacío si no hay datos.

    Raises:
        RuntimeError: Si la consulta a la API falla.
    """
    try:
        start = datetime.now(timezone.utc) - timedelta(days=days_back)

        request = StockBarsRequest(
            symbol_or_symbols=symbol,
            timeframe=timeframe,
            start=start,
            feed=feed,
        )

        bars = client.get_stock_bars(request)

        # bars.df tiene índice multi-nivel (symbol, timestamp).
        # NOTA: 'symbol in bars' es unreliable en BarSet — usamos el DataFrame
        # directamente y verificamos si el símbolo existe en el índice.
        if not bars:
            return pd.DataFrame()

        full_df = bars.df
        if symbol not in full_df.index.get_level_values(0):
            return pd.DataFrame()

        df = full_df.loc[symbol].copy()

        # Asegurar que el índice sea datetime con timezone UTC
        if not df.empty:
            df.index = pd.to_datetime(df.index, utc=True)
            df = df.sort_index()

        return df

    except Exception as e:
        raise RuntimeError(
            f"Error obteniendo barras históricas de {symbol}: {e}"
        ) from e


def get_latest_bar(
    client: StockHistoricalDataClient,
    symbol: str,
    feed: DataFeed = DataFeed.IEX,
) -> pd.Series | None:
    """
    Obtiene la última vela completada para un símbolo.

    Args:
        client: Cliente de datos históricos de Alpaca.
        symbol: Ticker del activo.
        feed:   Feed de datos a usar.

    Returns:
        Series con [open, high, low, close, volume, vwap, trade_count, timestamp],
        o None si no hay datos disponibles.

    Raises:
        RuntimeError: Si la consulta a la API falla.
    """
    try:
        request = StockLatestBarRequest(
            symbol_or_symbols=symbol,
            feed=feed,
        )
        response = client.get_stock_latest_bar(request)

        if not response or symbol not in response:
            return None

        bar = response[symbol]

        return pd.Series({
            "timestamp": bar.timestamp,
            "open":      bar.open,
            "high":      bar.high,
            "low":       bar.low,
            "close":     bar.close,
            "volume":    bar.volume,
            "vwap":      bar.vwap,
            "trade_count": bar.trade_count,
        })

    except Exception as e:
        raise RuntimeError(
            f"Error obteniendo última barra de {symbol}: {e}"
        ) from e


def get_latest_quote(
    client: StockHistoricalDataClient,
    symbol: str,
    feed: DataFeed = DataFeed.IEX,
) -> dict | None:
    """
    Obtiene la última cotización (bid/ask) para un símbolo.
    Útil para calcular el spread antes de entrar a una posición.

    Args:
        client: Cliente de datos históricos de Alpaca.
        symbol: Ticker del activo.
        feed:   Feed de datos a usar.

    Returns:
        Dict con {bid_price, bid_size, ask_price, ask_size, timestamp},
        o None si no hay datos disponibles.

    Raises:
        RuntimeError: Si la consulta a la API falla.
    """
    try:
        request = StockLatestQuoteRequest(
            symbol_or_symbols=symbol,
            feed=feed,
        )
        response = client.get_stock_latest_quote(request)

        if not response or symbol not in response:
            return None

        quote = response[symbol]

        return {
            "timestamp": quote.timestamp,
            "bid_price": quote.bid_price,
            "bid_size":  quote.bid_size,
            "ask_price": quote.ask_price,
            "ask_size":  quote.ask_size,
            "spread":    round(quote.ask_price - quote.bid_price, 4),
        }

    except Exception as e:
        raise RuntimeError(
            f"Error obteniendo cotización de {symbol}: {e}"
        ) from e


def print_latest_bar(symbol: str, bar: pd.Series) -> None:
    """
    Imprime en consola un resumen legible de la última vela.

    Args:
        symbol: Ticker del activo.
        bar:    Serie con los datos OHLCV de la vela.
    """
    # timestamp es el índice de la Series (bar.name), no una columna
    ts = bar.name
    if hasattr(ts, "strftime"):
        ts_str = ts.strftime("%Y-%m-%d %H:%M UTC")
    else:
        ts_str = str(ts)

    print(f"  [{symbol}] {ts_str} | "
          f"O:{bar['open']:.2f}  H:{bar['high']:.2f}  "
          f"L:{bar['low']:.2f}  C:{bar['close']:.2f}  "
          f"Vol:{int(bar['volume']):,}")
