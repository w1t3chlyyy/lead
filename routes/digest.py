from datetime import timedelta

import httpx

from core import db, tg, ui
from core.auth import cron_ok
from core.config import APP_URL
from core.web import JSON


async def main(req):
    """Раз в сутки (Vercel Cron): сводка за вчера + чистка старых ключей дедупликации."""
    if not cron_ok(req):
        return 401, {"error": "unauthorized"}, JSON
    async with httpx.AsyncClient(timeout=25) as http:
        since = db.iso(db.now() - timedelta(days=1))
        leads = await db.sel(http, "lb_leads", select="id,status", created_at=f"gte.{since}")
        pending = await db.sel(http, "lb_leads", select="id", status="eq.new", limit="1000")
        if leads or pending:
            text = (f"🗓 <b>Сводка за сутки</b>\nНовых лидов: <b>{len(leads)}</b>\n"
                    f"Ждут реакции: <b>{len(pending)}</b>")
            kb = [[ui.b("📥 Открыть новые", "m:leads:new:0")]]
            if APP_URL.startswith("https://"):
                kb.append([ui.b("📊 Статистика", web=APP_URL)])
            await tg.notify_owners(http, text, kb)
        # дедуп-ключи старше 5 суток не нужны: сообщения старше 3 суток всё равно отсекаются по дате
        await db.dele(http, "lb_seen", created_at=f"lt.{db.iso(db.now() - timedelta(days=5))}")
    return 200, {"ok": True, "leads": len(leads)}, JSON

