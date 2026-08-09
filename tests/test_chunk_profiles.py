"""Chunking profiles — the per-KB table-heavy toggle.

Covers the three things that can go wrong: the wrong profile gets picked, the
profile gets picked but not applied, or turning it on quietly changes something
it has no business changing (the answering model, price extraction, ordinary
documents).
"""

from __future__ import annotations

import logging

import pytest

from app.core.chunking.base import MAX_EMBED_TOKENS, count_tokens, enforce_chunk_caps
from app.core.chunking.models import Chunk, ChunkType
from app.core.chunking.profiles import (
    STANDARD,
    TABLE_HEAVY,
    ChunkProfile,
    profile_for,
    profile_from_config,
)

_log = logging.getLogger(__name__)


def table_chunk(rows: int, cols: int = 6, cell: str = "1.450.000") -> Chunk:
    """An HTML table chunk big enough to need splitting.

    `token_count` must be set, exactly as every real chunker sets it: the
    splitter derives its context overhead as
    `embed_token_count(chunk) - chunk.token_count`, so leaving it at the 0
    default makes the whole table look like context and the row budget
    collapses to 1 token.
    """
    header = "<tr>" + "".join(f"<td>Cột {i}</td>" for i in range(cols)) + "</tr>"
    body = "".join(
        "<tr>" + "".join(f"<td>{cell}</td>" for _ in range(cols)) + "</tr>" for _ in range(rows)
    )
    content = f"<table>{header}{body}</table>"
    return Chunk(
        document_id="d",
        kb_id="k",
        filename="bang-gia.pdf",
        chunk_type=ChunkType.TABLE,
        content=content,
        page_num=1,
        token_count=count_tokens(content),
    )


class TestProfileSelection:
    def test_flag_off_is_the_unchanged_default(self):
        p = profile_for(False)
        assert p is STANDARD
        assert (p.text_token_num, p.table_context_size, p.table_cap_tokens) == (512, 128, 3000)

    def test_flag_on_is_the_benchmark_configuration(self):
        p = profile_for(True)
        assert p is TABLE_HEAVY
        assert p.table_cap_tokens == 1500
        assert p.table_context_size == 0, "table context must be OFF for table-heavy docs"

    def test_text_budget_is_the_same_in_both(self):
        """Only the TABLE handling differs. Prose merging was never the
        variable under test in either measurement."""
        assert STANDARD.text_token_num == TABLE_HEAVY.text_token_num
        assert STANDARD.overlap_percent == TABLE_HEAVY.overlap_percent


class TestConfigRoundTrip:
    @pytest.mark.parametrize("flag", [False, True])
    def test_profile_survives_the_queue(self, flag):
        """The profile is resolved at upload time and rebuilt in the worker, so
        a job keeps the settings it was queued with even if the KB flag is
        flipped while it sits in RabbitMQ."""
        original = profile_for(flag)
        assert profile_from_config(original.to_config()) == original

    def test_a_job_queued_before_this_feature_falls_back_to_standard(self):
        """Old payloads have no `chunk_profile` key. They must behave exactly
        as they did when they were queued."""
        legacy = {"chunk_token_num": 512, "chunk_overlap_pct": 15, "table_context_size": 128}
        assert profile_from_config(legacy) == STANDARD

    def test_an_empty_config_is_standard(self):
        assert profile_from_config({}) == STANDARD

    def test_an_unknown_profile_name_falls_back_rather_than_crashing(self):
        assert profile_from_config({"chunk_profile": "nonsense"}).name == "standard"

    def test_per_upload_overrides_apply_on_top(self):
        p = profile_from_config({"chunk_profile": "table_heavy", "table_cap_tokens": 900})
        assert p.table_cap_tokens == 900
        assert p.table_context_size == 0  # rest of the profile intact

    def test_zero_table_context_is_an_override_not_a_missing_value(self):
        """`0` disables the mechanism and must not be read as "unset" — the
        classic falsy-default bug, and here it would silently re-enable the
        context the table-heavy profile exists to turn off."""
        assert STANDARD.with_overrides(table_context_size=0).table_context_size == 0


class TestCapIsApplied:
    def test_table_heavy_cuts_the_same_table_into_more_pieces(self):
        big = table_chunk(rows=400)
        standard = enforce_chunk_caps([big], "d", _log, table_cap_tokens=STANDARD.table_cap_tokens)
        heavy = enforce_chunk_caps([big], "d", _log, table_cap_tokens=TABLE_HEAVY.table_cap_tokens)
        assert len(heavy) > len(standard) > 1

    def test_every_piece_respects_its_cap(self):
        from app.core.chunking.base import embed_token_count

        pieces = enforce_chunk_caps([table_chunk(400)], "d", _log, table_cap_tokens=1500)
        assert all(embed_token_count(c) <= 1500 for c in pieces)

    def test_the_default_argument_is_still_3000(self):
        """Callers that don't pass a cap keep the old behaviour — the eval
        scripts and any code path not yet threaded through rely on this."""
        big = table_chunk(rows=400)
        assert enforce_chunk_caps([big], "d", _log) == enforce_chunk_caps(
            [big], "d", _log, table_cap_tokens=3000
        )

    def test_a_small_table_is_untouched_by_either_profile(self):
        """An ordinary document's table sits well under both caps, so the
        toggle is a no-op for it — which is why leaving it off is safe."""
        small = [table_chunk(rows=3)]
        assert enforce_chunk_caps(small, "d", _log, table_cap_tokens=3000) == small
        assert enforce_chunk_caps(small, "d", _log, table_cap_tokens=1500) == small

    def test_the_hard_embedding_cap_is_not_configurable(self):
        """`table_cap_tokens` tunes retrieval quality. MAX_EMBED_TOKENS is the
        API's own limit and must hold regardless of what a profile asks for."""
        from app.core.chunking.base import embed_token_count

        pieces = enforce_chunk_caps([table_chunk(3000)], "d", _log, table_cap_tokens=100_000)
        assert all(embed_token_count(c) <= MAX_EMBED_TOKENS for c in pieces)


class TestProfileIsOnlyAboutChunking:
    def test_a_profile_carries_no_model_setting(self):
        """The study's best end-to-end row also names gpt-oss-20b as the
        generator. That is NOT adopted — generation stays on the production
        model, so a profile must not be able to express a model at all."""
        fields = ChunkProfile.__dataclass_fields__.keys()
        assert not any("model" in f for f in fields)
        assert not any("model" in k for k in TABLE_HEAVY.to_config())

    def test_turning_it_on_does_not_change_the_chat_model(self):
        from app.config import Settings

        assert (
            Settings.model_fields["openrouter_chat_model"].default == "google/gemini-2.5-flash"
        )

    def test_a_profile_carries_no_price_extraction_setting(self):
        """The two KB flags are independent: how a document is cut, versus
        whether price rows are parsed out of it."""
        assert not any("price" in k for k in TABLE_HEAVY.to_config())
