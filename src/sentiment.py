"""
sentiment.py — Fachada del Modulo 5: Sentimiento.
"""

from src.domain.sentiment_models import SentimentResult
from src.services.sentiment_service import get_sentiment, print_sentiment

__all__ = [
    "SentimentResult",
    "get_sentiment",
    "print_sentiment",
]
