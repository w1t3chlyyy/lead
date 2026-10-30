"""Один проход глобального поиска по ВСЕМ публичным чатам Telegram (не только тем, где ты состоишь).

Запускается по расписанию (GitHub Actions / Vercel Cron) или кнопкой в боте.
Telethon подключается, делает несколько SearchGlobal-запросов за последние N дней (N <= 3) и отключается."""
from __future__ import annotations

import asyncio
import hashlib
import re
import time
from datetime import timedelta

from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.functions.messages import SearchGlobalRequest
from telethon.tl.types import Channel, InputMessagesFilterEmpty, InputPeerEmpty, Message

from . import catalog, db, llm, tg, ui
from .config import (MAX_AGE_LIMIT_DAYS, MAX_PUSH_PER_RUN, OWNER_IDS, TG_API_HASH, TG_API_ID,
                     TG_SESSION_STRING)
from .keywords import DEFAULT_QUERIES, quick_filter


async def ensure_queries(http) -> None:
    if not await db.sel(http, "lb_queries", select="id", limit="1"):
        await db.ins(http, "lb_queries", [{"q": q} for q in DEFAULT_QUERIES], on_conflict="q", ignore=True)


def build_link(chat, msg_id: int) -> str:
    username = getattr(chat, "username", None)
    return f"https://t.me/{username}/{msg_id}" if username else f"https://t.me/c/{chat.id}/{msg_id}"


async def _search(client, q: str, cutoff, pages: int = 2):
    """Глобальный поиск с пагинацией. Возвращает (messages, chats, users)."""
    msgs, chats, users = [], {}, {}
    rate, peer, last_id = 0, InputPeerEmpty(), 0
    for _ in range(pages):
        kw = dict(q=q, filter=InputMessagesFilterEmpty(), min_date=cutoff, max_date=None,
                  offset_rate=rate, offset_peer=peer, offset_id=last_id, limit=50)
        try:
            req = SearchGlobalRequest(groups_only=True, **kw)  # новые слои Telegram: только группы
        except TypeError:
            req = SearchGlobalRequest(**kw)
        res = await client(req)
        msgs += list(res.messages)
        chats.update({c.id: c for c in res.chats})
        users.update({u.id: u for u in res.users})
        next_rate = getattr(res, "next_rate", None)
        if not res.messages or not next_rate:
            break
        try:
            last = res.messages[-1]
            peer = await client.get_input_entity(last.peer_id)
            rate, last_id = next_rate, last.id
        except Exception:
            break
    return msgs, chats, users


async def _process(http, cfg, cat, bad, m, chat, sender, query, st, sem) -> bool:
    text = m.message
    if not quick_filter(text):
        return False
    st["passed"] += 1
    norm = re.sub(r"\W+", " ", text.lower()).strip()
    keys = [f"m:{chat.id}:{m.id}", f"t:{hashlib.sha1(norm.encode()).hexdigest()}"]
    if not await db.claim(http, keys):  # уже видели это сообщение или кросс-пост
        return False

    title = getattr(chat, "title", None) or "чат"
    async with sem:
        st["llm"] += 1
        verdict = await llm.classify(http, text, cat, title, bad)
    if verdict is None:  # сбой модели: освобождаем ключи, повторим в следующий раз
        await db.release(http, keys)
        st["errors"] += 1
        return False
    try:
        score = int(verdict.get("score", 0))
    except (TypeError, ValueError):
        score = 0
    if not verdict.get("is_lead") or score < cfg["min_score"]:
        return False

    uname = getattr(sender, "username", None) if sender else None
    name = " ".join(filter(None, [getattr(sender, "first_name", None), getattr(sender, "last_name", None)])) if sender else ""
    row = {
        "chat_id": chat.id, "msg_id": m.id, "chat_title": title, "link": build_link(chat, m.id),
        "author": f"@{uname}" if uname else (name or "автор скрыт"),
        "author_url": f"https://t.me/{uname}" if uname else None,
        "text": text[:1500], "score": score, "match": (verdict.get("match") or "")[:120],
        "reason": (verdict.get("reason") or "")[:200], "reply": (verdict.get("reply") or "")[:500],
        "query": query, "msg_date": db.iso(m.date),
    }
    saved = await db.ins(http, "lb_leads", [row], on_conflict="chat_id,msg_id", ignore=True)
    if not saved:
        return False
    st["leads"] += 1
    if st["leads"] <= MAX_PUSH_PER_RUN:
        lead = saved[0]
        for uid in OWNER_IDS:
            await tg.send(http, uid, ui.lead_card(lead), ui.lead_kb(lead))
    return True


