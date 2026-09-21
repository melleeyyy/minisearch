"""MiniSearch — indexer.

Reads data/pages.jsonl, builds an inverted index, and scores with BM25.
Saves data/index.json.
"""
import json
import math
import os
import re
from collections import Counter

# \w alone drops Malayalam combining vowel signs (e.g. the േ in കേരളം),
# which would split words into fragments — so we include the full Malayalam block.
TOKEN_RE = re.compile(r"[\w\u0D00-\u0D7F]+", re.UNICODE)

# A few common Malayalam + English stopwords (kept small on purpose)
STOPWORDS = {
    "ഒരു", "ഈ", "ആ", "അത്", "ഇത്", "അവർ", "ന്റെ", "യും", "ആണ്", "ഉണ്ട്",
    "ചെയ്ത", "വേണം", "കൊണ്ട്", "എന്ന", "മറ്റ്", "വളരെ", "പിന്നീട്", "ഇവിടെ",
    "the", "a", "an", "of", "and", "in", "to", "is", "are", "was", "for", "on",
    "with", "as", "by", "that", "it", "from", "or", "at", "be", "this",
}


def tokenize(text):
    tokens = [t.lower() for t in TOKEN_RE.findall(text)]
    return [t for t in tokens if len(t) > 1 and t not in STOPWORDS]


def build(pages_file="data/pages.jsonl", index_file="data/index.json"):
    docs = {}          # url -> {title, length}
    postings = {}       # term -> {url: term_frequency}
    doc_tokens = {}     # url -> token list (kept for snippet search)

    with open(pages_file, encoding="utf-8") as f:
        for line in f:
            pg = json.loads(line)
            toks = tokenize(pg["title"] + " " + pg["text"])
            docs[pg["url"]] = {"title": pg["title"], "length": len(toks)}
            doc_tokens[pg["url"]] = toks
            for term, tf in Counter(toks).items():
                postings.setdefault(term, {})[pg["url"]] = tf

    n_docs = len(docs)
    avgdl = sum(d["length"] for d in docs.values()) / n_docs if n_docs else 0
    df = {t: len(p) for t, p in postings.items()}

    # We store doc_tokens separately so the search UI can make snippets
    index = {
        "N": n_docs,
        "avgdl": avgdl,
        "docs": docs,
        "df": df,
        "postings": postings,
    }
    os.makedirs("data", exist_ok=True)
    with open(index_file, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False)
    with open("data/doctokens.json", "w", encoding="utf-8") as f:
        json.dump(doc_tokens, f, ensure_ascii=False)

    print(f"Indexed {n_docs} pages | vocabulary: {len(postings)} terms | saved {index_file}")
    return index


class BM25:
    """Okapi BM25 ranker over the built index."""

    def __init__(self, index, k1=1.5, b=0.75):
        self.k1, self.b = k1, b
        self.N = index["N"]
        self.avgdl = index["avgdl"] or 1
        self.docs = index["docs"]
        self.df = index["df"]
        self.postings = index["postings"]

    def search(self, query, top_k=10):
        scores = {}
        qtoks = tokenize(query)
        if not qtoks:
            return []
        for term in qtoks:
            plist = self.postings.get(term)
            if not plist:
                continue
            idf = math.log(1 + (self.N - len(plist) + 0.5) / (len(plist) + 0.5))
            for url, tf in plist.items():
                dl = self.docs[url]["length"]
                denom = tf + self.k1 * (1 - self.b + self.b * dl / self.avgdl)
                scores[url] = scores.get(url, 0.0) + idf * (tf * (self.k1 + 1) / denom)
        ranked = sorted(scores.items(), key=lambda x: -x[1])[:top_k]
        return ranked


if __name__ == "__main__":
    idx = build()
    bm = BM25(idx)
    print("Sample ranking check done. Use search.py to query.")
