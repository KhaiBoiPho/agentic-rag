"""Normalized answer-source metadata — the P0 "UI shows the wrong region" bug.

Reproduction of the original defect (see docs/kien-truc-chi-tiet.md §Nguồn):
a question about TP. Hồ Chí Minh rendered source chips labelled Hà Nội / Đà
Nẵng. The chip text was the *filename* (`BangGia-VLXD-DaNang-...pdf`) because
the wire format the chat endpoint emitted carried only
`{chunk_id, document_name, content, score}` — `region`, which Qdrant *does*
store on every price chunk and which `RetrievedChunk` *does* carry, was
dropped at the serialization boundary. The frontend had nothing but the file
name to go on, and a wrong-region chunk retrieved alongside the right one was
indistinguishable from it.

These tests pin the two halves of the fix: region survives serialization, and
a source tagged with a region nobody asked about never reaches the client.
"""

from __future__ import annotations

from app.core.chat.sources import (
    AnswerSource,
    dedupe_sources,
    filter_sources_by_region,
    rag_source,
    region_label,
    source_kinds,
    tool_source,
)
from app.core.retrieval.retriever import RetrievedChunk


def _chunk(chunk_id: str, name: str, region: str, score: float = 0.7) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=chunk_id,
        document_id=f"doc-{region}",
        document_name=name,
        content=f"Bảng giá vật liệu {region}",
        score=score,
        page_num=3,
        chunk_type="table",
        region=region,
        price_period="2026-06",
    )


class TestRegionSurvivesSerialization:
    def test_rag_source_carries_region_from_chunk_metadata(self):
        src = rag_source(_chunk("c1", "BangGia-VLXD-HCM.pdf", "HCM"))
        assert src.region == "HCM"
        assert src.price_period == "2026-06"

    def test_wire_format_exposes_region_and_keeps_legacy_keys(self):
        """Old clients key off document_name/score/chunk_id; those must stay."""
        wire = rag_source(_chunk("c1", "BangGia-VLXD-HCM.pdf", "HCM")).to_wire()
        assert wire["region"] == "HCM"
        assert wire["source_kind"] == "rag"
        # backward compatibility with the pre-fix `sources` array
        assert wire["chunk_id"] == "c1"
        assert wire["document_name"] == "BangGia-VLXD-HCM.pdf"
        assert wire["score"] == 0.7
        assert "content" in wire

    def test_region_is_never_inferred_from_the_filename(self):
        """Rule §8.1 — a Đà Nẵng-looking filename on an untagged chunk stays
        untagged rather than being relabelled from the text of its name."""
        src = rag_source(_chunk("c1", "BangGia-VLXD-DaNang-T06.pdf", ""))
        assert src.region is None
        assert region_label(src.region) == "Không gắn vùng"


