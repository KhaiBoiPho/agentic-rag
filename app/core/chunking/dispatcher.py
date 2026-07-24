"""Dispatcher — routes file to the correct chunker based on extension."""
from __future__ import annotations

import re

from app.core.chunking.base import BaseChunker
from app.core.chunking.docx_chunker import DocxChunker
from app.core.chunking.models import Chunk
from app.core.chunking.pdf_chunker import PdfChunker
from app.core.chunking.text_chunker import TextChunker


class ChunkDispatcher:
    def __init__(
        self,
        chunk_token_num: int = 512,
        delimiter: str = "\n!?。；！？",
        overlap_percent: int = 15,
        table_context_size: int = 128,
    ) -> None:
        kwargs = dict(
            chunk_token_num=chunk_token_num,
            delimiter=delimiter,
            overlap_percent=overlap_percent,
            table_context_size=table_context_size,
        )
        self._chunkers: dict[str, BaseChunker] = {
            "pdf":  PdfChunker(**kwargs),
            "docx": DocxChunker(**kwargs),
            "doc":  DocxChunker(**kwargs),
            "txt":  TextChunker(**kwargs),
            "md":   TextChunker(**kwargs),
            "markdown": TextChunker(**kwargs),
        }

    def chunk(self, filename: str, content: bytes, **kwargs) -> list[Chunk]:
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        chunker = self._chunkers.get(ext)
        if not chunker:
            raise ValueError(f"Unsupported file type: .{ext}")
        return chunker.chunk(filename, content, **kwargs)
