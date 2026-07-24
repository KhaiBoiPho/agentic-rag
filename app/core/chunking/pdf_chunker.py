"""PDF chunker — layout-aware text + table extraction.

Strategy (RAGFlow-inspired):
  1. Use PyMuPDF (fitz) for text blocks ordered by page/position.
  2. Use pdfplumber for table extraction per page.
  3. Interleave text sections and table chunks in reading order.
  4. Apply naive_merge to text sections, keep tables as standalone chunks.
  5. Attach table_context_size tokens of surrounding text to each table chunk.
"""

from __future__ import annotations

from io import BytesIO

import fitz  # PyMuPDF
import pdfplumber

from app.core.chunking.base import BaseChunker, add_table_context, count_tokens, naive_merge
from app.core.chunking.models import Chunk, ChunkType


class PdfChunker(BaseChunker):
    def chunk(self, filename: str, content: bytes, **kwargs) -> list[Chunk]:
        doc_id = kwargs.get("document_id", "")
        kb_id = kwargs.get("kb_id", "")

        raw_items = self._extract_ordered(content)
        merged = self._merge_and_contextualize(raw_items)

        chunks: list[Chunk] = []
        for item in merged:
            c = Chunk(
                content=item["text"],
                chunk_type=item["chunk_type"],
                document_id=doc_id,
                kb_id=kb_id,
                filename=filename,
                page_num=item.get("page", 0),
                context_above=item.get("context_above", ""),
                context_below=item.get("context_below", ""),
                token_count=count_tokens(item["text"]),
            )
            chunks.append(c)

        return chunks

    # ─── Internal ────────────────────────────────────────────────────────────

    def _extract_ordered(self, content: bytes) -> list[dict]:
        """Return list of {page, y, text, chunk_type} sorted in reading order."""
        items: list[dict] = []

        with fitz.open(stream=content, filetype="pdf") as pdf_doc:
            text_by_page = self._extract_text_blocks(pdf_doc)

        with pdfplumber.open(BytesIO(content)) as pdf:
            table_by_page = self._extract_tables(pdf)

        all_pages = set(text_by_page.keys()) | set(table_by_page.keys())
        for page_idx in sorted(all_pages):
            page_items: list[dict] = []

            for block in text_by_page.get(page_idx, []):
                page_items.append(
                    {
                        "page": page_idx,
                        "y": block["y"],
                        "text": block["text"],
                        "chunk_type": ChunkType.TEXT,
                    }
                )

            for tbl in table_by_page.get(page_idx, []):
                page_items.append(
                    {
                        "page": page_idx,
                        "y": tbl["y"],
                        "text": tbl["text"],
                        "chunk_type": ChunkType.TABLE,
                    }
                )

            # sort by vertical position within each page
            page_items.sort(key=lambda x: x["y"])
            items.extend(page_items)

        return items

    def _extract_text_blocks(self, doc: fitz.Document) -> dict[int, list[dict]]:
        result: dict[int, list[dict]] = {}
        for page_idx, page in enumerate(doc):
            blocks = page.get_text("blocks")
            result[page_idx] = []
            for b in blocks:
                # b = (x0, y0, x1, y1, text, block_no, block_type)
                text = b[4].strip()
                if not text or b[6] != 0:  # skip image blocks
                    continue
                result[page_idx].append({"y": b[1], "text": text})
        return result

    def _extract_tables(self, pdf: pdfplumber.PDF) -> dict[int, list[dict]]:
        result: dict[int, list[dict]] = {}
        for page_idx, page in enumerate(pdf.pages):
            tables = page.extract_tables()
            if not tables:
                continue
            result[page_idx] = []
            # Approximate Y position from the page's table bboxes
            page_tables = page.find_tables()
            for i, table in enumerate(tables):
                html = self._table_to_html(table)
                y = page_tables[i].bbox[1] if i < len(page_tables) else 0
                result[page_idx].append({"y": y, "text": html})
        return result

    def _table_to_html(self, rows: list[list]) -> str:
        if not rows:
            return ""
        html = ["<table>"]
        for i, row in enumerate(rows):
            tag = "th" if i == 0 else "td"
            cells = "".join(f"<{tag}>{str(cell or '').strip()}</{tag}>" for cell in row)
            html.append(f"<tr>{cells}</tr>")
        html.append("</table>")
        return "\n".join(html)

    def _merge_and_contextualize(self, items: list[dict]) -> list[dict]:
        """Merge text items, keep tables standalone, then add context to tables."""
        # Split into groups: consecutive text items are merged; tables are kept separate.
        result: list[dict] = []
        text_buffer: list[str] = []
        text_meta: dict = {}

        def flush_text():
            if not text_buffer:
                return
            merged = naive_merge(
                text_buffer,
                chunk_token_num=self.chunk_token_num,
                delimiter=self.delimiter,
                overlap_percent=self.overlap_percent,
            )
            for t in merged:
                result.append(
                    {
                        "text": t,
                        "chunk_type": ChunkType.TEXT,
                        "page": text_meta.get("page", 0),
                    }
                )
            text_buffer.clear()

        for item in items:
            if item["chunk_type"] == ChunkType.TEXT:
                text_buffer.append(item["text"])
                text_meta = {"page": item["page"]}
            else:
                flush_text()
                result.append(item)

        flush_text()

        # Add context to table chunks
        add_table_context(result, self.table_context_size)
        return result
