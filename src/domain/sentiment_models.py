"""
sentiment_models.py — Modelos de dominio para sentimiento.
"""

from dataclasses import dataclass


@dataclass
class SentimentResult:
    symbol: str
    score: int
    reason: str
    headlines: list[str]
    available: bool
