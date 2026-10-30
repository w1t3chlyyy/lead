import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx  # noqa: E402

from core.config import CRON_SECRET  # noqa: E402
from core.handlers import handle_update  # noqa: E402
from core.web import JSON, make_handler  # noqa: E402


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


handler = make_handler(main)
