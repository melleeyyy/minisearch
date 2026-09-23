"""MiniSearch — engine tests (crawler normalization + indexing + BM25).

Run:  python -m unittest tests.test_engine -v
(or:  python tests/test_engine.py)
"""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import crawler   # noqa: E402
import indexer   # noqa: E402


class TestURLNormalization(unittest.TestCase):
    def test_fragment_dropped(self):
        self.assertEqual(crawler.normalize_url("https://x.com/a#sec"),
                         "https://x.com/a")

    def test_tracking_params_dropped(self):
        self.assertEqual(
            crawler.normalize_url("https://x.com/a?utm_source=tw&id=7"),
            "https://x.com/a?id=7")

    def test_content_params_kept(self):
        self.assertEqual(
            crawler.normalize_url("https://x.com/a?id=7&b=2"),
            "https://x.com/a?b=2&id=7")

    def test_duplicate_query_params_sorted(self):
        self.assertEqual(
            crawler.normalize_url("https://x.com/a?b=2&a=1"),
            crawler.normalize_url("https://x.com/a?a=1&b=2"))

    def test_relative_resolved(self):
        self.assertEqual(crawler.normalize_url("../b/c", base="https://x.com/a/d/e"),
                         "https://x.com/a/b/c")

    def test_trailing_slash_removed(self):
        self.assertEqual(crawler.normalize_url("https://x.com/a/"),
                         "https://x.com/a")
        self.assertEqual(crawler.normalize_url("https://x.com/"),
                         "https://x.com/")

    def test_scheme_host_lowercased_default_port(self):
        self.assertEqual(crawler.normalize_url("HTTPS://X.COM:443/a"),
                         "https://x.com/a")

    def test_non_http_rejected(self):
        self.assertIsNone(crawler.normalize_url("mailto:a@b.com"))
        self.assertIsNone(crawler.normalize_url("javascript:void(0)"))
        self.assertIsNone(crawler.normalize_url(""))
        self.assertIsNone(crawler.normalize_url("#top"))

    def test_skip_namespaces(self):
        self.assertTrue(crawler.should_skip("https://en.wikipedia.org/wiki/Special:Search"))
        self.assertFalse(crawler.should_skip("https://en.wikipedia.org/wiki/Python"))


class TestTokenizer(unittest.TestCase):
    def test_lowercase(self):
        self.assertEqual(indexer.tokenize("JavaScript JAVASCRIPT"), ["javascript", "javascript"])

    def test_malayalam_combining_marks_kept(self):
        self.assertIn("കേരളം", indexer.tokenize("കേരളം ഒരു സംസ്ഥാനം"))

    def test_stopwords_removed(self):
        self.assertNotIn("the", indexer.tokenize("the quick brown fox"))


def _write_pages(tmp, pages):
    path = os.path.join(tmp, "pages.jsonl")
    with open(path, "w", encoding="utf-8") as f:
        for p in pages:
            f.write(json.dumps(p, ensure_ascii=False) + "\n")
    return path


class TestIndexAndBM25(unittest.TestCase):
    PAGES = [
        {"url": "https://a.com/javascript", "title": "JavaScript Tutorial",
         "text": "JavaScript tutorial for beginners. Learn JavaScript basics and arrays.",
         "links": ["https://b.com/py", "https://a.com/js-arrays"]},
        {"url": "https://b.com/py", "title": "Python Guide",
         "text": "Python is a programming language. Python tutorial here.",
         "links": ["https://a.com/javascript"]},
        {"url": "https://a.com/js-arrays", "title": "JS Arrays",
         "text": "Arrays in JavaScript. The map method of arrays explained.",
         "links": []},
        {"url": "https://c.com/kerala", "title": "കേരളം",
         "text": "കേരളം ഇന്ത്യയിലെ ഒരു സംസ്ഥാനമാണ്. കേരളത്തിലെ വിദ്യാഭ്യാസം മികച്ചതാണ്.",
         "links": []},
    ]

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.pages_file = _write_pages(self.tmp, self.PAGES)
        self.oldcwd = os.getcwd()
        os.chdir(self.tmp)
        os.makedirs("data", exist_ok=True)
        self.index = indexer.build(self.pages_file, "data/index.json")
        self.bm25 = indexer.BM25(self.index)

    def tearDown(self):
        os.chdir(self.oldcwd)

    def test_basic_search(self):
        for q in ("javascript", "python", "arrays"):
            self.assertTrue(self.bm25.search(q), q)

    def test_case_insensitive(self):
        low = self.bm25.search("javascript")
        up = self.bm25.search("JavaScript")
        self.assertEqual([u for u, _ in low], [u for u, _ in up])

    def test_multiword(self):
        self.assertTrue(self.bm25.search("javascript tutorial"))

    def test_malayalam(self):
        r = self.bm25.search("കേരളം")
        self.assertEqual(r[0][0], "https://c.com/kerala")
        self.assertTrue(self.bm25.search("കേരളത്തിലെ വിദ്യാഭ്യാസം"))

    def test_invalid_query_no_results(self):
        self.assertEqual(self.bm25.search("abcxyz123"), [])

    def test_empty_query(self):
        self.assertEqual(self.bm25.search(""), [])

    def test_ranking_deterministic(self):
        r1 = self.bm25.search("javascript")
        r2 = self.bm25.search("javascript")
        self.assertEqual(r1, r2)

    def test_link_graph_built(self):
        links = json.load(open("data/links.json", encoding="utf-8"))
        self.assertEqual(links["https://a.com/javascript"],
                         ["https://b.com/py", "https://a.com/js-arrays"])
        # only corpus URLs are kept in the graph
        self.assertEqual(links["https://c.com/kerala"], [])

    def test_stable_doc_ids(self):
        ids = self.index["docIds"]
        self.assertEqual(len(ids), 4)
        self.assertEqual(sorted(ids.values()), [0, 1, 2, 3])


if __name__ == "__main__":
    unittest.main(verbosity=2)
