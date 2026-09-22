# MiniSearch

**Live site:** https://melleeyyy.github.io/minisearch/
**Repo:** https://github.com/melleeyyy/minisearch

MiniSearch has five search tabs:

1. **Web** (default) — live full-corpus search across several Wikipedia language
   editions (English, Malayalam, Hindi, Tamil — ~65 million articles combined)
   via the MediaWiki API. No API key required.
2. **Images** — image search over all of Wikimedia Commons, with a responsive
   thumbnail grid.
3. **Videos** — video search over Wikimedia Commons: real playable WebM/OGV
   files rendered with HTML5 `<video>` players.
4. **News** — live global news search via the GDELT 2.0 API (keyless, updated
   every 15 minutes), with an automatic Wikipedia fallback if it is unreachable.
5. **My index** — our own crawler + inverted index + BM25 ranking, running fully
   in your browser over the pages in `data/`.

All tabs use silent infinite scroll — more results load automatically as you
scroll. Minimal UI in a blue / green / white / black palette, a subtle rain +
lightning backdrop, dark theme by default with a System / Light / Dark switch in
settings, and `/` to focus the search box.

Every push to `main` triggers a GitHub Actions workflow that re-crawls the seed
sites, rebuilds the index and redeploys the site, so the indexed data always
stays fresh.

## How it works (architecture)

```
seeds.txt ──> crawler.py ──> data/pages.jsonl ──> indexer.py ──> data/index.json
                                                          (BM25 ranking)
                                    search.py (CLI)  <────┘
                                    app.py    (local web UI - http://localhost:5000)

Web / Images / Videos / News tabs ──> live APIs, queried from the browser
Index tab ──> docs/data/search-data.json (BM25 in JS)
```

1. **crawler.py** — starts from the URLs in `seeds.txt`, downloads each page,
   extracts title, text and links. Respects robots.txt and waits 1 second
   between requests (to stay polite).
2. **indexer.py** — tokenizes each page and builds an **inverted index**
   (word → which pages contain it). Malayalam vowel signs are kept inside
   words so words like "കേരളം" tokenize correctly.
3. **BM25 ranking** — the improved successor of TF-IDF, the same family of
   scoring Google's early ranking used, decides which results go on top.
4. **Web / Images / Videos / News modes** — query the MediaWiki and GDELT APIs
   from the browser and interleave the results.

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
| Images / Videos | Wikimedia Commons (freely licensed) | The whole web |
| News | GDELT (global news, 15-min updates) | Google News |
| Ranking | BM25 (word counts only) | ML models + PageRank + hundreds of signals |
| Crawling | The seed sites you choose | The whole web, continuously |
| Infrastructure | A laptop / free GitHub Actions | Hundreds of thousands of servers |

## Files

| File | What it does |
|---|---|
| `crawler.py` | Crawls websites into pages.jsonl |
| `indexer.py` | Builds the inverted index + BM25 |
| `search.py` | Command-line search |
| `app.py` | Local web UI (Flask) |
| `build_static.py` | Builds docs/data/search-data.json |
| `docs/` | The static site served on GitHub Pages (web, images, videos, news, index tabs) |
| `.github/workflows/deploy.yml` | Crawl → index → build → deploy (GitHub Actions) |
| `seeds.txt` | Where the crawl starts |
| `data/` | Crawled pages and the built index |

**Note:** This is an educational project. Respect the robots.txt and terms of
the sites you crawl; for large-scale crawling prefer official APIs.
