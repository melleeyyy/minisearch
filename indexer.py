"""MiniSearch — indexer (Phase 2): builds the SQLite search database.

Reads data/pages.jsonl (produced by crawler.py) and writes
data/minisearch.db with:

  - pages      — one row per crawled page (+ token length for BM25)
  - images     — one row per discovered image (source page, alt, size...)
  - links      — the web link graph (source, target, anchor text, rel)
  - postings   — inverted index (term, doc_id, term frequency)
  - meta       — corpus statistics (N, avgdl)

The server (server/engine.py) loads this database into memory at
startup and answers queries; build_static.py builds the small
browser-side fallback bundle from it.
"""
import json
import math
import os
import re
import sqlite3
from collections import Counter
from urllib.parse import urlparse

DB_PATH = os.environ.get("MS_DB", "data/minisearch.db")

# \w alone drops Malayalam combining vowel signs (e.g. the േ in കേരളം),
# which would split words into fragments — so we include the full Malayalam block.
TOKEN_RE = re.compile(r"[\w\u0D00-\u0D7F]+", re.UNICODE)

# A few common Malayalam + English stopwords (kept small on purpose)
STOPWORDS = {
    "ഒരു", "ഈ", "ആ", "അത്", "ഇത്", "അവർ", "ന്റെ", "യും", "ആണ്", "ഉണ്ട്",
    "ചെയ്ത", "വേണം", "കൊണ്ട്", "എന്ന", "മറ്റ്", "വളരെ", "പിന്നീട്", "ഇവിടെ",
    "the", "a", "an", "of", "and", "in", "to", "is", "are", "was", "for", "on",
    "with", "as", "by", "that", "it", "from", "or", "at", "be", "this",
}


def tokenize(text):
    tokens = [t.lower() for t in TOKEN_RE.findall(text)]
    return [t for t in tokens if len(t) > 1 and t not in STOPWORDS]


MIME_BY_EXT = {
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
    ".gif": "image/gif", ".webp": "image/webp", ".svg": "image/svg+xml",
    ".bmp": "image/bmp", ".avif": "image/avif", ".ico": "image/x-icon",
}


def build(pages_file="data/pages.jsonl", db_path=None):
    db_path = db_path or DB_PATH
    os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
    if os.path.exists(db_path):
        os.remove(db_path)
    con = sqlite3.connect(db_path)
    cur = con.cursor()
    cur.executescript("""
    CREATE TABLE pages (
        id INTEGER PRIMARY KEY, url TEXT UNIQUE, canonical_url TEXT,
        title TEXT, description TEXT, language TEXT, text TEXT,
        headings TEXT, word_count INTEGER, content_hash TEXT,
        domain TEXT, status_code INTEGER, crawled_at TEXT,
        last_modified TEXT, etag TEXT, length INTEGER);
    CREATE TABLE images (
        id INTEGER PRIMARY KEY, image_url TEXT UNIQUE, source_id INTEGER,
        source_url TEXT, domain TEXT, alt TEXT, title TEXT, caption TEXT,
        width INTEGER, height INTEGER, mime TEXT, source TEXT, crawled_at TEXT);
    CREATE TABLE links (
        source_id INTEGER, target_url TEXT, anchor TEXT, rel TEXT);
    CREATE TABLE postings (
        term TEXT, doc_id INTEGER, tf INTEGER);
    CREATE INDEX idx_postings_term ON postings(term);
    CREATE INDEX idx_links_target ON links(target_url);
    CREATE TABLE meta (k TEXT PRIMARY KEY, v TEXT);
    """)

    n_docs = 0
    total_len = 0
    seen_images = {}
    with open(pages_file, encoding="utf-8") as f:
        for line in f:
            pg = json.loads(line)
            toks = tokenize(pg["title"] + " " + pg["text"])
            cur.execute(
                "INSERT INTO pages (url, canonical_url, title, description, language,"
                " text, headings, word_count, content_hash, domain, status_code,"
                " crawled_at, last_modified, etag, length) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (pg["url"], pg.get("canonicalUrl", pg["url"]), pg["title"],
                 pg.get("description", ""), pg.get("language", ""),
                 pg.get("text", ""), json.dumps(pg.get("headings", []), ensure_ascii=False),
                 pg.get("wordCount", 0), pg.get("contentHash", ""),
                 pg.get("domain", ""), pg.get("statusCode", 0),
                 pg.get("crawledAt", ""), pg.get("lastModified", ""),
                 pg.get("etag", ""), len(toks)))
            doc_id = cur.lastrowid
            n_docs += 1
            total_len += len(toks)

            cur.executemany(
                "INSERT INTO postings (term, doc_id, tf) VALUES (?,?,?)",
                [(term, doc_id, tf) for term, tf in Counter(toks).items()])

            for l in pg.get("links", []):
                if isinstance(l, dict):
                    cur.execute(
                        "INSERT INTO links (source_id, target_url, anchor, rel) VALUES (?,?,?,?)",
                        (doc_id, l["url"], l.get("anchor", ""), l.get("rel", "")))

            for im in pg.get("images", []):
                url = im.get("imageUrl")
                if not url or url in seen_images:
                    continue
                seen_images[url] = True
                ext = os.path.splitext(urlparse(url).path)[1].lower()
                cur.execute(
                    "INSERT OR IGNORE INTO images (image_url, source_id, source_url,"
                    " domain, alt, title, caption, width, height, mime, source, crawled_at)"
                    " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                    (url, doc_id, pg["url"], pg.get("domain", ""),
                     im.get("alt", ""), im.get("title", ""), im.get("caption", ""),
                     im.get("width"), im.get("height"),
                     MIME_BY_EXT.get(ext, ""),
                     im.get("source", ""), pg.get("crawledAt", "")))

    avgdl = total_len / n_docs if n_docs else 0
    cur.execute("INSERT INTO meta (k, v) VALUES ('N', ?)", (str(n_docs),))
    cur.execute("INSERT INTO meta (k, v) VALUES ('avgdl', ?)", (str(avgdl),))
    con.commit()

    # quick summary
    imgs = cur.execute("SELECT COUNT(*) FROM images").fetchone()[0]
    lnks = cur.execute("SELECT COUNT(*) FROM links").fetchone()[0]
    terms = cur.execute("SELECT COUNT(DISTINCT term) FROM postings").fetchone()[0]
    con.close()
    print(f"Indexed {n_docs} pages | {terms} terms | {imgs} images | "
          f"{lnks} link edges | saved {db_path}")
    return db_path


def load_stats(db_path=None):
    db_path = db_path or DB_PATH
    con = sqlite3.connect(db_path)
    meta = dict(con.execute("SELECT k, v FROM meta").fetchall())
    con.close()
    return meta


if __name__ == "__main__":
    build()
