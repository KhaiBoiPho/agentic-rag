"""Estimated per-model USD cost per token, for the Usage page.

Not pulled live from OpenRouter — our chat path is SSE streaming, and
OpenRouter doesn't return a `usage`/`cost` field on that path the way it
does for a plain non-streaming chat.completions call. Token counts here are
real (tiktoken, same encoder as chunking), but the $ figure is an estimate
against this static table, refreshed by hand — treat the Usage page as
"roughly how much", not an invoice. Rates are $ per 1M tokens, from public
OpenRouter/provider pricing at the time this was written.
"""
from __future__ import annotations

# (input $/1M tokens, output $/1M tokens) — kept in sync with
# frontend/components/settings/SettingsView.tsx's MODEL_OPTIONS (only
# models confirmed to actually respond on this OpenRouter account, see that
# file's comment — many plausible-looking ids 404).
_RATES: dict[str, tuple[float, float]] = {
    # Rẻ
    "openai/gpt-4o-mini": (0.15, 0.60),
    "openai/gpt-4.1-mini": (0.40, 1.60),
    "google/gemini-2.5-flash-lite": (0.10, 0.40),
    "meta-llama/llama-3.1-8b-instruct": (0.05, 0.08),
    # Vừa
    "openai/gpt-4o": (2.50, 10.00),
    "openai/gpt-4.1": (2.00, 8.00),
    "google/gemini-2.5-flash": (0.30, 2.50),
    # Đắt
    "anthropic/claude-sonnet-4.5": (3.00, 15.00),
    "google/gemini-2.5-pro": (1.25, 10.00),
    "openai/gpt-5": (1.25, 10.00),
    "anthropic/claude-opus-4.1": (15.00, 75.00),
    # Voice (not selectable in Settings, but used for TTS usage tracking)
    "openai/gpt-audio-mini": (0.60, 2.40),
    "openai/gpt-audio": (2.50, 10.00),
}
_DEFAULT_RATE = (0.50, 1.50)  # generic mid-tier estimate for unlisted models


def estimate_cost_usd(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    rate_in, rate_out = _RATES.get(model, _DEFAULT_RATE)
    return (prompt_tokens * rate_in + completion_tokens * rate_out) / 1_000_000
