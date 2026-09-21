"""MiniSearch — web UI (Flask).

Run:  python app.py   then open http://localhost:5000
"""
import json
import re

from flask import Flask, render_template, request

from indexer import BM25, tokenize

app = Flask(__name__)

with open("data/index.json", encoding="utf-8") as f:
    INDEX = json.load(f)
PAGES = {}
with open("data/pages.jsonl", encoding="utf-8") as f:
    for line in f:
        pg = json.loads(line)
        PAGES[pg["url"]] = pg
BM = BM25(INDEX)


def snippet_with_highlight(text, query, width=260):
    toks_q = [t for t in tokenize(query) if t]
    lowered = text.lower()
    pos = -1
    for t in toks_q:
        pos = lowered.find(t)
        if pos >= 0:
            break
    if pos < 0:
        return text[:width]
    start = max(0, pos - width // 3)
    snippet = text[start:start + width]
    if start > 0:
        snippet = "\u2026" + snippet
    if start + width < len(text):
        snippet += "\u2026"
    esc = re.escape
    pattern = re.compile("(" + "|".join(esc(t) for t in toks_q) + ")", re.IGNORECASE)
    return pattern.sub(r"<b>\1</b>", snippet)


@app.route("/")
def home():
    return render_template("index.html", n_docs=INDEX["N"], n_terms=len(INDEX["postings"]))


@app.route("/search")
def search():
    q = request.args.get("q", "").strip()
    results = []
    if q:
        ranked = BM.search(q, top_k=10)
        for url, score in ranked:
            pg = PAGES.get(url, {"title": url, "text": ""})
            results.append({
                "title": pg["title"],
                "url": url,
                "snippet": snippet_with_highlight(pg["text"], q),
                "score": round(score, 2),
            })
    return render_template("results.html", q=q, results=results,
                           n_docs=INDEX["N"], n_terms=len(INDEX["postings"]))


if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=5000)
