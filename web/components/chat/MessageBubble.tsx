"use client";

import { memo } from "react";
import { useT } from "@/lib/i18n";
import { isRagSource, isWebSource, type ChatMessage, type RagSource, type WebSource } from "@/lib/types";
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

  const rag = (msg.sources ?? []).filter(isRagSource) as RagSource[];
  const web = (msg.sources ?? []).filter(isWebSource) as WebSource[];
  // Chips must agree with the badge: showing confident-looking citation
  // chips under a "Chat thường — không dùng RAG" badge reads as a
  // contradiction, so gate both on the same ragContext signal.
  const showRagChips = !msg.streaming && !!msg.ragContext && rag.length > 0;

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
            <Badges msg={msg} hasRag={rag.length > 0} />

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
                  <span className="chip" key={s.chunk_id || i} title={s.content?.slice(0, 200)}>
                    <span className="idx">{i + 1}</span>
                    <span className="ellip" style={{ maxWidth: 220 }}>
                      {s.document_name}
                    </span>
                    <span className="score">{Math.round((s.score ?? 0) * 100)}%</span>
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

function Badges({ msg, hasRag }: { msg: ChatMessage; hasRag: boolean }) {
  const { t } = useT();
  // precedence: RAG (only if real citations) → web → plain
  let badge: React.ReactNode;
  if (msg.ragContext && hasRag) {
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
  } else if (!msg.streaming && !(msg.pendingForm && !msg.content)) {
    // a bare form-request bubble (no answer text yet) isn't "plain chat" —
    // showing that badge over an interactive form reads as a stray answer
    badge = <span className="badge plain">{t.chat.badgePlain}</span>;
  }

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
