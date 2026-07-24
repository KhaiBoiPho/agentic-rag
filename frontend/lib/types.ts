export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export interface KBResponse {
  id: string;
  name: string;
  description: string | null;
  document_count: number;
  created_at: number;
  is_system: boolean;
}

export interface DocumentItem {
  id: string;
  filename: string;
  status: 'pending' | 'processing' | 'done' | 'error' | string;
  chunk_count: number;
  created_at: number;
}

export interface IngestJobResponse {
  job_id: string;
  filename: string;
  status: string;
}

export interface ProjectResponse {
  id: string;
  name: string;
  description: string | null;
  kb_ids: string[];
  kb_names: string[];
  created_at: number;
  updated_at: number;
}

export interface NoteResponse {
  id: string;
  title: string | null;
  content: string | null;
  created_at: number;
  updated_at: number;
}

export interface UsageDaily {
  date: string;
  cost_usd: number;
  messages: number;
}

export interface UsageHistoryItem {
  id: string;
  model: string;
  prompt_tokens: number;
  completion_tokens: number;
  cost_usd: number;
  duration_ms: number;
  created_at: number;
}

export interface UsageResponse {
  total_cost_usd: number;
  total_duration_ms: number;
  total_messages: number;
  total_prompt_tokens: number;
  total_completion_tokens: number;
  avg_duration_ms: number;
  avg_cost_usd: number;
  daily: UsageDaily[];
  history: UsageHistoryItem[];
}

export interface SkillMeta {
  id: string;
  label: string;
  icon: string;
  description: string;
}

export type SourceItem =
  | { chunk_id: string; document_name: string; content: string; score: number }
  | { url: string; title: string; snippet?: string }
  | { name: string; arguments: unknown; result: unknown };

export interface RagContext {
  kind: 'kb' | 'project';
  name: string;
}

export interface CostFormField {
  name: string;
  label?: string;
  type?: string;
  required?: boolean;
  default?: unknown;
  options?: { value: string; label: string }[];
}

export interface PendingForm {
  form_id: string;
  title: string;
  fields: CostFormField[];
  prefill?: Record<string, unknown>;
}

export interface ResearchStep {
  node: string;
  status: string;
  content?: string;
  progress?: number;
  iteration?: number;
  sources?: { url: string; title: string; snippet?: string }[];
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  streaming?: boolean;
  sources?: SourceItem[];
  ragContext?: RagContext | null;
  webMode?: 'search' | 'research';
  pendingForm?: PendingForm;
  researchSteps?: ResearchStep[];
  researchProgress?: number;
  viaVoice?: boolean;
  error?: string;
}

export interface ConversationMeta {
  id: string;
  title: string;
  updated_at: number;
}

export type ChatMode = 'chat' | 'search' | 'research';

export const MODEL_TIERS: { tier: string; models: { id: string; label: string }[] }[] = [
  {
    tier: 'Budget',
    models: [
      { id: 'openai/gpt-4o-mini', label: 'GPT-4o mini' },
      { id: 'openai/gpt-4.1-mini', label: 'GPT-4.1 mini' },
      { id: 'google/gemini-2.5-flash-lite', label: 'Gemini 2.5 Flash Lite' },
      { id: 'meta-llama/llama-3.1-8b-instruct', label: 'Llama 3.1 8B' },
    ],
  },
  {
    tier: 'Standard',
    models: [
      { id: 'openai/gpt-4o', label: 'GPT-4o' },
      { id: 'openai/gpt-4.1', label: 'GPT-4.1' },
      { id: 'google/gemini-2.5-flash', label: 'Gemini 2.5 Flash' },
    ],
  },
  {
    tier: 'Premium',
    models: [
      { id: 'anthropic/claude-sonnet-4.5', label: 'Claude Sonnet 4.5' },
      { id: 'google/gemini-2.5-pro', label: 'Gemini 2.5 Pro' },
      { id: 'openai/gpt-5', label: 'GPT-5' },
      { id: 'anthropic/claude-opus-4.1', label: 'Claude Opus 4.1' },
    ],
  },
];

export const DEFAULT_MODEL = 'openai/gpt-4o-mini';
