"""MiniSearch — engine tests (crawler, indexer/SQLite, search engine).

Run:  python -m unittest tests.test_engine -v
"""
import json
import os
import sys
import tempfile
import unittest
from urllib.parse import urlparse

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


class TestSSRFProtection(unittest.TestCase):
    def test_localhost_blocked(self):
        self.assertFalse(crawler.url_is_safe("http://localhost/admin"))
        self.assertFalse(crawler.url_is_safe("http://127.0.0.1:8080/x"))

    def test_private_ranges_blocked(self):
        self.assertFalse(crawler.url_is_safe("http://192.168.1.1/router"))
        self.assertFalse(crawler.url_is_safe("http://10.0.0.5/internal"))
        self.assertFalse(crawler.url_is_safe("http://169.254.169.254/metadata"))

    def test_bad_scheme_rejected(self):
        self.assertFalse(crawler.url_is_safe("ftp://x.com/file"))

    def test_public_domain_allowed(self):
        self.assertTrue(crawler.url_is_safe("https://en.wikipedia.org/wiki/Kerala"))


class TestSitemapParsing(unittest.TestCase):
    def test_parse_urlset(self):
        xml = ('<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
               '<url><loc>https://x.com/a</loc></url>'
               '<url><loc>https://x.com/b</loc></url></urlset>')
        # parse_sitemap fetches the URL; test the parsing logic via ET feed
        import xml.etree.ElementTree as ET
        root = ET.fromstring(xml)
        ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
        locs = [l.text for l in root.findall(".//sm:url/sm:loc", ns)]
        self.assertEqual(locs, ["https://x.com/a", "https://x.com/b"])


class TestImageExtraction(unittest.TestCase):
    def test_lazy_and_og_images(self):
        from bs4 import BeautifulSoup
        html = """
        <html><head>
          <meta property="og:image" content="https://x.com/og.jpg">
        </head><body>
          <img src="placeholder.jpg" data-src="https://x.com/real.jpg" alt="Kerala beach" width="800" height="600">
          <img src="https://x.com/pixel.gif" width="1" height="1">
          <img srcset="https://x.com/a.jpg 400w, https://x.com/b.jpg 1200w" alt="srcset img">
        </body></html>"""
        soup = BeautifulSoup(html, "html.parser")
        images = crawler.extract_images(soup, "https://x.com/page", title="Page")
        urls = [i["imageUrl"] for i in images]
        self.assertIn("https://x.com/real.jpg", urls)      # lazy-loaded
        self.assertIn("https://x.com/og.jpg", urls)        # open graph
        self.assertIn("https://x.com/b.jpg", urls)         # largest srcset
        self.assertNotIn("https://x.com/pixel.gif", urls)  # 1x1 tracking pixel
        alts = {i["imageUrl"]: i["alt"] for i in images}
        self.assertEqual(alts["https://x.com/real.jpg"], "Kerala beach")

    def test_data_uri_ignored(self):
        from bs4 import BeautifulSoup
        html = '<img src="data:image/png;base64,xxxx">'
        soup = BeautifulSoup(html, "html.parser")
        self.assertEqual(crawler.extract_images(soup, "https://x.com/p", "t"), [])


class TestLinkExtraction(unittest.TestCase):
    def test_links_with_anchor_and_rel(self):
        from bs4 import BeautifulSoup
        html = ('<a href="/docs">Docs</a>'
                '<a href="https://external.com/x" rel="nofollow">ext</a>'
                '<a href="mailto:a@b.com">mail</a>')
        soup = BeautifulSoup(html, "html.parser")
        crawl, graph = crawler.extract_links(soup, "https://x.com/",
                                             {"x.com"})
        self.assertEqual(len(graph), 2)               # mailto ignored
        anchors = {l["url"]: l["anchor"] for l in graph}
        self.assertEqual(anchors["https://x.com/docs"], "Docs")
        rels = {l["url"]: l["rel"] for l in graph}
        self.assertEqual(rels["https://external.com/x"], "nofollow")
        # only allowed domains are crawl candidates
        self.assertEqual([l["url"] for l in crawl], ["https://x.com/docs"])


class TestTokenizer(unittest.TestCase):
    def test_lowercase(self):
        self.assertEqual(indexer.tokenize("JavaScript JAVASCRIPT"),
                         ["javascript", "javascript"])

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


# a small corpus shared by the search tests
CORPUS = [
    {"url": "https://a.com/javascript", "title": "JavaScript Tutorial",
     "description": "Learn JS", "language": "en",
     "text": "JavaScript tutorial for beginners. Learn JavaScript basics and arrays.",
     "headings": ["Basics"], "domain": "a.com", "crawledAt": "2026-01-01",
     "links": [{"url": "https://b.com/py", "anchor": "python", "rel": ""},
               {"url": "https://a.com/js-arrays", "anchor": "arrays", "rel": ""}],
     "images": [{"imageUrl": "https://a.com/js.png", "alt": "javascript code",
                 "title": "JavaScript Tutorial", "caption": "", "width": 800,
                 "height": 600, "source": "img"}]},
    {"url": "https://b.com/py", "title": "Python Guide",
     "description": "Python", "language": "en",
     "text": "Python is a programming language. Python tutorial here.",
     "headings": ["Guide"], "domain": "b.com", "crawledAt": "2026-01-01",
     "links": [{"url": "https://a.com/javascript", "anchor": "js", "rel": ""}],
     "images": [{"imageUrl": "https://b.com/py.png", "alt": "python logo",
                 "title": "Python Guide", "caption": "", "width": 400,
                 "height": 400, "source": "img"}]},
    {"url": "https://a.com/js-arrays", "title": "JS Arrays",
     "description": "", "language": "en",
     "text": "Arrays in JavaScript. The map method of arrays explained.",
     "headings": [], "domain": "a.com", "crawledAt": "2026-01-01",
     "links": [], "images": []},
    {"url": "https://c.com/kerala", "title": "കേരളം",
     "description": "", "language": "ml",
     "text": "കേരളം ഇന്ത്യയിലെ ഒരു സംസ്ഥാനമാണ്. കേരളത്തിലെ വിദ്യാഭ്യാസം മികച്ചതാണ്.",
     "headings": ["ആമുഖം"], "domain": "c.com", "crawledAt": "2026-01-01",
     "links": [], "images": [{"imageUrl": "https://c.com/k.jpg", "alt": "കേരളം",
                              "title": "കേരളം", "caption": "", "source": "og"}]},
]


