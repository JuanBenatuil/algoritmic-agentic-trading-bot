"""
notification_service.py — Servicios de notificacion.
"""

import os

from src.infra.notifications.telegram_client import TelegramNotifier


_notifier = TelegramNotifier(
    token=os.getenv("TELEGRAM_BOT_TOKEN", "").strip(),
    chat_id=os.getenv("TELEGRAM_CHAT_ID", "").strip(),
)


def notify(text: str) -> None:
    _notifier.send(text)


def notify_startup(mode: str, symbols: list[str]) -> None:
    symbols_str = ", ".join(symbols)
    notify(
        "🤖 <b>Bot iniciado</b>\n"
        f"Modo: <code>{mode.upper()}</code>\n"
        f"Simbolos: {symbols_str}\n"
        "Analisis: 9:35 ET · 12:30 ET\n"
        "Monitoreo SL/TP: cada 30 min"
    )


def notify_cycle(momento: str) -> None:
    notify(f"⏱ <b>Ciclo {momento.upper()} iniciado</b>")


def notify_buy(symbol: str, notional: float, precio: float, sl: float, tp: float) -> None:
    fracciones = notional / precio
    notify(
        f"✅ <b>COMPRA ejecutada — {symbol}</b>\n"
        f"Monto: <code>${notional:.2f}</code> (~{fracciones:.4f} acc)\n"
        f"Precio: <code>${precio:.2f}</code>\n"
        f"SL: <code>${sl:.2f}</code> · TP: <code>${tp:.2f}</code>"
    )


def notify_sell(symbol: str, motivo: str) -> None:
    notify(f"📤 <b>VENTA ejecutada — {symbol}</b>\nMotivo: {motivo}")


def notify_stop_loss(symbol: str, entrada: float, actual: float, pnl_pct: float) -> None:
    notify(
        f"🔴 <b>Stop-Loss — {symbol}</b>\n"
        f"Entrada: <code>${entrada:.2f}</code> · Actual: <code>${actual:.2f}</code>\n"
        f"P&amp;L: <code>{pnl_pct:.2f}%</code>"
    )


def notify_take_profit(symbol: str, entrada: float, actual: float, pnl_pct: float) -> None:
    notify(
        f"🟢 <b>Take-Profit — {symbol}</b>\n"
        f"Entrada: <code>${entrada:.2f}</code> · Actual: <code>${actual:.2f}</code>\n"
        f"P&amp;L: <code>+{pnl_pct:.2f}%</code>"
    )


def notify_universe(symbols: list[str], total_pool: int, total_candidatos: int, reason: str) -> None:
    symbols_str = " · ".join(f"<code>{s}</code>" for s in symbols)
    reason_line = f"\n💡 {reason}" if reason else ""
    notify(
        f"🌐 <b>Universo del día ({len(symbols)} acciones)</b>\n"
        f"Pool analizado: {total_pool} · Con momentum: {total_candidatos}\n"
        f"{symbols_str}"
        f"{reason_line}"
    )


def notify_error(context: str, error: str) -> None:
    notify(f"❌ <b>Error — {context}</b>\n<code>{error}</code>")


def notify_shutdown() -> None:
    notify("🛑 <b>Bot detenido manualmente.</b>")
