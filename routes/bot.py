import traceback

import httpx

from core.config import CRON_SECRET
from core.handlers import handle_update
from core.web import JSON


async def main(req):
    """Вебхук Telegram. Всегда отвечаем 200, иначе Telegram будет слать повторы."""
    if req.headers.get("x-telegram-bot-api-secret-token") != CRON_SECRET or not CRON_SECRET:
        return 403, {"error": "forbidden"}, JSON
    async with httpx.AsyncClient(timeout=25) as http:
        try:
            await handle_update(http, req.json())
        except Exception:
            traceback.print_exc()
    return 200, {"ok": True}, JSON

