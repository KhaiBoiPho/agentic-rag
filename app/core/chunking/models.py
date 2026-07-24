"""Chunk data model — shared across all chunkers."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class ChunkType(StrEnum):
    TEXT = "text"
    TABLE = "table"


@dataclass
class Chunk:
    content: str  # text content (table as HTML or plain text)
    chunk_type: ChunkType = ChunkType.TEXT
    document_id: str = ""
    kb_id: str = ""
    filename: str = ""
    page_num: int = 0
    position: list[int] = field(default_factory=list)  # [page, x0, x1, top, bottom]
    context_above: str = ""  # surrounding text for table chunks
    context_below: str = ""
    token_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def full_content(self) -> str:
        """Concatenated context + content used for embedding/indexing."""
        parts = []
        if self.context_above:
            parts.append(self.context_above)
        parts.append(self.content)
        if self.context_below:
            parts.append(self.context_below)
        return "\n".join(parts)
