"""
config.py — Carga y validación de variables de entorno.

Este módulo es el único punto de contacto con el archivo .env.
El resto del código importa las variables desde aquí, nunca directamente
desde os.environ, para mantener un único lugar de configuración.
"""

import os
from dotenv import load_dotenv

# Carga las variables del archivo .env al entorno del proceso
load_dotenv()


def get_config() -> dict:
    """
    Lee y valida las variables de entorno necesarias para el bot.

    Returns:
        dict: Diccionario con las claves de configuración.

    Raises:
        ValueError: Si alguna variable obligatoria no está definida.
    """
    required_vars = {
        "ALPACA_API_KEY": os.getenv("ALPACA_API_KEY"),
        "ALPACA_SECRET_KEY": os.getenv("ALPACA_SECRET_KEY"),
        "ALPACA_MODE": os.getenv("ALPACA_MODE", "paper"),
    }

    # Validar que las variables críticas existan y no sean el valor de ejemplo
    missing = []
    for var_name, value in required_vars.items():
        if not value or value.startswith("TU_"):
            missing.append(var_name)

    if missing:
        raise ValueError(
            f"Variables de entorno faltantes o sin configurar: {', '.join(missing)}\n"
            "Por favor, copia .env.example como .env y rellena tus credenciales."
        )

    # Validar modo de operación
    mode = required_vars["ALPACA_MODE"].lower()
    if mode not in ("paper", "live"):
        raise ValueError(
            f"ALPACA_MODE inválido: '{mode}'. Debe ser 'paper' o 'live'."
        )

    return {
        "api_key": required_vars["ALPACA_API_KEY"],
        "secret_key": required_vars["ALPACA_SECRET_KEY"],
        "paper": mode == "paper",
    }
