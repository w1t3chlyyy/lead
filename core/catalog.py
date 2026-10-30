"""Актуальный каталог из Supabase магазина (products + projects)."""
from __future__ import annotations

import re
import time

import httpx

from .config import SHOP_SUPABASE_KEY, SHOP_SUPABASE_URL

TTL = 600
_cache = {"ts": 0.0, "text": ""}
_TAGS = re.compile(r"<[^>]+>")


def invalidate() -> None:
    _cache["ts"] = 0.0


def _h() -> dict:
    return {"apikey": SHOP_SUPABASE_KEY, "Authorization": f"Bearer {SHOP_SUPABASE_KEY}"}


async def get_catalog(http: httpx.AsyncClient) -> str:
    if _cache["text"] and time.time() - _cache["ts"] < TTL:
        return _cache["text"]
    try:
        r = await http.get(f"{SHOP_SUPABASE_URL}/rest/v1/products", headers=_h(), params={
            "select": "name,price,category,description,section",
            "deleted": "eq.false", "hidden": "eq.false", "limit": "150"})
        r.raise_for_status()
        products = r.json()
        r = await http.get(f"{SHOP_SUPABASE_URL}/rest/v1/projects", headers=_h(), params={
            "select": "title,short_desc", "hidden": "eq.false", "limit": "50"})
        r.raise_for_status()
        projects = r.json()
    except Exception as e:
        print(f"[catalog] ошибка загрузки: {e}")
        return _cache["text"] or "(каталог недоступен)"

    lines = ["ТОВАРЫ И УСЛУГИ:"]
    for p in products:
        tag = " (кейс/пример работы)" if p.get("section") == "case" else ""
        desc = _TAGS.sub("", p.get("description") or "")[:140]
        lines.append(f"- {p['name']}{tag} [{p.get('category') or ''}] от {p.get('price')} ₽ — {desc}")
    lines.append("НАШИ ПРОЕКТЫ:")
    for p in projects:
        lines.append(f"- {p['title']} — {_TAGS.sub('', p.get('short_desc') or '')[:140]}")
    _cache["text"], _cache["ts"] = "\n".join(lines), time.time()
    return _cache["text"]
