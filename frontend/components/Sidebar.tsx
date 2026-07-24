'use client';

import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import clsx from 'clsx';
import { useAppStore } from '@/lib/store';
import { clearTokens, decodeJwt, getAccessToken } from '@/lib/auth';

const NAV = [
  { href: '/chat', label: 'Trò chuyện', icon: '💬' },
  { href: '/notes', label: 'Ghi chú', icon: '📝' },
  { href: '/projects', label: 'Dự án', icon: '📁' },
  { href: '/kb', label: 'Cơ sở tri thức', icon: '📚' },
  { href: '/usage', label: 'Sử dụng', icon: '📊' },
  { href: '/settings', label: 'Cài đặt', icon: '⚙️' },
];

export default function Sidebar() {
  const pathname = usePathname();
  const router = useRouter();
  const kbs = useAppStore((s) => s.kbs);
  const projects = useAppStore((s) => s.projects);
  const conversations = useAppStore((s) => s.conversations);
  const activeKbId = useAppStore((s) => s.activeKbId);
  const activeProjectId = useAppStore((s) => s.activeProjectId);
  const setActiveKb = useAppStore((s) => s.setActiveKb);
  const setActiveProject = useAppStore((s) => s.setActiveProject);

  const token = getAccessToken();
  const email = token ? decodeJwt(token)?.email : null;

  function newChat() {
    const id = crypto.randomUUID();
    router.push(`/chat/${id}`);
  }

  function logout() {
    clearTokens();
    router.replace('/login');
  }

  return (
    <aside className="flex h-full w-72 shrink-0 flex-col bg-sidebar text-sidebar-text">
      <div className="flex items-center gap-2 px-3 py-3">
        <div className="flex h-8 w-8 items-center justify-center rounded-full bg-white/10 text-base">🏗️</div>
        <div className="text-sm font-semibold leading-tight">
          Agentic RAG
          <div className="text-xs font-normal text-sidebar-mute">Vật liệu xây dựng</div>
        </div>
      </div>

      <div className="px-3">
        <button
          onClick={newChat}
          className="flex w-full items-center gap-2 rounded-lg border border-sidebar-border px-3 py-2 text-sm font-medium transition hover:bg-sidebar-hover"
        >
          <span className="text-base leading-none">＋</span> Trò chuyện mới
        </button>
      </div>

      <nav className="mt-2 px-2">
        {NAV.map((item) => (
          <Link
            key={item.href}
            href={item.href}
            className={clsx(
              'flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm transition',
              pathname === item.href || pathname.startsWith(item.href + '/')
                ? 'bg-sidebar-active text-white'
                : 'text-sidebar-text/90 hover:bg-sidebar-hover',
            )}
          >
            <span className="text-[15px]">{item.icon}</span>
            {item.label}
          </Link>
        ))}
      </nav>

      <div className="mt-4 flex-1 overflow-y-auto px-3 pb-4">
        <SidebarSection title="Phạm vi RAG">
          <button
            onClick={() => {
              setActiveKb(null);
              setActiveProject(null);
            }}
            className={clsx(
              'block w-full truncate rounded-md px-2 py-1.5 text-left text-xs',
              !activeKbId && !activeProjectId
                ? 'bg-sidebar-active text-white'
                : 'text-sidebar-mute hover:bg-sidebar-hover',
            )}
          >
            Không dùng RAG (chat thường)
          </button>
          {projects.map((p) => (
            <button
              key={p.id}
              onClick={() => setActiveProject(p.id)}
              className={clsx(
                'block w-full truncate rounded-md px-2 py-1.5 text-left text-xs',
                activeProjectId === p.id
                  ? 'bg-sidebar-active text-white'
                  : 'text-sidebar-mute hover:bg-sidebar-hover',
              )}
              title={p.name}
            >
              📁 {p.name}
            </button>
          ))}
          {kbs.map((kb) => (
            <button
              key={kb.id}
              onClick={() => setActiveKb(kb.id)}
              className={clsx(
                'block w-full truncate rounded-md px-2 py-1.5 text-left text-xs',
                activeKbId === kb.id
                  ? 'bg-sidebar-active text-white'
                  : 'text-sidebar-mute hover:bg-sidebar-hover',
              )}
              title={kb.name}
            >
              📚 {kb.name}
            </button>
          ))}
        </SidebarSection>

        <SidebarSection title="Cuộc trò chuyện gần đây">
          {conversations.length === 0 && (
            <p className="px-2 text-xs text-sidebar-mute">Chưa có cuộc trò chuyện nào</p>
          )}
          {conversations.map((c) => (
            <Link
              key={c.id}
              href={`/chat/${c.id}`}
              className={clsx(
                'block truncate rounded-md px-2 py-1.5 text-xs',
                pathname === `/chat/${c.id}`
                  ? 'bg-sidebar-active text-white'
                  : 'text-sidebar-mute hover:bg-sidebar-hover',
              )}
              title={c.title}
            >
              {c.title || 'Cuộc trò chuyện mới'}
            </Link>
          ))}
        </SidebarSection>
      </div>

      <div className="flex items-center justify-between border-t border-sidebar-border px-4 py-3 text-xs text-sidebar-mute">
        <span className="truncate" title={email ?? undefined}>
          {email ?? 'Người dùng'}
        </span>
        <button onClick={logout} className="font-medium text-sidebar-text hover:underline">
          Đăng xuất
        </button>
      </div>
    </aside>
  );
}

function SidebarSection({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="mb-4">
      <div className="mb-1 px-2 text-[11px] font-semibold uppercase tracking-wide text-sidebar-mute">{title}</div>
      <div className="space-y-0.5">{children}</div>
    </div>
  );
}
