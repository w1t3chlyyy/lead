import httpx

from core import tg
from core.auth import cron_ok
from core.config import APP_URL, CRON_SECRET
from core.web import JSON


async def main(req):
    """Открой один раз в браузере после деплоя: https://<домен>/api/setup?key=<CRON_SECRET>"""
    if not cron_ok(req):
        return 401, {"error": "unauthorized"}, JSON
    base = APP_URL or f"https://{req.headers.get('x-forwarded-host') or req.headers.get('host')}"
    async with httpx.AsyncClient(timeout=25) as http:
        out = {
            "webhook": await tg.call(http, "setWebhook", url=f"{base}/api/bot", secret_token=CRON_SECRET,
                                     allowed_updates=["message", "callback_query"], drop_pending_updates=True),
            "commands": await tg.call(http, "setMyCommands", commands=[
                {"command": "start", "description": "Главное меню"}]),
            "menu_button": await tg.call(http, "setChatMenuButton", menu_button={
                "type": "web_app", "text": "Статистика", "web_app": {"url": base}}),
        }
    out["base_url"] = base
    return 200, out, JSON

