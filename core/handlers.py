"""Вся логика бота: команды, кнопки, состояния."""
from __future__ import annotations

from . import catalog, db, llm, scanner, tg, ui
from .config import OWNER_IDS
from .ui import e


# ---------- экраны ----------
async def _counts(http) -> tuple[int, int]:
    new = await db.sel(http, "lb_leads", select="id", status="eq.new", limit="1000")
    work = await db.sel(http, "lb_leads", select="id", status="eq.work", limit="1000")
    return len(new), len(work)


async def show(http, cid: int, mid: int | None, text: str, kb: list) -> None:
    if mid:
        await tg.edit(http, cid, mid, text, kb)
    else:
        await tg.send(http, cid, text, kb)


async def show_main(http, cid, mid=None):
    cfg = await db.get_settings(http)
    n, w = await _counts(http)
    await show(http, cid, mid, *ui.main_menu(cfg, n, w))


async def show_leads(http, cid, mid, flt: str, page: int):
    params = {"select": "id,score,match,chat_title,msg_date,status", "order": "created_at.desc",
              "limit": str(ui.PAGE + 1), "offset": str(page * ui.PAGE)}
    if flt != "all":
        params["status"] = f"eq.{flt}"
    rows = await db.sel(http, "lb_leads", **params)
    await show(http, cid, mid, *ui.leads_list(rows[:ui.PAGE], flt, page, len(rows) > ui.PAGE))


async def show_settings(http, cid, mid):
    await show(http, cid, mid, *ui.settings_screen(await db.get_settings(http)))


async def show_queries(http, cid, mid, page: int):
    await scanner.ensure_queries(http)
    rows = await db.sel(http, "lb_queries", select="id,q,active,hits", order="id.asc",
                        limit=str(ui.QPAGE + 1), offset=str(page * ui.QPAGE))
    await show(http, cid, mid, *ui.queries_screen(rows[:ui.QPAGE], page, len(rows) > ui.QPAGE))


async def show_catalog(http, cid, mid):
    text = await catalog.get_catalog(http)
    kb = [[ui.b("🔄 Обновить", "c:ref")], ui.BACK]
    await show(http, cid, mid, "<b>Каталог, который видит Qwen</b>\n\n" + e(text[:3300]), kb)


async def edit_lead(http, cid, mid, lead: dict):
    await tg.edit(http, cid, mid, ui.lead_card(lead), ui.lead_kb(lead))


def _scan_summary(r: dict) -> str:
    if r.get("skipped") == "locked":
        return "⏳ Сканирование уже идёт, подожди минуту."
    if r.get("skipped"):
        return f"Пропущено: {r['skipped']}"
    if r.get("error") and not r.get("queries"):
        return f"⚠️ {e(str(r['error']))}"
    s = (f"✅ Готово за {r['ms'] // 1000} с\nФраз: {r['queries']} · найдено: {r['found']} · "
         f"свежих: {r['fresh']}\nКандидаты: {r['passed']} · дубликаты: {r.get('duplicates', 0)} · "
         f"лимит пропустил: {r.get('quota_skipped', 0)}\nК Qwen: {r['llm']} · "
         f"не лид: {r.get('qwen_rejected', 0)} · ниже порога: {r.get('low_score', 0)} · "
         f"<b>лидов: {r['leads']}</b>")
    if r.get("detail"):
        s += "\n\nНайдено по фразам:\n" + "\n".join(f"• {e(d)}" for d in r["detail"])
    if r.get("errors"):
        s += f"\n⚠️ Ошибок: {r['errors']}"
        if r.get("last_error"):
            s += f" · {e(r['last_error'])}"
    if r.get("error"):
        s += f"\n⚠️ {e(str(r['error']))}"
    return s


# ---------- входящие ----------
async def handle_update(http, upd: dict) -> None:
    if not await db.claim(http, [f"u:{upd.get('update_id')}"]):
        return  # Telegram повторил доставку
    if "callback_query" in upd:
        await on_callback(http, upd["callback_query"])
    elif "message" in upd:
        await on_message(http, upd["message"])


async def on_message(http, msg: dict) -> None:
    uid, cid = msg.get("from", {}).get("id"), msg["chat"]["id"]
    if uid not in OWNER_IDS:
        return
    text = (msg.get("text") or "").strip()
    cfg = await db.get_settings(http)

    if cfg.get("awaiting") == "add_query" and text and not text.startswith("/"):
        await db.set_setting(http, "awaiting", "")
        q = " ".join(text.lower().split())[:80]
        await db.ins(http, "lb_queries", [{"q": q}], on_conflict="q", ignore=True)
        await tg.send(http, cid, f"✅ Добавлена фраза: <code>{e(q)}</code>")
        await show_queries(http, cid, None, 0)
        return
    if cfg.get("awaiting"):
        await db.set_setting(http, "awaiting", "")
    await show_main(http, cid)