async def _scan(http, client, cfg, st, t0, budget) -> None:
    await ensure_queries(http)
    days = max(1, min(int(cfg["max_age_days"]), MAX_AGE_LIMIT_DAYS))
    cutoff = db.now() - timedelta(days=days)
    n = int(cfg["queries_per_run"])
    queries = await db.sel(http, "lb_queries", select="id,q,hits", active="eq.true",
                           order="last_run.asc.nullsfirst", limit=str(n))
    cat = await catalog.get_catalog(http)
    bad = [r["text"] for r in await db.sel(http, "lb_leads", select="text", status="eq.bad",
                                           order="created_at.desc", limit="5")]
    sem = asyncio.Semaphore(4)

    for q in queries:
        if time.time() - t0 > budget:
            break
        st["queries"] += 1
        try:
            msgs, chats, users = await _search(client, q["q"], cutoff)
        except Exception as e:
            st["errors"] += 1
            print(f"[scan] '{q['q']}': {e}")
            if "FloodWait" in type(e).__name__:
                break
            continue
        st["found"] += len(msgs)

        cands = []
        for m in msgs:
            if not isinstance(m, Message) or not m.message or m.date < cutoff:
                continue  # жёсткий фильтр свежести: старше N дней не берём
            st["fresh"] += 1
            cid = getattr(m.peer_id, "channel_id", None) or getattr(m.peer_id, "chat_id", None)
            chat = chats.get(cid)
            if chat is None or (isinstance(chat, Channel) and chat.broadcast):
                continue  # каналы-«витрины»: там пишут админы, а не клиенты
            uid = getattr(m.from_id, "user_id", None)
            sender = users.get(uid)
            if sender is not None and (getattr(sender, "bot", False) or getattr(sender, "is_self", False)):
                continue
            cands.append((m, chat, sender))

        results = await asyncio.gather(
            *[_process(http, cfg, cat, bad, m, c, s, q["q"], st, sem) for m, c, s in cands],
            return_exceptions=True)
        got = 0
        for r in results:
            if isinstance(r, Exception):
                st["errors"] += 1
                print(f"[scan] ошибка обработки: {r!r}")
            elif r:
                got += 1
        await db.upd(http, "lb_queries", {"last_run": db.iso(db.now()), "hits": q["hits"] + got}, id=f"eq.{q['id']}")


async def run_scan(http, budget: int = 30, trigger: str = "cron") -> dict:
    t0 = time.time()
    cfg = await db.get_settings(http)
    if trigger == "cron" and not cfg["enabled"]:
        return {"skipped": "paused"}
    if not (TG_API_ID and TG_API_HASH and TG_SESSION_STRING):
        return {"error": "TG_API_ID / TG_API_HASH / TG_SESSION_STRING не заданы"}
    if not await db.acquire_lock(http, budget + 30):
        return {"skipped": "locked"}  # другой запуск ещё идёт: две копии одной сессии Telegram не терпит

    st = dict(queries=0, found=0, fresh=0, passed=0, llm=0, leads=0, errors=0)
    err = None
    client = TelegramClient(StringSession(TG_SESSION_STRING), TG_API_ID, TG_API_HASH)
    try:
        await client.connect()
        if not await client.is_user_authorized():
            raise RuntimeError("Telegram-сессия не авторизована: перегенерируй TG_SESSION_STRING")
        await asyncio.wait_for(_scan(http, client, cfg, st, t0, budget), timeout=budget + 10)
    except asyncio.TimeoutError:
        err = "timeout"
    except Exception as e:
        err = f"{type(e).__name__}: {e}"[:300]
        print(f"[scan] {err}")
    finally:
        try:
            await client.disconnect()
        except Exception:
            pass
        await db.release_lock(http)

    ms = int((time.time() - t0) * 1000)
    try:
        await db.ins(http, "lb_runs", [{**st, "trigger": trigger, "ms": ms, "error": err}])
        await db.set_setting(http, "last_scan", db.iso(db.now()))
    except Exception as e:
        print(f"[scan] не записал статистику: {e}")
    if err and "не авторизована" in err:
        await tg.notify_owners(http, f"⚠️ {err}")
    return {**st, "ms": ms, "error": err}
