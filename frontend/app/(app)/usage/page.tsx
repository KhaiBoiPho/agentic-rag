'use client';

import { useEffect, useState } from 'react';
import { api, ApiError } from '@/lib/api';
import type { UsageResponse } from '@/lib/types';

function fmtUsd(n: number): string {
  return `$${n.toFixed(4)}`;
}

function fmtMs(n: number): string {
  return n >= 1000 ? `${(n / 1000).toFixed(2)}s` : `${Math.round(n)}ms`;
}

export default function UsagePage() {
  const [usage, setUsage] = useState<UsageResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .get<UsageResponse>('/api/v1/usage')
      .then(setUsage)
      .catch((err) => setError(err instanceof ApiError ? err.message : 'Không thể tải dữ liệu sử dụng'));
  }, []);

  if (error) {
    return (
      <div className="h-full overflow-y-auto px-6 py-8">
        <p className="text-sm text-red-500">{error}</p>
      </div>
    );
  }
  if (!usage) {
    return (
      <div className="h-full overflow-y-auto px-6 py-8">
        <p className="text-sm text-slate-400">Đang tải…</p>
      </div>
    );
  }

  const maxCost = Math.max(...usage.daily.map((d) => d.cost_usd), 0.0001);

  return (
    <div className="h-full overflow-y-auto px-6 py-8">
      <div className="mx-auto max-w-4xl">
        <h1 className="text-xl font-semibold">Sử dụng</h1>
        <p className="mt-1 text-sm text-slate-500">Chi phí và lưu lượng sử dụng LLM.</p>

        <div className="mt-6 grid grid-cols-2 gap-3 sm:grid-cols-4">
          <StatCard label="Tổng chi phí" value={fmtUsd(usage.total_cost_usd)} />
          <StatCard label="Tổng tin nhắn" value={usage.total_messages.toLocaleString()} />
          <StatCard label="Chi phí TB / tin" value={fmtUsd(usage.avg_cost_usd)} />
          <StatCard label="Thời gian TB" value={fmtMs(usage.avg_duration_ms)} />
          <StatCard label="Prompt tokens" value={usage.total_prompt_tokens.toLocaleString()} />
          <StatCard label="Completion tokens" value={usage.total_completion_tokens.toLocaleString()} />
          <StatCard label="Tổng thời gian" value={fmtMs(usage.total_duration_ms)} />
        </div>

        <div className="mt-8">
          <h2 className="mb-3 text-sm font-semibold text-slate-600 dark:text-slate-300">Chi phí theo ngày</h2>
          <div className="flex h-40 items-end gap-1.5 rounded-xl border border-slate-200 p-4 dark:border-slate-800">
            {usage.daily.map((d) => (
              <div key={d.date} className="flex flex-1 flex-col items-center gap-1" title={`${d.date}: ${fmtUsd(d.cost_usd)}`}>
                <div
                  className="w-full rounded-t bg-brand-500"
                  style={{ height: `${Math.max((d.cost_usd / maxCost) * 100, 2)}%` }}
                />
                <span className="rotate-0 text-[9px] text-slate-400">{d.date.slice(5)}</span>
              </div>
            ))}
            {usage.daily.length === 0 && <p className="text-sm text-slate-400">Chưa có dữ liệu.</p>}
          </div>
        </div>

        <div className="mt-8">
          <h2 className="mb-3 text-sm font-semibold text-slate-600 dark:text-slate-300">Lịch sử</h2>
          <div className="overflow-x-auto rounded-xl border border-slate-200 dark:border-slate-800">
            <table className="w-full text-left text-xs">
              <thead className="bg-slate-50 text-slate-500 dark:bg-slate-800/60">
                <tr>
                  <th className="px-3 py-2">Model</th>
                  <th className="px-3 py-2">Prompt</th>
                  <th className="px-3 py-2">Completion</th>
                  <th className="px-3 py-2">Chi phí</th>
                  <th className="px-3 py-2">Thời gian</th>
                  <th className="px-3 py-2">Lúc</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                {usage.history.map((h) => (
                  <tr key={h.id}>
                    <td className="px-3 py-2 font-medium">{h.model}</td>
                    <td className="px-3 py-2">{h.prompt_tokens}</td>
                    <td className="px-3 py-2">{h.completion_tokens}</td>
                    <td className="px-3 py-2">{fmtUsd(h.cost_usd)}</td>
                    <td className="px-3 py-2">{fmtMs(h.duration_ms)}</td>
                    <td className="px-3 py-2 text-slate-400">
                      {new Date(h.created_at * 1000).toLocaleString('vi-VN')}
                    </td>
                  </tr>
                ))}
                {usage.history.length === 0 && (
                  <tr>
                    <td colSpan={6} className="px-3 py-6 text-center text-slate-400">
                      Chưa có lịch sử.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}

function StatCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-slate-200 p-3 dark:border-slate-800">
      <p className="text-[11px] text-slate-400">{label}</p>
      <p className="mt-1 text-base font-semibold">{value}</p>
    </div>
  );
}
