'use client';

import { useState } from 'react';
import type { PendingForm } from '@/lib/types';

const FIELD_LABELS: Record<string, string> = {
  area_per_floor_m2: 'Diện tích sàn mỗi tầng (m²)',
  num_floors: 'Số tầng',
  region: 'Khu vực',
  finish_level: 'Mức hoàn thiện',
};

const REGION_OPTIONS = [
  { value: 'HN', label: 'Hà Nội' },
  { value: 'DN', label: 'Đà Nẵng' },
  { value: 'HCM', label: 'TP. Hồ Chí Minh' },
];

const FINISH_OPTIONS = [
  { value: 'tho', label: 'Nhà thô' },
  { value: 'hoan_thien_co_ban', label: 'Hoàn thiện cơ bản' },
  { value: 'hoan_thien_cao_cap', label: 'Hoàn thiện cao cấp' },
];

export default function CostForm({
  form,
  onSubmit,
  disabled,
}: {
  form: PendingForm;
  onSubmit: (data: Record<string, unknown>) => void;
  disabled?: boolean;
}) {
  const initial: Record<string, unknown> = {
    area_per_floor_m2: form.prefill?.area_per_floor_m2 ?? '',
    num_floors: form.prefill?.num_floors ?? 1,
    region: form.prefill?.region ?? 'HN',
    finish_level: form.prefill?.finish_level ?? 'hoan_thien_co_ban',
  };
  const [data, setData] = useState<Record<string, unknown>>(initial);

  const fields =
    form.fields && form.fields.length > 0
      ? form.fields
      : [
          { name: 'area_per_floor_m2', type: 'number', required: true },
          { name: 'num_floors', type: 'number', required: true, default: 1 },
          { name: 'region', type: 'select', required: true, options: REGION_OPTIONS },
          { name: 'finish_level', type: 'select', default: 'hoan_thien_co_ban', options: FINISH_OPTIONS },
        ];

  function update(name: string, value: unknown) {
    setData((d) => ({ ...d, [name]: value }));
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    onSubmit(data);
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="mt-2 max-w-md space-y-3 rounded-xl border border-slate-200 bg-slate-50 p-4 dark:border-slate-700 dark:bg-slate-800/60"
    >
      <p className="text-sm font-semibold">{form.title || 'Dự toán chi phí xây dựng'}</p>
      {fields.map((f) => {
        const label = f.label || FIELD_LABELS[f.name] || f.name;
        if (f.name === 'region' || f.type === 'select') {
          const options = f.options ?? (f.name === 'finish_level' ? FINISH_OPTIONS : REGION_OPTIONS);
          return (
            <div key={f.name}>
              <label className="mb-1 block text-xs font-medium text-slate-600 dark:text-slate-300">{label}</label>
              <select
                value={String(data[f.name] ?? '')}
                onChange={(e) => update(f.name, e.target.value)}
                required={f.required}
                className="w-full rounded-md border border-slate-300 bg-white px-2 py-1.5 text-sm dark:border-slate-600 dark:bg-slate-900"
              >
                {options.map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </select>
            </div>
          );
        }
        return (
          <div key={f.name}>
            <label className="mb-1 block text-xs font-medium text-slate-600 dark:text-slate-300">{label}</label>
            <input
              type="number"
              required={f.required}
              value={String(data[f.name] ?? '')}
              onChange={(e) => update(f.name, e.target.value === '' ? '' : Number(e.target.value))}
              className="w-full rounded-md border border-slate-300 bg-white px-2 py-1.5 text-sm dark:border-slate-600 dark:bg-slate-900"
            />
          </div>
        );
      })}
      <button
        type="submit"
        disabled={disabled}
        className="rounded-lg bg-brand-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-60"
      >
        Tính toán
      </button>
    </form>
  );
}
