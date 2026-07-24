'use client';

import { useEffect, useRef, useState } from 'react';
import { ApiError, streamPost } from '@/lib/api';
import { useAppStore } from '@/lib/store';
import MessageBubble from './MessageBubble';
import Composer from './Composer';
import type { ChatMessage, ChatMode, ResearchStep } from '@/lib/types';

function upsertStep(steps: ResearchStep[], next: ResearchStep): ResearchStep[] {
  const idx = steps.findIndex((s) => s.node === next.node);
  if (idx === -1) return [...steps, next];
  const copy = steps.slice();
  copy[idx] = { ...copy[idx], ...next };
  return copy;
}

function buildContext(messages: ChatMessage[]): string {
  return messages
    .slice(-6)
    .map((m) => `${m.role === 'user' ? 'User' : 'Assistant'}: ${m.content}`)
    .join('\n');
}

export default function ChatView({ conversationId }: { conversationId: string }) {
  const kbs = useAppStore((s) => s.kbs);
  const projects = useAppStore((s) => s.projects);
  const activeKbId = useAppStore((s) => s.activeKbId);
  const activeProjectId = useAppStore((s) => s.activeProjectId);
  const model = useAppStore((s) => s.model);
  const temperature = useAppStore((s) => s.temperature);
  const maxTokens = useAppStore((s) => s.maxTokens);
  const upsertConversation = useAppStore((s) => s.upsertConversation);
  const storedMessages = useAppStore((s) => s.messagesByConversation[conversationId]);
  const setStoredMessages = useAppStore((s) => s.setMessages);

  const [messages, setMessages] = useState<ChatMessage[]>(storedMessages ?? []);
  const [mode, setMode] = useState<ChatMode>('chat');
  const [busy, setBusy] = useState(false);
  const listRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    setMessages(storedMessages ?? []);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [conversationId]);

  useEffect(() => {
    setStoredMessages(conversationId, messages);
    const el = listRef.current;
    if (el) el.scrollTop = el.scrollHeight;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [messages]);

  useEffect(() => {
    return () => abortRef.current?.abort();
  }, []);

  const activeKb = kbs.find((k) => k.id === activeKbId);
  const activeProject = projects.find((p) => p.id === activeProjectId);
  const scopeLabel = activeProject
    ? `Dự án: ${activeProject.name}`
    : activeKb
      ? `Cơ sở tri thức: ${activeKb.name}`
      : 'Chat thường — không dùng RAG';

  function patchMessage(id: string, patch: Partial<ChatMessage> | ((m: ChatMessage) => Partial<ChatMessage>)) {
    setMessages((prev) =>
      prev.map((m) => (m.id === id ? { ...m, ...(typeof patch === 'function' ? patch(m) : patch) } : m)),
    );
  }

  async function playTts(text: string) {
    try {
      const res = await fetch('/api/v1/voice/tts/stream', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${localStorage.getItem('agentic_access_token') ?? ''}`,
        },
        body: JSON.stringify({ text }),
      });
      if (!res.ok || !res.body) return;
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const audio = new Audio(url);
      audio.play().catch(() => {});
    } catch {
      // best-effort playback
    }
  }

  async function runChat(userText: string, viaVoice: boolean, formSubmission?: { form_id: string; data: object }) {
    const assistantId = crypto.randomUUID();
    setMessages((prev) => [
      ...prev,
      { id: assistantId, role: 'assistant', content: '', streaming: true },
    ]);

    const controller = new AbortController();
    abortRef.current = controller;
    let sawDocSource = false;

    try {
      await streamPost(
        '/api/v1/chat/stream',
        {
          message: formSubmission ? undefined : userText,
          conversation_id: conversationId,
          kb_id: activeProjectId ? null : activeKbId,
          project_id: activeProjectId,
          model,
          skill_id: null,
          temperature,
          max_tokens: maxTokens,
          use_rag: !!(activeKbId || activeProjectId),
          top_k: 5,
          score_threshold: 0.5,
          mode: 'agent',
          form_submission: formSubmission ?? null,
        },
        (evt) => {
          if (evt.type === 'text') {
            if (!evt.done) {
              patchMessage(assistantId, (m) => ({ content: m.content + (evt.delta ?? '') }));
            } else {
              const docSources = (evt.sources ?? []).filter((s: any) => 'document_name' in s);
              sawDocSource = docSources.length > 0;
              patchMessage(assistantId, {
                streaming: false,
                sources: evt.sources ?? [],
                ragContext: sawDocSource ? evt.rag_context ?? null : null,
                viaVoice,
              });
            }
          } else if (evt.type === 'form_request') {
            patchMessage(assistantId, {
              streaming: false,
              pendingForm: {
                form_id: evt.form_id,
                title: evt.title,
                fields: evt.fields ?? [],
                prefill: evt.prefill,
              },
            });
          }
        },
        { signal: controller.signal },
      );
      if (viaVoice) {
        setMessages((prev) => {
          const m = prev.find((x) => x.id === assistantId);
          if (m?.content) playTts(m.content);
          return prev;
        });
      }
    } catch (err) {
      patchMessage(assistantId, {
        streaming: false,
        error: err instanceof ApiError ? err.message : 'Đã xảy ra lỗi khi kết nối máy chủ.',
      });
    } finally {
      setBusy(false);
    }
  }

  async function runSearch(query: string) {
    const assistantId = crypto.randomUUID();
    setMessages((prev) => [
      ...prev,
      { id: assistantId, role: 'assistant', content: '', streaming: true, webMode: 'search' },
    ]);
    const context = buildContext(messages);
    const controller = new AbortController();
    abortRef.current = controller;
    try {
      await streamPost(
        '/api/v1/search/web',
        { query, max_results: 6, context },
        (evt) => {
          if (evt.type === 'sources') {
            patchMessage(assistantId, { sources: evt.sources ?? [] });
          } else if (evt.type === 'token') {
            patchMessage(assistantId, (m) => ({ content: m.content + (evt.delta ?? '') }));
          } else if (evt.type === 'done') {
            patchMessage(assistantId, { streaming: false });
          } else if (evt.error) {
            patchMessage(assistantId, { streaming: false, error: evt.error });
          }
        },
        { signal: controller.signal },
      );
    } catch (err) {
      patchMessage(assistantId, {
        streaming: false,
        error: err instanceof ApiError ? err.message : 'Đã xảy ra lỗi khi kết nối máy chủ.',
      });
    } finally {
      setBusy(false);
    }
  }

  async function runResearch(query: string) {
    const assistantId = crypto.randomUUID();
    setMessages((prev) => [
      ...prev,
      {
        id: assistantId,
        role: 'assistant',
        content: '',
        streaming: true,
        webMode: 'research',
        researchSteps: [],
        researchProgress: 0,
      },
    ]);
    const context = buildContext(messages);
    const controller = new AbortController();
    abortRef.current = controller;
    try {
      await streamPost(
        '/api/v1/research/stream',
        {
          query,
          max_iterations: 2,
          max_search_results: 6,
          quality_threshold: 0.75,
          search_first: true,
          context,
        },
        (evt) => {
          if (evt.node === 'response_generator' && evt.status === 'streaming') {
            patchMessage(assistantId, (m) => ({
              content: m.content + (evt.content ?? ''),
              researchProgress: evt.progress ?? m.researchProgress,
              researchSteps: upsertStep(m.researchSteps ?? [], {
                node: 'response_generator',
                status: 'started',
                content: 'Đang soạn câu trả lời…',
              }),
            }));
          } else if (evt.node === 'response_generator' && evt.status === 'completed') {
            patchMessage(assistantId, (m) => ({
              content: evt.content ?? m.content,
              sources: evt.sources ?? m.sources,
              researchProgress: evt.progress ?? m.researchProgress,
              researchSteps: upsertStep(m.researchSteps ?? [], {
                node: 'response_generator',
                status: 'completed',
                content: 'Đã soạn xong câu trả lời',
              }),
            }));
          } else if (evt.node === 'done' && evt.done) {
            patchMessage(assistantId, { streaming: false, researchProgress: 1 });
          } else if (evt.node) {
            patchMessage(assistantId, (m) => ({
              researchProgress: evt.progress ?? m.researchProgress,
              researchSteps: upsertStep(m.researchSteps ?? [], {
                node: evt.node,
                status: evt.status,
                content: evt.content,
                progress: evt.progress,
                iteration: evt.iteration,
                sources: evt.sources,
              }),
            }));
          }
        },
        { signal: controller.signal },
      );
    } catch (err) {
      patchMessage(assistantId, {
        streaming: false,
        error: err instanceof ApiError ? err.message : 'Đã xảy ra lỗi khi kết nối máy chủ.',
      });
    } finally {
      setBusy(false);
    }
  }

  function titleFrom(text: string): string {
    return text.length > 48 ? `${text.slice(0, 48)}…` : text;
  }

  async function handleSend(text: string, viaVoice = false) {
    setMessages((prev) => [...prev, { id: crypto.randomUUID(), role: 'user', content: text, viaVoice }]);
    upsertConversation(conversationId, titleFrom(text));
    setBusy(true);
    if (mode === 'search') await runSearch(text);
    else if (mode === 'research') await runResearch(text);
    else await runChat(text, viaVoice);
  }

  async function handleFormSubmit(assistantMsgId: string, data: Record<string, unknown>) {
    const formId = messages.find((m) => m.id === assistantMsgId)?.pendingForm?.form_id ?? 'construction_cost';
    patchMessage(assistantMsgId, { pendingForm: undefined });
    setBusy(true);
    await runChat('', false, { form_id: formId, data });
  }

  return (
    <div className="flex h-full flex-col bg-canvas dark:bg-[#212121]">
      <div ref={listRef} className="flex-1 overflow-y-auto px-4 py-6">
        <div className="mx-auto flex max-w-3xl flex-col gap-5">
          {messages.length === 0 && (
            <div className="mt-16 text-center text-ink-mute">
              <div className="mb-2 text-3xl">🏗️</div>
              <p className="text-sm">
                Hỏi về vật liệu xây dựng, dự toán chi phí, hoặc bật Search / Research để tra cứu trên web.
              </p>
            </div>
          )}
          {messages.map((m) => (
            <MessageBubble
              key={m.id}
              message={m}
              onFormSubmit={(data) => handleFormSubmit(m.id, data)}
              formDisabled={busy}
            />
          ))}
        </div>
      </div>
      <Composer
        mode={mode}
        onModeChange={setMode}
        onSend={(text) => handleSend(text)}
        onVoiceText={(text) => handleSend(text, true)}
        disabled={busy}
        scopeLabel={scopeLabel}
      />
    </div>
  );
}
