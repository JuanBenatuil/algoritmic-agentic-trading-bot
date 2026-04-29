"""
config.py — Carga y validación de variables de entorno.

Único punto de contacto con el archivo .env. El resto del código
importa AppConfig desde aquí, nunca directamente desde os.environ,
garantizando un único punto de configuración (SRP).
"""

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()

_VALID_MODES = ("paper", "live")


@dataclass(frozen=True)
class AppConfig:
    """Configuración inmutable de la aplicación.

    Usar un dataclass tipado en lugar de un dict genérico aporta:
    - Autocompletado e inferencia de tipos en el IDE.
    - Inmutabilidad (frozen=True): la config no puede mutar en runtime.
    - Documentación explícita de cada campo.
    """

    api_key: str
    secret_key: str
    paper: bool

    @property
    def mode(self) -> str:
        return "paper" if self.paper else "live"


def get_config() -> AppConfig:
    """Lee y valida las variables de entorno necesarias para el bot.

    Returns:
        AppConfig: Configuración tipada e inmutable.

    Raises:
        ValueError: Si alguna variable obligatoria no está definida o
                    si ALPACA_MODE tiene un valor inválido.
    """
    api_key    = os.getenv("ALPACA_API_KEY", "")
    secret_key = os.getenv("ALPACA_SECRET_KEY", "")
    mode_raw   = os.getenv("ALPACA_MODE", "paper").lower()

    _validate_credentials(api_key, secret_key)
    _validate_mode(mode_raw)

    return AppConfig(
        api_key=api_key,
        secret_key=secret_key,
        paper=(mode_raw == "paper"),
    )


# ─── helpers de validación (privados) ───────────────────────────────────────

def _validate_credentials(api_key: str, secret_key: str) -> None:
    """Verifica que las credenciales estén definidas y no sean placeholder."""
    missing = []
    for name, value in (("ALPACA_API_KEY", api_key), ("ALPACA_SECRET_KEY", secret_key)):
        if not value or value.startswith("TU_"):
            missing.append(name)

    if missing:
        raise ValueError(
            f"Variables de entorno faltantes o sin configurar: {', '.join(missing)}\n"
            "Copia .env.example como .env y rellena tus credenciales."
        )


def _validate_mode(mode: str) -> None:
    """Verifica que ALPACA_MODE sea 'paper' o 'live'."""
    if mode not in _VALID_MODES:
        raise ValueError(
            f"ALPACA_MODE inválido: '{mode}'. Debe ser 'paper' o 'live'."
        )
