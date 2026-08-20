"use client";

import { memo } from "react";
import { useT } from "@/lib/i18n";
import {
  isRagSource,
  isWebSource,
  sourceKind,
  type ChatMessage,
  type RagSource,
  type Source,
  type WebSource,
} from "@/lib/types";
import { Book, Bot, Globe, Mic, Pin, Trash, Warn } from "../Icons";
import Markdown from "./Markdown";
import ResearchPanel from "./ResearchPanel";
import CostForm from "./CostForm";

interface Props {
  msg: ChatMessage;
  onSubmitForm: (formId: string, data: Record<string, unknown>) => void;
  onTogglePin: (id: string) => void;
  onDelete: (id: string) => void;
}

function MessageBubbleImpl({ msg, onSubmitForm, onTogglePin, onDelete }: Props) {
  const { t, lang } = useT();

  if (msg.role === "user") {
    return (
      <div className={`msg user${msg.pinned ? " pinned" : ""}`}>
        <span className="g">{lang === "vi" ? "Bạn" : "You"}</span>
        <div className="msg-col">
          <div className="bubble">
            <div className="meta">
              {msg.pinned && (
                <span className="badge pin-badge">
                  <Pin width={11} height={11} /> {t.chat.pinned}
                </span>
              )}
            </div>
            {msg.viaVoice ? (
              <div className="voice-orb-row">
                <span className="voice-orb">
                  <span className="voice-orb-ring" />
                  <Mic />
                </span>
                <span className="voice-orb-label">{t.chat.voiceMsgSent}</span>
              </div>
            ) : (
              <div className="md streaming" style={{ whiteSpace: "pre-wrap" }}>
                {msg.content}
              </div>
            )}
          </div>
          <MsgActions msg={msg} onTogglePin={onTogglePin} onDelete={onDelete} />
        </div>
      </div>
    );
  }

  // Document/tool citations vs web citations. `rag` here means "renders as a
  // chip" — it holds both retrieved chunks and material_prices rows, which the
  // chip itself distinguishes by kind and region.
  const rag = (msg.sources ?? []).filter(isRagSource) as RagSource[];
  const web = (msg.sources ?? []).filter(isWebSource) as WebSource[];
  const kinds = answerKinds(msg.sources ?? [], msg.sourceKinds);
  // Chips must agree with the badge. A tool-backed answer has real citations
  // even with no RAG context, so gating chips on `ragContext` alone hid the
  // provenance of exactly the answers whose provenance matters most.
  const showRagChips = !msg.streaming && rag.length > 0 && (!!msg.ragContext || kinds.has("tool"));

  // Nothing has arrived yet (no token, no form, no research step, no
  // error) — show a lightweight "thinking" indicator instead of an empty
  // bordered bubble, which used to appear the instant a message was sent.
  const isThinking =
    !!msg.streaming &&
    !msg.content &&
    !msg.pendingForm &&
    !(msg.researchSteps && msg.researchSteps.length > 0) &&
    !msg.error;

  return (
    <div className={`msg assistant${msg.pinned ? " pinned" : ""}`}>
      <span className="g" title="Cốt"><Bot width={17} height={17} /></span>
      <div className="msg-col">
        {isThinking ? (
          <div className="thinking-row" aria-live="polite" aria-label={t.chat.thinking}>
            <span className="thinking-dots">
              <i /><i /><i />
            </span>
          </div>
        ) : (
          <div className="bubble">
            <Badges msg={msg} kinds={kinds} />

            {msg.researchSteps && msg.researchSteps.length > 0 && (
              <ResearchPanel
                steps={msg.researchSteps}
                progress={msg.researchProgress ?? 0}
                running={!!msg.streaming}
              />
            )}

            {msg.content && (
              <div style={{ marginTop: msg.researchSteps?.length ? 12 : 0 }}>
                <Markdown content={msg.content} streaming={msg.streaming} webSources={web} />
              </div>
            )}

            {msg.pendingForm && (
              <CostForm
                form={msg.pendingForm}
                submittedData={msg.formSubmittedData}
                disabled={msg.streaming}
                onSubmit={onSubmitForm}
              />
            )}

            {msg.error && (
              <div className="cite-note" style={{ marginTop: 8 }}>
                <Warn width={12} height={12} /> {msg.error}
              </div>
            )}

            {showRagChips && (
              <div className="cite-row">
                {rag.map((s, i) => (
                  <span
                    className="chip"
                    key={s.source_id || s.chunk_id || i}
                    title={s.content?.slice(0, 200)}
                  >
                    <span className="idx">{i + 1}</span>
                    <span className="ellip" style={{ maxWidth: 220 }}>
                      {s.document_name}
                    </span>
                    {/* The citation's OWN region, straight from its metadata.
                        Never the region of the question — see lib/types.ts. */}
                    <span className="chip-region">{regionText(s, t.chat.sourceNoRegion)}</span>
                    {s.price_period && <span className="chip-period">{s.price_period}</span>}
                    {/* A percentage only when the score IS one. Retrieval is
                        hybrid now, so `score` is usually an RRF score — a sum
                        of reciprocal ranks, ~0.03 at the top — and rendering
                        that as "3%" reads as "this source is 3% relevant".
                        For those the [n] beside the filename already conveys
                        what RRF produces: the rank. */}
                    {s.score_kind !== "rrf" && sourceKind(s) !== "tool" && (
                      <span className="score">{Math.round((s.score ?? 0) * 100)}%</span>
                    )}
                  </span>
                ))}
              </div>
            )}

            {!msg.streaming && web.length > 0 && (
              <div className="sources-foot">
                <div className="lbl">{t.chat.sourcesLabel}</div>
                <ol>
                  {web.map((s, i) => (
                    <li key={i}>
                      <a href={s.url} target="_blank" rel="noreferrer noopener">
                        {s.title || s.url}
                      </a>
                    </li>
                  ))}
                </ol>
              </div>
            )}
          </div>
        )}
        {!msg.streaming && <MsgActions msg={msg} onTogglePin={onTogglePin} onDelete={onDelete} />}
      </div>
    </div>
  );
}

