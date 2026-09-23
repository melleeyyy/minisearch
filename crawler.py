"""MiniSearch — general-purpose web crawler (Phase 2).

Architecture:

    seed URLs + sitemap discovery
              │
              ▼
        URL frontier (deque, normalized + deduplicated)
              │
              ▼
        fetch (robots.txt checked first, per-domain limits,
               retries + exponential backoff, conditional GET)
              │
              ▼
        content parser (title, description, language, headings,
                        main content, links with anchor text, images)
              │
        ┌─────┴──────┐
        ▼            ▼
    pages.jsonl   images embedded per page (indexer splits them)

Everything is configurable via environment variables (see CONFIG below).
The crawler is deliberately conservative: robots.txt is never bypassed,
delays are enforced, private/internal addresses are blocked (SSRF
protection), and total + per-domain page limits are always respected.
"""
import hashlib
import json
import os
import re
import socket
import sys
import time
import xml.etree.ElementTree as ET
from collections import deque
from datetime import datetime, timezone
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup

# ----------------------------- configuration -----------------------------
def _pages_arg():
    for a in sys.argv[2:]:
        if a.isdigit():
            return a
    return "300"


MAX_PAGES = int(os.environ.get("MS_MAX_PAGES", _pages_arg()))
MAX_DEPTH = int(os.environ.get("MS_MAX_DEPTH", "2"))
REQUEST_DELAY = float(os.environ.get("MS_DELAY", "1.0"))
REQUEST_TIMEOUT = float(os.environ.get("MS_TIMEOUT", "15"))
MAX_RETRIES = int(os.environ.get("MS_RETRIES", "3"))
MAX_CONTENT_SIZE = int(os.environ.get("MS_MAX_BYTES", str(3 * 1024 * 1024)))
MAX_PAGES_PER_DOMAIN = int(os.environ.get("MS_MAX_PAGES_PER_DOMAIN", "60"))
BLOCKED_DOMAINS = {d.strip().lower() for d in
                   os.environ.get("MS_BLOCKED_DOMAINS", "").split(",") if d.strip()}
# optional JS rendering for pages with no static content (off by default;
# requires `pip install playwright && playwright install chromium`)
PLAYWRIGHT_FALLBACK = os.environ.get("MS_PLAYWRIGHT", "") == "1"
MAX_SITEMAP_URLS = int(os.environ.get("MS_MAX_SITEMAP_URLS", "300"))

HEADERS = {"User-Agent": "MiniSearchBot/2.0 (educational project)"}

TAGS_TO_DROP = ("script", "style", "nav", "footer", "header", "aside", "form")

# Query parameters that only track users, never identify content.
TRACKING_PARAMS = ("utm_source", "utm_medium", "utm_campaign", "utm_term",
                   "utm_content", "utm_id", "fbclid", "gclid", "msclkid",
                   "mc_cid", "mc_eid", "igshid", "yclid", "_ga", "ref",
                   "referrer", "source")

_robots_cache = {}          # domain -> (RobotFileParser, sitemap urls)
_content_hashes = set()     # sha256 of normalized text (duplicate detection)
_seen_urls = set()          # normalized URLs ever queued
_domain_counts = {}         # domain -> pages fetched (per-domain limit)
_state = {"crawled": 0, "failed": 0, "ignored": 0, "duplicates": 0}


# ---------------------------- SSRF protection ----------------------------
def _ip_is_private(ip):
    import ipaddress
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return True
    return (addr.is_private or addr.is_loopback or addr.is_link_local
            or addr.is_reserved or addr.is_multicast or addr.is_unspecified)


def _proxy_enabled():
    """True when outbound traffic goes through an HTTP(S) proxy.

    Behind a proxy, socket-level DNS checks neither work nor reflect
    what `requests` can reach (the proxy resolves names), so the DNS
    part of the SSRF check is skipped — literal/internal hostname checks
    still apply.
    """
    return bool(os.environ.get("HTTP_PROXY") or os.environ.get("HTTPS_PROXY")
                or os.environ.get("http_proxy") or os.environ.get("https_proxy"))


_dns_cache = {}


