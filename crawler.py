"""MiniSearch — a tiny but real search engine.

Crawler: fetches pages starting from seed URLs (seeds.txt),
respects robots.txt, stays on the seed domains, saves pages.jsonl.
"""
import json
import re
import sys
import time
from collections import deque
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup

HEADERS = {"User-Agent": "MiniSearchBot/0.1 (educational demo)"}
MAX_PAGES = int(sys.argv[2]) if len(sys.argv) > 2 else 30   # total pages to fetch
MAX_DEPTH = 1          # how many link-hops from a seed page
DELAY = 1.0            # seconds between requests (be polite!)

TAGS_TO_DROP = ("script", "style", "nav", "footer", "header", "aside", "form")

_robots_cache = {}


def can_fetch(url):
    """Check robots.txt permission for a URL (cached per domain).

    robots.txt is fetched with `requests` + our own User-Agent, because
    many sites block Python's default urllib agent with a 403.
    If robots.txt cannot be fetched at all, we allow the fetch (the
    crawl is small, slow and educational).
    """
    p = urlparse(url)
    base = f"{p.scheme}://{p.netloc}"
    if base not in _robots_cache:
        rp = RobotFileParser()
        try:
            resp = requests.get(base + "/robots.txt", headers=HEADERS, timeout=10)
            if resp.status_code == 200:
                rp.parse(resp.text.splitlines())
            else:  # 404 etc. -> no restrictions
                rp.parse([])
        except Exception:
            rp.parse([])
        _robots_cache[base] = rp
    return _robots_cache[base].can_fetch(HEADERS["User-Agent"], url)


def extract_text(soup):
    for tag in soup(TAGS_TO_DROP):
        tag.decompose()
    text = soup.get_text(" ", strip=True)
    return re.sub(r"\s+", " ", text)


def should_skip(url):
    """Skip non-article pages (Wikipedia namespaces, edit links, media files)."""
    skip_parts = ("action=", "redlink=", "File:", "Template:", "Special:",
                  "Wikipedia:", "Talk:", "Help:", "Category:", "Portal:",
                  "പ്രമാണം:", "ഫലകം:", "സവിശേഷത:", "വിക്കിപീഡിയ:",
                  "സംവാദം:", "വിഭാഗം:", "സഹായം:")
    return any(s.lower() in url.lower() for s in skip_parts)


def extract_links(soup, page_url, allowed_domains):
    out = []
    for a in soup.find_all("a", href=True):
        link = urljoin(page_url, a["href"].split("#")[0])
        p = urlparse(link)
        if p.scheme in ("http", "https") and p.netloc in allowed_domains:
            if not should_skip(link):
                out.append(link)
    return out


def crawl(seed_file, out_file):
    with open(seed_file, encoding="utf-8") as f:
        seeds = [ln.strip() for ln in f if ln.strip() and not ln.startswith("#")]
    allowed = {urlparse(s).netloc for s in seeds}

    queue = deque((s, 0) for s in seeds)
    seen = set(seeds)
    pages = []
    fetched = 0

    print(f"Seeds: {len(seeds)} | max pages: {MAX_PAGES} | max depth: {MAX_DEPTH}")

    while queue and fetched < MAX_PAGES:
        url, depth = queue.popleft()
        if not can_fetch(url):
            print(f"[blocked by robots.txt] {url}")
            continue
        try:
            print(f"[fetch {fetched + 1}] {url}")
            resp = requests.get(url, headers=HEADERS, timeout=15)
            ctype = resp.headers.get("Content-Type", "")
            if resp.status_code != 200 or "text/html" not in ctype:
                continue
            resp.encoding = resp.apparent_encoding or "utf-8"
            soup = BeautifulSoup(resp.text, "html.parser")
        except Exception as e:
            print(f"  !! failed: {e}")
            continue

        title = soup.title.get_text(strip=True) if soup.title else url
        text = extract_text(soup)
        if len(text) > 100:  # skip near-empty pages
            pages.append({"url": url, "title": title, "text": text})
            fetched += 1

        if depth < MAX_DEPTH:
            for link in extract_links(soup, url, allowed):
                if link not in seen:
                    seen.add(link)
                    queue.append((link, depth + 1))
        time.sleep(DELAY)

    with open(out_file, "w", encoding="utf-8") as f:
        for pg in pages:
            f.write(json.dumps(pg, ensure_ascii=False) + "\n")
    print(f"\nDone: {len(pages)} pages saved to {out_file}")


if __name__ == "__main__":
    seed_file = sys.argv[1] if len(sys.argv) > 1 else "seeds.txt"
    crawl(seed_file, "data/pages.jsonl")
