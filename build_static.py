"""MiniSearch — build the static site's data bundle.

Reads data/pages.jsonl + data/index.json (produced by crawler.py + indexer.py)
and writes docs/data/search-data.json, which the static web UI fetches.

Size optimisations (the browser should not download unnecessary data):
  - pages are keyed by a compact integer document ID (postings shrink a lot)
  - page text is truncated for the web bundle (snippets + phrase search
    only need a window, not the whole article)
  - df is derived from postings in the browser, not shipped
  - vocabulary terms without any letter (pure numbers) are dropped

The full crawl metadata and the link graph stay in data/ for the local
pipeline (future authority ranking).
"""
import json
import os

MAX_VOCAB = 30000    # autocomplete / typo-correction vocabulary cap (by df)
MAX_TEXT = 25000     # characters of body text shipped per page


def main():
    os.makedirs("docs/data", exist_ok=True)

    pages = {}
    with open("data/pages.jsonl", encoding="utf-8") as f:
        for line in f:
            pg = json.loads(line)
            pages[pg["url"]] = {
                "title": pg.get("title", pg["url"]),
                "description": pg.get("description", ""),
                "language": pg.get("language", ""),
                "text": pg.get("text", "")[:MAX_TEXT],
                "headings": pg.get("headings", []),
            }

    index = json.load(open("data/index.json", encoding="utf-8"))

    # stable integer IDs (same order as the indexer's docIds)
    urls = sorted(pages.keys())
    url_to_id = {u: i for i, u in enumerate(urls)}

    docs = [[pages[u]["title"], index["docs"][u]["length"]] for u in urls]
    web_pages = [pages[u] for u in urls]

    # postings: term -> {docId: term_frequency}
    web_postings = {}
    for term, plist in index["postings"].items():
        web_postings[term] = {url_to_id[u]: tf for u, tf in plist.items()
                              if u in url_to_id}

    # vocabulary: most frequent terms first; keep only terms with a letter
    def has_letter(t):
        return any(c.isalpha() for c in t)

    vocab = sorted((t for t in web_postings if has_letter(t)),
                   key=lambda t: -len(web_postings[t]))[:MAX_VOCAB]

    bundle = {
        "N": len(urls),
        "avgdl": index["avgdl"],
        "urls": urls,
        "docs": docs,          # id -> [title, bodyLength]
        "postings": web_postings,   # term -> {id: tf}
        "pages": web_pages,    # id -> {title, description, language, text, headings}
        "vocab": vocab,
    }
    out = "docs/data/search-data.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(bundle, f, ensure_ascii=False, separators=(",", ":"))
    print(f"wrote {out} ({os.path.getsize(out) // 1024} KB, {len(urls)} pages, "
          f"{len(vocab)} vocab terms)")


if __name__ == "__main__":
    main()