def url_is_safe(url):
    """Block internal/private/metadata targets (SSRF protection).

    IP literals are checked directly; hostnames are resolved and every
    address is checked (cached per host). If DNS resolution itself
    fails, the hostname checks above still apply and we allow it (the
    fetch would fail anyway) — this keeps the check robust inside
    sandboxes/proxies.
    """
    import ipaddress
    try:
        p = urlparse(url)
    except ValueError:
        return False
    if p.scheme not in ("http", "https") or not p.netloc:
        return False
    host = p.hostname
    if not host:
        return False
    if (host in ("localhost", "metadata.google.internal")
            or host.endswith(".local") or host.endswith(".internal")):
        return False
    # IP literal (e.g. http://127.0.0.1 or http://[::1])
    try:
        addr = ipaddress.ip_address(host)
        return not (addr.is_private or addr.is_loopback or addr.is_link_local
                    or addr.is_reserved or addr.is_multicast or addr.is_unspecified)
    except ValueError:
        pass
    if _proxy_enabled():
        return True
    if host in _dns_cache:
        return _dns_cache[host]
    try:
        infos = socket.getaddrinfo(host, None, socket.AF_UNSPEC,
                                   socket.SOCK_STREAM)
        ok = all(not _ip_is_private(i[4][0]) for i in infos)
    except (socket.gaierror, UnicodeError):
        ok = True
    _dns_cache[host] = ok
    return ok


# ---------------------------- URL normalization ----------------------------
def normalize_url(raw, base=None):
    """Resolve + normalize a URL. Returns None for non-crawlable targets."""
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


# ------------------------------ robots + sitemaps ------------------------------
def domain_root(url):
    p = urlparse(url)
    return f"{p.scheme}://{p.netloc}"


def get_robots(url):
    """robots.txt for a URL's domain, cached. Never bypassed.

    Returns (RobotFileParser, [sitemap urls]). If robots.txt cannot be
    fetched at all, no restrictions are assumed (the crawl is small,
    slow and educational) — but the crawler still blocks internal
    addresses and enforces delays and limits.
    """
    root = domain_root(url)
    if root not in _robots_cache:
        rp = RobotFileParser()
        sitemaps = []
        try:
            resp = requests.get(root + "/robots.txt", headers=HEADERS,
                                timeout=REQUEST_TIMEOUT)
            if resp.status_code == 200:
                rp.parse(resp.text.splitlines())
                for line in resp.text.splitlines():
                    m = re.match(r"(?i)sitemap\s*:\s*(\S+)", line.strip())
                    if m:
                        sitemaps.append(m.group(1))
            else:
                rp.parse([])
        except Exception:
            rp.parse([])
        _robots_cache[root] = (rp, sitemaps)
    return _robots_cache[root]


def can_fetch(url):
    rp, _ = get_robots(url)
    return rp.can_fetch(HEADERS["User-Agent"], url)


def parse_sitemap(url, depth=0):
    """Best-effort sitemap parsing. Returns a list of page URLs.

    Handles <sitemapindex> (recurses once) and plain <urlset>.
    Downloads are streamed and size-capped so a huge sitemap can never
    stall the crawl. Missing / invalid sitemaps simply return [].
    """
    if depth > 1:
        return []
    try:
        with requests.get(url, headers=HEADERS, timeout=10, stream=True) as resp:
            if resp.status_code != 200:
                return []
            clength = resp.headers.get("Content-Length")
            if clength and clength.isdigit() and int(clength) > MAX_CONTENT_SIZE:
                return []
            chunks, size = [], 0
            for chunk in resp.iter_content(chunk_size=65536):
                size += len(chunk)
                if size > 1024 * 1024:      # 1 MB sitemap cap
                    return []
                chunks.append(chunk)
        root = ET.fromstring(b"".join(chunks))
    except Exception:
        return []
    ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    urls = []
    for loc in root.findall(".//sm:url/sm:loc", ns) or root.findall(".//url/loc"):
        if loc.text:
            urls.append(loc.text.strip())
    if not urls:  # maybe a sitemap index
        for loc in root.findall(".//sm:sitemap/sm:loc", ns) or root.findall(".//sitemap/loc"):
            if loc.text:
                urls.extend(parse_sitemap(loc.text.strip(), depth + 1))
    out = []
    for u in urls[:MAX_SITEMAP_URLS]:
        n = normalize_url(u)
        if n and url_is_safe(n):
            out.append(n)
    return out


