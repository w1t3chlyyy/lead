"""Общие типы для HTTP-обработчиков (routes/*)."""
from __future__ import annotations

import json
from dataclasses import dataclass


@dataclass
class Req:
    method: str
    path: str
    query: dict
    headers: dict
    body: bytes = b""

    def json(self) -> dict:
        try:
            return json.loads(self.body or b"{}")
        except Exception:
            return {}


JSON = "application/json"


def encode(payload) -> bytes:
    if isinstance(payload, bytes):
        return payload
    if isinstance(payload, str):
        return payload.encode()
    return json.dumps(payload, ensure_ascii=False).encode()
