"""
analysis.py — Fachada del Modulo 3: Motor de Analisis.

Mantiene la API publica original y delega la logica a la estrategia EMA/RSI.
"""

from src.domain.analysis_models import AnalysisResult, Signal, StrategyConfig
from src.strategies.ema_rsi import calculate_indicators, get_signal, print_analysis

__all__ = [
    "AnalysisResult",
    "Signal",
    "StrategyConfig",
    "calculate_indicators",
    "get_signal",
    "print_analysis",
]
