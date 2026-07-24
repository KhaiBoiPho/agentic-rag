'use client';

import { memo, useState } from 'react';
import clsx from 'clsx';
import type { ResearchStep } from '@/lib/types';

const NODE_LABELS: Record<string, string> = {
  start: 'Bắt đầu',
  pre_search: 'Search trước (context)',
  prompt_expander: 'Mở rộng câu hỏi',
  web_searcher: 'Tìm kiếm trên web',
  content_aggregator: 'Tổng hợp nội dung',
  quality_checker: 'Kiểm tra chất lượng',
  response_generator: 'Soạn câu trả lời',
  done: 'Hoàn tất',
};

function ResearchPanelInner({
  steps,
  progress,
  running,
}: {
  steps: ResearchStep[];
  progress: number;
  running: boolean;
}) {
  const [open, setOpen] = useState(true);
  const pct = Math.round((progress ?? 0) * 100);

  return (
    <div className="mt-2 max-w-xl overflow-hidden rounded-xl border border-slate-200 dark:border-slate-700">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center justify-between gap-3 bg-slate-50 px-3 py-2 text-left dark:bg-slate-800/60"
      >
        <span className="flex items-center gap-2 text-xs font-medium text-slate-600 dark:text-slate-300">
          <span>🔎</span> Nghiên cứu {running ? 'đang chạy…' : 'đã hoàn tất'}
        </span>
        <span className="flex items-center gap-2">
          <span className="h-1.5 w-24 overflow-hidden rounded-full bg-slate-200 dark:bg-slate-700">
            <span
              className="block h-full rounded-full bg-brand-500 transition-all"
              style={{ width: `${pct}%` }}
            />
          </span>
          <span className="text-[11px] tabular-nums text-slate-500">{pct}%</span>
          <span className="text-slate-400">{open ? '▲' : '▼'}</span>
        </span>
      </button>
      {open && (
        <ul className="divide-y divide-slate-100 px-3 py-2 dark:divide-slate-800">
          {steps.map((s, i) => {
            const done = s.status === 'completed' || s.status === 'ready';
            return (
              <li key={`${s.node}-${i}`} className="flex items-start gap-2 py-1.5 text-xs">
                <span className={clsx('mt-0.5', done ? 'text-emerald-500' : 'text-brand-500 animate-pulse')}>
                  {done ? '✓' : '●'}
                </span>
                <div>
                  <div className="font-medium text-slate-700 dark:text-slate-200">
                    {NODE_LABELS[s.node] ?? s.node}
                  </div>
                  {s.content && <div className="text-slate-500">{s.content}</div>}
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

export default memo(ResearchPanelInner);