function MsgActions({
  msg,
  onTogglePin,
  onDelete,
}: {
  msg: ChatMessage;
  onTogglePin: (id: string) => void;
  onDelete: (id: string) => void;
}) {
  const { t } = useT();
  return (
    <div className="msg-actions">
      <button
        className={`msg-action-btn${msg.pinned ? " active" : ""}`}
        onClick={() => onTogglePin(msg.id)}
        aria-label={msg.pinned ? t.chat.unpin : t.chat.pin}
        title={msg.pinned ? t.chat.unpin : t.chat.pin}
        type="button"
      >
        <Pin width={14} height={14} />
      </button>
      <button
        className="msg-action-btn"
        onClick={() => onDelete(msg.id)}
        aria-label={t.chat.deleteMsg}
        title={t.chat.deleteMsg}
        type="button"
      >
        <Trash width={14} height={14} />
      </button>
    </div>
  );
}

/** The label for a citation's region. Renders the backend's own label when it
 *  sent one, falls back to the code, and shows "Không gắn vùng" for a source
 *  that genuinely has no region — including every citation persisted before
 *  regions were carried through. A missing region is displayed as missing; it
 *  is never filled in from the question (rule §8.8). */
function regionText(s: Source, noRegionLabel: string): string {
  const src = s as RagSource;
  if (src.region_label) return src.region_label;
  if (src.region) return src.region;
  return noRegionLabel;
}

/** Which kinds back this answer. Prefers the backend's `source_kinds`; derives
 *  it from the items otherwise (legacy messages). */
function answerKinds(sources: Source[], sent?: ChatMessage["sourceKinds"]): Set<string> {
  if (sent?.length) return new Set(sent);
  return new Set(sources.map(sourceKind));
}

function Badges({ msg, kinds }: { msg: ChatMessage; kinds: Set<string> }) {
  const { t } = useT();
  // precedence: provenance badge → web mode → plain.
  //
  // The badge now reads the SOURCE KINDS rather than "is ragContext set", so a
  // tool-only answer says "Tra cứu dữ liệu" instead of borrowing the RAG label
  // it never earned (rule §8.10).
  const hasTool = kinds.has("tool");
  const hasRag = kinds.has("rag");
  let badge: React.ReactNode;
  if (hasTool && hasRag) {
    badge = (
      <span className="badge rag">
        <Book /> {t.chat.badgeToolRag}
      </span>
    );
  } else if (hasTool) {
    badge = (
      <span className="badge rag">
        <Book /> {t.chat.badgeTool}
      </span>
    );
  } else if (hasRag && msg.ragContext) {
    badge = (
      <span className="badge rag">
        <Book /> RAG · {msg.ragContext.name}
      </span>
    );
  } else if (msg.webMode === "search") {
    badge = (
      <span className="badge web">
        <Globe /> {t.chat.badgeSearch}
      </span>
    );
  } else if (msg.webMode === "research") {
    badge = (
      <span className="badge web">
        <Globe /> {t.chat.badgeResearch}
      </span>
    );
  }
  // No "Plain chat — no RAG" fallback badge any more: an answer with no
  // sources isn't necessarily unrelated small talk — a price lookup that
  // came back NOT_FOUND/CLARIFY/AMBIGUOUS legitimately has zero sources too
  // (nothing was found to cite), and labelling that "plain chat" read as the
  // system having silently abandoned the lookup rather than having tried and
  // come up empty. No badge in that case is more honest than a wrong one.

  if (!badge && !msg.viaVoice && !msg.pinned) return null;
  return (
    <div className="badge-row">
      {msg.pinned && (
        <span className="badge pin-badge">
          <Pin width={11} height={11} /> {t.chat.pinned}
        </span>
      )}
      {badge}
      {msg.viaVoice && (
        <span className="badge voice">
          <Mic /> {t.chat.badgeVoice}
        </span>
      )}
    </div>
  );
}

export default memo(MessageBubbleImpl);