def discover_sitemaps(url):
    """robots.txt Sitemap: declarations + the two well-known locations."""
    _, sitemaps = get_robots(url)
    for guess in ("/sitemap.xml", "/sitemap_index.xml"):
        n = normalize_url(domain_root(url) + guess)
        if n:
            sitemaps.append(n)
    seen, out = set(), []
    for s in sitemaps:
        if s and s not in seen:
            seen.add(s)
            out.append(s)
    return out[:3]   # keep the crawl polite


# ------------------------------ fetching ------------------------------
TRANSIENT_STATUS = (429, 500, 502, 503, 504)


def fetch(url, etag="", last_modified=""):
    """GET with retries + exponential backoff + conditional request.

    Permanent 4xx errors are returned (not retried) so the caller can
    record the status; connection errors are retried.
    """
    headers = dict(HEADERS)
    if etag:
        headers["If-None-Match"] = etag
    if last_modified:
        headers["If-Modified-Since"] = last_modified
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT,
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


def detect_language(soup, text):
    """html lang attribute first; character-ratio heuristic as fallback."""
    if soup.html and soup.html.get("lang"):
        return soup.html["lang"][:12]
    if not text:
        return ""
    mal = len(re.findall(r"[\u0D00-\u0D7F]", text))
    dev = len(re.findall(r"[\u0900-\u097F]", text))
    n = max(1, min(len(text), 2000))
    if mal / n > 0.15:
        return "ml"
    if dev / n > 0.15:
        return "hi"
    return "en"


def extract_metadata(soup):
    title = soup.title.get_text(strip=True) if soup.title else ""
    description = ""
    meta = soup.find("meta", attrs={"name": "description"})
    if meta and meta.get("content"):
        description = meta["content"].strip()
    headings = [h.get_text(" ", strip=True) for h in soup.find_all(["h1", "h2", "h3"])]
    return title, description[:400], headings[:10]


def get_canonical(soup, page_url):
    """<link rel=\"canonical\"> if present, normalized."""
    link = soup.find("link", rel=lambda v: v and "canonical" in v)
    if link and link.get("href"):
        return normalize_url(link["href"], base=page_url)
    return None


def extract_links(soup, page_url, allowed_domains):
    """Normalized outgoing links with anchor text and rel.

    Returns [{url, anchor, rel}] — restricted to allowed domains
    (so the crawl stays focused), but ALL extracted links are kept in
    the page record for the link graph (any domain).
    """
    crawl, graph = [], []
    for a in soup.find_all("a", href=True):
        link = normalize_url(a["href"], base=page_url)
        if link is None or not url_is_safe(link):
            continue
        anchor = a.get_text(" ", strip=True)[:200]
        rel = (a.get("rel") or [])
        rel = " ".join(rel) if isinstance(rel, list) else str(rel)
        graph.append({"url": link, "anchor": anchor, "rel": rel[:50]})
        p = urlparse(link)
        if (p.netloc in allowed_domains and p.netloc not in BLOCKED_DOMAINS
                and not should_skip(link) and len(graph) <= 300):
            crawl.append({"url": link, "anchor": anchor, "rel": rel[:50]})
    # dedupe crawl candidates
    seen, out = set(), []
    for l in crawl:
        if l["url"] not in seen:
            seen.add(l["url"])
            out.append(l)
    return out, graph[:300]


def _srcset_best(srcset):
    """Pick the URL of the largest candidate in a srcset attribute."""
    best, best_w = None, -1
    for part in srcset.split(","):
        bits = part.strip().split()
        if not bits:
            continue
        w = 0
        if len(bits) > 1 and bits[1].endswith("w"):
            try:
                w = int(bits[1][:-1])
            except ValueError:
                w = 0
        if w >= best_w:
            best, best_w = bits[0], w
    return best


