"""OCR fallback for scanned/image-only PDFs.

PdfChunker (PyMuPDF text blocks + pdfplumber tables) returns zero chunks for
pages that are just a scanned image with no text layer — silently, since
that's a legitimate PDF, not a parse error. This module renders each such
page to an image and asks an OpenRouter vision model to transcribe it, then
runs the transcribed text through the normal chunking pipeline so it still
becomes searchable.

Only invoked when normal extraction yields no chunks at all — running a
vision-LLM call per page on every PDF would be slow and unnecessary for the
~8 documents that already have a real text layer.
"""
from __future__ import annotations

import base64
import logging

import fitz  # PyMuPDF

from app.core.chunking.base import naive_merge
from app.core.chunking.models import Chunk, ChunkType
from app.core.llm.openrouter import OpenRouterClient

logger = logging.getLogger(__name__)

_RENDER_DPI = 150


async def ocr_pdf_to_chunks(
    content: bytes,
    filename: str,
    document_id: str,
    kb_id: str,
    chunk_token_num: int = 512,
    overlap_percent: int = 15,
) -> list[Chunk]:
    """Render every page to an image, OCR it via the vision model, and chunk
    the resulting text. Returns [] if OCR finds no readable text either
    (e.g. truly blank pages) — caller keeps the document at 0 chunks then."""
    llm = OpenRouterClient()
    page_texts: list[str] = []

    with fitz.open(stream=content, filetype="pdf") as doc:
        for page_idx, page in enumerate(doc):
            pixmap = page.get_pixmap(dpi=_RENDER_DPI)
            image_b64 = base64.b64encode(pixmap.tobytes("png")).decode("ascii")
            try:
                text = await llm.vision_ocr(image_b64)
            except Exception as exc:
                logger.warning(
                    "OCR failed file=%s page=%d: %s — skipping this page", filename, page_idx, exc
                )
                continue
            if text:
                page_texts.append(text)

    if not page_texts:
        logger.warning("OCR found no readable text in any page of %s", filename)
        return []

    merged = naive_merge(page_texts, chunk_token_num=chunk_token_num, overlap_percent=overlap_percent)
    chunks = [
        Chunk(
            content=text,
            chunk_type=ChunkType.TEXT,
            document_id=document_id,
            kb_id=kb_id,
            filename=filename,
            metadata={"source": "ocr"},
        )
        for text in merged
    ]
    from app.core.chunking.base import count_tokens
    for c in chunks:
        c.token_count = count_tokens(c.content)

    logger.info("OCR fallback: %s -> %d page(s) with text -> %d chunks", filename, len(page_texts), len(chunks))
    return chunks
