'use client';

import { useState } from 'react';
import Link from 'next/link';
import { api, ApiError } from '@/lib/api';
import { useAppStore } from '@/lib/store';
import type { KBResponse } from '@/lib/types';

export default function KbListPage() {
  const kbs = useAppStore((s) => s.kbs);
  const refreshKbs = useAppStore((s) => s.refreshKbs);
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);

  async function create(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim()) return;
    setCreating(true);
    setError(null);
    try {
      await api.post<KBResponse>('/api/v1/kb', { name: name.trim(), description: description.trim() || undefined });
      setName('');
      setDescription('');
      await refreshKbs();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Không thể tạo cơ sở tri thức');
    } finally {
      setCreating(false);
    }
  }

  async function remove(id: string) {
    if (!confirm('Xoá cơ sở tri thức này?')) return;
    try {
      await api.del(`/api/v1/kb/${id}`);
      await refreshKbs();
    } catch (err) {
      alert(err instanceof ApiError ? err.message : 'Không thể xoá');
    }
  }

  return (
    <div className="h-full overflow-y-auto px-6 py-8">
      <div className="mx-auto max-w-3xl">
        <h1 className="text-xl font-semibold">Cơ sở tri thức</h1>
        <p className="mt-1 text-sm text-slate-500">Quản lý các bộ tài liệu dùng cho truy hồi RAG.</p>

        <form onSubmit={create} className="mt-6 flex flex-wrap gap-2 rounded-xl border border-slate-200 p-4 dark:border-slate-800">
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Tên cơ sở tri thức"
            className="min-w-[180px] flex-1 rounded-lg border border-slate-300 bg-transparent px-3 py-2 text-sm outline-none focus:border-brand-600 dark:border-slate-700"
          />
          <input
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Mô tả (tuỳ chọn)"
            className="min-w-[180px] flex-1 rounded-lg border border-slate-300 bg-transparent px-3 py-2 text-sm outline-none focus:border-brand-600 dark:border-slate-700"
          />
          <button
            type="submit"
            disabled={creating || !name.trim()}
            className="rounded-full bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-60"
          >
            Tạo mới
          </button>
        </form>
        {error && <p className="mt-2 text-sm text-red-500">{error}</p>}

        <div className="mt-6 grid gap-3 sm:grid-cols-2">
          {kbs.map((kb) => (
            <div
              key={kb.id}
              className="flex flex-col justify-between rounded-xl border border-slate-200 p-4 dark:border-slate-800"
            >
              <div>
                <div className="flex items-center gap-2">
                  <Link href={`/kb/${kb.id}`} className="font-medium hover:underline">
                    {kb.name}
                  </Link>
                  {kb.is_system && (
                    <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-medium text-slate-500 dark:bg-slate-800">
                      hệ thống
                    </span>
                  )}
                </div>
                {kb.description && <p className="mt-1 text-xs text-slate-500">{kb.description}</p>}
                <p className="mt-2 text-xs text-slate-400">{kb.document_count} tài liệu</p>
              </div>
              {!kb.is_system && (
                <button
                  onClick={() => remove(kb.id)}
                  className="mt-3 self-start text-xs font-medium text-red-500 hover:underline"
                >
                  Xoá
                </button>
              )}
            </div>
          ))}
          {kbs.length === 0 && <p className="text-sm text-slate-400">Chưa có cơ sở tri thức nào.</p>}
        </div>
      </div>
    </div>
  );
}
