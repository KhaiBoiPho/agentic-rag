"""BM25 sparse vectors — the lexical half of hybrid retrieval.

WHY THIS EXISTS
---------------
Dense retrieval alone loses on exactly the queries this corpus is made of.
Measured over 500 questions (`scripts/eval_final_500.py`), adding BM25 and
fusing with RRF moved Recall@5 on the table-aware arm from 343/500 (68,6%) to
410/500 (82,0%) — +67 questions, the single largest retrieval gain in the whole
study. On price lookups specifically it was 189/252 -> 238/252.

The reason is not subtle: a product is identified by a code. `PCB40`,
`CXV-150`, `D12`, `60/70` are rare literal strings, and an embedding averages
them into a general "cement-ish" direction where a dozen products look alike.
BM25 weights a rare term by its IDF and puts the exact match first.

HOW OKAPI BM25 IS OBTAINED FROM QDRANT
--------------------------------------
Qdrant's `Modifier.IDF` multiplies each stored term value by that term's IDF,
computed across the collection. It does NOT apply BM25's term-frequency
saturation or document-length normalisation. So the split is:

    index time  (here)   value = tf·(k1+1) / (tf + k1·(1 - b + b·len/avg_len))
    query time  (Qdrant) score = Σ IDF(t) · value(t)

which multiplies out to Okapi BM25 exactly. Query vectors therefore carry a
value of 1.0 per term — all the weighting lives in the index and in Qdrant's
IDF, never in the query.

The IDF formula Qdrant uses is `ln(1 + (N - df + 0.5)/(df + 0.5))`, the
non-negative variant — the same one `scripts/bench_retrieval.py` implements in
memory, which is why the benchmark's ordering carries over rather than merely
resembling it.

TOKENIZATION MUST NOT DRIFT
---------------------------
The tokenizer below is character-for-character the one the benchmark measured
with. It is duplicated here rather than imported from `scripts/` (application
code must not depend on the benchmark harness), and `tests/test_sparse.py`
asserts the two produce identical output on a corpus of real strings — a test
that fails loudly if either side is ever edited alone.
"""

from __future__ import annotations

import hashlib
import re
from collections import Counter

from app.db.postgres.repositories.material_price_repo import _STOPWORDS, _strip_accents

# k1 controls term-frequency saturation, b the document-length normalisation.
# The Okapi defaults, deliberately untuned: tuning them on the same questions
# used to report the result would be fitting the benchmark, not the corpus.
K1 = 1.5
B = 0.75

_MIN_WORD_LEN = 2
_WORD_RE = re.compile(r"[0-9a-z]+")
# A code-shaped run: alphanumeric groups joined by the separators that appear
# inside product codes and specs. Requires at least one separator, so ordinary
# words never match and get double-counted.
_CODE_RE = re.compile(r"[0-9a-z]+(?:[._/-][0-9a-z]+)+")


def tokenize(text: str) -> list[str]:
    """Accent-stripped, lower-cased word tokens, plus each code-shaped run
    normalised to its separator-free form.

    `CXV-150` yields `['cxv', '150', 'cxv150']`: the parts keep a
    partially-worded query findable, and the joined form gives an exact code
    match a far rarer — hence higher-IDF — term to win on. Both `cxv-150` and
    `cxv150` collapse to the same rare token, so the two spellings of one code
    meet.

    Normalising rather than ALSO emitting the raw form is a measured choice:
    emitting both scored +4 on broken-code queries but -4 on whole-name
    queries (+3/200 overall, inside the noise) because the extra tokens
    lengthen the document, and BM25 with b=0,75 penalises long documents —
    hitting hardest exactly the code-dense chunks a whole-name query needs.
    """
    folded = _strip_accents(text).lower()
    words = [
        w for w in _WORD_RE.findall(folded) if len(w) >= _MIN_WORD_LEN and w not in _STOPWORDS
    ]
    codes = [
        c.replace("-", "").replace(".", "").replace("/", "").replace("_", "")
        for c in _CODE_RE.findall(folded)
    ]
    return words + codes


def term_id(token: str) -> int:
    """Stable 32-bit id for a token.

    Python's built-in `hash()` is salted per process (PYTHONHASHSEED), so using
    it would give a chunk indexed today a different term id from the same word
    in tomorrow's query — silently retrieving nothing. blake2b is stable across
    processes, machines and releases, which is the only property that matters
    here.
    """
    return int.from_bytes(hashlib.blake2b(token.encode("utf-8"), digest_size=4).digest(), "big")


def encode_document(text: str, avg_doc_len: float) -> tuple[list[int], list[float]]:
    """(indices, values) for a stored chunk — BM25 weights minus IDF.

    Qdrant supplies the IDF at query time (see module docstring), so what is
    stored is the saturated, length-normalised term frequency and nothing else.
    """
    tokens = tokenize(text)
    if not tokens:
        return [], []
    doc_len = len(tokens)
    norm = K1 * (1 - B + B * (doc_len / avg_doc_len)) if avg_doc_len > 0 else K1
    counts = Counter(tokens)
    indices: list[int] = []
    values: list[float] = []
    for token, tf in counts.items():
        indices.append(term_id(token))
        values.append(tf * (K1 + 1) / (tf + norm))
    return indices, values


def encode_query(text: str) -> tuple[list[int], list[float]]:
    """(indices, values) for a query.

    Every value is 1.0. A query term's weight is its IDF, which Qdrant applies;
    repeating a word in the question should not make it count double.
    """
    tokens = tokenize(text)
    if not tokens:
        return [], []
    unique = list(dict.fromkeys(tokens))  # order-stable dedupe, for readable tests
    return [term_id(t) for t in unique], [1.0] * len(unique)
