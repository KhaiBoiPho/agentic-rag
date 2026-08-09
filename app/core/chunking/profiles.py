"""Chunking profiles — two named configurations, chosen per knowledge base.

WHY TWO PROFILES
----------------
The corpus is not one kind of document. It holds two, and a single set of
chunking constants cannot serve both:

  · **Ordinary documents** — knowledge notes, standards, vendor letters. Prose
    with the occasional small or medium table embedded in it. The table is
    part of an argument the surrounding paragraphs are making, so the text
    around it is genuine context, and a table is rarely big enough to need
    cutting at all.

  · **Table-heavy documents** — a published price appendix is a table from
    page 1 to page 699. There is no surrounding prose to borrow context from;
    what sits "above" a table on such a page is a page header or the tail of
    the previous table. Cutting matters here because a single table is
    thousands of rows.

Applying one mechanism to both is what the retrieval study calls out
(§Y.4.3): "Quyết định này tránh áp dụng một cơ chế chung cho hai loại tài liệu
có cấu trúc rất khác nhau."

THE TWO MEASUREMENTS, AND WHY THEY DISAGREED
--------------------------------------------
`STANDARD.table_cap_tokens = 3000` comes from `scripts/eval_chunk_cap.py`,
measured on how many of 242 known CADIVI prices land in a top-5 window. That
measurement is **still valid for what it measured** — documents whose tables
are incidental — and it is why the default is unchanged. (That script has since
been removed from the tree; the numbers it produced are recorded verbatim in
base.py's comment above MAX_TABLE_CHUNK_TOKENS, but it can no longer be re-run
from this repo.)

`TABLE_HEAVY` comes from the retrieval study's own arms
(`scripts/eval_final_500.py`, 500 questions, T1500 vs R1500 at matched
budget): cap 1.500 and `add_table_context` OFF, which is the configuration
that produced the confirmed best end-to-end hybrid result on the price corpus.

Same corpus, opposite conclusions, because they are answering different
questions on different document types. Rather than pick a winner, each is
applied where it was measured.

NOT PART OF A PROFILE: the answering model. The study's best end-to-end row
also names `openai/gpt-oss-20b` as the generator, and that is deliberately NOT
adopted here — generation stays on the production model
(`settings.openrouter_chat_model`, Gemini 2.5 Flash). A profile decides how a
document is cut up, nothing else.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ChunkProfile:
    """How one document gets cut up. Frozen — a profile is an identity, not a
    mutable settings bag; call `with_overrides` to derive a variant."""

    name: str
    # Token budget for PROSE merging (`naive_merge`). Does not apply to tables:
    # a table becomes one chunk and is governed by `table_cap_tokens` instead.
    text_token_num: int
    overlap_percent: int
    # Tokens of surrounding prose glued onto each table chunk before embedding.
    # 0 disables the mechanism entirely.
    table_context_size: int
    # Retrieval cap: the largest table chunk still worth putting in a top-k
    # window. Above this the chunk is split row-wise with its header repeated.
    table_cap_tokens: int

    def with_overrides(
        self,
        text_token_num: int | None = None,
        overlap_percent: int | None = None,
        table_context_size: int | None = None,
        table_cap_tokens: int | None = None,
    ) -> ChunkProfile:
        """Per-upload tuning on top of a profile (see the upload endpoint's
        query params). Keeps the profile name so logs still say which baseline
        was tuned."""
        return ChunkProfile(
            name=self.name,
            text_token_num=text_token_num or self.text_token_num,
            overlap_percent=overlap_percent or self.overlap_percent,
            table_context_size=(
                self.table_context_size if table_context_size is None else table_context_size
            ),
            table_cap_tokens=table_cap_tokens or self.table_cap_tokens,
        )

    def to_config(self) -> dict:
        """Serialized into the RabbitMQ ingest job — the worker rebuilds the
        profile from this, so a job queued before a profile change keeps the
        settings it was queued with."""
        return {
            "chunk_profile": self.name,
            "chunk_token_num": self.text_token_num,
            "chunk_overlap_pct": self.overlap_percent,
            "table_context_size": self.table_context_size,
            "table_cap_tokens": self.table_cap_tokens,
        }


# Prose-first documents with incidental tables. Unchanged from what the system
# has always run — this is the default and stays the default.
STANDARD = ChunkProfile(
    name="standard",
    text_token_num=512,
    overlap_percent=15,
    table_context_size=128,
    table_cap_tokens=3000,
)

# Long table appendices / price books. Tighter cap, and no borrowed context:
# on a page that is entirely table, "surrounding text" is a page header or
# another table's rows, so attaching it adds noise and eats the token budget.
TABLE_HEAVY = ChunkProfile(
    name="table_heavy",
    text_token_num=512,
    overlap_percent=15,
    table_context_size=0,
    table_cap_tokens=1500,
)

PROFILES: dict[str, ChunkProfile] = {p.name: p for p in (STANDARD, TABLE_HEAVY)}


def profile_for(table_heavy: bool) -> ChunkProfile:
    """Pick a profile from the knowledge base's `table_heavy_chunking` flag."""
    return TABLE_HEAVY if table_heavy else STANDARD


def profile_from_config(config: dict) -> ChunkProfile:
    """Rebuild a profile inside the ingest worker.

    Tolerates a job queued before this field existed (and any job whose name
    no longer resolves) by falling back to STANDARD — the behaviour those jobs
    were queued expecting.
    """
    base = PROFILES.get(config.get("chunk_profile", ""), STANDARD)
    return base.with_overrides(
        text_token_num=config.get("chunk_token_num"),
        overlap_percent=config.get("chunk_overlap_pct"),
        table_context_size=config.get("table_context_size"),
        table_cap_tokens=config.get("table_cap_tokens"),
    )