def extract_images(soup, page_url, title=""):
    """Images from img tags (incl. lazy-loaded), Open Graph, Twitter cards
    and JSON-LD. Returns metadata records, never the image bytes."""
    out, seen = [], set()

    def add(raw_url, alt="", caption="", width=None, height=None, source="img"):
        url = normalize_url(raw_url, base=page_url)
        if (not url or url in seen
                or url.startswith(("data:", "javascript:"))
                or not url_is_safe(url)):
            return
        seen.add(url)
        out.append({
            "imageUrl": url,
            "alt": (alt or "")[:300],
            "title": title[:200],
            "caption": (caption or "")[:300],
            "width": width,
            "height": height,
            "source": source,
        })

    for img in soup.find_all("img"):
        src = (img.get("data-src") or img.get("src") or "").strip()
        if not src and img.get("data-srcset"):
            src = _srcset_best(img["data-srcset"])
        if not src and img.get("srcset"):
            src = _srcset_best(img["srcset"])
        if not src:
            continue
        try:
            w = int(re.sub(r"\D", "", str(img.get("width") or "")) or 0) or None
            h = int(re.sub(r"\D", "", str(img.get("height") or "")) or 0) or None
        except ValueError:
            w = h = None
        if w == 1 or h == 1:      # tracking pixels / spacers
            continue
        add(src, alt=img.get("alt") or "", caption=img.get("title") or "",
            width=w, height=h, source="img")

    og = soup.find("meta", property="og:image")
    if og and og.get("content"):
        add(og["content"], alt=title, source="og")
    tw = soup.find("meta", attrs={"name": "twitter:image"})
    if tw and tw.get("content"):
        add(tw["content"], alt=title, source="twitter")

    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "{}")
        except (json.JSONDecodeError, TypeError):
            continue
        items = data if isinstance(data, list) else [data]
        for item in items:
            if not isinstance(item, dict):
                continue
            img = item.get("image")
            if isinstance(img, str):
                add(img, alt=title, source="jsonld")
            elif isinstance(img, dict) and img.get("url"):
                add(img["url"], alt=title, source="jsonld")

    return out[:25]


