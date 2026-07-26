"use client";

import { useT } from "@/lib/i18n";
import { isRagSource, isWebSource, type ChatMessage, type RagSource, type WebSource } from "@/lib/types";
import { Book, Globe, Mic, Warn } from "../Icons";
import Markdown from "./Markdown";
import ResearchPanel from "./ResearchPanel";
import CostForm from "./CostForm";

export default function MessageBubble({
  msg,
  onSubmitForm,
}: {
  msg: ChatMessage;
  onSubmitForm: (formId: string, data: Record<string, unknown>) => void;
}) {
  const { t, lang } = useT();

  if (msg.role === "user") {
    return (
      <div className="msg user">
        <span className="g">{lang === "vi" ? "Bạn" : "You"}</span>
        <div className="bubble">
          <div className="meta">
            {msg.viaVoice && (
              <span className="badge voice" style={{ padding: "1px 7px" }}>
                <Mic /> {t.chat.badgeVoice}
              </span>
            )}
          </div>
          <div className="md streaming" style={{ whiteSpace: "pre-wrap" }}>
            {msg.content}
          </div>
        </div>
      </div>
    );
  }

  const rag = (msg.sources ?? []).filter(isRagSource) as RagSource[];
  const web = (msg.sources ?? []).filter(isWebSource) as WebSource[];

  return (
    <div className="msg assistant">
      <span className="g">Cố</span>
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
          <CostForm form={msg.pendingForm} disabled={msg.streaming} onSubmit={onSubmitForm} />
        )}

        {msg.error && (
          <div className="cite-note" style={{ marginTop: 8 }}>
            <Warn width={12} height={12} /> {msg.error}
          </div>
        )}

        {!msg.streaming && rag.length > 0 && (
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
  } else if (!msg.streaming) {
    badge = <span className="badge plain">{t.chat.badgePlain}</span>;
  }

  if (!badge && !msg.viaVoice) return null;
  return (
    <div className="badge-row">
      {badge}
      {msg.viaVoice && (
        <span className="badge voice">
          <Mic /> {t.chat.badgeVoice}
        </span>
      )}
    </div>
  );
}
