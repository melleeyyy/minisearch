"""MiniSearch — search API (Phase 2).

Flask app exposing:

    GET /health                  — service + index status
    GET /api/search?q=&page=&limit=    — web search (server-side paging)
    GET /api/images?q=&page=&limit=    — image search (own image index)
    GET /api/suggest?q=           — autocomplete
    GET /api/stats                — anonymous aggregate analytics

If a docs/ directory exists, the static frontend is served from it,
so local development runs with a single process.

Security: strict input validation, per-IP rate limiting, safe
HTML-escaped snippets, no personal information collected.
"""
import os
import re
import time

from flask import Flask, jsonify, request, send_from_directory

from .engine import SearchEngine

# ----------------------------- configuration -----------------------------
CACHE_TTL = float(os.environ.get("SEARCH_CACHE_TTL", "60"))     # seconds
RATE_LIMIT = int(os.environ.get("MS_RATE_LIMIT", "60"))          # req/min per IP
MAX_QUERY_LEN = 300
DOCS_DIR = os.environ.get("MS_DOCS_DIR",
                          os.path.join(os.path.dirname(__file__), "..", "docs"))

app = Flask(__name__, static_folder=None)
engine = SearchEngine()

# ----------------------------- in-memory TTL cache -----------------------------
_cache = {}
_CACHE_MAX = 500


def cache_get(key):
    hit = _cache.get(key)
    if not hit:
        return None, False
    expires, value = hit
    if time.monotonic() > expires:
        _cache.pop(key, None)
        return None, False
    return value, True


