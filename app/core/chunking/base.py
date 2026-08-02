"""Base chunker — token counting + naive merge algorithm (RAGFlow-inspired)."""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import replace

import tiktoken

from app.core.chunking.models import Chunk, ChunkType

_enc = tiktoken.get_encoding("cl100k_base")

# text-embedding-3-small/large both cap input at 8191 tokens (verified
# directly against OpenRouter — the "large" variant has no bigger context,
# it only has larger output dimensions). A single oversized item in a batch
# embeddings request fails the WHOLE batch, which real wide price-list PDFs
# hit easily (one table -> one HTML chunk with no size cap). So instead of
# swapping models (no fix), oversized TABLE chunks are split row-wise —
# see split_oversized_table_chunk() below.
MAX_EMBED_TOKENS = 8000

_TABLE_ROW_RE = re.compile(r"<tr>.*?</tr>", re.DOTALL)


def embed_token_count(chunk: Chunk) -> int:
    """Tokens the embeddings API will actually see for this chunk.

    `Chunk.token_count` counts `content` alone, but what gets embedded is
    `full_content` = context_above + content + context_below (see
    models.py). Guarding on token_count let a 7.900-token table chunk plus
    its 2×128 tokens of context sail past an 8.000 limit and hit the API's
    8.192 ceiling, failing the whole batch — which is exactly what the guard
    exists to prevent."""
    return count_tokens(chunk.full_content)


def split_oversized_table_chunk(chunk: Chunk, max_tokens: int = MAX_EMBED_TOKENS) -> list[Chunk]:
    """Split an over-budget HTML TABLE chunk into several smaller chunks,
    repeating the header row (first <tr>) in each so column context isn't
    lost. Falls back to returning the chunk unsplit if it isn't a
    single-header HTML table (e.g. TEXT chunks, or something naive_merge
    already produced) — callers should still guard against oversized chunks
    reaching the embeddings API in that case.
    """
    if embed_token_count(chunk) <= max_tokens:
        return [chunk]
    if chunk.chunk_type != ChunkType.TABLE:
        return [chunk]

    rows = _TABLE_ROW_RE.findall(chunk.content)
    if len(rows) < 2:
        return [chunk]

    # Every produced chunk keeps the same context_above/context_below, so the
    # row budget has to leave room for them — otherwise the split pieces
    # individually pass the check and the batch still fails at the API.
    context_overhead = embed_token_count(chunk) - chunk.token_count
    max_tokens = max(max_tokens - context_overhead, 1)

    header, body_rows = rows[0], rows[1:]
    header_tokens = count_tokens(header) + count_tokens("<table>\n\n</table>")

    groups: list[list[str]] = []
    current: list[str] = [header]
    current_tokens = header_tokens

    for row in body_rows:
        row_tokens = count_tokens(row)
        if row_tokens > max_tokens - header_tokens:
            # A single row alone exceeds the budget (e.g. one cell has a huge
            # multi-paragraph note) — nothing safe to do but drop it; flush
            # what's accumulated so far first.
            if len(current) > 1:
                groups.append(current)
                current, current_tokens = [header], header_tokens
            continue
        if current_tokens + row_tokens > max_tokens and len(current) > 1:
            groups.append(current)
            current, current_tokens = [header], header_tokens
        current.append(row)
        current_tokens += row_tokens

    if len(current) > 1:
        groups.append(current)

    if not groups:
        return []

    result: list[Chunk] = []
    for rows_group in groups:
        html = "<table>\n" + "\n".join(rows_group) + "\n</table>"
        result.append(replace(chunk, content=html, token_count=count_tokens(html)))
    return result


def count_tokens(text: str) -> int:
    return len(_enc.encode(text, disallowed_special=()))


