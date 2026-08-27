"""Request Router — the mandated routing cases (spec §12.1-§12.5).

The rule layer is deterministic and runs with no model call, so these are
plain sync assertions. `route_request` is exercised too, to pin that a
rule-decided route is never handed to the classifier.
"""

from __future__ import annotations

import pytest

from app.core.chat.router import (
    RequestRoute,
    RouteDecision,
    route_by_rules,
    route_request,
)


class TestMandatedCases:
    def test_1_exact_price_question_routes_to_tool_with_region(self):
        d = route_by_rules("Giá xi măng PCB40 ở Hồ Chí Minh?")
        assert d.route is RequestRoute.EXACT_STRUCTURED
        assert d.regions == ["HCM"]
        assert "price" in d.requested_fields

    def test_2_price_plus_vat_is_mixed(self):
        d = route_by_rules("Giá xi măng PCB40 ở Hồ Chí Minh đã gồm VAT chưa?")
        assert d.route is RequestRoute.MIXED
        assert d.regions == ["HCM"]

    def test_3_comparison_question_is_document_rag(self):
        d = route_by_rules("PCB40 khác PCB30 thế nào?")
        assert d.route is RequestRoute.DOCUMENT_RAG

    def test_4_whole_house_cost_is_estimate(self):
        d = route_by_rules("Xây nhà 100 m² ở Hà Nội hết bao nhiêu?")
        assert d.route is RequestRoute.ESTIMATE
        assert d.regions == ["HN"]

    def test_5_price_without_region_clarifies_and_never_guesses(self):
        d = route_by_rules("Giá xi măng?")
        assert d.route is RequestRoute.CLARIFY
        assert "region" in d.missing_slots
        assert d.regions == []  # no region invented


class TestPriceRouting:
    @pytest.mark.parametrize(
        "message",
        [
            "đơn giá thép D12 tại Đà Nẵng",
            "cát xây tô ở TPHCM giá bao nhiêu",
            "báo giá gạch ống Hà Nội",
            "thép Việt Nhật D10 ở Đà Nẵng bao nhiêu tiền",
        ],
    )
    def test_price_questions_reach_the_tool(self, message):
        assert route_by_rules(message).route is RequestRoute.EXACT_STRUCTURED

    def test_structured_field_question_is_exact_structured(self):
        """Rule §4 — a column that exists in material_prices is a lookup."""
        d = route_by_rules("Xi măng PCB40 ở Hà Nội bán theo đơn vị tính nào?")
        assert d.route is RequestRoute.EXACT_STRUCTURED
        assert "unit" in d.requested_fields

    def test_manufacturer_question_is_exact_structured(self):
        d = route_by_rules("Cáp CXV-150 ở TPHCM do nhà sản xuất nào cung cấp?")
        assert d.route is RequestRoute.EXACT_STRUCTURED
        assert "manufacturer" in d.requested_fields

    def test_price_question_without_a_subject_clarifies(self):
        d = route_by_rules("giá bao nhiêu vậy?")
        assert d.route is RequestRoute.CLARIFY
        assert "material_name" in d.missing_slots


class TestDocumentRouting:
    @pytest.mark.parametrize(
        "message",
        [
            "Giá vật liệu công bố đã bao gồm VAT chưa?",
            "Phạm vi áp dụng của bảng giá xi măng này là gì?",
            "Xi măng PCB40 là gì?",
            "Cát xây tô và cát bê tông khác nhau chỗ nào?",
        ],
    )
    def test_narrative_questions_go_to_rag(self, message):
        assert route_by_rules(message).route in (
            RequestRoute.DOCUMENT_RAG,
            RequestRoute.MIXED,
        )

    def test_vat_only_question_is_not_a_price_lookup(self):
        d = route_by_rules("Bảng giá xi măng đã gồm thuế VAT chưa?")
        # It mentions "giá", so it is MIXED at worst — never RAG-suppressed
        # into a bare document answer that quotes a number from a chunk.
        assert d.route in (RequestRoute.MIXED, RequestRoute.DOCUMENT_RAG)


class TestEstimateRouting:
    @pytest.mark.parametrize(
        "message",
        [
            "Dự toán chi phí xây nhà 80m2 ở TPHCM",
            "Xây nhà cấp 4 120 m² ở Đà Nẵng tốn bao nhiêu?",
            "Cần bao nhiêu khối lượng vật liệu cho nhà 100m2 Hà Nội",
        ],
    )
    def test_project_scale_questions_are_estimates(self, message):
        assert route_by_rules(message).route is RequestRoute.ESTIMATE

    def test_unit_price_phrasing_is_not_an_estimate(self):
        """"đơn giá thép xây nhà ở Hà Nội" is a row lookup that happens to use
        a construction verb — routing it to the cost tool would answer a price
        question with a whole-project estimate."""
        d = route_by_rules("đơn giá thép xây nhà ở Hà Nội là bao nhiêu")
        assert d.route is RequestRoute.EXACT_STRUCTURED


