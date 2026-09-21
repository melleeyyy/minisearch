"""MiniSearch — build the static site's data bundle.

Reads data/pages.jsonl + data/index.json (produced by crawler.py + indexer.py)
and writes docs/data/search-data.json, which the static web UI fetches.
"""
import json
import os


def main():
    os.makedirs("docs/data", exist_ok=True)

    pages = {}
    with open("data/pages.jsonl", encoding="utf-8") as f:
        for line in f:
            pg = json.loads(line)
            pages[pg["url"]] = pg

    index = json.load(open("data/index.json", encoding="utf-8"))

    bundle = {
        "N": index["N"],
        "avgdl": index["avgdl"],
        "docs": index["docs"],
        "df": index["df"],
        "postings": index["postings"],
        "pages": pages,
    }
    out = "docs/data/search-data.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(bundle, f, ensure_ascii=False, separators=(",", ":"))
    print(f"wrote {out} ({os.path.getsize(out) // 1024} KB, {len(pages)} pages)")


if __name__ == "__main__":
    main()