class TestSearchEngine(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        pages_file = _write_pages(cls.tmp, CORPUS)
        cls.oldcwd = os.getcwd()
        os.chdir(cls.tmp)
        os.makedirs("data", exist_ok=True)
        indexer.build(pages_file, "data/test.db")
        from server.engine import SearchEngine
        cls.engine = SearchEngine("data/test.db")

    @classmethod
    def tearDownClass(cls):
        os.chdir(cls.oldcwd)

    def test_engine_loaded(self):
        self.assertTrue(self.engine.ok)
        self.assertEqual(self.engine.N, 4)

    def test_basic_search(self):
        for q in ("javascript", "python", "arrays"):
            r = self.engine.search(q)
            self.assertGreater(r["total"], 0, q)

    def test_case_insensitive(self):
        self.assertEqual(
            [x["url"] for x in self.engine.search("javascript")["results"]],
            [x["url"] for x in self.engine.search("JavaScript")["results"]])

    def test_multiword(self):
        self.assertGreater(self.engine.search("javascript tutorial")["total"], 0)

    def test_malayalam(self):
        r = self.engine.search("കേരളം")
        self.assertEqual(r["results"][0]["url"], "https://c.com/kerala")

    def test_phrase_search(self):
        quoted = self.engine.search('"javascript tutorial"')
        unquoted = self.engine.search("javascript tutorial")
        self.assertLessEqual(quoted["total"], unquoted["total"])
        for r in quoted["results"]:
            d = next(x for x in self.engine.docs if x["url"] == r["url"])
            self.assertIn("javascript tutorial", d["text"].lower())

    def test_phrase_only_absent(self):
        r = self.engine.search('"xyzabc notaword"')
        self.assertEqual(r["total"], 0)

    def test_invalid_query(self):
        self.assertEqual(self.engine.search("abcxyz123zzz")["total"], 0)

    def test_empty_query(self):
        self.assertEqual(self.engine.search("")["total"], 0)

    def test_ranking_deterministic(self):
        r1 = self.engine.search("javascript")
        r2 = self.engine.search("javascript")
        self.assertEqual([x["url"] for x in r1["results"]],
                         [x["url"] for x in r2["results"]])

    def test_title_boost(self):
        # the page whose TITLE is exactly "JavaScript Tutorial" should be
        # boosted above pages that merely mention javascript
        r = self.engine.search("javascript tutorial")
        self.assertEqual(r["results"][0]["url"], "https://a.com/javascript")

    def test_authority_signal(self):
        # b.com/py links to a.com/javascript -> it has 1 in-link
        self.assertEqual(self.engine._authority("https://a.com/javascript"), 1)

    def test_snippet_highlight_is_safe(self):
        r = self.engine.search("javascript")
        snip = r["results"][0]["snippet"]
        self.assertIn("<b>", snip)          # highlighted
        # raw < > of a fake tag must never survive from the content
        self.assertNotIn("<script", snip)

    def test_typo_did_you_mean(self):
        r = self.engine.search("javascrpt")
        self.assertEqual(r["total"], 0)
        self.assertEqual(r["did_you_mean"], "javascript")

    def test_pagination(self):
        r1 = self.engine.search("javascript", page=1, limit=1)
        r2 = self.engine.search("javascript", page=2, limit=1)
        self.assertEqual(r1["total"], r2["total"])
        if r1["results"] and r2["results"]:
            self.assertNotEqual(r1["results"][0]["url"], r2["results"][0]["url"])

    def test_image_search(self):
        r = self.engine.search_images("javascript")
        self.assertGreater(r["total"], 0)
        self.assertEqual(r["results"][0]["imageUrl"], "https://a.com/js.png")
        r2 = self.engine.search_images("കേരളം")
        self.assertEqual(r2["results"][0]["imageUrl"], "https://c.com/k.jpg")

    def test_image_dedup_and_metadata(self):
        imgs = self.engine.images
        urls = [i["image_url"] for i in imgs]
        self.assertEqual(len(urls), len(set(urls)))   # deduplicated
        js = next(i for i in imgs if i["image_url"].endswith("js.png"))
        self.assertEqual(js["alt"], "javascript code")
        self.assertEqual(js["width"], 800)

    def test_suggest(self):
        s = self.engine.suggest("java")
        self.assertTrue(any("javascript" in x for x in s))
        self.assertTrue(any(x.lower().startswith("java") for x in s))

    def test_link_graph_in_db(self):
        import sqlite3
        con = sqlite3.connect("data/test.db")
        edges = con.execute("SELECT COUNT(*) FROM links").fetchone()[0]
        con.close()
        self.assertEqual(edges, 3)


if __name__ == "__main__":
    unittest.main(verbosity=2)
