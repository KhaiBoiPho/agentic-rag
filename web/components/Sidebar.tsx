"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { clearTokens, currentEmail, getRefresh, initials } from "@/lib/auth";
import { modelLabel } from "@/lib/models";
import { useStore } from "@/lib/store";
import { tf, useT } from "@/lib/i18n";
import { useShell } from "./Shell";
import { Book, Chart, Chat, Folder, Gear, Logout, Note, PanelLeft, Plus } from "./Icons";

export default function Sidebar({ onNavigate }: { onNavigate?: () => void }) {
  const pathname = usePathname();
  const router = useRouter();
  const { t, lang } = useT();
  const { toggleSidebar, collapsed } = useShell();
  const NAV = [
    { href: "/chat", label: t.nav.chat, Icon: Chat },
    { href: "/notes", label: t.nav.notes, Icon: Note },
    { href: "/projects", label: t.nav.projects, Icon: Folder },
    { href: "/kb", label: t.nav.kb, Icon: Book },
    { href: "/usage", label: t.nav.usage, Icon: Chart },
    { href: "/settings", label: t.nav.settings, Icon: Gear },
  ];
  const kbs = useStore((s) => s.kbs);
  const projects = useStore((s) => s.projects);
  const conversations = useStore((s) => s.conversations);
  const activeKbId = useStore((s) => s.activeKbId);
  const activeProjectId = useStore((s) => s.activeProjectId);
  const setActiveKb = useStore((s) => s.setActiveKb);
  const setActiveProject = useStore((s) => s.setActiveProject);
  const model = useStore((s) => s.settings.model);

  const email = currentEmail();

  function newChat() {
    router.push(`/chat/${crypto.randomUUID()}`);
    onNavigate?.();
  }

  async function logout() {
    const refresh_token = getRefresh();
    try {
      if (refresh_token) await api.post("/api/v1/auth/logout", { refresh_token });
    } catch {
      /* ignore */
    }
    clearTokens();
    router.replace("/login");
  }

  return (
    <aside className={`side${collapsed ? " collapsed" : ""}`}>
      <div className="side-brand">
        <span className="mark">
          <Book stroke="#fff" strokeWidth={1.6} />
        </span>
        <span className="nm lbl-text">
          C<span className="accent">ố</span>t
        </span>
        <button
          className="side-toggle"
          onClick={toggleSidebar}
          aria-label={t.nav.toggleSidebar}
          title={t.nav.toggleSidebar}
        >
          <PanelLeft />
        </button>
      </div>

      <button className="newbtn" onClick={newChat} title={t.common.newChat}>
        <span style={{ display: "inline-flex", alignItems: "center", gap: 8 }}>
          <Plus width={16} height={16} /> <span className="lbl-text">{t.common.newChat}</span>
        </span>
        <kbd className="lbl-text">⌘K</kbd>
      </button>

      <nav className="nav">
        {NAV.map(({ href, label, Icon }) => {
          const on = pathname === href || pathname.startsWith(href + "/");
          return (
            <Link key={href} href={href} className={on ? "on" : ""} onClick={onNavigate} title={label}>
              <Icon />
              <span className="lbl-text">{label}</span>
            </Link>
          );
        })}
      </nav>

      <div className="side-scroll-groups">
        {kbs.length > 0 && (
          <div>
            <div className="glabel">
              {t.nav.kb} <span>{kbs.length}</span>
            </div>
            <div className="side-list">
              {kbs.map((kb) => (
                <button
                  key={kb.id}
                  className={`kb-row${activeKbId === kb.id ? " on" : ""}`}
                  onClick={() => setActiveKb(activeKbId === kb.id ? null : kb.id)}
                  title={kb.description || kb.name}
                >
                  <span className="sq" />
                  <span className="ellip">{kb.name}</span>
                  <span className="sys">{kb.is_system ? t.common.system : kb.document_count + (lang === "vi" ? " tệp" : " files")}</span>
                </button>
              ))}
            </div>
          </div>
        )}

        {projects.length > 0 && (
          <div>
            <div className="glabel">{t.nav.projects}</div>
            <div className="side-list">
              {projects.map((p) => (
                <button
                  key={p.id}
                  className={`kb-row${activeProjectId === p.id ? " on" : ""}`}
                  onClick={() => setActiveProject(activeProjectId === p.id ? null : p.id)}
                  title={tf(t.projects.kbCount, { n: p.kb_ids.length })}
                >
                  <span className="sq proj" />
                  <span className="ellip">{p.name}</span>
                  <span className="sys">{p.kb_ids.length} KB</span>
                </button>
              ))}
            </div>
          </div>
        )}

        {conversations.length > 0 && (
          <div>
            <div className="glabel">{t.nav.recent}</div>
            <div className="side-list">
              {conversations.slice(0, 12).map((c) => {
                const on = pathname === `/chat/${c.id}`;
                return (
                  <Link key={c.id} href={`/chat/${c.id}`} className={`conv-row${on ? " on" : ""}`} onClick={onNavigate}>
                    <span className="t">{on ? "▸" : "·"}</span>
                    <span className="ellip">{c.title}</span>
                  </Link>
                );
              })}
            </div>
          </div>
        )}
      </div>

      <div className="sidefoot">
        <span className="av">{initials(email)}</span>
        <div className="who-wrap lbl-text" style={{ minWidth: 0 }}>
          <div className="who ellip">{email.split("@")[0] || t.nav.user}</div>
          <div className="plan">{modelLabel(model)}</div>
        </div>
        <button className="logout" onClick={logout} aria-label={t.nav.logout} title={t.nav.logout}>
          <Logout width={16} height={16} />
        </button>
      </div>
    </aside>
  );
}
