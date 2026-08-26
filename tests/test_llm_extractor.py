"""LLM slot re-extraction fallback — see app/core/chat/llm_extractor.py's
own docstring for why this exists and what it is/isn't allowed to do."""

from __future__ import annotations

import pytest

from app.core.chat.llm_extractor import ExtractedSlots, extract_slots_llm


class FakeLLM:
    def __init__(self, reply: str):
        self.reply = reply
        self.calls = 0

    async def chat(self, **kwargs):
        self.calls += 1
        return self.reply


class BrokenLLM:
    async def chat(self, **kwargs):
        raise RuntimeError("openrouter down")


class TestExtractSlotsLLM:
    async def test_parses_clean_json(self):
        llm = FakeLLM(
            '{"material_name": "thép", "manufacturer": null, '
            '"material_category": null, "code_variants": []}'
        )
        slots = await extract_slots_llm("tôi muốn biết giá thép xây dựng ở hà nội", llm)
        assert slots == ExtractedSlots(material_name="thép")

    async def test_strips_markdown_fence(self):
        llm = FakeLLM(
            '```json\n{"material_name": "xi măng PCB40", "code_variants": ["PCB40"]}\n```'
        )
        slots = await extract_slots_llm("giá pc b40", llm)
        assert slots is not None
        assert slots.material_name == "xi măng PCB40"
        assert slots.code_variants == ["PCB40"]

    async def test_code_variant_case(self):
        llm = FakeLLM('{"material_name": null, "code_variants": ["PCB40"]}')
        slots = await extract_slots_llm("giá xi măng pc b40 ở hà nội", llm)
        assert slots is not None
        assert slots.code_variants == ["PCB40"]

    async def test_llm_failure_fails_open(self):
        assert await extract_slots_llm("giá thép", BrokenLLM()) is None

    async def test_malformed_json_fails_open(self):
        assert await extract_slots_llm("giá thép", FakeLLM("not json at all")) is None

    async def test_empty_extraction_fails_open(self):
        """Never invents a candidate out of thin air — an all-null response
        is as good as no response for retry purposes."""
        llm = FakeLLM('{"material_name": null, "manufacturer": null, "code_variants": []}')
        assert await extract_slots_llm("kể chuyện vui đi", llm) is None

    async def test_non_dict_json_fails_open(self):
        assert await extract_slots_llm("giá thép", FakeLLM("[1, 2, 3]")) is None
