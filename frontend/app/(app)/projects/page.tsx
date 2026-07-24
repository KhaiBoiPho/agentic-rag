'use client';

import { useState } from 'react';
import { api, ApiError } from '@/lib/api';
import { useAppStore } from '@/lib/store';
import type { ProjectResponse } from '@/lib/types';

export default function ProjectsPage() {
  const projects = useAppStore((s) => s.projects);
  const kbs = useAppStore((s) => s.kbs);
  const refreshProjects = useAppStore((s) => s.refreshProjects);
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [editingKbs, setEditingKbs] = useState<string | null>(null);
  const [selectedKbIds, setSelectedKbIds] = useState<string[]>([]);

  async function create(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim()) return;
    setCreating(true);
    setError(null);
    try {
      await api.post<ProjectResponse>('/api/v1/projects', {
        name: name.trim(),
        description: description.trim() || undefined,
      });
      setName('');
      setDescription('');
      await refreshProjects();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Không thể tạo dự án');
    } finally {
      setCreating(false);
    }
  }

  async function remove(id: string) {
    if (!confirm('Xoá dự án này?')) return;
    try {
      await api.del(`/api/v1/projects/${id}`);
      await refreshProjects();
    } catch (err) {
      alert(err instanceof ApiError ? err.message : 'Không thể xoá');
    }
  }

  function openKbEditor(p: ProjectResponse) {
    setEditingKbs(p.id);
    setSelectedKbIds(p.kb_ids);
  }

  async function saveKbs(id: string) {
    try {
      await api.put<ProjectResponse>(`/api/v1/projects/${id}/knowledge-bases`, { kb_ids: selectedKbIds });
      setEditingKbs(null);
      await refreshProjects();
    } catch (err) {
      alert(err instanceof ApiError ? err.message : 'Không thể cập nhật');
    }
  }

  function toggleKb(id: string) {
    setSelectedKbIds((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
  }

  return (
    <div className="h-full overflow-y-auto px-6 py-8">
      <div className="mx-auto max-w-3xl">
        <h1 className="text-xl font-semibold">Dự án</h1>
        <p className="mt-1 text-sm text-slate-500">
          Gộp nhiều cơ sở tri thức để truy hồi RAG cùng lúc trong một dự án.
        </p>

        <form onSubmit={create} className="mt-6 flex flex-wrap gap-2 rounded-xl border border-slate-200 p-4 dark:border-slate-800">
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Tên dự án"
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

        <div className="mt-6 space-y-3">
          {projects.map((p) => (
            <div key={p.id} className="rounded-xl border border-slate-200 p-4 dark:border-slate-800">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="font-medium">{p.name}</p>
                  {p.description && <p className="text-xs text-slate-500">{p.description}</p>}
                  <p className="mt-1 text-xs text-slate-400">
                    {p.kb_names.length > 0 ? p.kb_names.join(', ') : 'Chưa gán cơ sở tri thức nào'}
                  </p>
                </div>
                <div className="flex shrink-0 gap-3 text-xs">
                  <button onClick={() => openKbEditor(p)} className="font-medium text-brand-600 hover:underline dark:text-brand-400">
                    Gán KB
                  </button>
                  <button onClick={() => remove(p.id)} className="font-medium text-red-500 hover:underline">
                    Xoá
                  </button>
                </div>
              </div>

              {editingKbs === p.id && (
                <div className="mt-3 rounded-lg border border-slate-200 p-3 dark:border-slate-700">
                  <div className="flex flex-wrap gap-2">
                    {kbs.map((kb) => (
                      <label
                        key={kb.id}
                        className="flex items-center gap-1.5 rounded-full border border-slate-200 px-2.5 py-1 text-xs dark:border-slate-700"
                      >
                        <input
                          type="checkbox"
                          checked={selectedKbIds.includes(kb.id)}
                          onChange={() => toggleKb(kb.id)}
                        />
                        {kb.name}
                      </label>
                    ))}
                  </div>
                  <div className="mt-3 flex gap-2">
                    <button
                      onClick={() => saveKbs(p.id)}
                      className="rounded-full bg-brand-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-brand-700"
                    >
                      Lưu
                    </button>
                    <button
                      onClick={() => setEditingKbs(null)}
                      className="rounded-lg border border-slate-300 px-3 py-1.5 text-xs dark:border-slate-700"
                    >
                      Huỷ
                    </button>
                  </div>
                </div>
              )}
            </div>
          ))}
          {projects.length === 0 && <p className="text-sm text-slate-400">Chưa có dự án nào.</p>}
        </div>
      </div>
    </div>
  );
}
