// Data shapes mirror the backend API contracts. IDs are UUID strings;
// timestamps are Unix seconds (integer).

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export interface JwtPayload {
  sub: string;
  email?: string;
  exp: number;
}

export interface KB {
  id: string;
  name: string;
  description: string | null;
  document_count: number;
  created_at: number;
  is_system: boolean;
}

export type DocStatus = "pending" | "processing" | "done" | "error";

export interface Doc {
  id: string;
  filename: string;
  status: DocStatus;
  chunk_count: number;
  created_at: number;
}

export interface Project {
  id: string;
  name: string;
  description: string | null;
  kb_ids: string[];
  kb_names: string[];
  created_at: number;
  updated_at: number;
}

export interface Note {
  id: string;
  title: string;
  content: string;
  created_at: number;
  updated_at: number;
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

export interface Usage {
  total_cost_usd: number;
  total_duration_ms: number;
  total_messages: number;
  total_prompt_tokens: number;
  total_completion_tokens: number;
  avg_duration_ms: number;
  avg_cost_usd: number;
  daily: { date: string; cost_usd: number; messages: number }[];
  history: UsageHistoryItem[];
}

// ── Chat / streaming ───────────────────────────────────────────────────────

export type ChatMode = "chat" | "search" | "research";

// A RAG document citation OR a web citation OR an agent tool log.
export interface RagSource {
  chunk_id?: string;
  document_name: string;
  content?: string;
  score: number;
}
export interface WebSource {
  url: string;
  title: string;
  snippet?: string;
}
export interface ToolLog {
  name: string;
  arguments: unknown;
  result: unknown;
}
export type Source = RagSource | WebSource | ToolLog;

export function isRagSource(s: Source): s is RagSource {
  return typeof (s as RagSource).document_name === "string";
}
export function isWebSource(s: Source): s is WebSource {
  return typeof (s as WebSource).url === "string" && typeof (s as WebSource).title === "string";
}

export interface RagContext {
  kind: "kb" | "project";
  name: string;
}

export interface FormField {
  name: string;
  label: string;
  type: "number" | "select" | "text";
  required?: boolean;
  default?: string | number;
  options?: { value: string; label: string }[];
}

export interface PendingForm {
  form_id: string;
  title: string;
  fields: FormField[];
  prefill?: Record<string, unknown>;
}

export interface ResearchStep {
  node: string;
  status: string;
  content?: string;
  progress?: number;
  iteration?: number;
  sources?: WebSource[];
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  streaming?: boolean;
  sources?: Source[];
  ragContext?: RagContext | null;
  webMode?: "search" | "research";
  pendingForm?: PendingForm;
  researchSteps?: ResearchStep[];
  researchProgress?: number;
  viaVoice?: boolean;
  error?: string;
  pinned?: boolean;
}

export interface Conversation {
  id: string;
  title: string;
  updated_at: number;
}

export interface AppSettings {
  model: string; // OpenRouter model id; "" → backend default
  temperature: number;
  max_tokens: number;
  top_k: number;
}
