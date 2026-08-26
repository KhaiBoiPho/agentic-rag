"""Price lookup service — the fail-closed contract (spec §6, §12.6-§12.9).

The repository is stubbed so the decision logic is under test, not Postgres.
"""

from __future__ import annotations

import uuid

import pytest

from app.core.pricing.service import (
    PriceStatus,
    canonicalize_material_name,
    lookup_material_record,
)


class _Row:
    """Minimal stand-in for a `material_prices` ORM row."""

    def __init__(
        self, name, region, price, *, unit="tấn", spec=None, size_spec=None, notes=None,
        raw=None, page_num=None,
    ):
        self.id = uuid.uuid4()
        self.document_id = uuid.uuid4()
        self.material_name = name
        self.material_category = "xi măng"
        self.region = region
        self.price_ex_vat = price
        self.unit = unit
        self.spec = spec
        self.size_spec = size_spec
        self.manufacturer = "Vicem"
        self.price_basis = "tai_chan_cong_trinh"
        self.source_type = "official_annex"
        self.price_period = "2026-06"
        self.notes = notes
        self.raw_row_text = raw or f"{name} | {region} | {price}"
        self.page_num = page_num


class FakeRepo:
    """Records every call so "exactly one alias retry" is verifiable."""

    def __init__(self, rows_by_region: dict[str, list[_Row]] | None = None, on_name=None):
        self.rows_by_region = rows_by_region or {}
        self.on_name = on_name or {}
        self.calls: list[dict] = []

    async def lookup(self, *, region=None, material_category=None, material_name=None,
                     manufacturer=None, limit=10):
        self.calls.append({"region": region, "material_name": material_name})
        if material_name in self.on_name:
            rows = self.on_name[material_name]
        else:
            rows = self.rows_by_region.get(region, []) if region else [
                r for rs in self.rows_by_region.values() for r in rs
            ]
        return rows[:limit]


HCM_CEMENT = _Row("Xi măng PCB40 Hà Tiên", "HCM", 1_450_000)
HN_CEMENT = _Row("Xi măng PCB40 Bút Sơn", "HN", 1_380_000)
DN_CEMENT = _Row("Xi măng PCB40 Sông Gianh", "DN", 1_410_000)


class TestRegionIsolation:
    async def test_12_6_same_material_in_three_regions_returns_only_the_one_asked(self):
        repo = FakeRepo({"HCM": [HCM_CEMENT], "HN": [HN_CEMENT], "DN": [DN_CEMENT]})
        res = await lookup_material_record(
            region="HCM", material_name="xi măng PCB40", repo=repo
        )
        assert res.status is PriceStatus.FOUND
        assert [r.region for r in res.records] == ["HCM"]
        assert res.records[0].price == 1_450_000

    async def test_12_7_missing_in_hcm_is_not_found_even_though_hn_and_dn_have_it(self):
        """The rule that the old pipeline broke: no HCM row means NOT_FOUND.
        Not a Hà Nội price, not a Đà Nẵng price, not a RAG number."""
        repo = FakeRepo({"HCM": [], "HN": [HN_CEMENT], "DN": [DN_CEMENT]})
        res = await lookup_material_record(
            region="HCM", material_name="xi măng PCB40", repo=repo
        )
        assert res.status is PriceStatus.NOT_FOUND
        assert res.records == []

    async def test_a_wrong_region_row_slipping_through_is_still_rejected(self):
        """Defence in depth — if the repository ever returns a foreign region,
        the service drops it rather than presenting it."""
        repo = FakeRepo({"HCM": [HN_CEMENT]})  # repo bug: HN row under an HCM query
        res = await lookup_material_record(
            region="HCM", material_name="xi măng PCB40", repo=repo
        )
        assert res.status is PriceStatus.NOT_FOUND


