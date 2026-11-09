"""Broad prefilter for buyer intent; catalog relevance is checked downstream by Qwen."""
from __future__ import annotations

import re

# The Telegram search query already narrows the topic. Keep this gate focused
# on buyer intent instead of a hard-coded list of product categories.
INTENT = re.compile(
    r"(\bищу\b|\bищем\b|\bнуж\w*\b|\bнадо\b|\bтребу\w+\b|\bзакажу\b|\bзаказать\b|"
    r"\bкуплю\b|\bкупить\b|\bхочу\s+(?:заказать|купить|найти)\b|"
    r"\bпосоветуйте\b|\bпорекомендуйте\b|\bподскажите\b|"
    r"\bкто\s+(?:сделает|может|умеет|занимается|возьм\w+|берет\w*|делает|знает)\b|"
    r"\b(?:сколько\s+стоит|стоимость|цена|прайс)\b|"
    r"\bгде\s+(?:заказать|купить|найти)\b|\bнужна\s+помощь\b|"
    r"\bneed\b|\blooking\s+for\b|\bwant\s+to\s+(?:buy|order)\b|"
    r"\bwhere\s+to\s+(?:buy|order|find)\b|\brecommend\b|\bhow\s+much\b)",
    re.I,
)

MIN_LEN, MAX_LEN = 12, 1800


def quick_filter(text: str) -> bool:
    """Reject only very short or non-buyer messages before catalog-aware Qwen."""
    if not text or not (MIN_LEN <= len(text) <= MAX_LEN):
        return False
    return bool(INTENT.search(text))


# Used only when a fresh database has no query rows. Existing user queries are
# preserved; the owner can generate more from the live catalog in the bot.
DEFAULT_QUERIES = [
    "ищу исполнителя", "нужен специалист", "кто может сделать", "посоветуйте специалиста",
    "сколько стоит", "нужна услуга", "ищу подрядчика", "нужен разработчик",
    "заказать разработку", "ищу дизайнера", "заказать дизайн", "купить подписку",
    "хочу заказать", "нужна помощь с проектом", "need a developer", "looking for a designer",
]