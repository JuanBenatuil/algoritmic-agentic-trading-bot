"""
notifier.py — Módulo de notificaciones vía Telegram.

Envía mensajes al usuario en los eventos clave del bot:
    - Arranque y apagado
    - Inicio de cada ciclo de análisis
    - Órdenes ejecutadas (compra/venta)
    - Stop-Loss y Take-Profit disparados
    - Errores críticos

Configuración (.env):
    TELEGRAM_BOT_TOKEN  — Token del bot (obtenido de @BotFather)
    TELEGRAM_CHAT_ID    — ID del chat destino (obtenido de @userinfobot)

Si alguna variable no está configurada, el módulo queda en modo silencioso
y el bot opera normalmente sin notificaciones.
"""

import json
import os
from urllib.error import URLError
from urllib.request import Request, urlopen


# ─── Singleton interno ────────────────────────────────────────────────────────

class _Notifier:
    def __init__(self) -> None:
        token   = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
        self._enabled = bool(token and chat_id)
        self._url     = f"https://api.telegram.org/bot{token}/sendMessage"
        self._chat_id = chat_id

    def send(self, text: str) -> None:
        if not self._enabled:
            return
        payload = json.dumps({
            "chat_id":    self._chat_id,
            "text":       text,
            "parse_mode": "HTML",
        }).encode()
        req = Request(self._url, data=payload, headers={"Content-Type": "application/json"})
        try:
            with urlopen(req, timeout=5):
                pass
        except (URLError, OSError):
            pass  # nunca bloquear el bot por un fallo de notificación


_notifier = _Notifier()


# ─── API pública ──────────────────────────────────────────────────────────────

def notify(text: str) -> None:
    """Envía un mensaje de Telegram. No lanza excepciones."""
    _notifier.send(text)


def notify_startup(mode: str, symbols: list[str]) -> None:
    symbols_str = ", ".join(symbols)
    notify(
        f"🤖 <b>Bot iniciado</b>\n"
        f"Modo: <code>{mode.upper()}</code>\n"
        f"Símbolos: {symbols_str}\n"
        f"Análisis: 9:35 ET · 12:30 ET\n"
        f"Monitoreo SL/TP: cada 30 min"
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


def notify_error(context: str, error: str) -> None:
    notify(f"❌ <b>Error — {context}</b>\n<code>{error}</code>")


def notify_shutdown() -> None:
    notify("🛑 <b>Bot detenido manualmente.</b>")
