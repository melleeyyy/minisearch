"""MiniSearch — a tiny but real search engine.

Crawler v2 (Phase 1 upgrade):
  - configurable limits (env vars, see CONFIG below)
  - URL normalization (fragments, tracking params, duplicates, relative links)
  - redirect handling with canonical final URLs and loop avoidance
  - content-type / content-length validation (HTML only)
  - retry with exponential backoff for transient errors
  - per-domain robots.txt caching (never bypassed)
  - rich crawl metadata (title, description, language, headings, contentHash, ...)
  - duplicate-content detection via content hashing
  - outgoing-link extraction (link graph, for future authority ranking)

Fetches pages starting from seed URLs (seeds.txt), stays on the seed
domains, saves data/pages.jsonl.
"""
import hashlib
import json
import os
import re
import sys
import time
from collections import deque
from datetime import datetime, timezone
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup

# ----------------------------- configuration -----------------------------
# Order: env var > command line (pages only) > default.
def _pages_arg():
    for a in sys.argv[2:]:
        if a.isdigit():
            return a
    return "100"


MAX_PAGES = int(os.environ.get("MS_MAX_PAGES", _pages_arg()))
MAX_DEPTH = int(os.environ.get("MS_MAX_DEPTH", "2"))
REQUEST_DELAY = float(os.environ.get("MS_DELAY", "1.0"))
REQUEST_TIMEOUT = float(os.environ.get("MS_TIMEOUT", "15"))
MAX_RETRIES = int(os.environ.get("MS_RETRIES", "3"))
MAX_CONTENT_SIZE = int(os.environ.get("MS_MAX_BYTES", str(3 * 1024 * 1024)))

HEADERS = {"User-Agent": "MiniSearchBot/1.0 (educational project)"}

TAGS_TO_DROP = ("script", "style", "nav", "footer", "header", "aside", "form")

# Query parameters that only track users, never identify content.
TRACKING_PARAMS = ("utm_source", "utm_medium", "utm_campaign", "utm_term",
                   "utm_content", "utm_id", "fbclid", "gclid", "msclkid",
                   "mc_cid", "mc_eid", "igshid", "yclid", "_ga", "ref",
                   "referrer", "source")

_robots_cache = {}          # domain -> RobotFileParser
_content_hashes = set()     # sha256 of normalized text (duplicate detection)
_seen_urls = set()          # normalized URLs already queued or fetched


# ---------------------------- URL normalization ----------------------------
def normalize_url(raw, base=None):
    """Resolve + normalize a URL. Returns None for non-crawlable targets.

    raw -> resolve relative -> drop fragment -> strip tracking params
        -> lowercase scheme/host -> drop default ports -> sort query
        -> validate -> dedupe-ready canonical string
    """
    if raw is None:
        return None
    raw = raw.strip()
    if not raw or raw.startswith(("#", "mailto:", "tel:", "javascript:", "data:")):
        return None
    try:
        url = urljoin(base, raw) if base else raw
    except ValueError:
        return None
    p = urlparse(url)
    if p.scheme not in ("http", "https") or not p.netloc:
        return None
    scheme = p.scheme.lower()
    netloc = p.netloc.lower()
    if scheme == "http" and netloc.endswith(":80"):
        netloc = netloc[:-3]
    if scheme == "https" and netloc.endswith(":443"):
        netloc = netloc[:-4]
    path = re.sub(r"/{2,}", "/", p.path or "/")
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")
    # Keep content-bearing query params; drop trackers; sort for stability.
    q = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True)
         if k.lower() not in TRACKING_PARAMS]
    q.sort()
    return urlunparse((scheme, netloc, path, "", urlencode(q), ""))


def should_skip(url):
    """Skip non-article pages (Wikipedia namespaces, edit links, media files)."""
    skip_parts = ("action=", "redlink=", "File:", "Template:", "Special:",
                  "Wikipedia:", "Talk:", "Help:", "Category:", "Portal:",
                  "പ്രമാണം:", "ഫലകം:", "സവിശേഷത:", "വിക്കിപീഡിയ:",
                  "സംവാദം:", "വിഭാഗം:", "സഹായം:")
    return any(s.lower() in url.lower() for s in skip_parts)


# ------------------------------ robots.txt ------------------------------
def can_fetch(url):
    """robots.txt permission for a URL (cached per domain, never bypassed).

    robots.txt is fetched with `requests` + our own User-Agent, because
    many sites block Python's default urllib agent with a 403. If
    robots.txt cannot be fetched at all, we allow the fetch (the crawl
    is small, slow and educational).
    """
    p = urlparse(url)
    base = f"{p.scheme}://{p.netloc}"
    if base not in _robots_cache:
        rp = RobotFileParser()
        try:
            resp = requests.get(base + "/robots.txt", headers=HEADERS,
                                timeout=REQUEST_TIMEOUT)
            if resp.status_code == 200:
                rp.parse(resp.text.splitlines())
            else:  # 404 etc. -> no restrictions
                rp.parse([])
        except Exception:
            rp.parse([])
        _robots_cache[base] = rp
    return _robots_cache[base].can_fetch(HEADERS["User-Agent"], url)


# ------------------------------ fetching ------------------------------
TRANSIENT_STATUS = (429, 500, 502, 503, 504)


