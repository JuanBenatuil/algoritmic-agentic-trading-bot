"""
alpaca_news_client.py — Cliente de noticias Alpaca.
"""

from datetime import datetime, timedelta, timezone
import logging
import requests

logger = logging.getLogger(__name__)

ALPACA_NEWS_URL = "https://data.alpaca.markets/v1beta1/news"


def get_headlines(
    symbol: str,
    api_key: str,
    secret_key: str,
    max_news: int,
    hours_back: int,
) -> list[str]:
    try:
        start = (datetime.now(timezone.utc) - timedelta(hours=hours_back)).isoformat()

        response = requests.get(
            ALPACA_NEWS_URL,
            headers={
                "APCA-API-KEY-ID": api_key,
                "APCA-API-SECRET-KEY": secret_key,
            },
            params={
                "symbols": symbol,
                "limit": max_news,
                "sort": "desc",
                "start": start,
            },
            timeout=10,
        )
        response.raise_for_status()
        news_items = response.json().get("news", [])
        return [item["headline"] for item in news_items if "headline" in item]

    except Exception as exc:
        logger.warning(f"[{symbol}] No se pudieron obtener noticias: {exc}")
        return []