class TestClassifierIsSubordinate:
    class _RefusingLLM:
        """Route classifier would send everything to DOCUMENT_RAG if it were
        ever consulted; the slot extractor (llm_extractor.py — always
        consulted for a price-shaped decision now, see _apply_llm_slots) gets
        a harmless non-JSON reply, which fails open to no slots at all.
        Tracks the two kinds of call separately by system-prompt content, so
        a test can assert "the ROUTE classifier was never asked" without that
        being confused by the (now unconditional) slot-refinement call."""

        def __init__(self):
            self.route_calls = 0
            self.other_calls = 0

        async def chat(self, **kwargs):
            system = (kwargs.get("messages") or [{}])[0].get("content", "")
            if "EXACT_STRUCTURED" in system and "DOCUMENT_RAG" in system:
                self.route_calls += 1
                return "DOCUMENT_RAG"
            self.other_calls += 1
            return "not json — fails open in extract_slots_llm"

    async def test_classifier_never_sees_a_clear_price_question(self):
        """The ROUTE classifier specifically must never be consulted for a
        rule-clear price question — the slot extractor still runs (see
        TestLLMSlotRefinement below), that's a separate, always-on pass."""
        llm = self._RefusingLLM()
        d = await route_request("Giá xi măng PCB40 ở Hồ Chí Minh?", llm=llm)
        assert d.route is RequestRoute.EXACT_STRUCTURED
        assert llm.route_calls == 0
        assert d.decided_by == "rule"

    async def test_classifier_handles_what_rules_abstain_on(self):
        llm = self._RefusingLLM()
        d = await route_request("Mình đang phân vân giữa hai phương án móng", llm=llm)
        assert llm.route_calls == 1
        assert d.decided_by == "classifier"

    async def test_no_llm_falls_back_to_general_chat(self):
        d = await route_request("kể chuyện vui đi", llm=None)
        assert d.route is RequestRoute.GENERAL_CHAT

    async def test_classifier_failure_falls_open(self):
        class Broken:
            async def chat(self, **kwargs):
                raise RuntimeError("openrouter down")

        d = await route_request("Mình đang phân vân giữa hai phương án móng", llm=Broken())
        assert d.route is RequestRoute.GENERAL_CHAT


class TestLLMSlotRefinement:
    """Regex phrase-stripping is a fixed word list fighting real phrasing
    variety it can never fully enumerate — measured live: "tìm giá xi măng ở
    sài gòn" extracted material_name "tìm xi măng" ("tìm" was never added to
    the strip list), and a condensed follow-up left "TP" stuck onto the next
    material entirely. The LLM slot pass (_apply_llm_slots) now always runs
    for a price-shaped decision and replaces the regex-derived slots — not
    just when regex found nothing, since regex finding something WRONG is
    exactly the failure mode above."""

    class _SlotLLM:
        def __init__(self, reply: str):
            self.reply = reply
            self.calls = 0

        async def chat(self, **kwargs):
            self.calls += 1
            return self.reply

    async def test_fixes_a_garbled_material_name_the_regex_list_missed(self):
        """"tìm" is not on the phrase-strip list — the measured live bug."""
        llm = self._SlotLLM('{"material_name": "xi măng", "code_variants": []}')
        d = await route_request("tìm giá xi măng ở sài gòn", llm=llm)
        assert d.route is RequestRoute.EXACT_STRUCTURED
        assert d.material_name == "xi măng"
        assert d.decided_by == "llm_slots"
        assert d.regions == ["HCM"]

    async def test_can_turn_clarify_into_exact_structured(self):
        """A message the regex list finds NO subject in at all — LLM slots
        can resolve what rule-only CLARIFY couldn't."""
        llm = self._SlotLLM('{"material_name": "thép D12", "code_variants": []}')
        d = await route_request("giá bao nhiêu vậy ở hà nội", llm=llm)
        assert d.route is RequestRoute.EXACT_STRUCTURED
        assert d.material_name == "thép D12"

    async def test_llm_failure_falls_back_to_the_regex_slots_not_broken(self):
        class Broken:
            async def chat(self, **kwargs):
                raise RuntimeError("openrouter down")

        d = await route_request("Giá xi măng PCB40 ở Hồ Chí Minh?", llm=Broken())
        assert d.route is RequestRoute.EXACT_STRUCTURED
        assert d.material_name  # still the regex-derived slot, not empty
        assert d.decided_by == "rule"

    async def test_non_price_decisions_are_left_alone(self):
        """The slot pass only touches price-shaped decisions — a document
        question must not trigger a wasted extraction call."""
        llm = self._SlotLLM('{"material_name": "should never be used"}')
        d = await route_request("PCB40 khác PCB30 thế nào?", llm=llm)
        assert d.route is RequestRoute.DOCUMENT_RAG
        assert llm.calls == 0


class TestRegionSlots:
    def test_multi_region_comparison_keeps_both(self):
        d = route_by_rules("So sánh giá thép ở Hà Nội và Đà Nẵng")
        assert set(d.regions) == {"HN", "DN"}
        assert d.route is RequestRoute.EXACT_STRUCTURED

    def test_condensed_followup_resolves_its_region(self):
        """"còn Đà Nẵng thì sao?" is condensed upstream (followup.py) before it
        reaches the router — the router sees the standalone rewrite (§12.14)."""
        d = route_by_rules("Giá xi măng PCB40 ở Đà Nẵng là bao nhiêu?")
        assert d.regions == ["DN"]
        assert d.route is RequestRoute.EXACT_STRUCTURED


class TestContract:
    def test_decision_serializes(self):
        d = route_by_rules("Giá xi măng PCB40 ở Hồ Chí Minh?")
        payload = d.model_dump(mode="json")
        assert payload["route"] == "exact_structured"
        assert RouteDecision.model_validate(payload).route is RequestRoute.EXACT_STRUCTURED

    def test_empty_message_abstains(self):
        assert route_by_rules("   ") is None
