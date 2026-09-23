"""MiniSearch — build the static fallback bundle for GitHub Pages.

Reads the SQLite database (data/minisearch.db, built by indexer.py)
and writes docs/data/search-data.json — the small browser-side index
used by the "My index" tab when the Search API is not reachable.

Size optimisations (the browser should not download unnecessary data):
  - pages are keyed by a compact integer document ID
  - page text is truncated (snippets + phrase search only need a window)
  - vocabulary capped, letter-less terms dropped
"""
import json
import os
import sqlite3

DB_PATH = os.environ.get("MS_DB", "data/minisearch.db")
MAX_VOCAB = 30000
MAX_TEXT = 25000


def main():
    os.makedirs("docs/data", exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row

    rows = con.execute(
        "SELECT url, title, description, language, text, headings, length"
        " FROM pages ORDER BY url").fetchall()
    meta = dict(con.execute("SELECT k, v FROM meta").fetchall())
    con.close()

    pages = [{"title": r["title"] or r["url"],
              "description": r["description"] or "",
              "language": r["language"] or "",
              "text": (r["text"] or "")[:MAX_TEXT],
              "headings": json.loads(r["headings"] or "[]")} for r in rows]
    urls = [r["url"] for r in rows]
    docs = [[r["title"] or r["url"], r["length"]] for r in rows]
    url_to_id = {u: i for i, u in enumerate(urls)}

    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    raw_to_id = {}
    for r in con.execute("SELECT id, url FROM pages"):
        if r["url"] in url_to_id:
            raw_to_id[r["id"]] = url_to_id[r["url"]]
    web_postings = {}
    for term, doc_id, tf in con.execute("SELECT term, doc_id, tf FROM postings"):
        bid = raw_to_id.get(doc_id)
        if bid is not None:
            web_postings.setdefault(term, {})[bid] = tf
    con.close()

    def has_letter(t):
        return any(c.isalpha() for c in t)

    vocab = sorted((t for t in web_postings if has_letter(t)),
                   key=lambda t: -len(web_postings[t]))[:MAX_VOCAB]

    bundle = {
        "N": len(urls),
        "avgdl": float(meta.get("avgdl", 1)) or 1,
        "urls": urls,
        "docs": docs,
        "postings": web_postings,
        "pages": pages,
        "vocab": vocab,
    }
    out = "docs/data/search-data.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(bundle, f, ensure_ascii=False, separators=(",", ":"))
    print(f"wrote {out} ({os.path.getsize(out) // 1024} KB, {len(urls)} pages, "
          f"{len(vocab)} vocab terms)")


if __name__ == "__main__":
    main()
