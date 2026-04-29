"""
sentiment.py — Módulo 5: Sentimiento de Noticias (Experimental).

Flujo:
    1. Obtener los últimos N titulares de Alpaca News para el símbolo.
    2. Enviar los titulares a Claude Haiku (Anthropic) para scoring.
    3. Retornar un score de sentimiento: +1 (alcista), 0 (neutral), -1 (bajista).

Integración con el ciclo de trading:
    - Score >= 0 → permite ejecutar señal BUY del Módulo 3.
    - Score  < 0 → bloquea la señal BUY (las noticias son negativas).
    - Señales SELL y HOLD no son afectadas por el sentimiento.

Degradación graciosa:
    - Si ANTHROPIC_API_KEY no está configurada → score 0 (neutral), sin bloqueos.
    - Si Alpaca News no devuelve titulares → score 0 (neutral), sin bloqueos.
    - Si la API de Anthropic falla → score 0 (neutral) + log de aviso.
    El bot siempre opera; el sentimiento es un filtro adicional, no un requisito.
"""

import os
import json
import logging
import requests
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# Configuración
# ─────────────────────────────────────────────
MAX_NEWS       = 5     # Número de titulares a analizar por símbolo
NEWS_HOURS_BACK = 24   # Buscar noticias de las últimas N horas
ALPACA_NEWS_URL = "https://data.alpaca.markets/v1beta1/news"
CLAUDE_MODEL    = "claude-haiku-4-5-20251001"


@dataclass
class SentimentResult:
    """Resultado del análisis de sentimiento para un símbolo."""
    symbol:    str
    score:     int          # +1, 0, -1
    reason:    str          # Explicación del modelo
    headlines: list[str]    # Titulares analizados
    available: bool         # False si el módulo no está configurado


# ─────────────────────────────────────────────
# Obtención de noticias (Alpaca News API)
# ─────────────────────────────────────────────

def _get_headlines(symbol: str, api_key: str, secret_key: str) -> list[str]:
    """
    Obtiene los titulares más recientes de Alpaca News para el símbolo.

    Args:
        symbol:     Ticker del activo.
        api_key:    Alpaca API Key.
        secret_key: Alpaca Secret Key.

    Returns:
        Lista de titulares (strings). Lista vacía si no hay noticias o falla la API.
    """
    try:
        start = (datetime.now(timezone.utc) - timedelta(hours=NEWS_HOURS_BACK)).isoformat()

        response = requests.get(
            ALPACA_NEWS_URL,
            headers={
                "APCA-API-KEY-ID":     api_key,
                "APCA-API-SECRET-KEY": secret_key,
            },
            params={
                "symbols": symbol,
                "limit":   MAX_NEWS,
                "sort":    "desc",
                "start":   start,
            },
            timeout=10,
        )
        response.raise_for_status()
        news_items = response.json().get("news", [])
        return [item["headline"] for item in news_items if "headline" in item]

    except Exception as e:
        logger.warning(f"[{symbol}] No se pudieron obtener noticias: {e}")
        return []


# ─────────────────────────────────────────────
# Scoring con Claude Haiku
# ─────────────────────────────────────────────

def _score_with_claude(symbol: str, headlines: list[str], anthropic_key: str) -> tuple[int, str]:
    """
    Usa Claude Haiku para analizar el sentimiento de los titulares.

    El prompt está diseñado para obtener una respuesta JSON estructurada
    con el score y una breve justificación.

    Args:
        symbol:        Ticker del activo.
        headlines:     Lista de titulares a analizar.
        anthropic_key: Clave de API de Anthropic.

    Returns:
        tuple (score, reason): score es +1, 0 o -1; reason es texto breve.
    """
    import anthropic

    headlines_text = "\n".join(f"- {h}" for h in headlines)

    prompt = f"""Eres un analista financiero. Analiza el sentimiento de estas noticias recientes sobre {symbol} para decidir si son alcistas, neutrales o bajistas para el precio de la acción a corto plazo.

Noticias:
{headlines_text}

Responde ÚNICAMENTE con un JSON válido, sin texto adicional:
{{"score": <número>, "reason": "<explicación breve en español de máximo 15 palabras>"}}

Donde score debe ser exactamente uno de estos valores:
 1  → noticias mayormente positivas/alcistas
 0  → noticias neutras o mixtas
-1  → noticias mayormente negativas/bajistas"""

    try:
        client = anthropic.Anthropic(api_key=anthropic_key)
        message = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=100,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = message.content[0].text.strip()
        data = json.loads(raw)
        score  = int(data.get("score", 0))
        reason = str(data.get("reason", "sin razón"))

        # Asegurar que el score sea válido
        if score not in (-1, 0, 1):
            score = 0

        return score, reason

    except json.JSONDecodeError:
        logger.warning(f"[{symbol}] Claude no devolvió JSON válido.")
        return 0, "respuesta inválida del modelo"
    except Exception as e:
        logger.warning(f"[{symbol}] Error en llamada a Anthropic: {e}")
        return 0, f"error de API: {str(e)[:50]}"


# ─────────────────────────────────────────────
# Función principal del módulo
# ─────────────────────────────────────────────

def get_sentiment(symbol: str, alpaca_api_key: str, alpaca_secret_key: str) -> SentimentResult:
    """
    Punto de entrada del Módulo 5.

    Obtiene titulares de Alpaca News y los scorea con Claude Haiku.
    Degrada graciosamente si algún componente no está disponible.

    Args:
        symbol:            Ticker del activo.
        alpaca_api_key:    Clave API de Alpaca (para la News API).
        alpaca_secret_key: Secret Key de Alpaca.

    Returns:
        SentimentResult con score (+1/0/-1), razón y titulares analizados.
    """
    anthropic_key = os.getenv("ANTHROPIC_API_KEY", "").strip()

    # Sin clave de Anthropic → módulo desactivado
    if not anthropic_key:
        return SentimentResult(
            symbol=symbol, score=0,
            reason="módulo desactivado (sin ANTHROPIC_API_KEY)",
            headlines=[], available=False,
        )

    # Obtener titulares
    headlines = _get_headlines(symbol, alpaca_api_key, alpaca_secret_key)
    if not headlines:
        return SentimentResult(
            symbol=symbol, score=0,
            reason="sin noticias recientes — se asume neutral",
            headlines=[], available=True,
        )

    # Scorear con Claude Haiku
    score, reason = _score_with_claude(symbol, headlines, anthropic_key)

    return SentimentResult(
        symbol=symbol, score=score,
        reason=reason, headlines=headlines,
        available=True,
    )


def print_sentiment(result: SentimentResult) -> None:
    """
    Imprime el resultado del análisis de sentimiento de forma legible.

    Args:
        result: SentimentResult con todos los datos del análisis.
    """
    if not result.available:
        return  # No loguear si el módulo está desactivado silenciosamente

    icons = {1: "📰🟢", 0: "📰🟡", -1: "📰🔴"}
    labels = {1: "ALCISTA", 0: "NEUTRAL", -1: "BAJISTA"}
    icon  = icons.get(result.score, "📰")
    label = labels.get(result.score, "NEUTRAL")

    print(f"  {icon} [{result.symbol}] Sentimiento: {label} | {result.reason}")
    if result.headlines:
        print(f"       Noticias analizadas: {len(result.headlines)}")
