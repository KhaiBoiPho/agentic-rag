"""Follow-up question condensing — app/core/chat/followup.py.

No test file existed for this module before. Covers the mechanical shape
(history windowing, fail-open, the "model answered instead of rewriting"
guard) and pins the two hard rules the system prompt carries — region
preservation, and the pronoun-resolution rule added after a real failure:
"tiêu chuẩn kỹ thuật của nó là gì?" (following a turn about a streetlight
made by Phương Đông) got condensed into a question about an unrelated cable
product ("cáp ngầm hạ thế... Phú Thắng") that was never the subject of the
conversation — the prompt had detailed region-preservation guidance but no
equivalent instruction for resolving a pronoun to the right antecedent.
"""

from __future__ import annotations

from app.core.chat.followup import _CONDENSE_SYSTEM, condense_followup


class FakeLLM:
    def __init__(self, reply: str | None = None, raise_exc: Exception | None = None):
        self.reply = reply
        self.raise_exc = raise_exc
        self.calls: list[dict] = []

    async def chat(self, **kwargs):
        self.calls.append(kwargs)
        if self.raise_exc:
            raise self.raise_exc
        return self.reply


def _history(*turns: tuple[str, str]) -> list[dict]:
    return [{"role": role, "content": content} for role, content in turns]


class TestCondenseFollowup:
    async def test_returns_the_rewrite_on_success(self):
        llm = FakeLLM(reply="Giá thép ở Đà Nẵng là bao nhiêu?")
        history = _history(
            ("user", "Giá thép ở Hà Nội thế nào?"),
            ("assistant", "Giá thép ở Hà Nội là ..."),
        )
        out = await condense_followup(llm, "còn ở Đà Nẵng thì sao?", history)
        assert out == "Giá thép ở Đà Nẵng là bao nhiêu?"

    async def test_strips_surrounding_quotes(self):
        llm = FakeLLM(reply='"Giá thép ở Đà Nẵng là bao nhiêu?"')
        history = _history(("user", "Giá thép ở Hà Nội?"), ("assistant", "..."))
        out = await condense_followup(llm, "còn Đà Nẵng?", history)
        assert out == "Giá thép ở Đà Nẵng là bao nhiêu?"

    async def test_empty_history_returns_none_without_calling_the_model(self):
        llm = FakeLLM(reply="should never be used")
        assert await condense_followup(llm, "còn Đà Nẵng?", []) is None
        assert llm.calls == []

    async def test_a_paragraph_instead_of_a_rewrite_falls_back_to_none(self):
        """Guard against a model that answered the question instead of
        rewriting it — that's a paragraph, not a short standalone question."""
        llm = FakeLLM(reply="Giá thép ở Đà Nẵng hiện tại là khoảng " + "1.500.000 đồng " * 20)
        history = _history(("user", "Giá thép ở Hà Nội?"), ("assistant", "..."))
        assert await condense_followup(llm, "còn Đà Nẵng?", history) is None

    async def test_llm_failure_fails_open(self):
        llm = FakeLLM(raise_exc=RuntimeError("openrouter down"))
        history = _history(("user", "Giá thép ở Hà Nội?"), ("assistant", "..."))
        assert await condense_followup(llm, "còn Đà Nẵng?", history) is None

    async def test_only_the_last_4_user_assistant_messages_are_sent(self):
        llm = FakeLLM(reply="rewritten")
        history = _history(
            ("user", "turn 1"),
            ("assistant", "reply 1"),
            ("user", "turn 2"),
            ("assistant", "reply 2"),
            ("user", "turn 3"),
            ("assistant", "reply 3"),
        )
        await condense_followup(llm, "follow-up", history)
        prompt = llm.calls[0]["messages"][1]["content"]
        assert "turn 1" not in prompt
        assert "turn 3" in prompt

    async def test_non_user_assistant_roles_are_excluded_from_history(self):
        llm = FakeLLM(reply="rewritten")
        history = [
            {"role": "system", "content": "should never appear"},
            {"role": "user", "content": "Giá thép ở Hà Nội?"},
            {"role": "assistant", "content": "..."},
        ]
        await condense_followup(llm, "còn Đà Nẵng?", history)
        prompt = llm.calls[0]["messages"][1]["content"]
        assert "should never appear" not in prompt


class TestSystemPromptRules:
    """The prompt itself is what actually governs behaviour (no code-level
    enforcement) — pin that both hard rules are present, so a future edit
    can't silently drop the guidance that fixes a real, measured failure."""

    def test_carries_the_region_preservation_rule(self):
        assert "QUY TẮC VÙNG" in _CONDENSE_SYSTEM
        assert "Đà Nẵng" in _CONDENSE_SYSTEM  # the worked example is present

    def test_carries_the_pronoun_resolution_rule(self):
        assert "QUY TẮC CHỦ ĐỀ" in _CONDENSE_SYSTEM
        # The measured failure this rule fixes, kept as the worked example.
        assert "Phương Đông" in _CONDENSE_SYSTEM
        assert "LƯỢT NGAY TRƯỚC ĐÓ" in _CONDENSE_SYSTEM
