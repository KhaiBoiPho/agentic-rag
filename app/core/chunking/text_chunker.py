"""Plain text / Markdown chunker — token-based splitting."""

from __future__ import annotations

import re
from itertools import groupby

from app.core.chunking.base import BaseChunker, count_tokens, naive_merge
from app.core.chunking.models import Chunk, ChunkType

_CHUNK_ID_RE = re.compile(r"<!--\s*chunk_id:\s*([\w-]+)\s*-->")


class TextChunker(BaseChunker):
    def chunk(self, filename: str, content: bytes, **kwargs) -> list[Chunk]:
        doc_id = kwargs.get("document_id", "")
        kb_id = kwargs.get("kb_id", "")

        text = content.decode("utf-8", errors="replace")

        if filename.lower().endswith((".md", ".markdown")):
            tagged_sections = self._split_markdown_with_ids(text)
        else:
            tagged_sections = [(None, s) for s in self._split_plain(text)]

        result: list[Chunk] = []
        # Merge within each chunk_id group independently so citations stay
        # anchored to the source .md section instead of blurring across
        # unrelated sections when the token budget spans a boundary.
        for chunk_id, group in groupby(tagged_sections, key=lambda t: t[0]):
            sections = [s for _, s in group]
            merged = naive_merge(
                sections,
                chunk_token_num=self.chunk_token_num,
                delimiter=self.delimiter,
                overlap_percent=self.overlap_percent,
            )
            for t in merged:
                if not t.strip():
                    continue
                result.append(
                    Chunk(
                        content=t,
                        chunk_type=ChunkType.TEXT,
                        document_id=doc_id,
                        kb_id=kb_id,
                        filename=filename,
                        token_count=count_tokens(t),
                        metadata={"chunk_id": chunk_id} if chunk_id else {},
                    )
                )
        return result

    def _split_markdown_with_ids(self, text: str) -> list[tuple[str | None, str]]:
        """Split at each heading, tagging every section with the nearest
        preceding `<!-- chunk_id: ... -->` marker (forward-filled, since
        subsection headings don't repeat the marker of their parent)."""
        parts = re.split(r"(?=^#{1,6}\s)", text, flags=re.MULTILINE)
        tagged: list[tuple[str | None, str]] = []
        current_id: str | None = None
        for part in parts:
            match = _CHUNK_ID_RE.search(part)
            if match:
                current_id = match.group(1)
            cleaned = _CHUNK_ID_RE.sub("", part).strip()
            if cleaned:
                tagged.append((current_id, cleaned))
        return tagged

    def _split_plain(self, text: str) -> list[str]:
        # Split on paragraph boundaries
        paragraphs = re.split(r"\n\s*\n", text)
        return [p.strip() for p in paragraphs if p.strip()]
