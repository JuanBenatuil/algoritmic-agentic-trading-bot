"""
notifier.py — Fachada de notificaciones.
"""

from src.services.notification_service import (
    notify,
    notify_buy,
    notify_cycle,
    notify_error,
    notify_sell,
    notify_shutdown,
    notify_startup,
    notify_stop_loss,
    notify_take_profit,
    notify_universe,
)

__all__ = [
    "notify",
    "notify_buy",
    "notify_cycle",
    "notify_error",
    "notify_sell",
    "notify_shutdown",
    "notify_startup",
    "notify_stop_loss",
    "notify_take_profit",
    "notify_universe",
]