async def on_callback(http, cb: dict) -> None:
    uid = cb["from"]["id"]
    if uid not in OWNER_IDS:
        await tg.answer(http, cb["id"], "Нет доступа", True)
        return
    data = cb.get("data", "")
    cid, mid = cb["message"]["chat"]["id"], cb["message"]["message_id"]
    p = data.split(":")
    ack = ""

    if data == "noop":
        pass
    elif data == "m:main":
        await db.set_setting(http, "awaiting", "")
        await show_main(http, cid, mid)

    # --- лиды ---
    elif p[:2] == ["m", "leads"]:
        await show_leads(http, cid, mid, p[2], int(p[3]))
    elif p[:2] == ["l", "v"]:
        rows = await db.sel(http, "lb_leads", id=f"eq.{p[2]}")
        if rows:
            await tg.send(http, cid, ui.lead_card(rows[0]), ui.lead_kb(rows[0]))
    elif p[:2] == ["l", "st"]:
        rows = await db.upd(http, "lb_leads", {"status": p[3]}, id=f"eq.{p[2]}")
        if rows:
            await edit_lead(http, cid, mid, rows[0])
            ack = ui.STATUS.get(p[3], "")
    elif p[:2] == ["l", "re"]:
        rows = await db.sel(http, "lb_leads", id=f"eq.{p[2]}")
        if rows:
            items = await catalog.get_items(http)
            relevant = catalog.catalog_for_message(items, rows[0]["text"])
            new = await llm.redraft(http, rows[0]["text"], relevant, rows[0].get("reply") or "")
            if new:
                rows = await db.upd(http, "lb_leads", {"reply": new}, id=f"eq.{p[2]}")
                await edit_lead(http, cid, mid, rows[0])
                ack = "Новый черновик"
            else:
                ack = "Qwen не ответил"

    # --- ручной скан ---
    elif data == "m:scan":
        await tg.answer(http, cb["id"], "Ищу, пока не найду…")
        await tg.edit(http, cid, mid, "🔎 Ищу по всем фразам, пока не найду лид (до ~40 с)…")
        r = await scanner.run_scan(http, budget=40, trigger="manual", greedy=True, stop_on_lead=True)
        text = _scan_summary(r)
        if not r.get("skipped") and not r.get("leads"):
            text += "\n\nПока лидов нет. Нажми «Искать дальше»: пойдёт следующая порция фраз."
        kb = [[ui.b("🔁 Искать дальше", "m:scan")], [ui.b("📥 Новые лиды", "m:leads:new:0")], ui.BACK]
        await tg.edit(http, cid, mid, text, kb)
        return

    # --- настройки ---
    elif data == "m:set":
        await show_settings(http, cid, mid)
    elif p[0] == "s":
        cfg = await db.get_settings(http)
        if p[1] == "tog":
            await db.set_setting(http, "enabled", not cfg["enabled"])
        elif p[1] == "age":
            await db.set_setting(http, "max_age_days", max(1, min(3, int(p[2]))))
        elif p[1] == "score":
            await db.set_setting(http, "min_score", int(p[2]))
        elif p[1] == "qpr":
            await db.set_setting(http, "queries_per_run", int(p[2]))
        await show_settings(http, cid, mid)

    # --- фразы ---
    elif p[:2] == ["m", "q"]:
        await show_queries(http, cid, mid, int(p[2]))
    elif p[0] == "q":
        if p[1] == "tg":
            rows = await db.sel(http, "lb_queries", select="active", id=f"eq.{p[2]}")
            if rows:
                await db.upd(http, "lb_queries", {"active": not rows[0]["active"]}, id=f"eq.{p[2]}")
            await show_queries(http, cid, mid, int(p[3]))
        elif p[1] == "del":
            await db.dele(http, "lb_queries", id=f"eq.{p[2]}")
            await show_queries(http, cid, mid, int(p[3]))
        elif p[1] == "add":
            await db.set_setting(http, "awaiting", "add_query")
            await tg.edit(http, cid, mid, "Пришли фразу, по которой искать (например: <code>нужен дизайнер</code>).",
                          [[ui.b("Отмена", "m:q:0")]])
        elif p[1] == "gen":
            await tg.answer(http, cb["id"], "Qwen придумывает фразы…")
            have = [r["q"] for r in await db.sel(http, "lb_queries", select="q", limit="1000")]
            items = await catalog.get_items(http)
            catalog_index = catalog.catalog_for_query_generation(items)
            new = await llm.suggest_queries(http, catalog_index, have)
            if new:
                await db.ins(http, "lb_queries", [{"q": q} for q in new], on_conflict="q", ignore=True)
                await tg.send(http, cid, f"🤖 Добавлено фраз: <b>{len(new)}</b>\n" +
                              "\n".join(f"• {e(q)}" for q in new[:12]) + ("\n…" if len(new) > 12 else ""))
            else:
                await tg.send(http, cid, "Qwen не вернул фразы, попробуй ещё раз.")
            await show_queries(http, cid, None, 0)
            return
        elif p[1] == "reset":
            from .keywords import DEFAULT_QUERIES
            await db.ins(http, "lb_queries", [{"q": q} for q in DEFAULT_QUERIES], on_conflict="q", ignore=True)
            await show_queries(http, cid, mid, 0)
            ack = "Стартовые фразы добавлены"

    # --- каталог ---
    elif data == "m:cat":
        await show_catalog(http, cid, mid)
    elif data == "c:ref":
        catalog.invalidate()
        await show_catalog(http, cid, mid)
        ack = "Каталог обновлён"

    await tg.answer(http, cb["id"], ack)
