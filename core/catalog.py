"""Read the complete shop catalog from Supabase and retrieve relevant entries."""
from __future__ import annotations

import re
import time

import httpx

from .config import SHOP_SUPABASE_KEY, SHOP_SUPABASE_URL

TTL = 600
PAGE_SIZE = 1000
_cache = {"ts": 0.0, "items": []}
_TAGS = re.compile(r"<[^>]+>")
_WORDS = re.compile(r"[a-zа-яё0-9]+", re.I)
_STOP = {
    "а", "без", "бы", "в", "во", "вы", "для", "до", "его", "ее", "если", "есть",
    "и", "из", "или", "им", "их", "к", "как", "кто", "на", "над", "не", "ни",
    "но", "о", "об", "от", "по", "под", "при", "про", "с", "со", "у", "что",
    "это", "я", "мне", "мы", "ваш", "ваша", "ваше", "ваши", "наш", "наша",
    "нужен", "нужна", "нужно", "нужны", "ищу", "ищем", "хочу", "можно",
    "please", "the", "and", "for", "with", "from", "you", "your", "need",
    "looking", "want", "can", "get",
}


def invalidate() -> None:
    _cache["ts"] = 0.0


def _h() -> dict:
    return {
        "apikey": SHOP_SUPABASE_KEY,
        "Authorization": f"Bearer {SHOP_SUPABASE_KEY}",
        "Prefer": "count=exact",
    }


def _clean(value) -> str:
    return " ".join(_TAGS.sub(" ", str(value or "")).split())


def _tokens(value: str) -> set[str]:
    return {w.lower() for w in _WORDS.findall(value or "") if len(w) >= 3 and w.lower() not in _STOP}


async def _fetch_all(http: httpx.AsyncClient, table: str, filters: dict) -> list[dict]:
    """Fetch every matching row, respecting PostgREST's reported range/total."""
    rows: list[dict] = []
    offset = 0
    while True:
        params = {**filters, "limit": str(PAGE_SIZE), "offset": str(offset)}
        r = await http.get(f"{SHOP_SUPABASE_URL}/rest/v1/{table}", headers=_h(), params=params)
        r.raise_for_status()
        page = r.json()
        if not isinstance(page, list):
            raise RuntimeError(f"Supabase returned a non-list for {table}")
        if not page:
            break
        rows.extend(page)

        # count=exact lets pagination continue even when the project caps
        # the response below PAGE_SIZE.
        content_range = r.headers.get("content-range", "")
        match = re.search(r"/(\d+)$", content_range)
        total = int(match.group(1)) if match else None
        offset += len(page)
        if total is not None:
            if offset >= total:
                break
        elif len(page) < PAGE_SIZE:
            break
    return rows


def _prepare_items(products: list[dict], projects: list[dict]) -> list[dict]:
    items = []
    for p in products:
        item = {
            "kind": "product",
            "name": _clean(p.get("name")),
            "category": _clean(p.get("category")),
            "description": _clean(p.get("description")),
            "price": _clean(p.get("price")),
            "section": _clean(p.get("section")),
        }
        item["_name_tokens"] = _tokens(item["name"])
        item["_category_tokens"] = _tokens(item["category"])
        item["_description_tokens"] = _tokens(item["description"])
        if item["name"]:
            items.append(item)
    for p in projects:
        item = {
            "kind": "project",
            "name": _clean(p.get("title")),
            "category": "",
            "description": _clean(p.get("short_desc")),
            "price": "",
            "section": "case",
        }
        item["_name_tokens"] = _tokens(item["name"])
        item["_category_tokens"] = set()
        item["_description_tokens"] = _tokens(item["description"])
        if item["name"]:
            items.append(item)
    return items