def cache_set(key, value):
    if len(_cache) >= _CACHE_MAX:
        # drop the ~oldest quarter (simple eviction)
        for k in sorted(_cache, key=lambda k: _cache[k][0])[:_CACHE_MAX // 4]:
            _cache.pop(k, None)
    _cache[key] = (time.monotonic() + CACHE_TTL, value)


# ----------------------------- analytics (anonymous) -----------------------------
try:
    import sqlite3

    _AN_DB = os.environ.get("MS_ANALYTICS_DB", "data/analytics.db")

    def analytics_log(query, result_count, response_ms, page, cache_hit):
        try:
            os.makedirs(os.path.dirname(_AN_DB) or ".", exist_ok=True)
            con = sqlite3.connect(_AN_DB, timeout=2)
            con.execute(
                "CREATE TABLE IF NOT EXISTS analytics ("
                " ts REAL, query TEXT, result_count INTEGER,"
                " response_ms REAL, page INTEGER, cache_hit INTEGER)")
            con.execute("INSERT INTO analytics VALUES (?,?,?,?,?,?)",
                        (time.time(), query[:100], result_count,
                         response_ms, page, 1 if cache_hit else 0))
            con.commit()
            con.close()
        except Exception:
            pass  # analytics must never break search
except Exception:  # pragma: no cover
    def analytics_log(*a, **k):
        pass


def _percentile(values, p):
    if not values:
        return 0
    values = sorted(values)
    i = min(len(values) - 1, int(round(p / 100.0 * (len(values) - 1))))
    return values[i]


def analytics_stats():
    try:
        import sqlite3
        if not os.path.exists(_AN_DB):
            return {}
        con = sqlite3.connect(_AN_DB, timeout=2)
        con.row_factory = sqlite3.Row
        total = con.execute("SELECT COUNT(*) c FROM analytics").fetchone()["c"]
        if not total:
            return {"queries": 0}
        top = [r["query"] for r in con.execute(
            "SELECT query, COUNT(*) c FROM analytics GROUP BY query"
            " ORDER BY c DESC LIMIT 10")]
        zero = [r["query"] for r in con.execute(
            "SELECT DISTINCT query FROM analytics WHERE result_count = 0 LIMIT 10")]
        ms = [r["response_ms"] for r in
              con.execute("SELECT response_ms FROM analytics")]
        hits = con.execute(
            "SELECT COUNT(*) c FROM analytics WHERE cache_hit = 1").fetchone()["c"]
        con.close()
        return {
            "queries": total,
            "topQueries": top,
            "zeroResultQueries": zero,
            "avgResponseMs": round(sum(ms) / len(ms), 1),
            "p50ResponseMs": _percentile(ms, 50),
            "p95ResponseMs": _percentile(ms, 95),
            "cacheHitRate": round(hits / total, 3),
        }
    except Exception:
        return {}


# ----------------------------- rate limiting -----------------------------
_hits = {}


def rate_limited():
    now = time.monotonic()
    window = 60
    ip = (request.remote_addr or "?")[:45]
    t, n = _hits.get(ip, (now, 0))
    if now - t > window:
        t, n = now, 0
    n += 1
    _hits[ip] = (t, n)
    if len(_hits) > 10000:
        _hits.clear()
    return n > RATE_LIMIT


# ----------------------------- helpers -----------------------------
def clean_query(q):
    # strip control characters, clamp length
    q = re.sub(r"[\x00-\x1f\x7f]", "", q or "").strip()
    return q[:MAX_QUERY_LEN]


def int_param(name, default, lo, hi):
    try:
        v = int(request.args.get(name, default))
    except (TypeError, ValueError):
        v = default
    return max(lo, min(hi, v))


def after_request(resp):
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["X-Content-Type-Options"] = "nosniff"
    return resp


app.after_request(after_request)


@app.errorhandler(429)
def too_many(e):
    return jsonify({"error": "rate limit exceeded"}), 429


# ----------------------------- API routes -----------------------------
@app.route("/health")
def health():
    return jsonify({"ok": True, "indexLoaded": engine.ok, **engine.stats()})


@app.route("/api/search")
def api_search():
    if rate_limited():
        return jsonify({"error": "rate limit exceeded"}), 429
    t0 = time.monotonic()
    q = clean_query(request.args.get("q", ""))
    if not q:
        return jsonify({"error": "missing query parameter q"}), 400
    page = int_param("page", 1, 1, 1000)
    limit = int_param("limit", 10, 1, 50)
    key = ("search", q, page, limit)
    data, hit = cache_get(key)
    if data is None:
        data = engine.search(q, page, limit)
        cache_set(key, data)
    ms = round((time.monotonic() - t0) * 1000, 1)
    analytics_log(q, data.get("total", 0), ms, page, hit)
    return jsonify({"query": q, "page": page, "limit": limit,
                    "cache": "hit" if hit else "miss", **data})


@app.route("/api/images")
def api_images():
    if rate_limited():
        return jsonify({"error": "rate limit exceeded"}), 429
    q = clean_query(request.args.get("q", ""))
    if not q:
        return jsonify({"error": "missing query parameter q"}), 400
    page = int_param("page", 1, 1, 1000)
    limit = int_param("limit", 20, 1, 60)
    key = ("images", q, page, limit)
    data, hit = cache_get(key)
    if data is None:
        data = engine.search_images(q, page, limit)
        cache_set(key, data)
    return jsonify({"query": q, "page": page, "limit": limit, **data})


@app.route("/api/suggest")
def api_suggest():
    if rate_limited():
        return jsonify({"error": "rate limit exceeded"}), 429
    q = clean_query(request.args.get("q", ""))
    if not q:
        return jsonify({"suggestions": []})
    return jsonify({"suggestions": engine.suggest(q)})


@app.route("/api/stats")
def api_stats():
    return jsonify({"index": engine.stats(), "analytics": analytics_stats()})


# ----------------------------- static frontend -----------------------------
@app.route("/")
def index():
    return send_from_directory(DOCS_DIR, "index.html")


@app.route("/<path:path>")
def static_files(path):
    if path.startswith("api/") or path == "health":
        return jsonify({"error": "not found"}), 404
    full = os.path.normpath(os.path.join(DOCS_DIR, path))
    if not full.startswith(os.path.abspath(DOCS_DIR)):
        return jsonify({"error": "not found"}), 404
    if not os.path.exists(full):
        return send_from_directory(DOCS_DIR, "index.html")  # SPA-ish fallback
    return send_from_directory(DOCS_DIR, path)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    print(f"MiniSearch API on http://localhost:{port} "
          f"(index loaded: {engine.ok}, {engine.stats()})")
    app.run(host="0.0.0.0", port=port)
