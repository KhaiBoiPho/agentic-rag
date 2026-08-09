"""BM25 sparse encoding, and the guarantee that it matches the benchmark.

The whole justification for hybrid retrieval is a measurement made by
`scripts/bench_retrieval.py`. If the production tokenizer drifts from the one
that produced those numbers, the numbers stop describing the system — so the
parity test here is not a nicety, it is what keeps the claim true.
"""

from __future__ import annotations

import math

import pytest

from app.core.retrieval.sparse import (
    K1,
    B,
    encode_document,
    encode_query,
    term_id,
    tokenize,
)

# Real strings from the corpus and from the question set — codes, Vietnamese
# with diacritics, mixed separators, price-shaped numbers.
CORPUS_STRINGS = [
    "Xi măng bao Bút Sơn Xanh đa dụng PCB40",
    "Cáp vặn xoắn LV-ABC-4x95 - 0,6/1kV",
    "Thép Việt Nhật D12",
    "cáp điện CXV-150",
    "cáp điện CXV150",
    "Nhựa đường 60/70",
    "Giá xi măng PCB40 ở Hồ Chí Minh là bao nhiêu?",
    "Cát xây tô, đơn giá 250.000 đ/m3 tại chân công trình",
    "CÔNG TY CỔ PHẦN VIGLACERA TIÊN SƠN",
    "PC-30 và PC30 và PC 30",
    "",
    "của và có cho tại",  # stopwords only
]


class TestBenchmarkParity:
    def test_tokenizer_matches_the_benchmark_character_for_character(self):
        """`scripts/bench_retrieval.tokenize` is the implementation the +67
        Recall@5 result was measured with. Production duplicates it (app code
        must not import the benchmark harness); this proves the copy is exact.
        """
        from scripts.bench_retrieval import tokenize as bench_tokenize

        for text in CORPUS_STRINGS:
            assert tokenize(text) == bench_tokenize(text), text

    def test_bm25_constants_match_the_benchmark(self):
        from scripts import bench_retrieval as bench

        assert (K1, B) == (bench.K1, bench.B)

    def test_rrf_constant_matches_the_benchmark_and_qdrant(self):
        """RRF k=60 is the paper's value AND Qdrant's own default, which is why
        handing fusion to Qdrant reproduces the benchmark ordering rather than
        merely resembling it."""
        from scripts.bench_retrieval import RRF_K

        assert RRF_K == 60


class TestTokenizer:
    def test_codes_collapse_to_one_rare_token(self):
        """`cxv-150` and `cxv150` must meet at the same token, or the two
        spellings of one product code never match each other — the failure
        `_has_word`'s squashed lane fixes on the SQL side."""
        assert set(tokenize("CXV-150")) & set(tokenize("CXV150"))

    def test_a_code_yields_its_parts_and_the_joined_form(self):
        assert tokenize("CXV-150") == ["cxv", "150", "cxv150"]

    def test_diacritics_are_stripped(self):
        assert tokenize("Xi măng") == tokenize("Xi mang")

    def test_stopwords_and_single_characters_are_dropped(self):
        assert tokenize("của và có cho tại") == []

    def test_ordinary_words_are_not_treated_as_codes(self):
        """`_CODE_RE` needs a separator, so plain words are never emitted
        twice — double-counting would inflate document length and BM25
        penalises long documents."""
        toks = tokenize("xi mang bao")
        assert len(toks) == len(set(toks))

    def test_price_shaped_numbers_survive(self):
        """'1.140.000' collapses to one high-IDF token. Dropping numeric
        compounds would also lose '60/70', which real questions depend on."""
        assert "1140000" in tokenize("đơn giá 1.140.000 đ")
        assert "6070" in tokenize("Nhựa đường 60/70")


