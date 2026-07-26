"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useStore } from "@/lib/store";
import { ago } from "@/lib/format";
import { tf, useT } from "@/lib/i18n";
import TopBar from "@/components/TopBar";
import { Plus, Trash } from "@/components/Icons";
import type { Project } from "@/lib/types";

export default function ProjectsPage() {
  const { t, lang } = useT();
  const kbs = useStore((s) => s.kbs);
  const projects = useStore((s) => s.projects);
  const loadProjects = useStore((s) => s.loadProjects);

  const [editing, setEditing] = useState<Project | "new" | null>(null);
  const [name, setName] = useState("");
  const [desc, setDesc] = useState("");
  const [kbIds, setKbIds] = useState<string[]>([]);

  useEffect(() => {
    loadProjects().catch(() => {});
  }, [loadProjects]);

  function open(p: Project | "new") {
    setEditing(p);
    if (p === "new") {
      setName("");
      setDesc("");
      setKbIds([]);
    } else {
      setName(p.name);
      setDesc(p.description || "");
      setKbIds(p.kb_ids);
    }
  }

  function toggleKb(id: string) {
    setKbIds((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]));
  }

  async function save() {
    if (editing === "new") {
      const p = await api.post<Project>("/api/v1/projects", { name, description: desc || undefined });
      await api.put(`/api/v1/projects/${p.id}/knowledge-bases`, { kb_ids: kbIds });
    } else if (editing) {
      await api.patch(`/api/v1/projects/${editing.id}`, { name, description: desc || undefined });
      await api.put(`/api/v1/projects/${editing.id}/knowledge-bases`, { kb_ids: kbIds });
    }
    setEditing(null);
    await loadProjects();
  }

  async function remove(id: string) {
    if (!confirm(t.projects.confirmDelete)) return;
    await api.del(`/api/v1/projects/${id}`);
    await loadProjects();
  }

  return (
    <>
      <TopBar title={t.projects.title} />
      <div className="page">
        <div className="page-inner">
          <div className="page-head">
            <div>
              <h2>{t.projects.title}</h2>
              <p>{t.projects.subtitle}</p>
            </div>
            <button className="btn btn-primary" onClick={() => open("new")}>
              <Plus /> {t.projects.create}
            </button>
          </div>

          {editing && (
            <div className="settings-group">
              <div className="field" style={{ marginBottom: 12 }}>
                <label>{t.projects.name} <span className="req">*</span></label>
                <input className="control" value={name} onChange={(e) => setName(e.target.value)} placeholder={t.projects.namePh} />
              </div>
              <div className="field" style={{ marginBottom: 16 }}>
                <label>{t.projects.description}</label>
                <input className="control" value={desc} onChange={(e) => setDesc(e.target.value)} />
              </div>
              <div style={{ fontFamily: "var(--f-mono)", fontSize: 10, letterSpacing: ".1em", textTransform: "uppercase", color: "var(--muted)", marginBottom: 8 }}>
                {t.projects.kbsInProject}
              </div>
              <div className="model-opts" style={{ marginBottom: 16 }}>
                {kbs.map((kb) => (
                  <button key={kb.id} className={`model-opt${kbIds.includes(kb.id) ? " on" : ""}`} onClick={() => toggleKb(kb.id)} type="button">
                    {kb.name}
                    <span className="mid">{kb.is_system ? t.common.system : kb.document_count + (lang === "vi" ? " tệp" : " files")}</span>
                  </button>
                ))}
              </div>
              <div style={{ display: "flex", gap: 10 }}>
                <button className="btn btn-primary" onClick={save} disabled={!name.trim()}>{t.common.save}</button>
                <button className="btn btn-ghost" onClick={() => setEditing(null)}>{t.common.cancel}</button>
              </div>
            </div>
          )}

          <div className="list-grid">
            {projects.map((p) => (
              <div className="item-card" key={p.id}>
                <div className="row1">
                  <span className="sq" style={{ background: "var(--good)" }} />
                  <h3>{p.name}</h3>
                </div>
                <div className="desc">{p.description || "—"}</div>
                <div className="desc" style={{ fontSize: "var(--fs-xs)", color: "var(--faint)" }}>
                  {p.kb_names.join(" · ") || t.projects.noKbs}
                </div>
                <div className="foot">
                  <span>{tf(t.projects.kbCount, { n: p.kb_ids.length })} · {ago(p.updated_at)}</span>
                  <span className="actions">
                    <button className="btn btn-ghost btn-sm" onClick={() => open(p)}>{t.common.edit}</button>
                    <button className="icon-x" onClick={() => remove(p.id)} aria-label={t.common.delete}>
                      <Trash width={15} height={15} />
                    </button>
                  </span>
                </div>
              </div>
            ))}
          </div>
          {projects.length === 0 && !editing && <div className="empty">{t.projects.empty}</div>}
        </div>
      </div>
    </>
  );
}
