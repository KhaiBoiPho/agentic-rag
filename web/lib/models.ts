// There is no backend /models endpoint — this curated list is frontend-owned.
// Verified-working OpenRouter ids grouped by relative price tier.

export interface ModelTier {
  tier: "Budget" | "Standard" | "Premium";
  models: { id: string; label: string }[];
}

export const DEFAULT_MODEL = "openai/gpt-4o-mini";

export const MODEL_TIERS: ModelTier[] = [
  {
    tier: "Budget",
    models: [
      { id: "openai/gpt-4o-mini", label: "GPT-4o mini" },
      { id: "openai/gpt-4.1-mini", label: "GPT-4.1 mini" },
      { id: "google/gemini-2.5-flash-lite", label: "Gemini 2.5 Flash Lite" },
      { id: "meta-llama/llama-3.1-8b-instruct", label: "Llama 3.1 8B" },
    ],
  },
  {
    tier: "Standard",
    models: [
      { id: "openai/gpt-4o", label: "GPT-4o" },
      { id: "openai/gpt-4.1", label: "GPT-4.1" },
      { id: "google/gemini-2.5-flash", label: "Gemini 2.5 Flash" },
    ],
  },
  {
    tier: "Premium",
    models: [
      { id: "anthropic/claude-sonnet-4.5", label: "Claude Sonnet 4.5" },
      { id: "google/gemini-2.5-pro", label: "Gemini 2.5 Pro" },
      { id: "openai/gpt-5", label: "GPT-5" },
      { id: "anthropic/claude-opus-4.1", label: "Claude Opus 4.1" },
    ],
  },
];

export function modelLabel(id: string): string {
  for (const t of MODEL_TIERS) {
    const m = t.models.find((x) => x.id === id);
    if (m) return m.label;
  }
  return id || "mặc định";
}
