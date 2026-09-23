"""MiniSearch — API tests (Flask test client).

Run:  python -m unittest tests.test_api -v
"""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import indexer   # noqa: E402
from tests.test_engine import CORPUS, _write_pages  # noqa: E402


class TestAPI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        pages_file = _write_pages(cls.tmp, CORPUS)
        cls.db = os.path.join(cls.tmp, "test.db")
        indexer.build(pages_file, cls.db)
        os.environ["MS_DB"] = cls.db
        os.environ["MS_ANALYTICS_DB"] = os.path.join(cls.tmp, "analytics.db")
        os.environ["MS_DOCS_DIR"] = os.path.join(cls.tmp, "no-docs")
        from server import app as app_module
        # rebuild the app with the test database
        app_module.engine = app_module.SearchEngine(cls.db)
        cls.client = app_module.app.test_client()

    def test_health(self):
        r = self.client.get("/health")
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["pages"], 4)

    def test_search_valid(self):
        r = self.client.get("/api/search?q=javascript")
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        self.assertGreater(data["total"], 0)
        first = data["results"][0]
        for field in ("title", "url", "displayUrl", "snippet", "score",
                      "domain", "language", "crawledAt"):
            self.assertIn(field, first)

    def test_search_malayalam(self):
        r = self.client.get("/api/search?q=%E0%B4%95%E0%B5%87%E0%B4%B0%E0%B4%B3%E0%B4%82")
        data = r.get_json()
        self.assertGreater(data["total"], 0)
        self.assertEqual(data["results"][0]["url"], "https://c.com/kerala")

    def test_search_phrase(self):
        r = self.client.get('/api/search?q=%22javascript%20tutorial%22')
        data = r.get_json()
        self.assertGreaterEqual(data["total"], 1)

    def test_search_typo_suggestion(self):
        r = self.client.get("/api/search?q=javascrpt")
        data = r.get_json()
        self.assertEqual(data["total"], 0)
        self.assertEqual(data["did_you_mean"], "javascript")

    def test_search_empty_result(self):
        r = self.client.get("/api/search?q=abcxyz123zzz")
        self.assertEqual(r.get_json()["total"], 0)

    def test_search_missing_query(self):
        r = self.client.get("/api/search")
        self.assertEqual(r.status_code, 400)

    def test_search_long_query_rejected(self):
        r = self.client.get("/api/search?q=" + "a" * 500)
        self.assertEqual(r.status_code, 200)   # clamped, not an error
        # 300-char cap means it searches the clamped string (no results)
        self.assertEqual(r.get_json()["total"], 0)

    def test_search_invalid_params(self):
        r = self.client.get("/api/search?q=python&page=abc&limit=xyz")
        self.assertEqual(r.status_code, 200)   # falls back to defaults
        r = self.client.get("/api/search?q=python&limit=9999")
        self.assertEqual(r.get_json()["limit"], 50)   # clamped to max

    def test_search_pagination(self):
        r1 = self.client.get("/api/search?q=javascript&page=1&limit=2")
        r2 = self.client.get("/api/search?q=javascript&page=2&limit=2")
        d1, d2 = r1.get_json(), r2.get_json()
        self.assertEqual(d1["total"], d2["total"])
        urls1 = {x["url"] for x in d1["results"]}
        urls2 = {x["url"] for x in d2["results"]}
        self.assertFalse(urls1 & urls2)

    def test_search_snippet_safe_html(self):
        r = self.client.get("/api/search?q=javascript")
        snippet = r.get_json()["results"][0]["snippet"]
        self.assertNotIn("<script", snippet)

    def test_images_endpoint(self):
        r = self.client.get("/api/images?q=javascript")
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        self.assertGreater(data["total"], 0)
        im = data["results"][0]
        for field in ("imageUrl", "sourcePageUrl", "domain", "alt", "title"):
            self.assertIn(field, im)

    def test_images_pagination(self):
        r = self.client.get("/api/images?q=com&page=1&limit=1")
        self.assertEqual(len(r.get_json()["results"]), 1)

    def test_images_missing_query(self):
        r = self.client.get("/api/images")
        self.assertEqual(r.status_code, 400)

    def test_suggest(self):
        r = self.client.get("/api/suggest?q=java")
        self.assertEqual(r.status_code, 200)
        suggestions = r.get_json()["suggestions"]
        self.assertTrue(any("javascript" in s for s in suggestions))

    def test_suggest_empty(self):
        r = self.client.get("/api/suggest?q=")
        self.assertEqual(r.get_json()["suggestions"], [])

    def test_stats(self):
        # trigger some searches first so analytics has rows
        self.client.get("/api/search?q=javascript")
        self.client.get("/api/search?q=python")
        r = self.client.get("/api/stats")
        data = r.get_json()
        self.assertEqual(data["index"]["pages"], 4)
        self.assertGreaterEqual(data["analytics"]["queries"], 2)
        self.assertIn("cacheHitRate", data["analytics"])

    def test_cache_hit(self):
        self.client.get("/api/search?q=python&page=1&limit=10")
        r2 = self.client.get("/api/search?q=python&page=1&limit=10")
        self.assertEqual(r2.get_json()["cache"], "hit")

    def test_api_path_404(self):
        r = self.client.get("/api/nonexistent")
        self.assertEqual(r.status_code, 404)

    def test_cors_headers(self):
        r = self.client.get("/health")
        self.assertEqual(r.headers.get("Access-Control-Allow-Origin"), "*")

    def test_rate_limit(self):
        import server.app as app_module
        old = app_module.RATE_LIMIT
        app_module.RATE_LIMIT = 3
        app_module._hits.clear()
        codes = [self.client.get("/api/suggest?q=x").status_code for _ in range(5)]
        app_module.RATE_LIMIT = old
        app_module._hits.clear()
        self.assertIn(429, codes)
        # after clearing, requests work again
        self.assertEqual(self.client.get("/api/suggest?q=x").status_code, 200)


if __name__ == "__main__":
    unittest.main(verbosity=2)
