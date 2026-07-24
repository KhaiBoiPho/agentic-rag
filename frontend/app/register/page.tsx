'use client';

import { useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { api, ApiError } from '@/lib/api';
import { setTokens } from '@/lib/auth';
import type { TokenResponse } from '@/lib/types';

export default function RegisterPage() {
  const router = useRouter();
  const [fullName, setFullName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const res = await api.post<TokenResponse>('/api/v1/auth/register', {
        email,
        password,
        full_name: fullName || undefined,
      });
      setTokens(res.access_token, res.refresh_token);
      router.replace('/chat');
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Đăng ký thất bại');
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="gradient-mesh flex h-full items-center justify-center px-4">
      <div className="w-full max-w-sm rounded-2xl border border-hairline bg-canvas p-8 shadow-[0_8px_24px_rgba(0,55,112,0.08),0_2px_6px_rgba(0,55,112,0.04)] dark:border-slate-800 dark:bg-slate-900">
        <h1 className="text-xl font-semibold tracking-tight">Tạo tài khoản</h1>
        <p className="mt-1 text-sm text-slate-500">Agentic RAG — Trợ lý vật liệu xây dựng</p>
        <form onSubmit={onSubmit} className="mt-6 space-y-4">
          <div>
            <label className="mb-1 block text-sm font-medium">Họ tên</label>
            <input
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              className="w-full rounded-lg border border-slate-300 bg-transparent px-3 py-2 text-sm outline-none focus:border-brand-600 dark:border-slate-700"
              placeholder="Nguyễn Văn A"
            />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium">Email</label>
            <input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full rounded-lg border border-slate-300 bg-transparent px-3 py-2 text-sm outline-none focus:border-brand-600 dark:border-slate-700"
              placeholder="you@example.com"
            />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium">Mật khẩu</label>
            <input
              type="password"
              required
              minLength={8}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full rounded-lg border border-slate-300 bg-transparent px-3 py-2 text-sm outline-none focus:border-brand-600 dark:border-slate-700"
              placeholder="••••••••"
            />
          </div>
          {error && <p className="text-sm text-red-500">{error}</p>}
          <button
            type="submit"
            disabled={loading}
            className="w-full rounded-full bg-brand-600 px-3 py-2 text-sm font-medium text-white transition hover:bg-brand-700 disabled:opacity-60"
          >
            {loading ? 'Đang tạo…' : 'Đăng ký'}
          </button>
        </form>
        <p className="mt-4 text-center text-sm text-slate-500">
          Đã có tài khoản?{' '}
          <Link href="/login" className="font-medium text-brand-600 hover:underline dark:text-brand-400">
            Đăng nhập
          </Link>
        </p>
      </div>
    </div>
  );
}
