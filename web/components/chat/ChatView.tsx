"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { apiFetch } from "@/lib/api";
import { streamSSE } from "@/lib/sse";
import { loadMessages, saveMessages, useStore } from "@/lib/store";
import { useT } from "@/lib/i18n";
import { sourceKind, type ChatMessage, type ChatMode, type ConversationHistoryResponse, type KB, type ResearchStep } from "@/lib/types";
import TopBar from "../TopBar";
import { Book, Bot, Globe } from "../Icons";
import MessageBubble from "./MessageBubble";
import Composer, { type SendOpts } from "./Composer";

// Tick rate for the typewriter reveal — independent of how fast the network
// delivers deltas, so bursty SSE chunks don't make the text "pop" in clumps.
const REVEAL_MS = 18;

// Sentinel id for the synthetic "still working" placeholder shown while
// catching up on a reply that finished generating after the user navigated
// away (see the history-reconcile effect below).
const CATCHUP_ID = "__catchup__";

/** Reconstruct display messages from the server's persisted history. Fields
 * that only ever existed transiently during a live stream (webMode, research
 * steps, pendingForm, per-message pin) aren't recoverable and are left unset
 * — see the backend endpoint's docstring for what is/isn't persisted. */
function historyToMessages(resp: ConversationHistoryResponse, kbs: KB[], ragFallbackLabel: string): ChatMessage[] {
  const kbName = resp.kb_id ? kbs.find((k) => k.id === resp.kb_id)?.name : undefined;
  return resp.messages.map((m) => {
    if (m.role === "user") {
      return { id: m.id, role: "user", content: m.content };
    }
    const sources = m.sources ?? [];
    // Persisted sources keep their normalized metadata (region, kind), so a
    // reloaded conversation shows the same regions it showed live — the
    // history round-trip used to be a second place where region was lost.
    const kinds = Array.from(new Set(sources.map(sourceKind)));
    const hasRag = kinds.includes("rag");
    return {
      id: m.id,
      role: "assistant",
      content: m.content,
      sources,
      sourceKinds: kinds,
      ragContext: hasRag ? { kind: "kb" as const, name: kbName ?? ragFallbackLabel } : null,
    };
  });
}

