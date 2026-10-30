"""Тексты и инлайн-клавиатуры бота."""
from __future__ import annotations

import html
from datetime import datetime, timezone

from .config import APP_URL

e = html.escape

STATUS = {
    "new": "🆕 новый",
    "work": "🔧 в работе",
    "won": "💰 сделка",
    "lost": "🚫 не сложилось",
    "bad": "❌ не лид",
}


def b(text: str, cb: str | None = None, url: str | None = None, web: str | None = None) -> dict:
    d = {"text": text}
    if cb:
        d["callback_data"] = cb
    if url:
        d["url"] = url
    if web:
        d["web_app"] = {"url": web}
    return d


def ago(iso: str | None) -> str:
    if not iso:
        return ""
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return ""
    s = (datetime.now(timezone.utc) - dt).total_seconds()
    if s < 3600:
        return f"{max(1, int(s // 60))} мин назад"
    if s < 86400:
        return f"{int(s // 3600)} ч назад"
    return f"{int(s // 86400)} д назад"


BACK = [b("⬅️ Меню", "m:main")]


# ---------- карточка лида ----------
def lead_card(l: dict) -> str:
    head = f"🎯 <b>Лид · {l.get('score', 0)}%</b>"
    if l.get("match"):
        head += f" → <b>{e(l['match'])}</b>"
    parts = [
        head,
        f"💬 <i>{e(l.get('chat_title') or 'чат')}</i> · {e(l.get('author') or '—')} · {ago(l.get('msg_date'))}",
        f"📌 {STATUS.get(l.get('status', 'new'), l.get('status'))}",
        "",
        e((l.get("text") or "")[:700]),
    ]
    if l.get("reason"):
        parts += ["", f"🧠 {e(l['reason'])}"]
    if l.get("reply"):
        parts += ["", "✍️ Черновик ответа:", f"<code>{e(l['reply'])}</code>"]
    return "\n".join(parts)


def lead_kb(l: dict) -> list:
    i, st = l["id"], l.get("status", "new")
    links = []
    if l.get("link"):
        links.append(b("Открыть сообщение", url=l["link"]))
    if l.get("author_url"):
        links.append(b("Написать автору", url=l["author_url"]))
    if st == "new":
        row = [b("✅ В работу", f"l:st:{i}:work"), b("❌ Не лид", f"l:st:{i}:bad")]
    elif st == "work":
        row = [b("💰 Сделка", f"l:st:{i}:won"), b("🚫 Не сложилось", f"l:st:{i}:lost")]
    else:
        row = [b("↩️ Вернуть в новые", f"l:st:{i}:new")]
    kb = []
    if links:
        kb.append(links)
    kb.append(row)
    kb.append([b("🔁 Другой черновик", f"l:re:{i}"), b("⬅️ Меню", "m:main")])
    return kb


# ---------- главное меню ----------
def main_menu(cfg: dict, new_cnt: int, work_cnt: int) -> tuple[str, list]:
    state = "🟢 поиск включён" if cfg.get("enabled") else "⏸ поиск на паузе"
    last = ago(cfg.get("last_scan")) or "ещё не запускался"
    text = (
        "<b>Охотник за заказами</b>\n"
        f"{state}\n"
        f"Свежесть: не старше {cfg['max_age_days']} дн. · порог {cfg['min_score']}%\n"
        f"Последний скан: {last}\n\n"
        f"🆕 новых лидов: <b>{new_cnt}</b> · 🔧 в работе: <b>{work_cnt}</b>"
    )
    kb = [
        [b(f"📥 Новые лиды ({new_cnt})", "m:leads:new:0"), b("🔎 Искать сейчас", "m:scan")],
        [b("🔧 В работе", "m:leads:work:0"), b("🗂 Все лиды", "m:leads:all:0")],
        [b("🔑 Фразы поиска", "m:q:0"), b("⚙️ Настройки", "m:set")],
        [b("📦 Каталог", "m:cat")],
    ]
    if APP_URL.startswith("https://"):
        kb.append([b("📊 Статистика", web=APP_URL)])
    return text, kb


# ---------- список лидов ----------
FILTERS = {"new": "Новые", "work": "В работе", "won": "Сделки", "all": "Все"}
PAGE = 6


def leads_list(rows: list, flt: str, page: int, has_next: bool) -> tuple[str, list]:
    text = f"<b>{FILTERS[flt]}</b> · стр. {page + 1}" if rows else f"<b>{FILTERS[flt]}</b>\nПока пусто."
    kb = []
    for l in rows:
        label = f"{l['score']}% · {(l.get('match') or l.get('chat_title') or 'лид')[:22]} · {ago(l.get('msg_date'))}"
        kb.append([b(label, f"l:v:{l['id']}")])
    nav = []
    if page > 0:
        nav.append(b("◀️", f"m:leads:{flt}:{page - 1}"))
    if has_next:
        nav.append(b("▶️", f"m:leads:{flt}:{page + 1}"))
    if nav:
        kb.append(nav)
    kb.append([b(("• " if k == flt else "") + v, f"m:leads:{k}:0") for k, v in FILTERS.items()])
    kb.append(BACK)
    return text, kb


# ---------- настройки ----------
def settings_screen(cfg: dict) -> tuple[str, list]:
    text = (
        "<b>Настройки</b>\n"
        f"Статус: {'включён' if cfg['enabled'] else 'на паузе'}\n"
        f"Возраст сообщений: до {cfg['max_age_days']} дн.\n"
        f"Порог уверенности: {cfg['min_score']}%\n"
        f"Фраз за один запуск: {cfg['queries_per_run']}"
    )

    def chips(prefix, values, cur, suffix=""):
        return [b(("• " if v == cur else "") + f"{v}{suffix}", f"s:{prefix}:{v}") for v in values]

    kb = [
        [b("⏸ Поставить на паузу" if cfg["enabled"] else "▶️ Включить поиск", "s:tog")],
        [b("Возраст:", "noop")] + chips("age", (1, 2, 3), cfg["max_age_days"], " д"),
        [b("Порог:", "noop")] + chips("score", (50, 60, 70, 80), cfg["min_score"], "%"),
        [b("Фраз/запуск:", "noop")] + chips("qpr", (2, 4, 6, 8), cfg["queries_per_run"]),
        BACK,
    ]
    return text, kb


# ---------- фразы поиска ----------
QPAGE = 8


def queries_screen(rows: list, page: int, has_next: bool) -> tuple[str, list]:
    text = ("<b>Фразы поиска</b>\nКаждый запуск берёт те, что давно не проверялись. "
            "В скобках — сколько лидов принесла фраза.")
    kb = []
    for q in rows:
        dot = "🟢" if q["active"] else "⚪️"
        kb.append([b(f"{dot} {q['q'][:28]} ({q['hits']})", f"q:tg:{q['id']}:{page}"),
                   b("🗑", f"q:del:{q['id']}:{page}")])
    nav = []
    if page > 0:
        nav.append(b("◀️", f"m:q:{page - 1}"))
    if has_next:
        nav.append(b("▶️", f"m:q:{page + 1}"))
    if nav:
        kb.append(nav)
    kb.append([b("➕ Добавить", "q:add"), b("♻️ По умолчанию", "q:reset")])
    kb.append(BACK)
    return text, kb
