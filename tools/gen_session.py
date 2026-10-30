"""Один раз запусти локально: получишь строку сессии для TG_SESSION_STRING.
pip install telethon && python tools/gen_session.py
Строка = полный доступ к аккаунту. Храни как пароль, используй ОТДЕЛЬНЫЙ аккаунт."""
from telethon.sessions import StringSession
from telethon.sync import TelegramClient

api_id = int(input("API ID: ").strip())
api_hash = input("API HASH: ").strip()

with TelegramClient(StringSession(), api_id, api_hash) as client:
    print("\nTG_SESSION_STRING=" + client.session.save())
