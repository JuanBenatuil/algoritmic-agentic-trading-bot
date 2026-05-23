"""
universe_service.py — Descubrimiento dinámico de acciones para operar cada día.

Proceso (se ejecuta una vez al día antes del primer ciclo de análisis):
  1. Descarga barras de 5 días para las ~50 acciones del pool de sectores.
  2. Filtra las que muestran momentum alcista confirmado (EMA9 > EMA21 en
     las últimas dos velas de 15 min).
  3. Pasa los candidatos a Claude Haiku con noticias recientes del mercado.
  4. Claude elige las mejores MAX_SYMBOLS acciones para ese día.
  5. Si Claude no está disponible, usa las top N por fuerza técnica.

El resultado se usa como lista dinámica de símbolos en main.py, reemplazando
la lista fija [SPY, AAPL, TSLA, NVDA].
"""

import json
import logging
import os
from datetime import datetime, timedelta, timezone

from src.notifier import notify_universe

logger = logging.getLogger(__name__)

MAX_SYMBOLS = 10
FALLBACK    = ["SPY", "AAPL", "TSLA", "NVDA", "NVDA", "AMD", "MSFT", "GOOGL", "META", "AMZN"]


def build_daily_universe(
    data_client,
    alpaca_api_key: str,
    alpaca_secret_key: str,
    max_symbols: int = MAX_SYMBOLS,
) -> list[str]:
    """Construye la lista diaria de símbolos a analizar.

    Args:
        data_client:       StockHistoricalDataClient de Alpaca.
        alpaca_api_key:    Key de Alpaca (para noticias).
        alpaca_secret_key: Secret de Alpaca (para noticias).
        max_symbols:       Máximo de símbolos a devolver.

    Returns:
        Lista de tickers ordenada por prioridad para ese día.
    """
    from src.infra.market.sector_pools import get_full_pool

    pool = get_full_pool()
    print(f"\n  🌐 Descubrimiento de universo — analizando {len(pool)} acciones...")

    candidatos = _filtrar_momentum(data_client, pool)

    if not candidatos:
        print("  ⚠️  Sin candidatos técnicos — usando lista base.")
        notify_universe(FALLBACK[:max_symbols], len(pool), 0, "sin momentum alcista hoy, usando lista base")
        return FALLBACK[:max_symbols]

    print(f"  📈 {len(candidatos)} acciones con momentum alcista confirmado.")

    anthropic_key = os.getenv("ANTHROPIC_API_KEY", "")
    if anthropic_key.startswith("sk-ant-"):
        ranked, reason = _rankear_con_claude(
            candidatos, alpaca_api_key, alpaca_secret_key, anthropic_key, max_symbols
        )
        if ranked:
            notify_universe(ranked, len(pool), len(candidatos), reason)
            return ranked

    # Fallback técnico: top N por mayor spread EMA9-EMA21
    top = [s for s, _ in sorted(candidatos.items(), key=lambda x: x[1], reverse=True)]
    result = top[:max_symbols]
    print(f"  📊 Universo técnico (sin Claude): {result}")
    notify_universe(result, len(pool), len(candidatos), "")
    return result


# ─── Filtro técnico ───────────────────────────────────────────────────────────

def _filtrar_momentum(data_client, pool: list[str]) -> dict[str, float]:
    """Descarga barras de 5 días para todo el pool y filtra por EMA9 > EMA21.

    Returns:
        Dict {symbol: pct_diferencia_ema9_ema21} solo para acciones alcistas.
    """
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
    from alpaca.data.enums import DataFeed

    try:
        end   = datetime.now(timezone.utc)
        start = end - timedelta(days=7)
        req   = StockBarsRequest(
            symbol_or_symbols=pool,
            timeframe=TimeFrame(15, TimeFrameUnit.Minute),
            start=start,
            end=end,
            feed=DataFeed.IEX,
        )
        df = data_client.get_stock_bars(req).df
    except Exception as exc:
        logger.warning(f"Universe: error obteniendo barras del pool: {exc}")
        return {}

    candidatos: dict[str, float] = {}
    symbols_en_respuesta = set(df.index.get_level_values(0))

    for symbol in pool:
        if symbol not in symbols_en_respuesta:
            continue
        try:
            close = df.loc[symbol]["close"]
            if len(close) < 30:
                continue
            ema9  = close.ewm(span=9,  adjust=False).mean()
            ema21 = close.ewm(span=21, adjust=False).mean()
            e9,  e21  = float(ema9.iloc[-1]),  float(ema21.iloc[-1])
            pe9, pe21 = float(ema9.iloc[-2]),  float(ema21.iloc[-2])
            # Tendencia alcista confirmada: EMA9 > EMA21 en las dos últimas barras
            if e9 > e21 and pe9 > pe21:
                candidatos[symbol] = round((e9 - e21) / e21 * 100, 4)
        except Exception:
            continue

    return candidatos