def content_hash(text):
    normalized = re.sub(r"\s+", " ", text.strip().lower())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def render_with_playwright(url):
    """Optional JS rendering for pages whose static HTML is empty.

    Returns page HTML or None. Requires playwright; off by default
    (MS_PLAYWRIGHT=1) because rendering every page would be wasteful.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return None
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(user_agent=HEADERS["User-Agent"])
            page.goto(url, timeout=REQUEST_TIMEOUT * 1000)
            page.wait_for_load_state("networkidle", timeout=10000)
            html = page.content()
            browser.close()
            return html
    except Exception:
        return None


# ------------------------------- crawling -------------------------------
def crawl(seed_file, out_file):
    with open(seed_file, encoding="utf-8") as f:
        seeds = [normalize_url(ln.strip()) for ln in f
                 if ln.strip() and not ln.startswith("#")]
    seeds = [s for s in seeds if s and url_is_safe(s)]
    allowed = {urlparse(s).netloc for s in seeds}

    queue = deque()
    for s in seeds:
        if s not in _seen_urls:
            _seen_urls.add(s)
            queue.append((s, 0, "", ""))   # url, depth, etag, last_modified

    pages = []
    domains_done = set()
    print(f"Seeds: {len(seeds)} | domains: {len(allowed)} | "
          f"max pages: {MAX_PAGES} | max depth: {MAX_DEPTH}")

    while queue and _state["crawled"] < MAX_PAGES:
        url, depth, etag, last_modified = queue.popleft()
        domain = urlparse(url).netloc

        if domain in BLOCKED_DOMAINS or domain not in allowed:
            _state["ignored"] += 1
            continue
        if _domain_counts.get(domain, 0) >= MAX_PAGES_PER_DOMAIN:
            _state["ignored"] += 1
            continue
        if not can_fetch(url):
            print(f"[blocked by robots.txt] {url}", flush=True)
            _state["ignored"] += 1
            continue

        # one-time sitemap discovery per domain (adds crawl candidates)
        if domain not in domains_done:
            domains_done.add(domain)
            for sm in discover_sitemaps(url):
                for u in parse_sitemap(sm):
                    if u not in _seen_urls and urlparse(u).netloc in allowed:
                        _seen_urls.add(u)
                        queue.append((u, 0, "", ""))
                if len(queue) > MAX_PAGES * 5:
                    break
            time.sleep(REQUEST_DELAY)

        print(f"[fetch {_state['crawled'] + 1}] {url}", flush=True)
        resp = fetch(url, etag, last_modified)
        if resp is None:
            _state["failed"] += 1
            print("  !! failed after retries")
            time.sleep(REQUEST_DELAY)
            continue
        if resp.status_code == 304:      # not modified since last crawl
            _state["ignored"] += 1
            time.sleep(REQUEST_DELAY)
            continue

        canonical = get_canonical_resp_url(resp) or url
        if canonical in _seen_urls and canonical != url:
            print(f"  == redirect/canonical to already-seen URL, skipped")
            _state["ignored"] += 1
            time.sleep(REQUEST_DELAY)
            continue
        _seen_urls.add(canonical)

        ctype = resp.headers.get("Content-Type", "")
        clength = resp.headers.get("Content-Length")
        if resp.status_code != 200 or "text/html" not in ctype:
            print(f"  -- skipped: status {resp.status_code}, type {ctype[:40]}")
            _state["ignored"] += 1
            time.sleep(REQUEST_DELAY)
            continue
        if clength and clength.isdigit() and int(clength) > MAX_CONTENT_SIZE:
            print(f"  -- skipped: too large ({int(clength) // 1024} KB)")
            _state["ignored"] += 1
            time.sleep(REQUEST_DELAY)
            continue

        try:
            resp.encoding = resp.apparent_encoding or "utf-8"
            soup = BeautifulSoup(resp.text, "html.parser")
            text = extract_text(soup)
        except Exception as e:
            _state["failed"] += 1
            print(f"  !! parse failed: {e}")
            time.sleep(REQUEST_DELAY)
            continue

        # optional dynamic rendering for JS-only pages
        if len(text) < 200 and PLAYWRIGHT_FALLBACK and depth == 0:
            html = render_with_playwright(url)
            if html:
                soup = BeautifulSoup(html, "html.parser")
                text = extract_text(soup)

        title, description, headings = extract_metadata(soup)
        if len(text) <= 100:      # skip near-empty pages
            _state["ignored"] += 1
            time.sleep(REQUEST_DELAY)
            continue

        # <link rel=canonical> wins when it points at a different URL
        link_canonical = get_canonical(soup, canonical)
        if link_canonical and link_canonical != canonical:
            canonical = link_canonical
            if canonical in _seen_urls:
                _state["ignored"] += 1
                time.sleep(REQUEST_DELAY)
                continue
            _seen_urls.add(canonical)

        chash = content_hash(title + " " + text)
        if chash in _content_hashes:
            _state["duplicates"] += 1
            print("  == duplicate content, skipped")
            time.sleep(REQUEST_DELAY)
            continue
        _content_hashes.add(chash)

        crawl_links, graph_links = extract_links(soup, canonical, allowed)
        images = extract_images(soup, canonical, title=title)
        language = detect_language(soup, text)

        pages.append({
            "url": canonical,
            "originalUrl": url if url != canonical else "",
            "canonicalUrl": canonical,
            "title": title or canonical,
            "description": description,
            "language": language,
            "text": text[:60000],
            "headings": headings,
            "wordCount": len(text.split()),
            "contentHash": chash,
            "domain": urlparse(canonical).netloc,
            "statusCode": resp.status_code,
            "crawledAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "lastModified": resp.headers.get("Last-Modified", ""),
            "etag": resp.headers.get("ETag", ""),
            "links": graph_links,
            "images": images,
        })
        _state["crawled"] += 1
        _domain_counts[domain] = _domain_counts.get(domain, 0) + 1

        if depth < MAX_DEPTH:
            for l in crawl_links:
                if l["url"] not in _seen_urls:
                    _seen_urls.add(l["url"])
                    queue.append((l["url"], depth + 1, "", ""))
        time.sleep(REQUEST_DELAY)

    os.makedirs(os.path.dirname(out_file) or ".", exist_ok=True)
    with open(out_file, "w", encoding="utf-8") as f:
        for pg in pages:
            f.write(json.dumps(pg, ensure_ascii=False) + "\n")
    print(f"\nDone: {len(pages)} pages saved to {out_file}")
    print(f"State: {_state}")


def get_canonical_resp_url(resp):
    """Final URL after redirects, normalized."""
    return normalize_url(resp.url)


if __name__ == "__main__":
    seed_file = sys.argv[1] if len(sys.argv) > 1 else "seeds.txt"
    crawl(seed_file, "data/pages.jsonl")
