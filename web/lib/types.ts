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
  /** When true, uploads into this KB also extract structured price rows into
   *  material_prices (region is then required at upload time). */
  price_extraction: boolean;
  /** Which chunking profile uploads use — false = standard (prose with
   *  incidental tables), true = table-heavy (long price appendices: tighter
   *  chunk cap, no borrowed table context). Independent of price_extraction.
   *  See app/core/chunking/profiles.py. */
  table_heavy_chunking: boolean;
}

export type DocStatus = "pending" | "processing" | "done" | "error";

export interface Doc {
  id: string;
  filename: string;
  status: DocStatus;
  chunk_count: number;
  /** null = not a price document. 0 is meaningful: the file WAS scanned for
   *  price tables and none were readable. */
  price_row_count: number | null;
  price_warning_count: number | null;
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

// "agentic" = retrieval across EVERY knowledge base + construction tool
// calling (price lookup, cost estimate) — the default and only general-
// purpose mode; "chat" (single-KB-scoped RAG) was removed from the UI in
// favor of it. "search"/"research" remain as explicit web-only modes.
export type ChatMode = "search" | "research" | "agentic";

// ── Answer sources ─────────────────────────────────────────────────────────
//
// The backend now emits ONE normalized shape for every citation (see
// app/core/chat/sources.py). The legacy keys are still present on every item,
// so the type guards below keep working on conversations persisted before the
// change; the normalized fields are optional for exactly that reason.
//
// `region` is the important one: it is the citation's OWN region, read from
// material_prices.region or the Qdrant chunk metadata. It is NEVER the region
// the user asked about, and the UI must render it as-is — a chip that inherits
// the request's region is how a Hà Nội source used to display as TP.HCM.

export type SourceKind = "tool" | "rag" | "web";
export type SourceAuthority = "authoritative" | "supporting" | "unverified";

export interface NormalizedSourceFields {
  source_id?: string;
  source_kind?: SourceKind;
  authority?: SourceAuthority;
  used_for?: "price" | "structured_field" | "explanation" | "estimate";
  document_id?: string | null;
  filename?: string | null;
  page_num?: number | null;
  row_id?: string | null;
  /** "HN" | "DN" | "HCM" | "KH" | "AG" — or null for a region-neutral source.
   *  null must render as "Không gắn vùng", never as the requested region. */
  region?: string | null;
  region_label?: string | null;
  price_period?: string | null;
  /** What `score` means. "rrf" is a reciprocal-rank-fusion score (~0.03 at the
   *  top of a hybrid result set) — it is NOT a similarity and must never be
   *  rendered as a percentage. "exact" is a structured row, "cosine" the
   *  dense-only fallback. Absent on sources persisted before hybrid search. */
  score_kind?: "cosine" | "rrf" | "exact";
  used_in_answer?: boolean;
}

export interface RagSource extends NormalizedSourceFields {
  chunk_id?: string;
  document_name: string;
  content?: string;
  score: number;
}
export interface WebSource extends NormalizedSourceFields {
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
/** A citation the tool produced (a material_prices row), as opposed to a
 *  retrieved chunk. Falls back to "rag" for legacy items that predate the
 *  field — an old conversation has no tool citations to mislabel. */
export function sourceKind(s: Source): SourceKind {
  const k = (s as NormalizedSourceFields).source_kind;
  if (k) return k;
  return isWebSource(s) ? "web" : "rag";
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
  formSubmittedData?: Record<string, unknown>;
  researchSteps?: ResearchStep[];
  researchProgress?: number;
  viaVoice?: boolean;
  error?: string;
  pinned?: boolean;
  /** Which kinds of source actually back this answer — drives the badge.
   *  Sent by the backend on the `done` event; absent on legacy messages. */
  sourceKinds?: SourceKind[];
  /** The route the backend took (exact_structured / mixed / document_rag / …).
   *  Display/debug only; the badge reads sourceKinds. */
  route?: string;
}

export interface Conversation {
  id: string;
  title: string;
  updated_at: number;
  pinned?: boolean;
}

// GET /api/v1/chat/history/{conversation_id}
export interface HistoryMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  sources?: Source[] | null;
  created_at: number;
}
export interface ConversationHistoryResponse {
  conversation_id: string;
  kb_id: string | null;
  messages: HistoryMessage[];
}

export interface AppSettings {
  model: string; // OpenRouter model id; "" → backend default
  temperature: number;
  max_tokens: number;
  top_k: number;
}