class TestRegionFiltering:
    def test_hcm_query_drops_hanoi_and_danang_sources(self):
        """The P0 bug itself: asking about HCM must not ship HN/DN chips."""
        sources = [
            rag_source(_chunk("c1", "BangGia-VLXD-HCM.pdf", "HCM")),
            rag_source(_chunk("c2", "BangGia-VLXD-HaNoi.pdf", "HN")),
            rag_source(_chunk("c3", "BangGia-VLXD-DaNang.pdf", "DN")),
        ]
        kept, dropped = filter_sources_by_region(sources, ["HCM"])
        assert [s.region for s in kept] == ["HCM"]
        assert {s.region for s in dropped} == {"HN", "DN"}

    def test_wrong_region_source_is_dropped_never_relabelled(self):
        """Rule §8.4 — the fix is removal, not a cosmetic region rewrite."""
        sources = [rag_source(_chunk("c2", "BangGia-VLXD-HaNoi.pdf", "HN"))]
        kept, dropped = filter_sources_by_region(sources, ["HCM"])
        assert kept == []
        assert dropped[0].region == "HN"  # untouched

    def test_neutral_untagged_source_survives(self):
        neutral = RetrievedChunk(
            chunk_id="k1",
            document_id="doc-kb",
            document_name="KienThucNen-VatLieuXayDung.docx",
            content="Xi măng PCB40 là xi măng poóc lăng hỗn hợp mác 40.",
            score=0.8,
            page_num=1,
            chunk_type="text",
        )
        kept, dropped = filter_sources_by_region([rag_source(neutral)], ["HCM"])
        assert len(kept) == 1
        assert kept[0].region is None
        assert dropped == []

    def test_untagged_source_quoting_another_regions_price_is_dropped(self):
        """Rule §8.4 — "region=None" is only kept when the chunk is genuinely
        neutral. A legacy chunk with no region tag that quotes a Hà Nội price
        table is not neutral; keeping it re-introduces the bug by the back
        door (the model reads a HN number under an HCM question)."""
        legacy = RetrievedChunk(
            chunk_id="l1",
            document_id="doc-legacy",
            document_name="legacy.pdf",
            content="Bảng giá vật liệu xây dựng Hà Nội — xi măng PCB40: 1.450.000 đ/tấn",
            score=0.6,
            page_num=2,
            chunk_type="table",
        )
        kept, dropped = filter_sources_by_region([rag_source(legacy)], ["HCM"])
        assert kept == []
        assert len(dropped) == 1

    def test_multi_region_comparison_keeps_both_regions(self):
        sources = [
            rag_source(_chunk("c1", "hcm.pdf", "HCM")),
            rag_source(_chunk("c2", "hn.pdf", "HN")),
            rag_source(_chunk("c3", "dn.pdf", "DN")),
        ]
        kept, _ = filter_sources_by_region(sources, ["HN", "HCM"])
        assert {s.region for s in kept} == {"HN", "HCM"}

    def test_no_requested_region_keeps_everything(self):
        sources = [rag_source(_chunk("c1", "hn.pdf", "HN"))]
        kept, dropped = filter_sources_by_region(sources, [])
        assert len(kept) == 1 and dropped == []


class TestDedupe:
    def test_dedupe_does_not_collapse_across_regions(self):
        """Rule §8.7 — region is part of the composite key. Deduping on
        filename alone merged the HN and HCM rows of the same annex into one
        chip, which is how a comparison answer lost a region."""
        rows = [
            tool_source(
                row_id="1", document_id="d1", filename="annex.pdf",
                region="HN", price_period="2026-06",
            ),
            tool_source(
                row_id="2", document_id="d1", filename="annex.pdf",
                region="HCM", price_period="2026-06",
            ),
        ]
        assert len(dedupe_sources(rows)) == 2

    def test_identical_sources_collapse(self):
        a = tool_source(row_id="1", document_id="d1", filename="annex.pdf", region="HN")
        b = tool_source(row_id="1", document_id="d1", filename="annex.pdf", region="HN")
        assert len(dedupe_sources([a, b])) == 1


class TestBadgeKinds:
    def test_tool_only(self):
        assert source_kinds([tool_source(row_id="1", region="HCM")]) == {"tool"}

    def test_tool_plus_rag(self):
        mixed = [
            tool_source(row_id="1", region="HCM"),
            rag_source(_chunk("c1", "hcm.pdf", "HCM")),
        ]
        assert source_kinds(mixed) == {"tool", "rag"}

    def test_empty(self):
        assert source_kinds([]) == set()


class TestSchema:
    def test_authority_and_use_are_explicit(self):
        t = tool_source(row_id="1", region="HCM")
        assert (t.source_kind, t.authority, t.used_for) == ("tool", "authoritative", "price")
        r = rag_source(_chunk("c1", "hcm.pdf", "HCM"))
        assert (r.source_kind, r.authority, r.used_for) == ("rag", "supporting", "explanation")

    def test_from_wire_roundtrip_preserves_region(self):
        """Reloading a persisted conversation must not lose the region
        (rule §8.9) — history is stored as the wire dicts."""
        original = rag_source(_chunk("c1", "hcm.pdf", "HCM"))
        assert AnswerSource.from_wire(original.to_wire()).region == "HCM"

    def test_from_wire_tolerates_legacy_rows(self):
        """Conversations persisted before the fix have no region at all — they
        must read back as "Không gắn vùng", not be back-filled with a guess."""
        legacy = {"chunk_id": "c9", "document_name": "old.pdf", "content": "…", "score": 0.42}
        src = AnswerSource.from_wire(legacy)
        assert src.region is None
        assert src.source_kind == "rag"
        assert src.score == 0.42