def naive_merge(
    sections: list[str],
    chunk_token_num: int = 512,
    delimiter: str = "\n!?。；！？",
    overlap_percent: int = 15,
) -> list[str]:
    """Merge text sections into token-bounded chunks with optional overlap.

    Mirrors RAGFlow's naive_merge() logic: accumulates sections until the
    token budget is consumed, then starts a new chunk, prepending the overlap
    portion from the previous chunk.
    """
    return [
        text
        for text, _ in naive_merge_with_origins(
            sections, chunk_token_num, delimiter, overlap_percent
        )
    ]


def naive_merge_with_origins(
    sections: list[str],
    chunk_token_num: int = 512,
    delimiter: str = "\n!?。；！？",
    overlap_percent: int = 15,
) -> list[tuple[str, int]]:
    """naive_merge(), but each chunk is paired with the index of the first
    input section that contributed to it.

    Callers use the origin index to carry per-section metadata (page number,
    most importantly) onto the merged chunk instead of guessing.
    """
    if not sections:
        return []

    chunks: list[str] = [""]
    token_counts: list[int] = [0]
    origins: list[int] = [0]

    overlap_ratio = (100 - overlap_percent) / 100.0

    for idx, sec in enumerate(sections):
        sec = "\n" + sec
        tnum = count_tokens(sec)

        if not chunks[-1] or token_counts[-1] > chunk_token_num * overlap_ratio:
            # start new chunk, carry overlap from previous
            prev = chunks[-1]
            cutoff = int(len(prev) * overlap_ratio)
            overlap_tail = prev[cutoff:]
            chunks.append(overlap_tail + sec)
            token_counts.append(count_tokens(chunks[-1]))
            origins.append(idx)
        else:
            chunks[-1] += sec
            token_counts[-1] += tnum

    return [(c.strip(), o) for c, o in zip(chunks, origins, strict=True) if c.strip()]


def add_table_context(
    chunks: list[dict],
    context_size: int = 128,
) -> list[dict]:
    """Attach surrounding text context to table chunks (RAGFlow _add_context).

    Each table chunk dict has keys: text, chunk_type, index.
    Text chunks before/after are used to fill context_above / context_below.
    """
    if context_size <= 0:
        return chunks

    split_pat = re.compile(r"([。!?？；！\n]|\. )")

    def take_end(text: str, budget: int) -> str:
        sentences = split_pat.split(text)
        acc = ""
        for i in range(len(sentences) - 1, -1, -1):
            acc = sentences[i] + acc
            if count_tokens(acc) >= budget:
                break
        return acc

    def take_start(text: str, budget: int) -> str:
        sentences = split_pat.split(text)
        acc = ""
        for s in sentences:
            acc += s
            if count_tokens(acc) >= budget:
                break
        return acc

    for i, ck in enumerate(chunks):
        if ck["chunk_type"] != ChunkType.TABLE:
            continue

        # gather text above
        above = ""
        remain = context_size
        j = i - 1
        while j >= 0 and remain > 0:
            if chunks[j]["chunk_type"] == ChunkType.TEXT:
                piece = take_end(chunks[j]["text"], remain)
                above = piece + above
                remain -= count_tokens(piece)
            j -= 1
        ck["context_above"] = above

        # gather text below
        below = ""
        remain = context_size
        j = i + 1
        while j < len(chunks) and remain > 0:
            if chunks[j]["chunk_type"] == ChunkType.TEXT:
                piece = take_start(chunks[j]["text"], remain)
                below += piece
                remain -= count_tokens(piece)
            j += 1
        ck["context_below"] = below

    return chunks


class BaseChunker(ABC):
    def __init__(
        self,
        chunk_token_num: int = 512,
        delimiter: str = "\n!?。；！？",
        overlap_percent: int = 15,
        table_context_size: int = 128,
    ) -> None:
        self.chunk_token_num = chunk_token_num
        self.delimiter = delimiter
        self.overlap_percent = overlap_percent
        self.table_context_size = table_context_size

    @abstractmethod
    def chunk(self, filename: str, content: bytes, **kwargs) -> list[Chunk]: ...