class TestSlots:
    async def test_price_question_without_region_is_missing_slots(self):
        repo = FakeRepo({"HCM": [HCM_CEMENT]})
        res = await lookup_material_record(material_name="xi măng PCB40", repo=repo)
        assert res.status is PriceStatus.MISSING_SLOTS
        assert res.missing_slots == ["region"]
        assert repo.calls == []  # never queried on an unanswerable question

    async def test_no_subject_is_missing_slots(self):
        res = await lookup_material_record(region="HCM", repo=FakeRepo())
        assert res.status is PriceStatus.MISSING_SLOTS
        assert "material_name" in res.missing_slots

    async def test_catalogue_question_does_not_require_a_region(self):
        """"Công ty X bán những loại cát nào" names no province; demanding one
        made the model guess a region and get nothing back."""
        row = _Row("Cát xây tô", "HCM", 250_000, unit="m3")
        repo = FakeRepo(on_name={None: [row]})
        res = await lookup_material_record(
            manufacturer="Trung Đông", requested_fields=["catalog"], repo=repo
        )
        assert res.status is PriceStatus.FOUND


class TestAmbiguity:
    async def test_12_8_distinct_products_with_a_wide_price_spread_are_ambiguous(self):
        repo = FakeRepo(
            {
                "HCM": [
                    _Row("Xi măng PCB40 Hà Tiên", "HCM", 1_450_000),
                    _Row("Xi măng trắng PCW40", "HCM", 3_900_000),
                ]
            }
        )
        res = await lookup_material_record(region="HCM", material_name="xi măng", repo=repo)
        assert res.status is PriceStatus.AMBIGUOUS
        assert len(res.records) == 2  # candidates handed back for the user to pick

    async def test_same_product_family_with_a_tight_spread_is_found(self):
        """Two brands of the same grade are not a question — listing them is a
        complete answer, and forcing a clarification round-trip on every price
        query would be a regression."""
        repo = FakeRepo(
            {
                "HCM": [
                    _Row("Xi măng PCB40 Hà Tiên", "HCM", 1_450_000),
                    _Row("Xi măng PCB40 Nghi Sơn", "HCM", 1_490_000),
                ]
            }
        )
        res = await lookup_material_record(region="HCM", material_name="xi măng PCB40", repo=repo)
        assert res.status is PriceStatus.FOUND

    async def test_catalogue_listing_is_never_ambiguous(self):
        repo = FakeRepo(
            {"HCM": [_Row("Cát xây tô", "HCM", 250_000), _Row("Đá 1x2", "HCM", 480_000)]}
        )
        res = await lookup_material_record(
            region="HCM", manufacturer="Trung Đông", requested_fields=["catalog"], repo=repo
        )
        assert res.status is PriceStatus.FOUND


class TestAliasRetry:
    async def test_12_9_alias_normalizes_then_finds_on_exactly_one_retry(self):
        found = _Row("Xi măng PCB40 Hà Tiên", "HCM", 1_450_000)
        repo = FakeRepo(on_name={"bảng giá xi măng PCB 40": [], "xi măng PCB40": [found]})
        res = await lookup_material_record(
            region="HCM", material_name="bảng giá xi măng PCB 40", repo=repo
        )
        assert res.status is PriceStatus.FOUND
        assert res.alias_retry is True
        assert res.alias_applied == "xi măng PCB40"
        assert len(repo.calls) == 2  # exactly one retry, never a loop

    async def test_still_not_found_after_the_retry_stays_not_found(self):
        repo = FakeRepo(on_name={"xi măng Hoàng Thạch": [], "xi măng Hoàng Thạch ": []})
        res = await lookup_material_record(
            region="HCM", material_name="xi măng Hoàng Thạch", repo=repo
        )
        assert res.status is PriceStatus.NOT_FOUND
        assert len(repo.calls) <= 2

    async def test_no_retry_when_canonicalization_changes_nothing(self):
        repo = FakeRepo(on_name={"xi măng PCB40": []})
        res = await lookup_material_record(
            region="HCM", material_name="xi măng PCB40", repo=repo
        )
        assert res.status is PriceStatus.NOT_FOUND
        assert res.alias_retry is False
        assert len(repo.calls) == 1


class FakeLLM:
    def __init__(self, reply: str):
        self.reply = reply
        self.calls = 0

    async def chat(self, **kwargs):
        self.calls += 1
        return self.reply


