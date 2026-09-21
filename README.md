# MiniSearch — നിങ്ങളുടെ സ്വന്തമായ ചെറിയ Search Engine

**Live site:** https://melleeyyy.github.io/minisearch/
**Repo:** https://github.com/melleeyyy/minisearch

ഓരോ main-ലേക്കുള്ള push-ഉം GitHub Actions വഴി വീണ്ടും crawl → index → build →
deploy നടത്തുന്നതിനാൽ site-ലെ data എപ്പോഴും പുതിയതായിരിക്കും.

Google-ന്റെ അതേ അടിസ്ഥാന ആശയങ്ങൾ ഉപയോഗിക്കുന്ന, യഥാർത്ഥത്തിൽ പ്രവർത്തിക്കുന്ന
ഒരു ചെറിയ search engine: **crawler → indexer → search UI**.

## എങ്ങനെ പ്രവർത്തിക്കുന്നു (Architecture)

```
seeds.txt ──> crawler.py ──> data/pages.jsonl ──> indexer.py ──> data/index.json
                                                          (BM25 ranking)
                                    search.py (CLI)  <────┘
                                    app.py    (Web UI - http://localhost:5000)
```

1. **crawler.py** — `seeds.txt`-ൽ നിന്ന് തുടങ്ങി, ഓരോ page-ും download ചെയ്ത്
   title, text, links എടുക്കുന്നു. robots.txt അനുസരിക്കുന്നു, ഓരോ request-നും
   ഇടയിൽ 1 സെക്കൻഡ് കാത്തുന്നു (websites-നെ ബുദ്ധിമുട്ടിക്കാതിരിക്കാൻ).
2. **indexer.py** — ഓരോ page-ന്റെയും വാക്കുകൾ എണ്ണി, ഒരു **inverted index**
   (ഓരോ വാക്കിനും ഏതൊക്കെ page-ലാണ് വരുന്നത് എന്ന പട്ടിക) ഉണ്ടാക്കുന്നു.
3. **BM25 ranking** — Google-ൻ്റെ ആദ്യകാല ranking-ൽ ഉപയോഗിച്ചിരുന്ന
   TF-IDF-ന്റെ മെച്ചപ്പെടുത്തിയ പതിപ്പ്. ഇതാണ് ഏത് result ആണ് മുകളിൽ
   കാണിക്കണം എന്ന് തീരുമാനിക്കുന്നത്.
4. **app.py** — Google-ന് സമാനമായ ഒരു web UI (Flask). Query box + result snippets
   + highlight ചെയ്ത വാക്കുകൾ.

## എങ്ങനെ run ചെയ്യാം

```bash
pip install requests beautifulsoup4 flask

# 1. Crawl (ഏത് websites എന്ന് seeds.txt-ൽ മാറ്റാം)
python crawler.py seeds.txt 30        # 30 = എത്ര pages വരെ

# 2. Index build ചെയ്യുക
python indexer.py

# 3. Search — രണ്ട് വഴികൾ:
python search.py കേരളം               # command line
python app.py                        # web UI → http://localhost:5000
```

## മികച്ച രീതിയിൽ പ്രവർത്തിക്കാൻ

- `seeds.txt`-ൽ നിങ്ങൾക്കിഷ്ടമുള്ള websites ചേർക്കുക (ഓരോ വരിയിലും ഒരു URL).
  Crawler ആ കിട്ടിയ domains-ൽ മാത്രം നിൽക്കും.
- Page count കൂട്ടുക: `python crawler.py seeds.txt 200`
- `MAX_DEPTH` (crawler.py) കൂട്ടിയാൽ link-കൾ പിന്തുടർന്ന് കൂടുതൽ pages
  കിട്ടും — പക്ഷേ സമയം കൂടും.

## Google-ൽ നിന്ന് എന്ത് വ്യത്യാസം?

| | MiniSearch | Google |
|---|---|---|
| Pages | നൂറുകണക്കിന് | നൂറ് ബില്ല്യൺ+ |
| Ranking | BM25 (വാക്കിന്റെ എണ്ണം മാത്രം) | ML models + PageRank + നൂറുകണക്കിന് signals |
| Crawl | നിങ്ങൾ കൊടുക്കുന്ന sites മാത്രം | മുഴുവൻ internet, തുടർച്ചയായി |
| Infrastructure | ഒരു laptop | ലക്ഷക്കണക്കിന് servers |

## Next steps (business experiment ആയെങ്കിൽ ആലോചിക്കാവുന്നവ)

- **Spelling correction** — Levenshtein distance കൊണ്ട് "കേരളം" vs "കേരലം" പിടിക്കുക
- **Malayalam stemmer** — വാക്കിന്റെ endings (cases, suffixes) നീക്കി matching മെച്ചപ്പെടുത്തുക
- **TF-IDF vector search + semantic embeddings** — അർത്ഥം അനുസരിച്ചുള്ള തിരച്ചിൽ
- **Distributed crawl** — ഒന്നിലധികം machines-ൽ ഒരേസമയം crawl ചെയ്യുക
- robots.txt കൂടുതർ കൃത്യമായി honor ചെയ്യാൻ crawl-delay-യും പാലിക്കുക

## Files

| File | എന്ത് ചെയ്യുന്നു |
|---|---|
| `crawler.py` | Websites crawl ചെയ്ത് pages.jsonl ഉണ്ടാക്കുന്നു |
| `indexer.py` | Inverted index + BM25 ranking |
| `search.py` | Command-line search |
| `app.py` | Local web UI (Flask) |
| `build_static.py` | docs/data/search-data.json build ചെയ്യുന്നു |
| `docs/` | GitHub Pages-ൽ live ആയി പ്രവർത്തിക്കുന്ന static site (browser-ൽ BM25) |
| `.github/workflows/deploy.yml` | Crawl → index → build → deploy (GitHub Actions) |
| `seeds.txt` | എവിടന്ന് crawl തുടങ്ങണം എന്ന URLs |
| `data/` | Crawl ചെയ്ത pages-ഉം index-ഉം |

**Note:** ഇത് വിദ്യാഭ്യാസ ആവശ്യത്തിനുള്ളതാണ്. Crawl ചെയ്യുന്ന websites-ന്റെ
robots.txt-ഉം terms-ഉം അനുസരിക്കുക; വലിയ scale-ൽ crawl ചെയ്യാൻ API ഉപയോഗിക്കുന്നതാണ്
നല്ലത്.
