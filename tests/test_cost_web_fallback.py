"""Web price fallback gating (spec §10, §12.28-§12.29).

The fallback code itself is untouched — only the DEFAULT of the gate changed:
it used to be closed by default (missing DB price -> "missing", total
withheld) and is now open by default (missing DB price -> web search),
because real DB gaps exist for some region/material combinations (e.g. gạch
xây ở HCM has no "viên"-unit rows at all) and always reporting those as
"missing" made the estimate unusable there. These tests now pin that the gate
is OPEN by default, that `allow_web_fallback=False` still restores the old
fail-closed behaviour for a caller that wants it, and that an opted-in web
price is still labelled unverified rather than blended into the
published-price total.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

import app.core.mcp.tools.cost_tool as cost_tool


@pytest.fixture
def stubbed(monkeypatch):
    """No DB, no LLM, no Firecrawl. Tracks whether the web search ran."""
    state = {"web_calls": 0, "rows": []}

    class Repo:
        async def lookup(self, **kwargs):
            return state["rows"]

    async def fake_web(material_desc, region):
        state["web_calls"] += 1
        # A plausible in-bounds number so a leak would actually show up in the
        # total rather than being filtered out by the price bounds.
        return 1_500_000.0, "https://example.vn/gia", "Giá vật liệu"

    async def fake_docs(document_ids):
        return [], None

    monkeypatch.setattr(
        "app.db.postgres.repositories.material_price_repo.MaterialPriceRepository",
        lambda: Repo(),
    )
    monkeypatch.setattr("app.core.mcp.tools.web_price_fallback.search_web_price", fake_web)
    monkeypatch.setattr(cost_tool, "_fetch_source_docs", fake_docs)
    # _compute_cost imports these lazily, so the module attribute is the hook.
    monkeypatch.setattr(
        "app.core.llm.openrouter.OpenRouterClient", lambda: SimpleNamespace()
    )
    return state


ARGS = {"floor_area_m2": 100.0, "region": "HCM", "project_type": "nha_pho"}


class TestGate:
    async def test_28_default_now_falls_back_to_the_web(self, stubbed):
        """Default flipped to open: a missing DB price is filled from web
        search rather than always reported as missing (real DB gaps, e.g.
        gạch xây ở HCM, made the old default unusable for those cases)."""
        data = await cost_tool._compute_cost({**ARGS})
        assert stubbed["web_calls"] > 0
        assert data["web_sources"], "every web price must be citable"
        web_lines = [li for li in data["line_items"] if li.get("via_web")]
        assert web_lines and all(li.get("source_index") for li in web_lines)
        facts = cost_tool.build_cost_facts(data)
        assert "giá từ web, chưa xác thực" in facts

    async def test_explicit_false_restores_fail_closed(self, stubbed):
        """ACCEPTANCE §12.28 still reachable on demand: a caller that wants
        the old behaviour (missing price -> missing, total withheld, no web
        call) gets it by passing allow_web_fallback=False explicitly."""
        data = await cost_tool._compute_cost({**ARGS, "allow_web_fallback": False})
        assert stubbed["web_calls"] == 0
        assert data["has_full_pricing"] is False
        assert data["missing"], "the unpriced line items must be listed by name"
        assert data["web_sources"] == []
        facts = cost_tool.build_cost_facts(data)
        assert "KHÔNG đưa ra tổng vì thiếu giá của" in facts

    async def test_29_opting_in_marks_the_price_unverified(self, stubbed):
        """ACCEPTANCE §12.29 — allowed, but never presented as a published
        price: it carries a citation and an explicit "chưa xác thực" label."""
        data = await cost_tool._compute_cost({**ARGS, "allow_web_fallback": True})
        assert stubbed["web_calls"] > 0
        assert data["web_sources"], "every web price must be citable"
        web_lines = [li for li in data["line_items"] if li.get("via_web")]
        assert web_lines and all(li.get("source_index") for li in web_lines)
        facts = cost_tool.build_cost_facts(data)
        assert "giá từ web, chưa xác thực" in facts

    async def test_a_db_price_is_preferred_over_the_web_even_when_opted_in(self, stubbed):
        """The DB stays authoritative — the fallback is only for the gap.

        Uses "thép" (one of the 5 rough materials nha_pho still has after
        the scope cut — sân/xưởng/bê tông-thương-phẩm profiles were removed
        entirely, see project_types.py) rather than "bê tông"."""
        stubbed["rows"] = [
            SimpleNamespace(
                id=uuid.uuid4(),
                document_id=uuid.uuid4(),
                material_name="Thép xây dựng Việt Nhật D10",
                price_ex_vat=16_000,
                unit="kg",
                spec=None,
            )
        ]

        async def pick_first(llm, target_desc, candidates):
            return 0 if candidates else None

        import app.core.mcp.tools.cost_tool as ct

        original = ct._disambiguate
        ct._disambiguate = pick_first
        try:
            data = await ct._compute_cost({**ARGS, "allow_web_fallback": True})
        finally:
            ct._disambiguate = original
        steel = [li for li in data["line_items"] if "thép" in li["item"].lower()]
        assert steel and steel[0]["via_web"] is False


class TestMatchedProductVisibility:
    """The reply must name the EXACT product a price came from (not just the
    generic category label "Xi măng"/"Thép") and show how its quantity was
    derived from the formula — user-requested: "phải trả về tên vật liệu mà
    bạn đã lấy trong hệ thống và giá của nó"."""

    async def test_db_priced_line_names_its_exact_product_and_formula(self, stubbed):
        stubbed["rows"] = [
            SimpleNamespace(
                id=uuid.uuid4(),
                document_id=uuid.uuid4(),
                material_name="Thép xây dựng Việt Nhật D10",
                price_ex_vat=16_000,
                unit="kg",
                spec="D10",
                manufacturer="Việt Nhật",
            )
        ]

        async def pick_first(llm, target_desc, candidates):
            return 0 if candidates else None

        original = cost_tool._disambiguate
        cost_tool._disambiguate = pick_first
        try:
            data = await cost_tool._compute_cost({**ARGS, "allow_web_fallback": True})
        finally:
            cost_tool._disambiguate = original

        steel = next(li for li in data["line_items"] if "thép" in li["item"].lower())
        assert steel["matched_name"] == "Thép xây dựng Việt Nhật D10 (D10) — Việt Nhật"
        assert steel.get("formula_note")

        facts = cost_tool.build_cost_facts(data)
        assert 'Sản phẩm dùng để định giá (giá công bố): "Thép xây dựng Việt Nhật D10' in facts
        assert steel["formula_note"] in facts

        text = cost_tool._format_cost_text(data)
        assert "Thép xây dựng Việt Nhật D10" in text

    async def test_web_priced_line_names_the_web_result_it_used(self, stubbed):
        data = await cost_tool._compute_cost({**ARGS, "allow_web_fallback": True})
        web_line = next(li for li in data["line_items"] if li.get("via_web"))
        assert web_line["matched_name"] == "Giá vật liệu"  # fake_web's title
        facts = cost_tool.build_cost_facts(data)
        assert 'Sản phẩm dùng để định giá (giá tham khảo web): "Giá vật liệu"' in facts