class TestTermIds:
    def test_ids_are_stable_across_processes(self):
        """Python's built-in hash() is salted per process. If term ids were not
        stable, a chunk indexed today would not match the same word queried
        tomorrow — and it would fail silently, as an empty result."""
        import subprocess
        import sys

        out = subprocess.run(
            [
                sys.executable,
                "-c",
                "from app.core.retrieval.sparse import term_id; print(term_id('pcb40'))",
            ],
            capture_output=True,
            text=True,
            check=True,
            env={"PYTHONHASHSEED": "12345", "PATH": "/usr/bin:/bin"},
        )
        assert int(out.stdout.strip()) == term_id("pcb40")

    def test_ids_fit_in_a_uint32(self):
        for text in CORPUS_STRINGS:
            for tok in tokenize(text):
                assert 0 <= term_id(tok) < 2**32

    def test_different_tokens_get_different_ids(self):
        toks = {t for s in CORPUS_STRINGS for t in tokenize(s)}
        assert len({term_id(t) for t in toks}) == len(toks)


class TestDocumentEncoding:
    def test_stores_bm25_weights_without_idf(self):
        """IDF is Qdrant's job (Modifier.IDF). What is stored is the saturated,
        length-normalised term frequency — multiply the two and you have
        Okapi BM25."""
        text = "PCB40 PCB40 PCB40 xi mang"
        indices, values = encode_document(text, avg_doc_len=10.0)
        toks = tokenize(text)
        doc_len = len(toks)
        norm = K1 * (1 - B + B * doc_len / 10.0)
        expected = 3 * (K1 + 1) / (3 + norm)  # 'pcb40' occurs 3×
        assert values[indices.index(term_id("pcb40"))] == pytest.approx(expected)

    def test_term_frequency_saturates(self):
        """The point of k1: the 10th occurrence must add far less than the 2nd,
        or one keyword-stuffed chunk dominates every query containing it."""
        _, v2 = encode_document("pcb40 pcb40 " + "x " * 50, avg_doc_len=52)
        _, v10 = encode_document("pcb40 " * 10 + "x " * 42, avg_doc_len=52)
        gain_early = max(v2)
        gain_late = max(v10)
        assert gain_late > gain_early
        assert gain_late < 5 * gain_early, "no saturation — k1 is not being applied"

    def test_longer_documents_are_penalised(self):
        """b=0,75 length normalisation: the same single mention is worth less
        in a long chunk. Without it, a 3.000-token table outranks the precise
        row simply by containing more words."""
        _, short = encode_document("pcb40 xi mang", avg_doc_len=100.0)
        _, long_ = encode_document("pcb40 xi mang " + "khac " * 200, avg_doc_len=100.0)
        i_short = encode_document("pcb40 xi mang", avg_doc_len=100.0)[0].index(term_id("pcb40"))
        i_long = encode_document("pcb40 xi mang " + "khac " * 200, avg_doc_len=100.0)[0].index(
            term_id("pcb40")
        )
        assert long_[i_long] < short[i_short]

    def test_empty_text_encodes_to_nothing(self):
        assert encode_document("", 600.0) == ([], [])
        assert encode_document("của và có", 600.0) == ([], [])

    def test_values_are_finite_and_positive(self):
        for text in CORPUS_STRINGS:
            _, values = encode_document(text, 600.0)
            assert all(math.isfinite(v) and v > 0 for v in values)

    def test_a_zero_average_does_not_divide_by_zero(self):
        """An empty collection would otherwise take the first upsert down."""
        indices, values = encode_document("pcb40", avg_doc_len=0.0)
        assert indices and all(math.isfinite(v) for v in values)


class TestQueryEncoding:
    def test_query_values_are_all_one(self):
        """A query term's weight is its IDF, applied by Qdrant. Repeating a
        word in the question must not double its influence."""
        _, values = encode_query("xi măng PCB40 PCB40 PCB40")
        assert set(values) == {1.0}

    def test_query_terms_are_deduped(self):
        indices, _ = encode_query("pcb40 pcb40 pcb40")
        assert len(indices) == len(set(indices))

    def test_query_and_document_share_term_ids(self):
        """The two sides must agree on ids, or nothing ever matches."""
        d_idx, _ = encode_document("Xi măng bao Bút Sơn Xanh đa dụng PCB40", 600.0)
        q_idx, _ = encode_query("giá xi măng PCB40")
        assert set(q_idx) & set(d_idx)

    def test_a_stopword_only_question_yields_no_query(self):
        """Falls back to dense-only in QdrantStore.search rather than fusing
        against an empty branch."""
        assert encode_query("của và có cho tại") == ([], [])
