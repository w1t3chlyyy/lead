import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx  # noqa: E402

from core.auth import cron_ok  # noqa: E402
from core.scanner import run_scan  # noqa: E402
from core.web import JSON, make_handler  # noqa: E402


async def main(req):
    """Вызывается cron-job.org. У него лимит ответа 30 с, поэтому бюджет по умолчанию 18 с (?budget=10..45)."""
    if not cron_ok(req):
        return 401, {"error": "unauthorized"}, JSON
    try:
        budget = max(10, min(45, int(req.query.get("budget", 18))))
    except ValueError:
        budget = 18
    async with httpx.AsyncClient(timeout=25) as http:
        return 200, await run_scan(http, budget=budget, trigger="cron"), JSON


handler = make_handler(main)