export default function ChatView({ conversationId }: { conversationId: string }) {
  const { t } = useT();
  // Lazy initializer re-runs per mount — ChatView is remounted per
  // conversation (key={id} in the route), so this correctly hydrates each
  // conversation's own saved history instead of always starting empty.
  const [messages, setMessages] = useState<ChatMessage[]>(() => loadMessages(conversationId));
  const [mode, setMode] = useState<ChatMode>("agentic");
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

  // Persist this conversation's messages (debounced — typewriter ticks
  // update `messages` up to ~55x/sec while streaming, so writing on every
  // change would hammer localStorage; a short debounce coalesces that).
  const saveMsgTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => {
    if (saveMsgTimer.current) clearTimeout(saveMsgTimer.current);
    saveMsgTimer.current = setTimeout(() => saveMessages(conversationId, messages), 400);
    return () => {
      if (saveMsgTimer.current) clearTimeout(saveMsgTimer.current);
    };
  }, [messages, conversationId]);

  // Reconcile with the server's persisted history on open — localStorage
  // gives an instant (if possibly stale/device-local) first paint above,
  // this fetch is the authoritative source and wins once it lands. A 404
  // (brand-new conversation, nothing sent yet) or a network failure just
  // leaves whatever local state is already showing.
  //
  // Navigating away mid-reply doesn't cancel the in-flight request (it's a
  // plain fetch with no AbortController, and client-side routing doesn't
  // unload the page) — the backend keeps generating and persists the reply
  // when it finishes, but the ChatView instance that was watching it is
  // long gone by then. If we land back on a conversation whose last turn is
  // a user message with no reply yet, that's exactly this situation: show
  // a "still working" placeholder and poll history until the reply lands
  // (or give up after ~30s — the reply is still safely in Postgres and
  // will show up next time the conversation is opened either way).
  //
  // Exception: an unsubmitted form (form_request) is the ONE case where
  // "last turn is a user message with no reply" is completely normal, not
  // interrupted — the backend only persists a construction_cost turn once
  // the form is actually submitted (see app/api/v1/chat.py), so an
  // in-progress form has no server-side counterpart at all. Reconciling
  // against server history here would silently delete the form (and the
  // catch-up poll above would then wait forever for a reply that was never
  // going to come). The local cache is strictly more complete in this one
  // case, so skip reconciliation entirely and keep it as-is.
  useEffect(() => {
    const cachedLast = loadMessages(conversationId).at(-1);
    if (cachedLast?.role === "assistant" && cachedLast.pendingForm && !cachedLast.formSubmittedData) {
      return;
    }

    let cancelled = false;
    let pollTimer: ReturnType<typeof setTimeout> | null = null;

    async function fetchHistory(): Promise<ConversationHistoryResponse | null> {
      try {
        const res = await apiFetch(`/api/v1/chat/history/${conversationId}`);
        if (!res.ok) return null;
        return (await res.json()) as ConversationHistoryResponse;
      } catch {
        return null;
      }
    }

    function pollForReply(attempt: number) {
      if (cancelled) return;
      if (attempt >= 12) {
        setMessages((m) => m.filter((x) => x.id !== CATCHUP_ID));
        return;
      }
      pollTimer = setTimeout(async () => {
        const data = await fetchHistory();
        if (cancelled) return;
        const last = data?.messages[data.messages.length - 1];
        if (last?.role === "assistant") {
          setMessages(historyToMessages(data!, useStore.getState().kbs, t.chat.historicalRag));
          return;
        }
        pollForReply(attempt + 1);
      }, 2500);
    }

    (async () => {
      const data = await fetchHistory();
      if (cancelled || !data || data.messages.length === 0) return;
      setMessages(historyToMessages(data, useStore.getState().kbs, t.chat.historicalRag));
      if (data.messages[data.messages.length - 1].role === "user") {
        setMessages((m) => [...m, { id: CATCHUP_ID, role: "assistant", content: "", streaming: true }]);
        pollForReply(0);
      }
    })();

    return () => {
      cancelled = true;
      if (pollTimer) clearTimeout(pollTimer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [conversationId]);

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

  // Bump the sidebar's "recent" ordering on every turn, not just the first
  // — the title is only overwritten when explicitly given (new conversation),
  // otherwise the existing stored title is preserved.
  function touchConversation(title?: string) {
    const existing = useStore.getState().conversations.find((c) => c.id === conversationId);
    upsertConversation({
      id: conversationId,
      title: title ? title.slice(0, 60) : (existing?.title ?? conversationId),
      updated_at: Math.floor(Date.now() / 1000),
    });
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
    agentic?: boolean;
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
      // Agentic mode ignores the KB/project picker: it retrieves across every
      // knowledge base (the backend resolves `all_kbs`, so a KB created after
      // this page loaded is included) and may call the price/cost tools.
      use_rag: opts.agentic ? true : !!(activeKbId || activeProjectId),
      all_kbs: !!opts.agentic,
      top_k: settings.top_k,
      score_threshold: 0.5,
      // "auto" lets the Request Router decide (price → tool, narrative → RAG,
      // mixed → both). "rag" still exists as an explicit RAG-only override for
      // any client that wants it; we no longer send it by default, because it
      // is precisely the mode in which a price question is answered out of a
      // retrieved chunk.
      mode: opts.agentic ? "agent" : "auto",
      form_submission: opts.formSubmission ?? null,
      via_voice: !!opts.viaVoice,
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
            finalize(aId, {
              streaming: false,
              sources: ev.sources ?? [],
              ragContext: rc,
              sourceKinds: ev.source_kinds ?? undefined,
              route: ev.route ?? undefined,
            });
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
      touchConversation(isFirst ? text : undefined);
      try {
        if (mode === "search") await streamSearch(text);
        else if (mode === "research") await streamResearch(text);
        else await streamChat({ message: text, viaVoice: opts?.viaVoice, agentic: mode === "agentic" });
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
      // keep the form visible but locked, showing what was submitted —
      // rather than blanking the bubble out to an empty husk
      setMessages((m) => m.map((x) => (x.pendingForm && !x.formSubmittedData ? { ...x, formSubmittedData: data } : x)));
      touchConversation();
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
          ) : mode === "agentic" ? (
            <span className="badge web">
              <Bot /> {t.chat.badgeAgentic}
            </span>
          ) : (
            <span className="badge web">
              <Globe /> {mode === "search" ? t.chat.badgeSearch : t.chat.badgeResearch}
            </span>
          )
        }
      />

      <div className="thread" ref={threadRef}>
        {messages.length === 0 ? (
          <div className="welcome">
            <span className="mark">
              <Bot strokeWidth={1.6} />
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
