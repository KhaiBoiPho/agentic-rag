'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { api, ApiError } from '@/lib/api';
import { useAppStore } from '@/lib/store';
import type { DocumentItem, IngestJobResponse } from '@/lib/types';

const STATUS_LABEL: Record<string, string> = {
  pending: 'Đang chờ',
  processing: 'Đang xử lý',
  done: 'Hoàn tất',
  error: 'Lỗi',
};

export default function KbDetailPage({ params }: { params: { id: string } }) {
  const kbs = useAppStore((s) => s.kbs);
  const refreshKbs = useAppStore((s) => s.refreshKbs);
  const kb = kbs.find((k) => k.id === params.id);

  const [docs, setDocs] = useState<DocumentItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const load = useCallback(async () => {
    try {
      const res = await api.get<{ total: number; documents: DocumentItem[] }>(
        `/api/v1/documents/${params.id}?limit=200`,
      );
      setDocs(res.documents);
      setTotal(res.total);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Không thể tải tài liệu');
    } finally {
      setLoading(false);
    }
  }, [params.id]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    const hasPending = docs.some((d) => d.status === 'pending' || d.status === 'processing');
    if (hasPending && !pollRef.current) {
      pollRef.current = setInterval(load, 3000);
    }
    if (!hasPending && pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
    return () => {
      if (pollRef.current) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
    };
  }, [docs, load]);

  async function onUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    setError(null);
    try {
      const form = new FormData();
      form.append('file', file);
      await api.upload<IngestJobResponse>(`/api/v1/documents/upload/${params.id}`, form);
      await load();
      await refreshKbs();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Tải lên thất bại');
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  }

  async function remove(docId: string) {
    if (!confirm('Xoá tài liệu này?')) return;
    try {
      await api.del(`/api/v1/documents/${docId}`);
      await load();
      await refreshKbs();
    } catch (err) {
      alert(err instanceof ApiError ? err.message : 'Không thể xoá');
    }
  }

  return (
    <div className="h-full overflow-y-auto px-6 py-8">
      <div className="mx-auto max-w-3xl">
        <Link href="/kb" className="text-xs text-slate-400 hover:underline">
          ← Cơ sở tri thức
        </Link>
        <div className="mt-1 flex items-center gap-2">
          <h1 className="text-xl font-semibold">{kb?.name ?? 'Đang tải…'}</h1>
          {kb?.is_system && (
            <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-medium text-slate-500 dark:bg-slate-800">
              hệ thống — chỉ đọc
            </span>
          )}
        </div>
        {kb?.description && <p className="mt-1 text-sm text-slate-500">{kb.description}</p>}

        {!kb?.is_system && (
          <div className="mt-6 rounded-xl border border-dashed border-slate-300 p-4 text-sm dark:border-slate-700">
            <label className="flex cursor-pointer items-center gap-2">
              <input ref={fileInputRef} type="file" onChange={onUpload} disabled={uploading} className="hidden" />
              <span className="rounded-full bg-brand-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-brand-700">
                {uploading ? 'Đang tải lên…' : 'Tải lên tài liệu'}
              </span>
              <span className="text-xs text-slate-400">PDF, DOCX, TXT…</span>
            </label>
          </div>
        )}
        {error && <p className="mt-2 text-sm text-red-500">{error}</p>}

        <div className="mt-6">
          <p className="mb-2 text-xs font-medium text-slate-400">{total} tài liệu</p>
          {loading ? (
            <p className="text-sm text-slate-400">Đang tải…</p>
          ) : (
            <div className="divide-y divide-slate-100 rounded-xl border border-slate-200 dark:divide-slate-800 dark:border-slate-800">
              {docs.map((d) => (
                <div key={d.id} className="flex items-center justify-between px-4 py-2.5 text-sm">
                  <div className="min-w-0">
                    <p className="truncate font-medium">{d.filename}</p>
                    <p className="text-xs text-slate-400">{d.chunk_count} đoạn</p>
                  </div>
                  <div className="flex items-center gap-3">
                    <span
                      className={
                        d.status === 'done'
                          ? 'text-xs font-medium text-emerald-600'
                          : d.status === 'error'
                            ? 'text-xs font-medium text-red-500'
                            : 'text-xs font-medium text-amber-500'
                      }
                    >
                      {STATUS_LABEL[d.status] ?? d.status}
                    </span>
                    {!kb?.is_system && (
                      <button onClick={() => remove(d.id)} className="text-xs text-red-500 hover:underline">
                        Xoá
                      </button>
                    )}
                  </div>
                </div>
              ))}
              {docs.length === 0 && <p className="px-4 py-6 text-center text-sm text-slate-400">Chưa có tài liệu.</p>}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
