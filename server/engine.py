"""MiniSearch — search engine core (Phase 2, server side).

Loads the SQLite database built by indexer.py into memory once, then
answers queries with:

    BM25 (body)
    + title boost (exact > partial)
    + heading boost
    + URL boost
    + exact-phrase boost
    + authority boost (in-link count — a simple PageRank-like signal)
    + language relevance (query script -> matching pages)

All ranking weights are configurable (RANK + MS_RANK_* env overrides).
The engine is storage-agnostic from the caller's point of view: it
exposes search() / search_images() / suggest() and knows nothing about
HTTP.
"""
import json
import math
import os
import re
import sqlite3
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from indexer import tokenize  # noqa: E402  (shared tokenization, Malayalam-safe)

DB_PATH = os.environ.get("MS_DB", "data/minisearch.db")

K1, B = 1.5, 0.75

# Ranking weights — starting points, tune through benchmarking.
RANK = {
    "title_exact": float(os.environ.get("MS_RANK_TITLE_EXACT", 10)),
    "title_partial": float(os.environ.get("MS_RANK_TITLE_PARTIAL", 5)),
    "heading": float(os.environ.get("MS_RANK_HEADING", 4)),
    "url": float(os.environ.get("MS_RANK_URL", 3)),
    "phrase": float(os.environ.get("MS_RANK_PHRASE", 8)),
    "authority": float(os.environ.get("MS_RANK_AUTHORITY", 0.6)),   # per in-link
    "language": float(os.environ.get("MS_RANK_LANGUAGE", 2)),
}

PHRASE_QUOTES = re.compile("[\u201c\u201d\u00ab\u00bb]")


def parse_query(q):
    """Split a query into quoted phrases + plain terms."""
    qq = PHRASE_QUOTES.sub('"', q)
    phrases = []

    def _grab(m):
        if m.group(1).strip():
            phrases.append(m.group(1).strip())
        return " "

    rest = re.sub(r'"([^"]+)"', _grab, qq)
    return phrases, tokenize(rest)


def detect_script(q):
    """'ml', 'en' or '' — used for the language-relevance signal."""
    if re.search(r"[\u0D00-\u0D7F]", q):
        return "ml"
    if re.search(r"[A-Za-z]", q):
        return "en"
    return ""


