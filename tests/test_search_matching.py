import unittest
from unittest.mock import patch

from core.catalog import _fetch_all, _prepare_items, catalog_for_message
from core.keywords import is_buyer_query_phrase, quick_filter


class FakeResponse:
    def __init__(self, data, content_range):
        self._data = data
        self.headers = {"content-range": content_range}

    def raise_for_status(self):
        return None

    def json(self):
        return self._data


class FakeHttp:
    def __init__(self, rows, server_page_size):
        self.rows = rows
        self.server_page_size = server_page_size

    async def get(self, url, headers, params):
        offset = int(params["offset"])
        requested = int(params["limit"])
        page = self.rows[offset:offset + min(requested, self.server_page_size)]
        if page:
            end = offset + len(page) - 1
            content_range = f"{offset}-{end}/{len(self.rows)}"
        else:
            content_range = f"*/{len(self.rows)}"
        return FakeResponse(page, content_range)


class SearchMatchingTests(unittest.TestCase):
    def test_prefilter_does_not_require_a_hardcoded_topic(self):
        self.assertTrue(quick_filter("Ищу специалиста по юридическому переводу"))

    def test_sales_post_without_buyer_intent_is_rejected(self):
        self.assertFalse(quick_filter("Предлагаю услуги дизайна, беру заказы"))

    def test_generated_buyer_phrase_requires_clear_order_intent(self):
        self.assertTrue(is_buyer_query_phrase("ищу разработчика бота"))
        self.assertTrue(is_buyer_query_phrase("сколько стоит заказать сайт"))
        self.assertFalse(is_buyer_query_phrase("примеры работ по дизайну"))
        self.assertFalse(is_buyer_query_phrase("скидки на услуги"))
        self.assertFalse(is_buyer_query_phrase("ищу партнёра для проекта"))

    def test_catalog_item_is_selected_from_full_item_list(self):
        items = _prepare_items(
            [{"name": "Юридический перевод", "category": "Переводы",
              "description": "Перевод документов", "price": 1000, "section": "service"}],
            [],
        )
        result = catalog_for_message(items, "Ищу специалиста для перевода договора")
        self.assertIn("Юридический перевод", result)

    def test_catalog_fallback_is_used_for_synonyms(self):
        items = _prepare_items(
            [{"name": "Разработка чат-ботов", "category": "Автоматизация",
              "description": "Создание ботов для компаний", "price": 1000, "section": "service"}],
            [],
        )
        result = catalog_for_message(items, "Кто автоматизирует поддержку клиентов?")
        self.assertIn("Краткий индекс каталога", result)
        self.assertIn("Разработка чат-ботов", result)

    def test_catalog_pagination_respects_server_page_cap(self):
        rows = [{"name": f"item-{i}"} for i in range(5)]
        http = FakeHttp(rows, server_page_size=2)
        with patch("core.catalog.PAGE_SIZE", 500):
            result = self.async_run(_fetch_all(http, "products", {}))
        self.assertEqual(len(result), 5)

    @staticmethod
    def async_run(awaitable):
        import asyncio
        return asyncio.run(awaitable)


if __name__ == "__main__":
    unittest.main()