def fetch(url):
    """GET with retries + exponential backoff. Returns a Response or None.

    Permanent 4xx errors are returned (not retried) so the caller can
    record the status; connection errors are retried.
    """
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT,
                                allow_redirects=True)
            if resp.status_code in TRANSIENT_STATUS and attempt < MAX_RETRIES:
                time.sleep(2 ** attempt)
                continue
            return resp
        except requests.RequestException:
            if attempt >= MAX_RETRIES:
                return None
            time.sleep(2 ** attempt)
    return None


# ------------------------------ extraction ------------------------------
def extract_text(soup):
    for tag in soup(TAGS_TO_DROP):
        tag.decompose()
    text = soup.get_text(" ", strip=True)
    return re.sub(r"\s+", " ", text)


def extract_metadata(soup, resp):
    """Title, meta description, html language, headings (h1-h3)."""
    title = soup.title.get_text(strip=True) if soup.title else ""
    description = ""
    meta = soup.find("meta", attrs={"name": "description"})
    if meta and meta.get("content"):
        description = meta["content"].strip()
    language = ""
    if soup.html and soup.html.get("lang"):
        language = soup.html["lang"]
    headings = [h.get_text(" ", strip=True) for h in soup.find_all(["h1", "h2", "h3"])]
    return title, description[:400], language, headings[:10]


def extract_links(soup, page_url, allowed_domains):
    """Normalized outgoing links, restricted to the crawl corpus."""
    out, added = [], set()
    for a in soup.find_all("a", href=True):
        link = normalize_url(a["href"], base=page_url)
        if link is None:
            continue
        p = urlparse(link)
        if p.scheme in ("http", "https") and p.netloc in allowed_domains:
            if not should_skip(link) and link not in added:
                added.add(link)
                out.append(link)
    return out


def content_hash(text):
    """Stable hash of normalized content for duplicate detection."""
    normalized = re.sub(r"\s+", " ", text.strip().lower())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


# ------------------------------- crawling -------------------------------
def crawl(seed_file, out_file):
    with open(seed_file, encoding="utf-8") as f:
        seeds = [normalize_url(ln.strip()) for ln in f
                 if ln.strip() and not ln.startswith("#")]
    seeds = [s for s in seeds if s]
    allowed = {urlparse(s).netloc for s in seeds}

    queue = deque((s, 0) for s in seeds)
    for s in seeds:
        _seen_urls.add(s)
    pages = []
    fetched = 0
    duplicates = 0
    failed = 0

    print(f"Seeds: {len(seeds)} | max pages: {MAX_PAGES} | max depth: {MAX_DEPTH}")

    while queue and fetched < MAX_PAGES:
        url, depth = queue.popleft()
        if not can_fetch(url):
            print(f"[blocked by robots.txt] {url}")
            continue

        print(f"[fetch {fetched + 1}] {url}")
        resp = fetch(url)
        if resp is None:
            failed += 1
            print("  !! failed after retries")
            time.sleep(REQUEST_DELAY)
            continue

        canonical = normalize_url(resp.url) or url
        if canonical in _seen_urls and canonical != url:
            print(f"  == redirect to already-seen URL, skipped: {canonical}")
            time.sleep(REQUEST_DELAY)
            continue
        _seen_urls.add(canonical)

        ctype = resp.headers.get("Content-Type", "")
        clength = resp.headers.get("Content-Length")
        if resp.status_code != 200 or "text/html" not in ctype:
            print(f"  -- skipped: status {resp.status_code}, type {ctype[:40]}")
            time.sleep(REQUEST_DELAY)
            continue
        if clength and clength.isdigit() and int(clength) > MAX_CONTENT_SIZE:
            print(f"  -- skipped: too large ({int(clength) // 1024} KB)")
            time.sleep(REQUEST_DELAY)
            continue

        try:
            resp.encoding = resp.apparent_encoding or "utf-8"
            soup = BeautifulSoup(resp.text, "html.parser")
        except Exception as e:
            failed += 1
            print(f"  !! parse failed: {e}")
            time.sleep(REQUEST_DELAY)
            continue

        title, description, language, headings = extract_metadata(soup, resp)
        text = extract_text(soup)
        links = extract_links(soup, canonical, allowed)

        if len(text) <= 100:  # skip near-empty pages
            time.sleep(REQUEST_DELAY)
            continue

        chash = content_hash(title + " " + text)
        if chash in _content_hashes:
            duplicates += 1
            print("  == duplicate content, skipped")
            time.sleep(REQUEST_DELAY)
            continue
        _content_hashes.add(chash)

        pages.append({
            "url": canonical,
            "canonicalUrl": canonical,
            "title": title or canonical,
            "description": description,
            "language": language,
            "text": text[:60000],
            "headings": headings,
            "wordCount": len(text.split()),
            "contentHash": chash,
            "crawledAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "lastModified": resp.headers.get("Last-Modified", ""),
            "statusCode": resp.status_code,
            "links": links,
        })
        fetched += 1

        if depth < MAX_DEPTH:
            for link in links:
                if link not in _seen_urls:
                    _seen_urls.add(link)
                    queue.append((link, depth + 1))
        time.sleep(REQUEST_DELAY)

    os.makedirs(os.path.dirname(out_file) or ".", exist_ok=True)
    with open(out_file, "w", encoding="utf-8") as f:
        for pg in pages:
            f.write(json.dumps(pg, ensure_ascii=False) + "\n")
    print(f"\nDone: {len(pages)} pages saved to {out_file} "
          f"({duplicates} duplicates, {failed} failures)")


if __name__ == "__main__":
    seed_file = sys.argv[1] if len(sys.argv) > 1 else "seeds.txt"
    crawl(seed_file, "data/pages.jsonl")
