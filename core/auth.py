from __future__ import annotations

import hashlib
import hmac
import json
import time
from urllib.parse import parse_qsl

from .config import BOT_TOKEN, CRON_SECRET, OWNER_IDS


def check_init_data(init_data: str, max_age: int = 86400) -> dict | None:
    """Проверка подписи Telegram Mini App. Возвращает user или None."""
    if not init_data:
        return None
    pairs = dict(parse_qsl(init_data, keep_blank_values=True))
    got = pairs.pop("hash", None)
    check = "\n".join(f"{k}={v}" for k, v in sorted(pairs.items()))
    secret = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
    calc = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    if not got or not hmac.compare_digest(calc, got):
        return None
    if time.time() - int(pairs.get("auth_date", 0) or 0) > max_age:
        return None
    try:
        return json.loads(pairs.get("user", "{}"))
    except Exception:
        return None


def is_owner_init_data(init_data: str) -> bool:
    user = check_init_data(init_data)
    return bool(user and user.get("id") in OWNER_IDS)


def cron_ok(req) -> bool:
    if not CRON_SECRET:
        return False
    bearer = req.headers.get("authorization", "")
    given = bearer[7:] if bearer.lower().startswith("bearer ") else req.query.get("key", "")
    return hmac.compare_digest(given, CRON_SECRET)
