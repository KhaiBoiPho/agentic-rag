'use client';

import clsx from 'clsx';
import Markdown from './Markdown';
import CostForm from './CostForm';
import ResearchPanel from './ResearchPanel';
import type { ChatMessage, SourceItem } from '@/lib/types';

function isDocSource(s: SourceItem): s is { chunk_id: string; document_name: string; content: string; score: number } {
  return 'document_name' in s;
}

function isWebSource(s: SourceItem): s is { url: string; title: string; snippet?: string } {
  return 'url' in s && !('document_name' in s);
}

function Badge({ message }: { message: ChatMessage }) {
  if (message.ragContext) {
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-emerald-100 px-2 py-0.5 text-[11px] font-medium text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300">
        📚 RAG · {message.ragContext.name}
      </span>
    );
  }
  if (message.webMode === 'research') {
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-sky-100 px-2 py-0.5 text-[11px] font-medium text-sky-700 dark:bg-sky-900/40 dark:text-sky-300">
        🌐 Nghiên cứu web
      </span>
    );
  }
  if (message.webMode === 'search') {
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-sky-100 px-2 py-0.5 text-[11px] font-medium text-sky-700 dark:bg-sky-900/40 dark:text-sky-300">
        🌐 Tìm kiếm web
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-medium text-slate-500 dark:bg-slate-800 dark:text-slate-400">
      Chat thường — không dùng RAG
    </span>
  );
}

export default function MessageBubble({
  message,
  onFormSubmit,
  formDisabled,
}: {
  message: ChatMessage;
  onFormSubmit?: (data: Record<string, unknown>) => void;
  formDisabled?: boolean;
}) {
  const isUser = message.role === 'user';
  const docSources = (message.sources ?? []).filter(isDocSource);
  const webSources = (message.sources ?? []).filter(isWebSource);

  return (
    <div className={clsx('flex w-full', isUser ? 'justify-end' : 'justify-start')}>
      <div className={clsx('max-w-2xl', isUser ? 'items-end' : 'items-start', 'flex flex-col gap-1')}>
        {!isUser && (
          <div className="flex items-center gap-2">
            <Badge message={message} />
            {message.viaVoice && <span className="text-[11px] text-slate-400">🎙️ giọng nói</span>}
          </div>
        )}
        <div
          className={clsx(
            'rounded-2xl px-4 py-2.5 text-sm shadow-sm',
            isUser
              ? 'bg-brand-600 text-white'
              : 'bg-white text-slate-800 dark:bg-slate-800 dark:text-slate-100',
          )}
        >
          {message.streaming ? (
            <p className="whitespace-pre-wrap break-words">{message.content || '…'}</p>
          ) : message.content ? (
            <Markdown content={message.content} sources={message.sources} />
          ) : null}
          {message.error && <p className="text-sm text-red-400">{message.error}</p>}
        </div>

        {message.researchSteps && message.researchSteps.length > 0 && (
          <ResearchPanel
            steps={message.researchSteps}
            progress={message.researchProgress ?? 0}
            running={!!message.streaming}
          />
        )}

        {message.pendingForm && onFormSubmit && (
          <CostForm form={message.pendingForm} onSubmit={onFormSubmit} disabled={formDisabled} />
        )}

        {docSources.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {docSources.map((s, i) => (
              <span
                key={i}
                title={s.content}
                className="inline-flex items-center gap-1 rounded-full border border-emerald-200 bg-emerald-50 px-2 py-0.5 text-[11px] text-emerald-700 dark:border-emerald-800 dark:bg-emerald-900/30 dark:text-emerald-300"
              >
                #{i + 1} {s.document_name} · {Math.round((s.score ?? 0) * 100)}%
              </span>
            ))}
          </div>
        )}

        {webSources.length > 0 && (
          <div className="max-w-xl rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-xs dark:border-slate-700 dark:bg-slate-800/60">
            <p className="mb-1 font-medium text-slate-500">Nguồn</p>
            <ol className="list-decimal space-y-0.5 pl-4">
              {webSources.map((s, i) => (
                <li key={i}>
                  <a
                    href={s.url}
                    target="_blank"
                    rel="noreferrer"
                    className="text-brand-600 hover:underline dark:text-brand-400"
                  >
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
