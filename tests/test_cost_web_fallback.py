"""Web price fallback gating (spec §10, §12.28-§12.29).

The fallback code is untouched — it is only gated. These tests pin that the
gate is closed by default and that an opted-in web price is still labelled
unverified rather than blended into the published-price total.
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
    async def test_28_default_never_calls_the_web_and_withholds_the_total(self, stubbed):
        """ACCEPTANCE §12.28 — a missing price means missing, not invented."""
        data = await cost_tool._compute_cost({**ARGS})
        assert stubbed["web_calls"] == 0
        assert data["has_full_pricing"] is False
        assert data["missing"], "the unpriced line items must be listed by name"
        assert data["web_sources"] == []
        # Fail-closed: no single confident number when a major item is missing.
        facts = cost_tool.build_cost_facts(data)
        assert "KHÔNG đưa ra tổng vì thiếu giá của" in facts

    async def test_explicit_false_behaves_like_the_default(self, stubbed):
        await cost_tool._compute_cost({**ARGS, "allow_web_fallback": False})
        assert stubbed["web_calls"] == 0

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
        """The DB stays authoritative — the fallback is only for the gap."""
        stubbed["rows"] = [
            SimpleNamespace(
                id=uuid.uuid4(),
                document_id=uuid.uuid4(),
                material_name="Bê tông thương phẩm M250",
                price_ex_vat=1_200_000,
                unit="m3",
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
        concrete = [li for li in data["line_items"] if "tông" in li["item"].lower()]
        assert concrete and concrete[0]["via_web"] is False


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