# ─── Ranking con Claude ───────────────────────────────────────────────────────

def _rankear_con_claude(
    candidatos: dict[str, float],
    alpaca_api_key: str,
    alpaca_secret_key: str,
    anthropic_key: str,
    max_symbols: int,
) -> tuple[list[str], str]:
    """Pide a Claude que elija los mejores símbolos del día según noticias.

    Returns:
        (lista de símbolos seleccionados, razón) — o ([], "") si falla.
    """
    import anthropic
    from src.infra.sentiment.alpaca_news_client import get_headlines
    from src.infra.market.sector_pools import SECTOR_POOLS

    # Noticias para los top candidatos por momentum (máx 8 símbolos para no saturar)
    top_candidatos = sorted(candidatos.items(), key=lambda x: x[1], reverse=True)
    simbolos_noticias = [s for s, _ in top_candidatos[:8]]
    tickers_str = ",".join(simbolos_noticias)

    headlines = get_headlines(
        symbol=tickers_str,
        api_key=alpaca_api_key,
        secret_key=alpaca_secret_key,
        max_news=15,
        hours_back=24,
    )

    # Armar contexto de candidatos con sector
    ticker_a_sector = {
        sym: sector
        for sector, syms in SECTOR_POOLS.items()
        for sym in syms
    }
    candidatos_str = "\n".join(
        f"- {sym} [{ticker_a_sector.get(sym, 'otro')}]: EMA spread +{diff:.3f}%"
        for sym, diff in top_candidatos
    )
    noticias_str = (
        "\n".join(f"- {h}" for h in headlines[:12])
        if headlines else "Sin noticias recientes disponibles."
    )

    prompt = (
        "Eres un analista cuantitativo especializado en trading de corto plazo (day trading).\n\n"
        f"Estas acciones muestran momentum tecnico alcista confirmado hoy "
        f"(EMA9 > EMA21 en velas de 15 minutos):\n\n"
        f"{candidatos_str}\n\n"
        f"Noticias recientes del mercado:\n{noticias_str}\n\n"
        f"Selecciona las mejores {max_symbols} acciones para operar hoy. Criterios:\n"
        f"1. Mayor fuerza de momentum tecnico (mayor spread EMA)\n"
        f"2. Sectores favorecidos por las noticias del dia\n"
        f"3. Diversificacion: no mas de 3 acciones del mismo sector\n"
        f"4. Excluir acciones con noticias negativas relevantes\n\n"
        f"Responde UNICAMENTE con JSON valido:\n"
        f"{{\"symbols\": [\"SYM1\", \"SYM2\", ...], "
        f"\"reason\": \"explicacion en espanol de max 20 palabras\"}}"
    )

    try:
        client  = anthropic.Anthropic(api_key=anthropic_key)
        message = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=250,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = message.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()

        data    = json.loads(raw)
        symbols = [s for s in data.get("symbols", []) if s in candidatos]
        reason  = data.get("reason", "")

        if not symbols:
            return [], ""

        result = symbols[:max_symbols]
        print(f"  🤖 Universo Claude ({len(result)} acciones): {result}")
        if reason:
            print(f"  💡 Razon: {reason}")
        return result, reason

    except Exception as exc:
        logger.warning(f"Universe: error en Claude ranking: {exc}")
        return [], ""
