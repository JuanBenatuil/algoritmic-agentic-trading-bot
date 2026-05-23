"""
anthropic_client.py — Cliente para scoring de titulares con Claude.
"""

import json
import logging

logger = logging.getLogger(__name__)


def score_headlines(
    symbol: str,
    headlines: list[str],
    api_key: str,
    model: str,
) -> tuple[int, str]:
    import anthropic

    headlines_text = "\n".join(f"- {h}" for h in headlines)

    prompt = (
        f"Eres un analista financiero. Analiza el sentimiento de estas noticias "
        f"recientes sobre {symbol} para decidir si son alcistas, neutrales o "
        "bajistas para el precio de la accion a corto plazo.\n\n"
        "Noticias:\n"
        f"{headlines_text}\n\n"
        "Responde UNICAMENTE con un JSON valido, sin texto adicional:\n"
        "{\"score\": <numero>, \"reason\": \"explicacion breve en espanol de maximo 15 palabras\"}\n\n"
        "Donde score debe ser exactamente uno de estos valores:\n"
        " 1  → noticias mayormente positivas/alcistas\n"
        " 0  → noticias neutras o mixtas\n"
        "-1  → noticias mayormente negativas/bajistas"
    )

    try:
        client = anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model=model,
            max_tokens=100,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = message.content[0].text.strip()
        data = json.loads(raw)
        score = int(data.get("score", 0))
        reason = str(data.get("reason", "sin razon"))

        if score not in (-1, 0, 1):
            score = 0

        return score, reason

    except json.JSONDecodeError:
        logger.warning(f"[{symbol}] Claude no devolvio JSON valido.")
        return 0, "respuesta invalida del modelo"
    except Exception as exc:
        logger.warning(f"[{symbol}] Error en llamada a Anthropic: {exc}")
        return 0, f"error de API: {str(exc)[:50]}"
