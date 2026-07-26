"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { apiFetch } from "@/lib/api";
import { streamSSE } from "@/lib/sse";
import { useStore } from "@/lib/store";
import { useT } from "@/lib/i18n";
import type { ChatMessage, ChatMode, ResearchStep } from "@/lib/types";
import TopBar from "../TopBar";
import { Book, Globe } from "../Icons";
import MessageBubble from "./MessageBubble";
import Composer, { type SendOpts } from "./Composer";

// Tick rate for the typewriter reveal — independent of how fast the network
// delivers deltas, so bursty SSE chunks don't make the text "pop" in clumps.
const REVEAL_MS = 18;

export default function ChatView({ conversationId }: { conversationId: string }) {
  const { t } = useT();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [mode, setMode] = useState<ChatMode>("chat");
  const [speaking, setSpeaking] = useState(false);

  const SUGGESTIONS = [t.chat.suggestion1, t.chat.suggestion2, t.chat.suggestion3];

  const settings = useStore((s) => s.settings);
  const activeKbId = useStore((s) => s.activeKbId);
  const activeProjectId = useStore((s) => s.activeProjectId);
  const kbs = useStore((s) => s.kbs);
  const projects = useStore((s) => s.projects);
  const upsertConversation = useStore((s) => s.upsertConversation);

  const threadRef = useRef<HTMLDivElement>(null);
  const busyRef = useRef(false);
  const [busy, setBusy] = useState(false);

  // ── typewriter reveal ────────────────────────────────────────────────────
  // bufRef holds the full target text as it arrives (network-speed).
  // revealedRef holds what's currently on screen; a per-message interval
  // eases it toward the target at a fixed cadence, catching up faster when
  // the backlog grows so it never falls hopelessly behind a big chunk.
  const bufRef = useRef<Record<string, string>>({});
  const revealedRef = useRef<Record<string, string>>({});
  const tickerRef = useRef<Record<string, ReturnType<typeof setInterval>>>({});
  const finalizeRef = useRef<Record<string, () => void>>({});

  useEffect(() => {
    const tickers = tickerRef.current;
    return () => {
      Object.values(tickers).forEach(clearInterval);
    };
  }, []);

  const scrollDown = useCallback(() => {
    const el = threadRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, []);

  useEffect(scrollDown, [messages, scrollDown]);

  // ── message helpers ────────────────────────────────────────────────────
  function push(msg: ChatMessage) {
    setMessages((m) => [...m, msg]);
  }
  function patch(id: string, p: Partial<ChatMessage> | ((prev: ChatMessage) => Partial<ChatMessage>)) {
    setMessages((m) => m.map((x) => (x.id === id ? { ...x, ...(typeof p === "function" ? p(x) : p) } : x)));
  }
  function addStep(id: string, step: ResearchStep) {
    patch(id, (prev) => ({ researchSteps: [...(prev.researchSteps || []), step] }));
  }

  function stopTicker(id: string) {
    const timer = tickerRef.current[id];
    if (timer) {
      clearInterval(timer);
      delete tickerRef.current[id];
    }
  }
  function startTicker(id: string) {
    if (tickerRef.current[id]) return;
    tickerRef.current[id] = setInterval(() => {
      const full = bufRef.current[id] || "";
      const shown = revealedRef.current[id] || "";
      if (shown.length < full.length) {
        const backlog = full.length - shown.length;
        const step = Math.max(1, Math.ceil(backlog / 10));
        const next = full.slice(0, shown.length + step);
        revealedRef.current[id] = next;
        patch(id, { content: next });
      } else {
        const done = finalizeRef.current[id];
        if (done) {
          delete finalizeRef.current[id];
          stopTicker(id);
          done();
        } else {
          stopTicker(id);
        }
      }
    }, REVEAL_MS);
  }
  /** Append a network delta to the target text; the ticker reveals it gradually. */
  function append(id: string, delta: string) {
    bufRef.current[id] = (bufRef.current[id] || "") + delta;
    startTicker(id);
  }
  /** Reconcile the target text to an authoritative full string (e.g. research's "completed" event). */
  function reconcile(id: string, full: string) {
    bufRef.current[id] = full;
    startTicker(id);
  }
  /** Apply a patch once the visible text has fully caught up to the target. */
  function finalize(id: string, p: Partial<ChatMessage>) {
    const full = bufRef.current[id] || "";
    const shown = revealedRef.current[id] || "";
    if (shown.length >= full.length) {
      patch(id, p);
    } else {
      finalizeRef.current[id] = () => patch(id, p);
      startTicker(id);
    }
  }
  /** Skip straight to the full text (used on error, so nothing is lost mid-reveal). */
  function forceFlush(id: string) {
    const full = bufRef.current[id] || "";
    revealedRef.current[id] = full;
    stopTicker(id);
    delete finalizeRef.current[id];
    patch(id, { content: full });
  }
  function finalizeError(id: string, message: string) {
    forceFlush(id);
    patch(id, { streaming: false, error: message });
  }

  function assistantPlaceholder(id: string, extra: Partial<ChatMessage> = {}): ChatMessage {
    bufRef.current[id] = "";
    revealedRef.current[id] = "";
    return { id, role: "assistant", content: "", streaming: true, ...extra };
  }

  function recentContext(): string {
    return messages
      .slice(-6)
      .map((m) => `${m.role === "user" ? "User" : "Assistant"}: ${m.content}`)
      .join("\n");
  }

  function registerConversation(title: string) {
    upsertConversation({ id: conversationId, title: title.slice(0, 60), updated_at: Math.floor(Date.now() / 1000) });
  }

  // ── TTS ────────────────────────────────────────────────────────────────
  async function speak(text: string) {
    if (!text.trim()) return;
    setSpeaking(true);
    try {
      const res = await apiFetch("/api/v1/voice/tts/stream", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text }),
      });
      if (!res.ok) return setSpeaking(false);
      const buf = await res.arrayBuffer();
      const url = URL.createObjectURL(new Blob([buf], { type: "audio/wav" }));
      const audio = new Audio(url);
      audio.onended = () => {
        setSpeaking(false);
        URL.revokeObjectURL(url);
      };
      audio.onerror = () => setSpeaking(false);
      await audio.play();
    } catch {
      setSpeaking(false);
    }
  }
  function maybeSpeak(id: string, viaVoice?: boolean) {
    if (viaVoice) speak(bufRef.current[id] || "");
  }

  // ── chat (RAG) ─────────────────────────────────────────────────────────
  async function streamChat(opts: {
    message?: string;
    viaVoice?: boolean;
    formSubmission?: { form_id: string; data: Record<string, unknown> };
  }) {
    const aId = crypto.randomUUID();
    push(assistantPlaceholder(aId));
    const body = {
      message: opts.message ?? "",
      conversation_id: conversationId,
      kb_id: activeProjectId ? null : activeKbId,
      project_id: activeProjectId,
      model: settings.model || null,
      skill_id: null,
      temperature: settings.temperature,
      max_tokens: settings.max_tokens,
      use_rag: !!(activeKbId || activeProjectId),
      top_k: settings.top_k,
      score_threshold: 0.5,
      mode: "rag",
      form_submission: opts.formSubmission ?? null,
    };
    try {
      await streamSSE("/api/v1/chat/stream", body, (ev) => {
        if (ev.type === "form_request") {
          patch(aId, {
            streaming: false,
            pendingForm: { form_id: ev.form_id, title: ev.title, fields: ev.fields, prefill: ev.prefill },
          });
          return;
        }
        if (ev.type === "text") {
          if (ev.delta) append(aId, ev.delta);
          if (ev.done) {
            const rc = ev.rag_context ? { kind: ev.rag_context.kind, name: ev.rag_context.name } : null;
            finalize(aId, { streaming: false, sources: ev.sources ?? [], ragContext: rc });
            maybeSpeak(aId, opts.viaVoice);
          }
        }
      });
    } catch (e: any) {
      finalizeError(aId, e?.message || t.chat.connectionError);
    }
  }

  // ── web search ─────────────────────────────────────────────────────────
  async function streamSearch(query: string) {
    const context = recentContext();
    const aId = crypto.randomUUID();
    push(assistantPlaceholder(aId, { webMode: "search" }));
    try {
      await streamSSE(
        "/api/v1/search/web",
        { query, max_results: 6, scrape: false, context },
        (ev) => {
          if (ev.error) return finalizeError(aId, ev.error);
          if (ev.type === "sources") patch(aId, { sources: ev.sources ?? [] });
          else if (ev.type === "token") {
            if (ev.delta) append(aId, ev.delta);
          } else if (ev.type === "done" || ev.done) finalize(aId, { streaming: false });
        },
      );
    } catch (e: any) {
      finalizeError(aId, e?.message || t.chat.connectionError);
    }
  }

  // ── deep research ──────────────────────────────────────────────────────
  async function streamResearch(query: string) {
    const context = recentContext();
    const aId = crypto.randomUUID();
    push(assistantPlaceholder(aId, { webMode: "research", researchSteps: [], researchProgress: 0 }));
    try {
      await streamSSE(
        "/api/v1/research/stream",
        {
          query,
          max_iterations: 2,
          max_search_results: 6,
          quality_threshold: 0.75,
          search_first: true,
          context,
        },
        (ev) => {
          if (ev.error) return finalizeError(aId, ev.error);
          const node: string = ev.node;
          const status: string = ev.status;
          if (typeof ev.progress === "number") patch(aId, { researchProgress: ev.progress });

          if (node === "response_generator" && status === "streaming") {
            if (ev.content) append(aId, ev.content);
          } else if (node === "response_generator" && status === "completed") {
            if (ev.content) reconcile(aId, ev.content);
            patch(aId, { sources: ev.sources ?? [] });
          } else if (node === "done" || ev.done) {
            finalize(aId, { streaming: false, researchProgress: 1 });
          } else {
            addStep(aId, {
              node,
              status,
              content: ev.content,
              progress: ev.progress,
              iteration: ev.iteration,
              sources: ev.sources,
            });
          }
        },
      );
    } catch (e: any) {
      finalizeError(aId, e?.message || t.chat.connectionError);
    }
  }

  // ── entry points ───────────────────────────────────────────────────────
  const onSend = useCallback(
    async (text: string, opts?: SendOpts) => {
      if (busyRef.current) return;
      busyRef.current = true;
      setBusy(true);
      const isFirst = messages.length === 0;
      push({ id: crypto.randomUUID(), role: "user", content: text, viaVoice: opts?.viaVoice });
      if (isFirst) registerConversation(text);
      try {
        if (mode === "search") await streamSearch(text);
        else if (mode === "research") await streamResearch(text);
        else await streamChat({ message: text, viaVoice: opts?.viaVoice });
      } finally {
        busyRef.current = false;
        setBusy(false);
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [mode, messages.length, activeKbId, activeProjectId, settings],
  );

  const onSubmitForm = useCallback(
    async (formId: string, data: Record<string, unknown>) => {
      if (busyRef.current) return;
      busyRef.current = true;
      setBusy(true);
      setMessages((m) => m.map((x) => (x.pendingForm ? { ...x, pendingForm: undefined } : x)));
      try {
        await streamChat({ formSubmission: { form_id: formId, data } });
      } finally {
        busyRef.current = false;
        setBusy(false);
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [activeKbId, activeProjectId, settings],
  );

  const togglePin = useCallback((id: string) => {
    setMessages((m) => m.map((x) => (x.id === id ? { ...x, pinned: !x.pinned } : x)));
  }, []);

  const deleteMessage = useCallback(
    (id: string) => {
      if (!confirm(t.chat.confirmDeleteMsg)) return;
      setMessages((m) => m.filter((x) => x.id !== id));
    },
    [t],
  );

  const activeScope =
    kbs.find((k) => k.id === activeKbId)?.name || projects.find((p) => p.id === activeProjectId)?.name;

  return (
    <>
      <TopBar
        title={messages.length ? messages[0].content.slice(0, 48) : t.common.newChat}
        right={
          activeScope ? (
            <span className="badge rag">
              <Book /> {activeScope}
            </span>
          ) : mode !== "chat" ? (
            <span className="badge web">
              <Globe /> {mode === "search" ? t.chat.badgeSearch : t.chat.badgeResearch}
            </span>
          ) : null
        }
      />

      <div className="thread" ref={threadRef}>
        {messages.length === 0 ? (
          <div className="welcome">
            <span className="mark">
              <Book stroke="#fff" strokeWidth={1.6} />
            </span>
            <h2>{t.chat.welcomeTitle}</h2>
            <p>{t.chat.welcomeBody}</p>
            <div className="suggest">
              {SUGGESTIONS.map((s) => (
                <button key={s} onClick={() => onSend(s)}>
                  {s}
                </button>
              ))}
            </div>
          </div>
        ) : (
          <div className="thread-inner">
            {messages.map((m) => (
              <MessageBubble
                key={m.id}
                msg={m}
                onSubmitForm={onSubmitForm}
                onTogglePin={togglePin}
                onDelete={deleteMessage}
              />
            ))}
          </div>
        )}
      </div>

      <Composer mode={mode} setMode={setMode} onSend={onSend} busy={busy} speaking={speaking} />
    </>
  );
}
