"use client";

import { useState } from "react";
import Link from "next/link";
import { api, ApiError } from "@/lib/api";
import { useStore } from "@/lib/store";
import { ago } from "@/lib/format";
import { tf, useT } from "@/lib/i18n";
import TopBar from "@/components/TopBar";
import { Book, Plus, Trash } from "@/components/Icons";

export default function KbPage() {
  const { t } = useT();
  const kbs = useStore((s) => s.kbs);
  const loadKbs = useStore((s) => s.loadKbs);
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState("");
  const [desc, setDesc] = useState("");
  const [err, setErr] = useState<string | null>(null);

  async function create(e: React.FormEvent) {
    e.preventDefault();
    setErr(null);
    try {
      await api.post("/api/v1/kb/", { name, description: desc || undefined });
      setName("");
      setDesc("");
      setCreating(false);
      await loadKbs();
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : t.kb.createFailed);
    }
  }

  async function remove(id: string) {
    if (!confirm(t.kb.confirmDeleteKb)) return;
    try {
      await api.del(`/api/v1/kb/${id}`);
      await loadKbs();
    } catch {
      /* ignore */
    }
  }

  return (
    <>
      <TopBar title={t.kb.title} />
      <div className="page">
        <div className="page-inner">
          <div className="page-head">
            <div>
              <h2>{t.kb.title}</h2>
              <p>{t.kb.subtitle}</p>
            </div>
            <button className="btn btn-primary" onClick={() => setCreating((v) => !v)}>
              <Plus /> {t.kb.create}
            </button>
          </div>

          {creating && (
            <form className="settings-group" onSubmit={create}>
              {err && <div className="auth-err" style={{ marginBottom: 12 }}>{err}</div>}
              <div className="field" style={{ marginBottom: 12 }}>
                <label>{t.kb.name} <span className="req">*</span></label>
                <input className="control" required value={name} onChange={(e) => setName(e.target.value)} placeholder={t.kb.namePh} />
              </div>
              <div className="field" style={{ marginBottom: 14 }}>
                <label>{t.kb.description}</label>
                <input className="control" value={desc} onChange={(e) => setDesc(e.target.value)} placeholder={t.kb.descPh} />
              </div>
              <button className="btn btn-primary" type="submit">{t.common.create}</button>
            </form>
          )}

          <div className="list-grid">
            {kbs.map((kb) => (
              <div className="item-card" key={kb.id}>
                <div className="row1">
                  <span className="sq" />
                  <h3>{kb.name}</h3>
                  {kb.is_system && <span className="sys" style={{ position: "static" }}>{t.common.system}</span>}
                </div>
                <div className="desc">{kb.description || "—"}</div>
                <div className="foot">
                  <span>{tf(t.kb.docCount, { n: kb.document_count })}</span>
                  <span>· {ago(kb.created_at)}</span>
                  <span className="actions">
                    <Link className="btn btn-ghost btn-sm" href={`/kb/${kb.id}`}>
                      <Book width={13} height={13} /> {t.common.open}
                    </Link>
                    {!kb.is_system && (
                      <button className="icon-x" onClick={() => remove(kb.id)} aria-label={t.common.delete}>
                        <Trash width={15} height={15} />
                      </button>
                    )}
                  </span>
                </div>
              </div>
            ))}
          </div>
          {kbs.length === 0 && <div className="empty">{t.kb.empty}</div>}
        </div>
      </div>
    </>
  );
}
