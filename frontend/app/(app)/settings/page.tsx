'use client';

import { useAppStore } from '@/lib/store';
import { MODEL_TIERS } from '@/lib/types';

export default function SettingsPage() {
  const model = useAppStore((s) => s.model);
  const temperature = useAppStore((s) => s.temperature);
  const maxTokens = useAppStore((s) => s.maxTokens);
  const setModel = useAppStore((s) => s.setModel);
  const setTemperature = useAppStore((s) => s.setTemperature);
  const setMaxTokens = useAppStore((s) => s.setMaxTokens);

  return (
    <div className="h-full overflow-y-auto px-6 py-8">
      <div className="mx-auto max-w-xl">
        <h1 className="text-xl font-semibold">Cài đặt</h1>
        <p className="mt-1 text-sm text-slate-500">Áp dụng cho các tin nhắn mới.</p>

        <div className="mt-6">
          <label className="mb-2 block text-sm font-medium">Model</label>
          <div className="space-y-3">
            {MODEL_TIERS.map((tier) => (
              <div key={tier.tier}>
                <p className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-slate-400">{tier.tier}</p>
                <div className="flex flex-wrap gap-2">
                  {tier.models.map((m) => (
                    <button
                      key={m.id}
                      onClick={() => setModel(m.id)}
                      className={`rounded-lg border px-3 py-1.5 text-xs font-medium transition ${
                        model === m.id
                          ? 'border-brand-500 bg-brand-50 text-brand-700 dark:bg-brand-900/40 dark:text-brand-300'
                          : 'border-slate-200 text-slate-600 hover:bg-slate-50 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800'
                      }`}
                    >
                      {m.label}
                    </button>
                  ))}
                </div>
              </div>
            ))}
          </div>
          <p className="mt-2 text-xs text-slate-400">Đang chọn: {model}</p>
        </div>

        <div className="mt-8">
          <label className="mb-2 flex items-center justify-between text-sm font-medium">
            Temperature <span className="text-slate-400">{temperature.toFixed(1)}</span>
          </label>
          <input
            type="range"
            min={0}
            max={2}
            step={0.1}
            value={temperature}
            onChange={(e) => setTemperature(Number(e.target.value))}
            className="w-full"
          />
        </div>

        <div className="mt-6">
          <label className="mb-2 block text-sm font-medium">Max tokens</label>
          <input
            type="number"
            min={64}
            max={8192}
            step={64}
            value={maxTokens}
            onChange={(e) => setMaxTokens(Number(e.target.value))}
            className="w-40 rounded-lg border border-slate-300 bg-transparent px-3 py-2 text-sm outline-none focus:border-brand-500 dark:border-slate-700"
          />
        </div>
      </div>
    </div>
  );
}
