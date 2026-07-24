'use client';

import { useEffect, useState } from 'react';
import { api, ApiError } from '@/lib/api';
import type { NoteResponse } from '@/lib/types';

export default function NotesPage() {
  const [notes, setNotes] = useState<NoteResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    try {
      const res = await api.get<NoteResponse[]>('/api/v1/notes');
      setNotes(res.sort((a, b) => b.updated_at - a.updated_at));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Không thể tải ghi chú');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function createNote() {
    try {
      const note = await api.post<NoteResponse>('/api/v1/notes', { title: 'Ghi chú mới', content: '' });
      setNotes((prev) => [note, ...prev]);
    } catch (err) {
      alert(err instanceof ApiError ? err.message : 'Không thể tạo ghi chú');
    }
  }

  async function saveNote(id: string, patch: { title?: string; content?: string }) {
    setSaving(id);
    try {
      const updated = await api.patch<NoteResponse>(`/api/v1/notes/${id}`, patch);
      setNotes((prev) => prev.map((n) => (n.id === id ? updated : n)));
    } catch (err) {
      alert(err instanceof ApiError ? err.message : 'Không thể lưu');
    } finally {
      setSaving(null);
    }
  }

  async function removeNote(id: string) {
    if (!confirm('Xoá ghi chú này?')) return;
    try {
      await api.del(`/api/v1/notes/${id}`);
      setNotes((prev) => prev.filter((n) => n.id !== id));
    } catch (err) {
      alert(err instanceof ApiError ? err.message : 'Không thể xoá');
    }
  }

  return (
    <div className="h-full overflow-y-auto px-6 py-8">
      <div className="mx-auto max-w-3xl">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-xl font-semibold">Ghi chú</h1>
            <p className="mt-1 text-sm text-slate-500">Sổ tay cá nhân, không liên quan đến chat.</p>
          </div>
          <button
            onClick={createNote}
            className="rounded-full bg-brand-600 px-3 py-2 text-sm font-medium text-white hover:bg-brand-700"
          >
            + Ghi chú mới
          </button>
        </div>
        {error && <p className="mt-2 text-sm text-red-500">{error}</p>}

        {loading ? (
          <p className="mt-6 text-sm text-slate-400">Đang tải…</p>
        ) : (
          <div className="mt-6 grid gap-3 sm:grid-cols-2">
            {notes.map((n) => (
              <NoteCard key={n.id} note={n} onSave={saveNote} onDelete={removeNote} saving={saving === n.id} />
            ))}
            {notes.length === 0 && <p className="text-sm text-slate-400">Chưa có ghi chú nào.</p>}
          </div>
        )}
      </div>
    </div>
  );
}

function NoteCard({
  note,
  onSave,
  onDelete,
  saving,
}: {
  note: NoteResponse;
  onSave: (id: string, patch: { title?: string; content?: string }) => void;
  onDelete: (id: string) => void;
  saving: boolean;
}) {
  const [title, setTitle] = useState(note.title ?? '');
  const [content, setContent] = useState(note.content ?? '');

  return (
    <div className="flex flex-col gap-2 rounded-xl border border-slate-200 p-4 dark:border-slate-800">
      <input
        value={title}
        onChange={(e) => setTitle(e.target.value)}
        onBlur={() => title !== note.title && onSave(note.id, { title })}
        className="bg-transparent text-sm font-semibold outline-none"
        placeholder="Tiêu đề"
      />
      <textarea
        value={content}
        onChange={(e) => setContent(e.target.value)}
        onBlur={() => content !== note.content && onSave(note.id, { content })}
        rows={4}
        className="resize-none bg-transparent text-sm text-slate-600 outline-none dark:text-slate-300"
        placeholder="Nội dung…"
      />
      <div className="flex items-center justify-between text-xs text-slate-400">
        <span>{saving ? 'Đang lưu…' : ' '}</span>
        <button onClick={() => onDelete(note.id)} className="font-medium text-red-500 hover:underline">
          Xoá
        </button>
      </div>
    </div>
  );
}
