"""Unit tests for chunking logic — no external services required."""
import pytest

from app.core.chunking.base import count_tokens, naive_merge


SAMPLE_TEXT = (
    "The quick brown fox jumps over the lazy dog. "
    "She sells seashells by the seashore. "
    "How much wood would a woodchuck chuck if a woodchuck could chuck wood? "
    "Peter Piper picked a peck of pickled peppers. "
    "Red lorry yellow lorry. "
    "Unique New York unique New York you know you need unique New York. "
) * 10  # ~600 tokens when repeated 10 times


def test_count_tokens_non_empty():
    assert count_tokens("Hello world") > 0


def test_count_tokens_empty():
    assert count_tokens("") == 0


def test_naive_merge_respects_budget():
    sections = SAMPLE_TEXT.split(". ")
    chunks = naive_merge(sections, token_budget=512, overlap_pct=0.15)
    for chunk in chunks:
        # Allow up to 1.5x budget for the last partial chunk
        assert count_tokens(chunk) <= 512 * 1.5, f"Chunk exceeds budget: {count_tokens(chunk)}"


def test_naive_merge_non_empty_output():
    sections = ["Hello world.", "This is a test."]
    chunks = naive_merge(sections, token_budget=512, overlap_pct=0.15)
    assert len(chunks) >= 1
    assert all(c.strip() for c in chunks)


def test_naive_merge_empty_input():
    assert naive_merge([], token_budget=512, overlap_pct=0.15) == []