class SearchEngine:
    """In-memory search engine over the SQLite corpus."""

    def __init__(self, db_path=None):
        self.db_path = db_path or DB_PATH
        self.ok = False
        self.N = 0
        self.avgdl = 1.0
        self.docs = []            # index -> row
        self.by_url = {}
        self.postings = {}        # term -> {doc_index: tf}
        self.images = []
        self.image_terms = []     # image_index -> [terms]
        self.inlinks = {}         # url -> count
        self.vocab = []           # terms sorted by df desc
        self._load()

    # ------------------------- loading -------------------------
    def _load(self):
        if not os.path.exists(self.db_path):
            return
        con = sqlite3.connect(self.db_path)
        con.row_factory = sqlite3.Row
        try:
            rows = con.execute(
                "SELECT id, url, title, description, language, text, headings,"
                " word_count, domain, crawled_at, length FROM pages").fetchall()
            self.docs = [dict(r) for r in rows]
            self.by_url = {d["url"]: i for i, d in enumerate(self.docs)}
            self.N = len(self.docs)
            self.avgdl = (sum(d["length"] for d in self.docs) / self.N) if self.N else 1.0

            # postings store raw page ids -> map them to row indexes
            id_to_idx = {d["id"]: i for i, d in enumerate(self.docs)}
            self.postings = {}
            for term, doc_id, tf in con.execute(
                    "SELECT term, doc_id, tf FROM postings"):
                idx = id_to_idx.get(doc_id)
                if idx is not None:
                    self.postings.setdefault(term, {})[idx] = tf
            self.vocab = sorted(self.postings.keys(),
                                key=lambda t: -len(self.postings[t]))

            for _source_id, target in con.execute(
                    "SELECT source_id, target_url FROM links"):
                self.inlinks[target] = self.inlinks.get(target, 0) + 1

            imgs = con.execute(
                "SELECT image_url, source_url, domain, alt, title, caption,"
                " width, height, mime, source FROM images").fetchall()
            self.images = [dict(r) for r in imgs]
            # searchable text per image: alt + title + caption + domain + source page title
            url_to_title = {d["url"]: d["title"] for d in self.docs}
            self.image_terms = []
            for im in self.images:
                text = " ".join([im.get("alt") or "", im.get("title") or "",
                                 im.get("caption") or "", im.get("domain") or "",
                                 url_to_title.get(im.get("source_url"), "")])
                self.image_terms.append(tokenize(text))
            self.ok = True
        finally:
            con.close()

    # ------------------------- helpers -------------------------
    def _snippet(self, text, terms, phrases, width=240):
        """Densest window around query terms, safely highlighted."""
        lower = (text or "").lower()
        needles = [t for t in [x.lower() for x in terms + phrases] if len(t) > 1]
        positions = []
        for n in needles:
            i = lower.find(n)
            while i != -1 and len(positions) < 600:
                positions.append(i)
                i = lower.find(n, i + 1)
        start = 0
        if positions:
            positions.sort()
            best_start, best_count, j = positions[0], 0, 0
            for i in range(len(positions)):
                while positions[i] - positions[j] > 150:
                    j += 1
                if i - j + 1 > best_count:
                    best_count, best_start = i - j + 1, positions[j]
            start = max(0, best_start - 30)
        snip = (text or "")[start:start + width]
        if start > 0:
            snip = "…" + snip
        if start + width < len(text or ""):
            snip += "…"
        import html
        esc = html.escape(snip, quote=False)
        if not needles:
            return esc
        # highlight safely: both snippet and needles are HTML-escaped,
        # so the regex can never inject markup
        pat = re.compile("(" + "|".join(
            re.escape(html.escape(n, quote=False)) for n in needles) + ")",
            re.IGNORECASE)
        return pat.sub(r"<b>\1</b>", esc)

    def _authority(self, url):
        return min(self.inlinks.get(url, 0), 20)

    # ------------------------- web search -------------------------
    def search(self, query, page=1, limit=10):
        """Server-side paging: returns {total, results, did_you_mean}."""
        phrases, terms = parse_query(query)
        if not phrases and not terms:
            return {"total": 0, "results": [], "did_you_mean": None}

        scores = {}
        # 1) BM25 body scoring
        for term in set(terms):
            plist = self.postings.get(term)
            if not plist:
                continue
            n = len(plist)
            idf = math.log(1 + (self.N - n + 0.5) / (n + 0.5))
            for idx, tf in plist.items():
                dl = self.docs[idx]["length"] or 1
                denom = tf + K1 * (1 - B + B * dl / self.avgdl)
                scores[idx] = scores.get(idx, 0.0) + idf * (tf * (K1 + 1) / denom)

        # 2) exact-phrase containment (+boost)
        phrase_hits = set()
        for ph in phrases:
            lph = ph.lower()
            for idx, d in enumerate(self.docs):
                if lph in (d["text"] or "").lower():
                    phrase_hits.add(idx)
        for idx in phrase_hits:
            scores[idx] = scores.get(idx, 0.0) + RANK["phrase"]

        # 3) phrase-only query -> only pages containing the phrase
        if not terms and phrases:
            scores = {i: s for i, s in scores.items() if i in phrase_hits}

        if not scores:
            dym = self._did_you_mean(terms)
            return {"total": 0, "results": [], "did_you_mean": dym}

        # 4) field boosts + authority + language
        qscript = detect_script(query)
        for idx in scores:
            d = self.docs[idx]
            title = (d["title"] or "").lower()
            headings = " ".join(json.loads(d["headings"] or "[]")).lower()
            url_l = (d["url"] or "").lower()
            s = scores[idx]
            for t in set(terms):
                if title == t:
                    s += RANK["title_exact"]
                elif t in title:
                    s += RANK["title_partial"]
                if t in headings:
                    s += RANK["heading"]
                if t in url_l:
                    s += RANK["url"]
            s += RANK["authority"] * self._authority(d["url"])
            if qscript and (d["language"] or "").startswith(qscript):
                s += RANK["language"]
            scores[idx] = s

        ranked = sorted(scores.items(), key=lambda x: (-x[1], self.docs[x[0]]["url"]))
        total = len(ranked)
        start = (page - 1) * limit
        page_items = ranked[start:start + limit]

        results = []
        for idx, score in page_items:
            d = self.docs[idx]
            results.append({
                "title": d["title"] or d["url"],
                "url": d["url"],
                "displayUrl": (d["url"][:70] + "…") if len(d["url"]) > 70 else d["url"],
                "snippet": self._snippet(d["text"], terms, phrases),
                "score": round(score, 4),
                "domain": d["domain"],
                "language": d["language"],
                "crawledAt": d["crawled_at"],
            })
        return {"total": total, "results": results,
                "did_you_mean": None if total else self._did_you_mean(terms)}

    # ------------------------- typo tolerance -------------------------
    @staticmethod
    def _levenshtein(a, b, maxd):
        if abs(len(a) - len(b)) > maxd:
            return maxd + 1
        v0 = list(range(len(b) + 1))
        for i, ca in enumerate(a, 1):
            v1 = [i]
            row_min = i
            for j, cb in enumerate(b, 1):
                v1.append(min(v0[j] + 1, v1[j - 1] + 1, v0[j - 1] + (ca != cb)))
                row_min = min(row_min, v1[-1])
            if row_min > maxd:
                return maxd + 1
            v0 = v1
        return v0[-1]

    def _did_you_mean(self, terms):
        """Correct unknown terms against the vocabulary (bounded distance)."""
        if not self.vocab:
            return None
        corrected = list(terms)
        changed = False
        for i, t in enumerate(terms):
            if self.postings.get(t):
                continue
            best, best_d = None, 3
            for cand in self.vocab:
                if abs(len(cand) - len(t)) > 2:
                    continue
                d = self._levenshtein(t, cand, 2)
                if d < best_d:
                    best, best_d = cand, d
            if best and best_d <= 2:
                corrected[i] = best
                changed = True
        return " ".join(corrected) if changed else None

    # ------------------------- image search -------------------------
    def search_images(self, query, page=1, limit=20):
        terms = tokenize(query)
        if not terms or not self.images:
            return {"total": 0, "results": []}
        scores = {}
        for i, it in enumerate(self.image_terms):
            hits = 0
            for t in set(terms):
                if t in it:
                    hits += 1
            if hits:
                # all-term matches rank above partial matches
                scores[i] = hits * 2 + (hits == len(set(terms)))
        ranked = sorted(scores.items(), key=lambda x: (-x[1], self.images[x[0]]["image_url"]))
        total = len(ranked)
        start = (page - 1) * limit
        out = []
        for i, _ in ranked[start:start + limit]:
            im = dict(self.images[i])
            out.append({"imageUrl": im["image_url"], "sourcePageUrl": im["source_url"],
                        "domain": im["domain"], "alt": im.get("alt", ""),
                        "title": im.get("title", ""), "width": im.get("width"),
                        "height": im.get("height")})
        return {"total": total, "results": out}

    # ------------------------- autocomplete -------------------------
    def suggest(self, prefix, max_items=8):
        v = prefix.strip().lower()
        if not v:
            return []
        parts = v.split()
        last = parts[-1]
        base = v[:len(v) - len(last)]
        seen, out = set(), []
        # 1) titles beginning with the typed text
        if len(parts) == 1:
            for d in self.docs:
                if len(out) >= 4:
                    break
                tl = (d["title"] or "").lower()
                if tl.startswith(v) and tl not in seen:
                    seen.add(tl)
                    out.append(d["title"])
        # 2) vocabulary completions of the last word (most frequent first)
        for term in self.vocab:
            if len(out) >= max_items:
                break
            if term.startswith(last) and term != last and term not in seen:
                seen.add(term)
                out.append(base + term)
        return out[:max_items]

    # ------------------------- stats -------------------------
    def stats(self):
        return {"pages": self.N, "images": len(self.images),
                "terms": len(self.postings), "linkEdges": sum(self.inlinks.values())}
