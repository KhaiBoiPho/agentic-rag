"""Sparse (BM25) retrieval and dense+sparse fusion, shared by the benchmark
scripts.

Lives here rather than in app/ on purpose: nothing in the running system uses
BM25 yet. `QdrantStore` declares a `sparse` vector and its docstring claims
hybrid search, but `upsert_chunks` only ever writes the dense vector and
`search` only ever queries `using=DENSE_VECTOR` — so the sparse half has never
been populated or read. Measuring it here first means the A/B runs against the
exact same chunk set, with no re-indexing between arms and no change to the
live ingest path before the numbers say it is worth one.

Tokenisation reuses the price repository's normalisation (`_strip_accents` +
`[0-9a-z]+` + stopwords) so the lexical retrieval layer and the SQL matching
layer see the same words — a query that matches lexically in one matches in
the other, instead of the two disagreeing for reasons nobody can inspect. No
off-the-shelf BM25 tokenizer is used: none ship a Vietnamese stopword list,
and their punctuation defaults mangle the product codes this corpus is
actually queried by.

That word tokenizer alone is NOT sufficient here, which is worth spelling out
because it is not obvious. It splits 'LV-ABC-4x95' into ['lv','abc','4x95']
and 'CXV-150' into ['cxv','150']. Under the SQL matcher that is harmless —
every word must match, so a query for 'CXV-500' needs both 'cxv' AND '500' and
correctly finds nothing. BM25 sums per-term contributions instead, so 'cxv'
alone already scores, and a measured smoke test had a 'CXV-500' query rank the
CXV-150 row first.

So each code-shaped run (alphanumerics joined by '-', '.', '/' or '_') is ALSO
emitted whole, in addition to its parts: 'lv-abc-4x95', 'h.series', 'cxv-150',
'60/70'. These compounds are rare, so IDF weights them heavily and an exact
code match outranks a partial one. Purely numeric compounds ('1.140.000') are
kept rather than filtered — the alternative loses '60/70', which B24 depends
on — and cost only index size, since a high-IDF term nobody queries never
fires.

This does not by itself make a 'CXV-500' query return nothing: BM25 still
surfaces the nearest lexical neighbour, and it should. Recognising that the
retrieved row is CXV-150 and refusing is the generation model's job, which the
question set grades separately via `expect_refusal`.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass, field

from app.db.postgres.repositories.material_price_repo import _STOPWORDS, _strip_accents

_MIN_WORD_LEN = 2

_WORD_RE = re.compile(r"[0-9a-z]+")
# A code-shaped run: alphanumeric groups joined by the separators that appear
# inside product codes and specs. Requires at least one separator, so ordinary
# words never match and get double-counted.
_CODE_RE = re.compile(r"[0-9a-z]+(?:[._/-][0-9a-z]+)+")

# k1 controls term-frequency saturation, b the document-length normalisation.
# The Okapi defaults; not tuned, because tuning them on the same 30 questions
# used to report the result would be fitting the benchmark rather than the
# corpus.
K1 = 1.5
B = 0.75

# Reciprocal-rank-fusion constant. 60 is the value from the original RRF paper
# and Qdrant's own default, kept so a later port to Qdrant's native
# FusionQuery(RRF) reproduces these numbers instead of merely resembling them.
RRF_K = 60


def tokenize(text: str) -> list[str]:
    """Accent-stripped, lower-cased word tokens (the same form `_match_words`
    produces for SQL matching), plus each code-shaped run kept whole.

    A code contributes both its parts and itself: 'CXV-150' yields
    ['cxv', '150', 'cxv-150']. The parts keep a partially-worded query
    findable; the whole gives an exact code match a far rarer — hence
    higher-IDF — term to win on."""
    folded = _strip_accents(text).lower()
    words = [
        w
        for w in _WORD_RE.findall(folded)
        if len(w) >= _MIN_WORD_LEN and w not in _STOPWORDS
    ]
    # Mã được CHUẨN HOÁ về dạng đã xoá dấu ngăn, không phải phát thêm bên cạnh
    # dạng nguyên. Cả `cxv-150` lẫn `cxv150` cùng quy về `cxv150`, nên hai cách
    # viết của một mã gặp nhau ở đúng một token hiếm.
    #
    # Vì sao thay chứ không thêm: bản đầu phát CẢ HAI dạng và đo được kết quả
    # xấu — trục gãy mã +4 câu nhưng trục tên nguyên -4, tổng +3/200 nằm trong
    # nhiễu. Token thừa làm độ dài tài liệu tăng, mà BM25 với b=0,75 phạt tài
    # liệu dài; chunk nhiều mã bị phạt nặng nhất, và đó đúng là chunk mà truy
    # vấn tên nguyên cần. Chuẩn hoá giữ nguyên số token nên không có cái giá đó.
    codes = [
        c.replace("-", "").replace(".", "").replace("/", "").replace("_", "")
        for c in _CODE_RE.findall(folded)
    ]
    return words + codes


@dataclass
class BM25Index:
    """Okapi BM25 over a fixed corpus.

    IDF is computed here rather than left to Qdrant's `Modifier.IDF` because
    the harness scores in memory (see bench_agentic.py's module docstring for
    why retrieval is not run through Qdrant). The formula is Qdrant's — the
    non-negative ln(1 + (N - df + 0.5)/(df + 0.5)) variant — so that a later
    production port lands on the same ordering.
    """

    doc_tokens: list[list[str]]
    idf: dict[str, float] = field(default_factory=dict)
    tf: list[Counter] = field(default_factory=list)
    doc_len: list[int] = field(default_factory=list)
    avg_len: float = 0.0

    @classmethod
    def build(cls, texts: list[str]) -> BM25Index:
        doc_tokens = [tokenize(t) for t in texts]
        tf = [Counter(toks) for toks in doc_tokens]
        doc_len = [len(toks) for toks in doc_tokens]
        n = len(doc_tokens)
        avg_len = (sum(doc_len) / n) if n else 0.0

        df: Counter = Counter()
        for counts in tf:
            df.update(counts.keys())
        idf = {
            term: math.log(1 + (n - d + 0.5) / (d + 0.5))
            for term, d in df.items()
        }
        return cls(doc_tokens=doc_tokens, idf=idf, tf=tf, doc_len=doc_len, avg_len=avg_len)

    def scores(self, query: str) -> list[float]:
        q_terms = tokenize(query)
        out = [0.0] * len(self.tf)
        if not q_terms or not self.avg_len:
            return out
        for term in q_terms:
            idf = self.idf.get(term)
            if idf is None:  # term occurs in no document
                continue
            for i, counts in enumerate(self.tf):
                f = counts.get(term)
                if not f:
                    continue
                denom = f + K1 * (1 - B + B * self.doc_len[i] / self.avg_len)
                out[i] += idf * (f * (K1 + 1) / denom)
        return out

    def top(self, query: str, limit: int) -> list[int]:
        scored = self.scores(query)
        ranked = sorted(range(len(scored)), key=lambda i: -scored[i])
        return [i for i in ranked if scored[i] > 0][:limit]


def rrf_fuse(rankings: list[list[int]], limit: int) -> list[int]:
    """Reciprocal rank fusion over several ranked id lists.

    RRF is used rather than a weighted score sum because cosine similarity and
    BM25 are not on a comparable scale — normalising them against each other
    would need a per-query calibration that is itself a tuned parameter.
    """
    points: dict[int, float] = {}
    for ranking in rankings:
        for rank, idx in enumerate(ranking):
            points[idx] = points.get(idx, 0.0) + 1.0 / (RRF_K + rank + 1)
    return sorted(points, key=lambda i: -points[i])[:limit]
