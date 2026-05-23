"""
sentiment_service.py — Servicio de sentimiento.
"""

import os

from src.domain.sentiment_models import SentimentResult
from src.infra.sentiment.alpaca_news_client import get_headlines
from src.infra.sentiment.anthropic_client import score_headlines

MAX_NEWS = 5
NEWS_HOURS_BACK = 24
CLAUDE_MODEL = "claude-haiku-4-5-20251001"


def get_sentiment(symbol: str, alpaca_api_key: str, alpaca_secret_key: str) -> SentimentResult:
    anthropic_key = os.getenv("ANTHROPIC_API_KEY", "").strip()

    if not anthropic_key:
        return SentimentResult(
            symbol=symbol,
            score=0,
            reason="modulo desactivado (sin ANTHROPIC_API_KEY)",
            headlines=[],
            available=False,
        )

    headlines = get_headlines(
        symbol=symbol,
        api_key=alpaca_api_key,
        secret_key=alpaca_secret_key,
        max_news=MAX_NEWS,
        hours_back=NEWS_HOURS_BACK,
    )
    if not headlines:
        return SentimentResult(
            symbol=symbol,
            score=0,
            reason="sin noticias recientes — se asume neutral",
            headlines=[],
            available=True,
        )

    score, reason = score_headlines(symbol, headlines, anthropic_key, CLAUDE_MODEL)

    return SentimentResult(
        symbol=symbol,
        score=score,
        reason=reason,
        headlines=headlines,
        available=True,
    )


def print_sentiment(result: SentimentResult) -> None:
    if not result.available:
        return

    icons = {1: "📰🟢", 0: "📰🟡", -1: "📰🔴"}
    labels = {1: "ALCISTA", 0: "NEUTRAL", -1: "BAJISTA"}
    icon = icons.get(result.score, "📰")
    label = labels.get(result.score, "NEUTRAL")

    print(f"  {icon} [{result.symbol}] Sentimiento: {label} | {result.reason}")
    if result.headlines:
        print(f"       Noticias analizadas: {len(result.headlines)}")
