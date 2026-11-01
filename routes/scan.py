import httpx

from core.auth import cron_ok
from core.scanner import run_scan
from core.web import JSON


async def main(req):
    """Вызывается cron-job.org. У него лимит ответа 30 с, поэтому бюджет по умолчанию 18 с (?budget=10..45)."""
    if not cron_ok(req):
        return 401, {"error": "unauthorized"}, JSON
    try:
        budget = max(10, min(45, int(req.query.get("budget", 18))))
    except ValueError:
        budget = 18
    async with httpx.AsyncClient(timeout=25) as http:
        greedy = req.query.get("greedy") == "1"  # ?greedy=1 — идти по всем фразам, пока хватает бюджета
        return 200, await run_scan(http, budget=budget, trigger="cron", greedy=greedy), JSON
