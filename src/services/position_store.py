"""
position_store.py — Persistencia de posiciones abiertas.
"""

import json
import os
from pathlib import Path


def get_default_state_path() -> Path:
    return Path(os.getenv("STATE_FILE", "logs/posiciones.json"))


class PositionStore:
    def __init__(self, path: Path | None = None) -> None:
        self._path = path or get_default_state_path()

    def load(self) -> dict:
        if self._path.exists():
            try:
                with open(self._path, "r") as file:
                    return json.load(file)
            except (json.JSONDecodeError, IOError):
                return {}
        return {}

    def save(self, state: dict) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._path, "w") as file:
            json.dump(state, file, indent=2)

    def get_all(self) -> dict:
        return self.load()

    def has(self, symbol: str) -> bool:
        return symbol in self.load()

    def upsert(self, symbol: str, data: dict) -> None:
        state = self.load()
        state[symbol] = data
        self.save(state)

    def remove(self, symbol: str) -> None:
        state = self.load()
        state.pop(symbol, None)
        self.save(state)
