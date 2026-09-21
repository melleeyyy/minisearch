"""MiniSearch — command-line search over the built index."""
import json
import re
import sys

from indexer import BM25, tokenize

TOKEN_RE = re.compile(r"[\w]+", re.UNICODE)


def make_snippet(text, query, width=220):
    """Return a short snippet around the first query-term match."""
    toks_q = [t for t in tokenize(query)]
    lowered = text.lower()
    pos = -1
    for t in toks_q:
        pos = lowered.find(t)
        if pos >= 0:
            break
    if pos < 0:
        return text[:width] + ("..." if len(text) > width else "")
    start = max(0, pos - width // 3)
    snippet = text[start:start + width]
    if start > 0:
        snippet = "..." + snippet
    if start + width < len(text):
        snippet += "..."
    return snippet


def main():
    query = " ".join(sys.argv[1:])
    if not query:
        print("Usage: python search.py <query>")
        return
    with open("data/index.json", encoding="utf-8") as f:
        index = json.load(f)
    pages = {}
    with open("data/pages.jsonl", encoding="utf-8") as f:
        for line in f:
            pg = json.loads(line)
            pages[pg["url"]] = pg

    bm = BM25(index)
    results = bm.search(query, top_k=10)
    print(f"\nMiniSearch results for: {query!r}  ({len(results)} matches)\n" + "-" * 70)
    if not results:
        print("No pages matched. Try another word (in Malayalam or English).")
        return
    for rank, (url, score) in enumerate(results, 1):
        pg = pages.get(url, {"title": url, "text": ""})
        print(f"{rank}. {pg['title']}")
        print(f"   {make_snippet(pg['text'], query)}")
        print(f"   {url}   [BM25 score: {score:.2f}]\n")


if __name__ == "__main__":
    main()
