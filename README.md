# MiniSearch

A tiny but real search engine: general web crawler + SQLite index + BM25
ranking + field boosts + a Flask Search API, with a live web UI
(Malayalam + English).

**Live UI:** https://melleeyyy.github.io/minisearch/

## Architecture (Phase 2)

```
                    INTERNET
                       │
             URL Discovery (seeds + sitemaps)
                       ▼
                  URL Frontier          (crawler.py — dedup, depth, limits)
                       ▼
                    Crawler             (HTTP, robots.txt, retries, SSRF guard)
                       ▼
                 Content Parser         (title, text, headings, links, images)
                       │
        ┌──────────────┼─────────────────┐
        ▼              ▼                 ▼
    Web Content     Image Data         Link Graph
        │              │                 │
        ▼              ▼                 ▼
   Text Index      Image Index      Authority Data     (indexer.py → SQLite)
        │              │                 │
        └──────────────┼─────────────────┘
                       ▼
                  Search Engine            (server/engine.py — BM25 + boosts)
                       ▼
                   Search API               (server/app.py — /api/search ...)
                       ▼
                    Frontend                 (docs/index.html — GitHub Pages)
```

The browser no longer downloads the whole index: the Web and Images
tabs call the Search API (server-side pagination, caching, analytics)
and fall back to public live APIs (Wikipedia, Wikimedia Commons, GDELT)
plus the small local browser index ("My index" tab) when the API is not
reachable.

## Repository layout

| Path | What it is |
|---|---|
| `crawler.py` | General-purpose crawler: multi-domain, robots.txt, sitemaps, redirects, canonical URLs, retries + backoff, SSRF protection, duplicate detection, image + link extraction |
| `indexer.py` | Builds the SQLite database: pages, images, links, postings |
| `server/engine.py` | In-memory search engine: BM25 + title/heading/URL/phrase/authority/language boosts, snippets, typo tolerance, autocomplete, image search |
| `server/app.py` | Flask API: `/api/search`, `/api/images`, `/api/suggest`, `/api/stats`, `/health` + static frontend serving |
| `build_static.py` | Small browser-side fallback bundle for the "My index" tab |
| `docs/index.html` | The frontend (single file, no build step) |
| `tests/` | Unit tests (crawler, engine, API) |
| `seeds.txt` | Seed URLs (10 domains) |
| `render.yaml` | Deploy config for the Search API (Render) |

## Search API

```
GET /api/search?q=javascript&page=1&limit=10
GET /api/images?q=kerala&page=1&limit=20
GET /api/suggest?q=java
GET /api/stats
GET /health
```

Each web result contains `title`, `url`, `displayUrl`, `snippet`
(HTML-escaped, terms highlighted), `score`, `domain`, `language`,
`crawledAt`. Zero-result responses may include `did_you_mean` (typo
correction against the indexed vocabulary).

## Run locally

```bash
pip install -r server/requirements.txt

# 1) crawl (a focused multi-domain crawl; robots.txt is always respected)
python crawler.py seeds.txt 100

# 2) build the SQLite index
python indexer.py

# 3) build the browser fallback bundle
python build_static.py

# 4) run the API + frontend on http://localhost:5000
python -m server.app          # use PORT=... to change the port

# tests
python -m unittest tests.test_engine tests.test_api -v

# command-line search
python search.py "javascript tutorial"
```

No database server is needed — everything is SQLite + files.

## Configuration (environment variables)

Crawler: `MS_MAX_PAGES` (300), `MS_MAX_DEPTH` (2), `MS_DELAY` (1.0s),
`MS_TIMEOUT` (15s), `MS_RETRIES` (3), `MS_MAX_BYTES` (3 MB),
`MS_MAX_PAGES_PER_DOMAIN` (60), `MS_BLOCKED_DOMAINS` (csv),
`MS_PLAYWRIGHT` (0 — optional JS rendering for empty pages).

API: `SEARCH_CACHE_TTL` (60s), `MS_RATE_LIMIT` (60 req/min per IP),
`MS_DB` (data/minisearch.db).

Ranking weights (all optional): `MS_RANK_TITLE_EXACT` (10),
`MS_RANK_TITLE_PARTIAL` (5), `MS_RANK_HEADING` (4), `MS_RANK_URL` (3),
`MS_RANK_PHRASE` (8), `MS_RANK_AUTHORITY` (0.6 per in-link, capped),
`MS_RANK_LANGUAGE` (2).

## Deployment

**Frontend (GitHub Pages)** — automatic on every push to `main`:
the Actions workflow crawls 300 pages, builds the SQLite index and the
static bundle, runs the tests, commits `data/minisearch.db` back to
the repo (so the API deploy has data) and publishes `docs/`.

**Search API (Render, free tier)** — one-time setup:
1. On https://dashboard.render.com → **New → Blueprint**, select this repository.
2. Render reads `render.yaml` and creates the `minisearch-api` service.
3. Copy the service URL (e.g. `https://minisearch-api.onrender.com`) into
   `API_BASES` in `docs/index.html` — then the GitHub Pages frontend uses
   your API for Web/Images search (with Wikipedia/Commons as fallback).

The index database is committed by CI, so the API never has to crawl.

## Search features

- BM25 + configurable field boosts (title > heading > URL), exact-phrase
  support (`"javascript tutorial"`), authority signal (in-link count),
  language relevance, deterministic ordering
- Typo tolerance: `javascrpt` → *Did you mean: javascript?*
- Autocomplete from indexed titles + vocabulary (keyboard navigation)
- Snippets: densest window around the query terms, safely highlighted
- Image search over the crawled image index (alt text, captions, source page)
- Multilingual: Malayalam + English (Unicode-correct tokenization)

## Security

- The crawler blocks private/internal/metadata addresses (SSRF protection)
  and never bypasses robots.txt
- API input validation (query length, paging bounds), per-IP rate limiting,
  CORS headers, HTML-escaped snippets
- The frontend renders untrusted text via `textContent` / escaped HTML only

## Limitations (honest)

- ~300 pages, 10 domains — an educational project, not Google
- The browser fallback bundle truncates page text (25k chars/page)
- Authority ranking uses raw in-link counts, not full PageRank
- Freshness signal is not used yet (Last-Modified is unreliable across sites)
- Playwright rendering is optional and off by default
