from __future__ import annotations

import os


def env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


BOT_TOKEN = env("BOT_TOKEN")
OWNER_IDS = [int(x) for x in env("OWNER_IDS").replace(" ", "").split(",") if x]
CRON_SECRET = env("CRON_SECRET")

SUPABASE_URL = env("SUPABASE_URL").rstrip("/")
SUPABASE_KEY = env("SUPABASE_SERVICE_KEY")
SHOP_SUPABASE_URL = (env("SHOP_SUPABASE_URL") or SUPABASE_URL).rstrip("/")
SHOP_SUPABASE_KEY = env("SHOP_SUPABASE_KEY") or SUPABASE_KEY

TG_API_ID = int(env("TG_API_ID", "0") or 0)
TG_API_HASH = env("TG_API_HASH")
TG_SESSION_STRING = env("TG_SESSION_STRING")

QWEN_API_KEY = env("QWEN_API_KEY")
QWEN_BASE_URL = env("QWEN_BASE_URL", "https://dashscope-intl.aliyuncs.com/compatible-mode/v1").rstrip("/")
QWEN_MODEL = env("QWEN_MODEL", "qwen-plus")

_host = env("VERCEL_PROJECT_PRODUCTION_URL")
APP_URL = env("APP_URL").rstrip("/") or (f"https://{_host}" if _host else "")

# Настройки по умолчанию; меняются из бота (кнопка «Настройки») и хранятся в lb_settings
DEFAULTS = {
    "enabled": True,
    "max_age_days": 3,      # не старше N дней (жёсткий потолок 3)
    "min_score": 60,
    "queries_per_run": 4,   # сколько поисковых фраз за один запуск
    "awaiting": "",         # служебное: бот ждёт текст (например, новую фразу)
    "last_scan": "",
}
MAX_AGE_LIMIT_DAYS = 3
MAX_PUSH_PER_RUN = 15       # больше карточек за запуск не пушим (остальные видны в «Новые лиды»)
