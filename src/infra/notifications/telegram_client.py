"""
telegram_client.py — Cliente minimo para Telegram.
"""

import json
from urllib.error import URLError
from urllib.request import Request, urlopen


class TelegramNotifier:
    def __init__(self, token: str, chat_id: str) -> None:
        self._enabled = bool(token and chat_id)
        self._url = f"https://api.telegram.org/bot{token}/sendMessage"
        self._chat_id = chat_id

    def send(self, text: str) -> None:
        if not self._enabled:
            return
        payload = json.dumps({
            "chat_id": self._chat_id,
            "text": text,
            "parse_mode": "HTML",
        }).encode()
        req = Request(self._url, data=payload, headers={"Content-Type": "application/json"})
        try:
            with urlopen(req, timeout=5):
                pass
        except (URLError, OSError):
            pass