class TestToolLoopThreading:
    def test_the_llm_cannot_turn_the_gate_on_itself(self):
        """`allow_web_fallback` is not in the tool's public JSON schema, and the
        loop overwrites whatever the model passes with the request's value —
        so a model cannot opt itself into unverified prices."""
        from app.core.llm.tool_loop import _tool_input_schema

        schema = _tool_input_schema(cost_tool.COST_TOOL)
        assert "allow_web_fallback" not in schema["properties"]

    async def test_the_loop_forwards_the_request_flag(self, monkeypatch):
        seen: list[dict] = []

        async def spy(args):
            seen.append(args)
            from mcp.types import TextContent

            return [TextContent(type="text", text="ok")]

        import app.core.llm.tool_loop as tl

        monkeypatch.setitem(
            tl._AGENT_TOOLS, "calculate_construction_cost", (cost_tool.COST_TOOL, spy)
        )

        class LLM:
            def __init__(self):
                self.round = 0

            async def chat_with_tools(self, conversation, tools=None, model=None):
                self.round += 1
                if self.round == 1:
                    return SimpleNamespace(
                        content=None,
                        tool_calls=[
                            SimpleNamespace(
                                id="1",
                                function=SimpleNamespace(
                                    name="calculate_construction_cost",
                                    arguments='{"floor_area_m2": 100, "region": "HCM",'
                                    ' "allow_web_fallback": true}',
                                ),
                            )
                        ],
                    )
                return SimpleNamespace(content="xong", tool_calls=None)

        await tl.run_tool_loop([], llm=LLM(), allow_web_fallback=False)
        # The model asked for true; the request said false, and the request wins.
        assert seen[0]["allow_web_fallback"] is False