async def get_items(http: httpx.AsyncClient) -> list[dict]:
    """Return the complete, cached catalog as structured entries."""
    if _cache["items"] and time.time() - _cache["ts"] < TTL:
        return _cache["items"]
    try:
        products = await _fetch_all(http, "products", {
            "select": "name,price,category,description,section",
            "deleted": "eq.false",
            "hidden": "eq.false",
        })
        projects = await _fetch_all(http, "projects", {
            "select": "title,short_desc",
            "hidden": "eq.false",
        })
        _cache["items"] = _prepare_items(products, projects)
        _cache["ts"] = time.time()
    except Exception as e:
        print(f"[catalog] ошибка загрузки: {e}")
        if not _cache["items"]:
            return []
    return _cache["items"]


def _format_item(item: dict, description_limit: int = 140) -> str:
    if item["kind"] == "project":
        desc = item["description"][:description_limit]
        return f"- {item['name']} (кейс/пример работы) — {desc}"
    tag = " (кейс/пример работы)" if item.get("section") == "case" else ""
    desc = item["description"][:description_limit]
    price = f" от {item['price']} ₽" if item.get("price") else ""
    category = f" [{item['category']}]" if item.get("category") else ""
    suffix = f" — {desc}" if desc else ""
    return f"- {item['name']}{tag}{category}{price}{suffix}"


async def get_catalog(http: httpx.AsyncClient) -> str:
    """Compact full catalog text for the bot's catalog screen and phrase generator."""
    items = await get_items(http)
    if not items:
        return "(каталог пуст или недоступен)"
    products = [x for x in items if x["kind"] == "product"]
    projects = [x for x in items if x["kind"] == "project"]
    lines = ["ТОВАРЫ И УСЛУГИ:"]
    lines.extend(_format_item(x) for x in products)
    lines.append("НАШИ ПРОЕКТЫ:")
    lines.extend(_format_item(x) for x in projects)
    return "\n".join(lines)


def catalog_for_message(items: list[dict], text: str, query: str = "", limit: int = 10) -> str:
    """Select a small relevant catalog slice so large catalogs fit the model context."""
    target = _tokens(f"{text} {query}")
    if not items:
        return "(каталог недоступен)"
    if not target:
        return "(нет ключевых слов для сопоставления с каталогом)"

    ranked = []
    for item in items:
        name = item["_name_tokens"]
        category = item["_category_tokens"]
        description = item["_description_tokens"]
        # Prefix matching handles common Russian inflections (e.g. "бот" / "бота").
        name_hits = sum(
            1 for a in target for b in name
            if a == b or (len(a) >= 3 and len(b) >= 3 and (a.startswith(b) or b.startswith(a)))
        )
        category_hits = sum(
            1 for a in target for b in category
            if a == b or (len(a) >= 3 and len(b) >= 3 and (a.startswith(b) or b.startswith(a)))
        )
        desc_hits = sum(
            1 for a in target for b in description
            if a == b or (len(a) >= 4 and len(b) >= 4 and (a.startswith(b) or b.startswith(a)))
        )
        score = name_hits * 5 + category_hits * 3 + desc_hits
        if score:
            ranked.append((score, item))

    ranked.sort(key=lambda x: x[0], reverse=True)
    if not ranked:
        # Keep a compact, balanced fallback so semantic matches and synonyms
        # still have a chance even when no token overlaps with the catalog.
        return "Краткий индекс каталога (выборка по всему каталогу):\n" + catalog_for_query_generation(
            items, max_chars=9000
        )
    return "\n".join(_format_item(item, description_limit=220) for _, item in ranked[:limit])


def catalog_for_query_generation(items: list[dict], max_chars: int = 18000) -> str:
    """Build a balanced catalog index for phrase generation without huge prompts."""
    if not items:
        return "(каталог пуст или недоступен)"
    # Evenly sample the full catalog so the prompt is not biased toward the
    # first page of database rows when the catalog exceeds the context budget.
    budget = max(1, max_chars // 100)
    if len(items) > budget:
        step = len(items) / budget
        selected = [items[int(i * step)] for i in range(budget)]
    else:
        selected = items
    lines = [_format_item(item, description_limit=70) for item in selected]
    result = "\n".join(lines)
    return result[:max_chars]