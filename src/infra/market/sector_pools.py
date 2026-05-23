"""
sector_pools.py — Universo de acciones por sector para el descubrimiento diario.

El bot parte de este pool de ~50 acciones, filtra por momentum técnico y
luego Claude elige las mejores del día. Actualizar este archivo para ampliar
o ajustar los sectores cubiertos.
"""

SECTOR_POOLS: dict[str, list[str]] = {
    # Semiconductores — inspirado en SOXX (iShares Semiconductor ETF)
    "semiconductores": [
        "NVDA", "AMD", "AVGO", "QCOM", "AMAT",
        "MU",   "LRCX", "KLAC", "TXN",  "ADI",
        "INTC", "ON",   "MCHP", "SWKS", "WOLF",
    ],
    # Mega-cap tech
    "mega_tech": [
        "AAPL", "MSFT", "GOOGL", "META", "AMZN",
    ],
    # Growth / software
    "growth_tech": [
        "TSLA", "CRM", "NOW", "SNOW", "PLTR", "CRWD", "NET",
    ],
    # ETFs de referencia (liquidez alta, buenos para momentum)
    "etfs": [
        "SPY", "QQQ", "SOXX", "XLK", "IWM",
    ],
    # Finanzas
    "finanzas": [
        "JPM", "GS", "BAC", "MS",
    ],
    # Salud / biotech
    "salud": [
        "UNH", "LLY", "ABBV", "MRNA",
    ],
}


def get_full_pool() -> list[str]:
    """Devuelve todos los símbolos del pool sin duplicados, manteniendo orden por sector."""
    seen: set[str] = set()
    result: list[str] = []
    for symbols in SECTOR_POOLS.values():
        for s in symbols:
            if s not in seen:
                seen.add(s)
                result.append(s)
    return result
