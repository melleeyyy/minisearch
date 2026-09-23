# MiniSearch

**Live site:** https://melleeyyy.github.io/minisearch/
**Repo:** https://github.com/melleeyyy/minisearch

MiniSearch is an educational web search engine — a small, honest
implementation of how real search works: a crawler, an inverted index,
BM25 ranking with field boosts, plus live API search tabs. It is NOT a
Google-scale web index; the own-index tab covers the (small) set of
pages we crawl ourselves.

## Search tabs

1. **Web** (default) — live full-corpus search across several Wikipedia
   language editions (English, Malayalam, Hindi, Tamil) via the MediaWiki
   API. No API key required.
2. **Images** — image search over Wikimedia Commons.
3. **Videos** — video search over Wikimedia Commons (playable WebM/OGV).
4. **News** — live global news via the GDELT 2.0 API (keyless), with an
   automatic Wikipedia fallback if it is unreachable.
5. **My index** — our own crawler + inverted index + BM25, running fully
   in your browser over the pages in `data/`.

All tabs use silent infinite scroll. The UI is minimal (blue / green /
white / black palette), dark by default with System / Light / Dark in
settings, a subtle rain + lightning backdrop, and `/` to focus the
search box.

## My index: ranking model

Ranking is deterministic and field-aware:

```
finalScore = BM25(body)
           + title boost     (exact title match > partial match)
           + heading boost   (h1–h3 text)
           + URL boost
           + exact-phrase boost
```

- **Quoted phrase search** — `"കേരളത്തിന്റെ തലസ്ഥാനം"` restricts results to
  pages containing that exact phrase (both straight and mobile curly
  quotes work). Unquoted words behave as normal BM25 terms.
- **Autocomplete** — suggestions come from page titles and the index
  vocabulary (typed locally, debounced, no network requests). Arrow
  keys + Enter navigate; touch friendly.
- **Typo tolerance** — unknown terms are matched against the vocabulary
  with a bounded Levenshtein distance; a "Did you mean: …" link appears
  when a close correction exists.
- **Snippets** — the snippet window is chosen where query terms are
  densest, not just the first characters of the page.
- Ranking weights are configurable constants (`RANK` in `docs/index.html`).

## Crawler configuration

All limits are configurable via environment variables:

| Variable | Default | Meaning |
|---|---|---|
| `MS_MAX_PAGES` | 100 | total pages fetched (also `python crawler.py seeds.txt N`) |
| `MS_MAX_DEPTH` | 2 | link-hops from a seed page |
| `MS_DELAY` | 1.0 | seconds between requests (politeness) |
| `MS_TIMEOUT` | 15 | per-request timeout |
| `MS_RETRIES` | 3 | retries with exponential backoff |
| `MS_MAX_BYTES` | 3 MB | skip oversized downloads |

Crawler quality features: URL normalization (fragments, tracking
parameters, duplicate params, relative links, default ports), redirect
handling with canonical final URLs, HTML-only content-type validation,
per-domain robots.txt caching (never bypassed), duplicate-content
detection via content hashing, per-page crawl metadata (title,
description, language, headings, word count, content hash, timestamps),
and outgoing-link extraction (link graph in `data/links.json`, ready for
a future PageRank-like authority signal — not used in ranking yet).

## How it works (architecture)

```
seeds.txt ──> crawler.py ──> data/pages.jsonl ──> indexer.py ──> data/index.json
                   │             (metadata, links)      │         (inverted index,
                   │                                      │          BM25, doc IDs)
                   │                                      └──> data/links.json
                   └──> search.py (CLI) / app.py (local Flask UI)

Web / Images / Videos / News tabs ──> live APIs, queried from the browser
My index tab ──> docs/data/search-data.json (BM25 + field boosts in JS)
```

1. **crawler.py** — crawls from `seeds.txt`, stays on the seed domains,
   respects robots.txt, waits between requests.
2. **indexer.py** — tokenizes (Malayalam combining marks are kept inside
   words), builds the inverted index, stable document IDs and the link
   graph.
3. **build_static.py** — builds the lean web bundle (integer doc IDs,
   truncated body text, capped vocabulary) so the browser only downloads
   what it needs.
4. **GitHub Actions** re-crawls, re-indexes and redeploys on every push.

## How to run locally

```bash
pip install requests beautifulsoup4 flask

# 1. Crawl (edit seeds.txt to choose which sites to index)
python crawler.py seeds.txt 100        # or: MS_MAX_PAGES=100 python crawler.py

# 2. Build the index
python indexer.py

# 3. Build the static web bundle
python build_static.py

# 4. Search — three ways:
python search.py kerala               # command line
python app.py                         # local Flask UI → http://localhost:5000
python -m http.server 8899 -d docs    # static site → http://localhost:8899
```

## Tests

```bash
python -m unittest tests.test_engine -v
```

Covers URL normalization, tokenization (English + Malayalam), BM25
ranking (basic, case, multi-word, Malayalam, invalid, empty,
deterministic), the link graph and stable document IDs.

## Limitations (honest list)

- The own index is ~100 pages, not the web. Web/Images/Videos/News tabs
  use live public APIs (Wikipedia, Wikimedia Commons, GDELT) instead.
- Web-bundle body text is truncated to the first 25 000 characters per
  page, so phrase matches deep inside very long articles can be missed.
- Ranking uses BM25 + field boosts; no link authority is used yet.
- No semantic/vector search, no AI summaries — by design (Phase 2+).

## Tips

- Add your favourite websites to `seeds.txt` (one URL per line). The
  crawler stays on those domains only.
- Crawl more pages: `python crawler.py seeds.txt 500`.
- Raise `MS_MAX_DEPTH` to follow more links — it takes longer.

## How is this different from Google?

| | MiniSearch | Google |
|---|---|---|
| Own web results | ~100 crawled pages + Wikipedia API | Hundreds of billions of pages |
| Ranking | BM25 + title/heading/URL/phrase boosts | ML models + PageRank + hundreds of signals |
| Autocomplete | Own vocabulary | Massive query logs |
| Infrastructure | A laptop / free GitHub Actions | Hundreds of thousands of servers |

## Files

| File | What it does |
|---|---|
| `crawler.py` | Crawls websites into pages.jsonl (configurable, polite) |
| `indexer.py` | Builds the inverted index + BM25 + doc IDs + link graph |
| `build_static.py` | Builds the lean docs/data/search-data.json bundle |
| `search.py` | Command-line search |
| `app.py` | Local web UI (Flask) |
| `tests/test_engine.py` | Engine unit tests |
| `docs/` | The static site served on GitHub Pages |
| `.github/workflows/deploy.yml` | Crawl → index → build → deploy (GitHub Actions) |
| `seeds.txt` | Where the crawl starts |
| `data/` | Crawled pages and the built index (generated, not committed) |

**Note:** This is an educational project. Respect the robots.txt and terms of
the sites you crawl; for large-scale crawling prefer official APIs.
