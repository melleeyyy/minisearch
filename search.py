"""MiniSearch — command-line search over the SQLite index.

Usage: python search.py <query> [pages]
"""
import sys

from server.engine import SearchEngine


def main():
    if len(sys.argv) < 2 or not sys.argv[1].strip():
        print("Usage: python search.py <query> [pages]")
        return
    query = sys.argv[1]
    pages = int(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[2].isdigit() else 1

    engine = SearchEngine()
    if not engine.ok:
        print("No index found. Run: python crawler.py seeds.txt 300 && python indexer.py")
        return

    result = engine.search(query, page=1, limit=10 * pages)
    print(f"{result['total']} results for: {query}\n")
    for i, r in enumerate(result["results"], 1):
        import re
        snippet = re.sub(r"<[^>]+>", "", r["snippet"])
        print(f"{i}. {r['title']}\n   {r['url']}\n   {snippet}\n")
    if result.get("did_you_mean"):
        print(f"Did you mean: {result['did_you_mean']}")


if __name__ == "__main__":
    main()
