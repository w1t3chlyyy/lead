"""Qwen через OpenAI-совместимый эндпоинт DashScope."""
from __future__ import annotations

import json
import re

import httpx

from .config import QWEN_API_KEY, QWEN_BASE_URL, QWEN_MODEL

SYSTEM = """Ты — фильтр лидов для владельца магазина цифровых товаров и услуг.
Тебе дают сообщение из публичного Telegram-чата и актуальный каталог владельца.
Определи: ищет ли АВТОР сообщения (как покупатель/заказчик) то, что владелец может продать или выполнить.

НЕ лид: продавцы и исполнители, реклама, вакансии «в команду на работу», флуд, шутки,
общие вопросы без намерения купить/заказать, обсуждения, не связанные с каталогом.

Ответь строго JSON без пояснений:
{"is_lead": true|false, "score": 0-100, "match": "название подходящей позиции из каталога или пустая строка",
 "reason": "до 15 слов", "reply": "вежливый черновик первого ответа от владельца, 1-2 предложения, без цен и ссылок; пустая строка, если не уверен"}"""


async def _chat(http: httpx.AsyncClient, messages: list, *, json_mode: bool, temperature: float, timeout: int = 25) -> str:
    body = {"model": QWEN_MODEL, "temperature": temperature, "enable_thinking": False, "messages": messages}
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    r = await http.post(f"{QWEN_BASE_URL}/chat/completions", json=body,
                        headers={"Authorization": f"Bearer {QWEN_API_KEY}"}, timeout=timeout)
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]


def _parse(raw: str) -> dict | None:
    m = re.search(r"\{.*\}", raw.strip(), re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


async def classify(http, text: str, catalog: str, chat_title: str, bad_examples: list[str] | None = None) -> dict | None:
    system = f"{SYSTEM}\n\n{catalog}"
    if bad_examples:
        system += "\n\nВладелец ранее пометил как НЕ лид (учитывай похожие):\n" + "\n".join(
            f"- {t[:160]!r}" for t in bad_examples)
    try:
        raw = await _chat(http, [
            {"role": "system", "content": system},
            {"role": "user", "content": f"Чат: {chat_title}\nСообщение:\n{text[:1000]}"},
        ], json_mode=True, temperature=0.1)
        return _parse(raw)
    except Exception as e:
        print(f"[qwen] ошибка: {e}")
        return None


async def redraft(http, text: str, catalog: str, prev: str) -> str | None:
    try:
        raw = await _chat(http, [
            {"role": "system", "content": "Ты помогаешь владельцу магазина цифровых услуг отвечать потенциальным клиентам "
             "в Telegram. Напиши ДРУГОЙ вариант вежливого первого ответа (1-2 предложения, без цен и ссылок, на языке "
             f"сообщения клиента). Верни только текст ответа.\n\n{catalog}"},
            {"role": "user", "content": f"Сообщение клиента:\n{text[:1000]}\n\nПрошлый вариант (не повторяй):\n{prev}"},
        ], json_mode=False, temperature=0.7)
        return raw.strip().strip('"')[:500] or None
    except Exception as e:
        print(f"[qwen] redraft ошибка: {e}")
        return None


async def suggest_queries(http, catalog: str, existing: list[str], n: int = 25) -> list[str]:
    """Qwen придумывает короткие поисковые фразы под каталог (один вызов)."""
    try:
        raw = await _chat(http, [
            {"role": "system", "content": (
                "Ты помогаешь находить заказчиков в публичных Telegram-чатах. По каталогу владельца придумай "
                "поисковые фразы так, как реальные клиенты пишут в чатах, когда ищут такую услугу или товар. "
                "Фразы короткие (1-3 слова), нижний регистр, разные формулировки, сленг, русские и английские, "
                "без кавычек и знаков препинания. Не повторяй уже существующие. "
                'Верни строго JSON: {"queries": ["...", "..."]}\n\n' + catalog)},
            {"role": "user", "content": f"Нужно {n} новых фраз. Уже есть: " + "; ".join(existing[:60])},
        ], json_mode=True, temperature=0.8, timeout=40)
        out = []
        for q in (_parse(raw) or {}).get("queries", []):
            q = " ".join(str(q).lower().split())[:80]
            if len(q) >= 3 and q not in existing and q not in out:
                out.append(q)
        return out[:n]
    except Exception as e:
        print(f"[qwen] suggest ошибка: {e}")
        return []