class TestLLMFallbackRetry:
    """The third tier — only reached when the raw query AND the deterministic
    alias retry both find nothing. See lookup_material_record's docstring."""

    async def test_llm_extracted_name_finds_the_row_after_rule_extraction_fails(self):
        found = _Row("Thép Hoà Phát D12", "HN", 18_500_000)
        # "material_name" here is the kind of noise a phrase-list miss leaves
        # behind (garbled, unanswerable) — the raw message still holds the
        # real product, which only the LLM path ever sees.
        repo = FakeRepo(on_name={"tôi muốn biết thép xây dựng": [], "thép": [found]})
        llm = FakeLLM('{"material_name": "thép", "code_variants": []}')
        res = await lookup_material_record(
            region="HN",
            material_name="tôi muốn biết thép xây dựng",
            repo=repo,
            llm=llm,
            raw_message="tôi muốn biết giá thép xây dựng ở hà nội",
        )
        assert res.status is PriceStatus.FOUND
        assert res.llm_retry is True
        assert res.llm_applied == "thép"
        assert llm.calls == 1

    async def test_code_variant_finds_an_oddly_split_product_code(self):
        found = _Row("Xi măng PCB40 Hà Tiên", "HCM", 1_450_000)
        repo = FakeRepo(on_name={"pc b40": [], "xi măng pc b40": []})
        repo.on_name["PCB40"] = [found]
        llm = FakeLLM('{"material_name": null, "code_variants": ["PCB40"]}')
        res = await lookup_material_record(
            region="HCM",
            material_name="pc b40",
            repo=repo,
            llm=llm,
            raw_message="giá xi măng pc b40 ở tp hcm",
        )
        assert res.status is PriceStatus.FOUND
        assert res.llm_applied == "PCB40"

    async def test_not_reached_when_the_rule_query_already_found_something(self):
        """The LLM must never be spent on a question the deterministic path
        already answered — cost/latency guard, not just correctness."""
        found = _Row("Xi măng PCB40 Hà Tiên", "HCM", 1_450_000)
        repo = FakeRepo({"HCM": [found]})
        llm = FakeLLM('{"material_name": "should never be used"}')
        res = await lookup_material_record(
            region="HCM", material_name="xi măng PCB40", repo=repo, llm=llm,
            raw_message="giá xi măng PCB40 ở tp hcm",
        )
        assert res.status is PriceStatus.FOUND
        assert res.llm_retry is False
        assert llm.calls == 0

    async def test_not_reached_without_an_llm_or_raw_message(self):
        """Omitting llm/raw_message reproduces pre-fallback behaviour exactly
        — callers that don't opt in are unaffected."""
        repo = FakeRepo(on_name={"xi măng lạ": []})
        res = await lookup_material_record(region="HCM", material_name="xi măng lạ", repo=repo)
        assert res.status is PriceStatus.NOT_FOUND
        assert res.llm_retry is False
        assert res.llm_applied is None

    async def test_still_not_found_when_the_llm_also_finds_nothing(self):
        """Terminal stays terminal — the LLM candidate is tried exactly once,
        never a second guess on top of its own guess."""
        repo = FakeRepo(on_name={"vật liệu lạ": [], "gạch không nung": []})
        llm = FakeLLM('{"material_name": "gạch không nung", "code_variants": []}')
        res = await lookup_material_record(
            region="HCM",
            material_name="vật liệu lạ",
            repo=repo,
            llm=llm,
            raw_message="cho mình hỏi giá vật liệu lạ ở tp hcm",
        )
        assert res.status is PriceStatus.NOT_FOUND
        assert res.llm_retry is False
        assert res.llm_applied is None

    async def test_llm_failure_leaves_result_not_found_not_error(self):
        repo = FakeRepo(on_name={"xi măng lạ": []})
        res = await lookup_material_record(
            region="HCM",
            material_name="xi măng lạ",
            repo=repo,
            llm=BrokenLLM(),
            raw_message="giá xi măng lạ ở tp hcm",
        )
        assert res.status is PriceStatus.NOT_FOUND


class BrokenLLM:
    async def chat(self, **kwargs):
        raise RuntimeError("openrouter down")


class TestCanonicalizer:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("xi măng PCB 40", "xi măng PCB40"),
            ("bảng giá thép D 12", "thép D12"),
            ("giá cát xây tô", "cát xây tô"),
            ("XM PCB40", "xi măng PCB40"),
        ],
    )
    def test_canonical_spellings(self, raw, expected):
        assert canonicalize_material_name(raw) == expected

    def test_returns_none_when_already_canonical(self):
        assert canonicalize_material_name("xi măng PCB40") is None

    def test_never_returns_a_number_or_a_region(self):
        """The resolver maps a name to a name. It has no access to prices."""
        out = canonicalize_material_name("bảng giá xi măng PCB 40 ở Hà Nội") or ""
        assert not any(ch.isdigit() for ch in out.replace("PCB40", ""))


