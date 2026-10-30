"""Тонкая обёртка над Bot API."""
from __future__ import annotations

import httpx

from .config import BOT_TOKEN, OWNER_IDS

API = f"https://api.telegram.org/bot{BOT_TOKEN}"


async def call(http: httpx.AsyncClient, method: str, **data) -> dict:
    try:
        r = await http.post(f"{API}/{method}", json=data)
        j = r.json()
        if not j.get("ok") and "not modified" not in str(j.get("description", "")):
            print(f"[tg] {method}: {str(j)[:200]}")
        return j
    except Exception as e:
        print(f"[tg] {method} ошибка: {e}")
        return {"ok": False}


async def send(http, chat_id: int, text: str, kb: list | None = None) -> dict:
    data = {"chat_id": chat_id, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True}
    if kb:
        data["reply_markup"] = {"inline_keyboard": kb}
    return await call(http, "sendMessage", **data)


async def edit(http, chat_id: int, message_id: int, text: str, kb: list | None = None) -> dict:
    data = {"chat_id": chat_id, "message_id": message_id, "text": text,
            "parse_mode": "HTML", "disable_web_page_preview": True}
    if kb:
        data["reply_markup"] = {"inline_keyboard": kb}
    return await call(http, "editMessageText", **data)


async def answer(http, cb_id: str, text: str = "", alert: bool = False) -> None:
    await call(http, "answerCallbackQuery", callback_query_id=cb_id, text=text, show_alert=alert)


async def notify_owners(http, text: str, kb: list | None = None) -> None:
    for uid in OWNER_IDS:
        await send(http, uid, text, kb)
