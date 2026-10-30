from collections import Counter
from datetime import timedelta

import httpx

from core import db
from core.auth import is_owner_init_data
from core.web import JSON


async def main(req):
    """Данные для мини-аппа статистики. Доступ только владельцу (подпись Telegram initData)."""
    if not is_owner_init_data(req.headers.get("x-init-data", "")):
        return 401, {"error": "Открой статистику из бота"}, JSON
    async with httpx.AsyncClient(timeout=25) as http:
        since = db.iso(db.now() - timedelta(days=30))
        leads = await db.sel(http, "lb_leads", select="status,score,match,chat_title,query,created_at",
                             created_at=f"gte.{since}", order="created_at.desc", limit="5000")
        runs = await db.sel(http, "lb_runs", select="created_at,queries,found,fresh,passed,llm,leads,errors,ms",
                            created_at=f"gte.{since}", order="created_at.desc", limit="5000")
        queries = await db.sel(http, "lb_queries", select="q,hits,active", order="hits.desc", limit="10")
        cfg = await db.get_settings(http)

    today = db.now().date()
    days = [(today - timedelta(days=i)).isoformat() for i in range(13, -1, -1)]
    per_day = {d: {"d": d, "leads": 0, "fresh": 0} for d in days}
    for l in leads:
        d = l["created_at"][:10]
        if d in per_day:
            per_day[d]["leads"] += 1
    for r in runs:
        d = r["created_at"][:10]
        if d in per_day:
            per_day[d]["fresh"] += r["fresh"] or 0

    status = Counter(l["status"] for l in leads)
    closed = status["won"] + status["lost"]
    d7 = db.iso(db.now() - timedelta(days=7))
    funnel = {k: sum(r[k] or 0 for r in runs) for k in ("found", "fresh", "passed", "llm", "leads")}
    scores = [l["score"] for l in leads if l["score"] is not None]

    def top(key, n=6):
        c = Counter(l[key] for l in leads if l.get(key))
        return [{"name": k, "n": v} for k, v in c.most_common(n)]

    return 200, {
        "total": len(leads),
        "today": sum(1 for l in leads if l["created_at"][:10] == today.isoformat()),
        "week": sum(1 for l in leads if l["created_at"] >= d7),
        "avg_score": round(sum(scores) / len(scores)) if scores else 0,
        "win_rate": round(100 * status["won"] / closed) if closed else None,
        "status": dict(status),
        "daily": list(per_day.values()),
        "funnel": funnel,
        "top_match": top("match"),
        "top_chats": top("chat_title"),
        "top_queries": [{"name": q["q"], "n": q["hits"]} for q in queries if q["hits"]],
        "runs": len(runs),
        "errors": sum(r["errors"] or 0 for r in runs),
        "last_scan": cfg.get("last_scan"),
        "enabled": cfg.get("enabled"),
        "max_age_days": cfg.get("max_age_days"),
    }, JSON

