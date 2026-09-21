# MiniSearch — a tiny but real search engine

**Live site:** https://melleeyyy.github.io/minisearch/
**Repo:** https://github.com/melleeyyy/minisearch

MiniSearch has two search modes:

1. **Web** (default) — live full-corpus search across several Wikipedia language
   editions (English, Malayalam, Hindi, Tamil — ~65 million articles combined)
   via the MediaWiki API. Results come back in real time; no API key required.
2. **My index** — our own crawler + inverted index + BM25 ranking, running fully
   in your browser over the pages in `data/`.

Every push to `main` triggers a GitHub Actions workflow that re-crawls the seed
sites, rebuilds the index and redeploys the site, so the indexed data always
stays fresh.

## How it works (architecture)

```
seeds.txt ──> crawler.py ──> data/pages.jsonl ──> indexer.py ──> data/index.json
                                                          (BM25 ranking)
                                    search.py (CLI)  <────┘
                                    app.py    (local web UI - http://localhost:5000)

Web tab ──> MediaWiki search API (live, 4 languages)   [runs in the browser]
Index tab ──> docs/data/search-data.json (BM25 in JS)   [runs in the browser]
```

1. **crawler.py** — starts from the URLs in `seeds.txt`, downloads each page,
   extracts title, text and links. Respects robots.txt and waits 1 second
   between requests (to stay polite).
2. **indexer.py** — tokenizes each page and builds an **inverted index**
   (word → which pages contain it). Malayalam vowel signs are kept inside
   words so words like "കേരളം" tokenize correctly.
3. **BM25 ranking** — the improved successor of TF-IDF, the same family of
   scoring Google's early ranking used, decides which results go on top.
4. **Web mode** — queries the MediaWiki API of four Wikipedia editions in
   parallel and interleaves the results.

## How to run locally

```bash
pip install requests beautifulsoup4 flask

# 1. Crawl (edit seeds.txt to choose which sites to index)
python crawler.py seeds.txt 30        # 30 = max pages

# 2. Build the index
python indexer.py

# 3. Search — two ways:
python search.py kerala               # command line
python app.py                         # web UI → http://localhost:5000
```

## Tips

- Add your favourite websites to `seeds.txt` (one URL per line). The crawler
  stays on those domains only.
- Crawl more pages: `python crawler.py seeds.txt 200`
- Raise `MAX_DEPTH` (in crawler.py) to follow more links — it takes longer.

## How is this different from Google?

| | MiniSearch | Google |
|---|---|---|
| Web results | ~65M Wikipedia articles (live API) | Hundreds of billions of pages |
| Ranking | BM25 (word counts only) | ML models + PageRank + hundreds of signals |
| Crawling | The seed sites you choose | The whole web, continuously |
| Infrastructure | A laptop / free GitHub Actions | Hundreds of thousands of servers |

## Next steps (ideas for a business experiment)

- **Spelling correction** — Levenshtein distance to catch typos
- **Malayalam stemmer** — strip endings (case suffixes) for better matching
- **TF-IDF vector search + semantic embeddings** — meaning-based search
- **Distributed crawl** — crawl from several machines in parallel
- Honor `Crawl-delay` in robots.txt more strictly

## Files

| File | What it does |
|---|---|
| `crawler.py` | Crawls websites into pages.jsonl |
| `indexer.py` | Builds the inverted index + BM25 |
| `search.py` | Command-line search |
| `app.py` | Local web UI (Flask) |
| `build_static.py` | Builds docs/data/search-data.json |
| `docs/` | The static site served on GitHub Pages (web + index tabs) |
| `.github/workflows/deploy.yml` | Crawl → index → build → deploy (GitHub Actions) |
| `seeds.txt` | Where the crawl starts |
| `data/` | Crawled pages and the built index |

**Note:** This is an educational project. Respect the robots.txt and terms of
the sites you crawl; for large-scale crawling prefer official APIs.