class TestErrors:
    async def test_repository_failure_surfaces_as_error_not_as_no_data(self):
        """An outage must not read as "this product has no price" — that is a
        factual claim about the corpus, and it would be false."""

        class Broken:
            async def lookup(self, **kwargs):
                raise RuntimeError("connection reset")

        res = await lookup_material_record(
            region="HCM", material_name="xi măng PCB40", repo=Broken()
        )
        assert res.status is PriceStatus.ERROR
        assert res.records == []


class TestRecordShape:
    async def test_record_exposes_the_structured_fields_the_ui_needs(self):
        row = _Row(
            "Xi măng PCB40 Hà Tiên",
            "HCM",
            1_450_000,
            spec="bao 50kg, TCVN 6260:2020",
            page_num=42,
        )
        repo = FakeRepo({"HCM": [row]})
        rec = (
            await lookup_material_record(region="HCM", material_name="xi măng PCB40", repo=repo)
        ).records[0]
        assert rec.price == 1_450_000
        assert rec.unit == "tấn"
        assert rec.manufacturer == "Vicem"
        assert rec.price_basis == "tai_chan_cong_trinh"
        assert rec.price_period == "2026-06"
        assert rec.region == "HCM"
        assert rec.document_id and rec.row_id and rec.raw_row_text
        # extracted from the row's own text, not inferred
        assert rec.technical_standard == "TCVN 6260:2020"
        assert rec.page_num == 42

    async def test_page_num_is_none_when_the_row_predates_it(self):
        """A row ingested before migration 0011 (or a repo stub that never
        heard of the column) must not crash the lookup — just show no page,
        same as it did before this feature existed."""
        row = _Row("Cát xây tô", "HCM", 250_000)
        del row.page_num  # simulate an even older/lighter row shape
        repo = FakeRepo({"HCM": [row]})
        rec = (
            await lookup_material_record(region="HCM", material_name="cát", repo=repo)
        ).records[0]
        assert rec.page_num is None


class TestSizeSpecDistinctFromSpec:
    """size_spec ("Quy cách") is a separate column from spec ("Tiêu chuẩn kỹ
    thuật") — see migration 0012. display_name must show BOTH when present,
    and size_spec first: it's what actually distinguishes otherwise-identical
    rows (same material_name, different thickness/size)."""

    async def test_display_name_shows_size_spec_before_spec(self):
        row = _Row(
            "Ống thép mạ kẽm size lớn", "HN", 21_600,
            spec="JIS, AS/NZS, ASTM", size_spec="≥1.00-1.40mm",
        )
        repo = FakeRepo({"HN": [row]})
        rec = (
            await lookup_material_record(region="HN", material_name="ống thép", repo=repo)
        ).records[0]
        assert rec.size_spec == "≥1.00-1.40mm"
        assert rec.spec == "JIS, AS/NZS, ASTM"
        assert rec.display_name == (
            "Ống thép mạ kẽm size lớn (≥1.00-1.40mm, JIS, AS/NZS, ASTM)"
        )

    async def test_display_name_with_only_size_spec(self):
        row = _Row("Ống thép mạ kẽm", "HN", 21_600, size_spec="≥1.00-1.40mm")
        repo = FakeRepo({"HN": [row]})
        rec = (
            await lookup_material_record(region="HN", material_name="ống thép", repo=repo)
        ).records[0]
        assert rec.display_name == "Ống thép mạ kẽm (≥1.00-1.40mm)"

    async def test_size_spec_is_none_when_the_row_predates_it(self):
        row = _Row("Cát xây tô", "HCM", 250_000)
        del row.size_spec
        repo = FakeRepo({"HCM": [row]})
        rec = (
            await lookup_material_record(region="HCM", material_name="cát", repo=repo)
        ).records[0]
        assert rec.size_spec is None

    async def test_technical_standard_is_none_when_the_row_has_none(self):
        repo = FakeRepo({"HCM": [_Row("Cát xây tô", "HCM", 250_000)]})
        rec = (
            await lookup_material_record(region="HCM", material_name="cát", repo=repo)
        ).records[0]
        assert rec.technical_standard is None
