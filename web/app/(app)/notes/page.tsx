"use client";

import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { ago } from "@/lib/format";
import { useT } from "@/lib/i18n";
import TopBar from "@/components/TopBar";
import { Note as NoteIcon, Plus, Search, Trash } from "@/components/Icons";
import type { Note } from "@/lib/types";

export default function NotesPage() {
  const { t } = useT();
  const [notes, setNotes] = useState<Note[]>([]);
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState("");

  const [activeId, setActiveId] = useState<string | null>(null);
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [saveState, setSaveState] = useState<"idle" | "saving" | "saved">("idle");
  const [savedAt, setSavedAt] = useState<number | null>(null);

  const saveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const skipNextSave = useRef(false);

  async function load() {
    try {
      const list = await api.get<Note[]>("/api/v1/notes");
      setNotes(list);
      return list;
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function select(n: Note) {
    skipNextSave.current = true;
    setActiveId(n.id);
    setTitle(n.title);
    setContent(n.content);
    setSaveState("idle");
    setSavedAt(n.updated_at);
  }

  async function createNote() {
    const n = await api.post<Note>("/api/v1/notes", { title: t.notes.untitled, content: "" });
    setNotes((s) => [n, ...s]);
    select(n);
  }

  async function removeNote(id: string) {
    if (!confirm(t.notes.confirmDelete)) return;
    await api.del(`/api/v1/notes/${id}`);
    setNotes((s) => s.filter((x) => x.id !== id));
    if (activeId === id) {
      setActiveId(null);
      setTitle("");
      setContent("");
    }
  }

  // debounced autosave whenever the editor buffer changes
  useEffect(() => {
    if (!activeId) return;
    if (skipNextSave.current) {
      skipNextSave.current = false;
      return;
    }
    setSaveState("saving");
    if (saveTimer.current) clearTimeout(saveTimer.current);
    saveTimer.current = setTimeout(async () => {
      const updated = await api.patch<Note>(`/api/v1/notes/${activeId}`, { title, content });
      setNotes((s) => s.map((x) => (x.id === updated.id ? updated : x)));
      setSaveState("saved");
      setSavedAt(updated.updated_at);
    }, 700);
    return () => {
      if (saveTimer.current) clearTimeout(saveTimer.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [title, content]);

  const q = query.trim().toLowerCase();
  const filtered = [...notes]
    .sort((a, b) => b.updated_at - a.updated_at)
    .filter((n) => !q || n.title.toLowerCase().includes(q) || n.content.toLowerCase().includes(q));

  return (
    <>
      <TopBar title={t.notes.title} />
      <div className="notes-shell">
        <div className="notes-list">
          <div className="notes-list-head">
            <div className="notes-list-search">
              <Search />
              <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder={t.notes.searchPh} />
            </div>
            <button className="notes-list-new" onClick={createNote} aria-label={t.notes.newNote} title={t.notes.newNote}>
              <Plus />
            </button>
          </div>
          <div className="notes-list-count">{filtered.length}</div>
          <div className="notes-list-scroll">
            {loading ? (
              <div className="center-load" style={{ padding: 30 }}>
                <span className="spinner" />
              </div>
            ) : filtered.length === 0 ? (
              <div className="empty" style={{ padding: "30px 12px" }}>
                {q ? t.notes.noResults : t.notes.empty}
              </div>
            ) : (
              filtered.map((n) => (
                <button
                  key={n.id}
                  className={`note-card${activeId === n.id ? " on" : ""}`}
                  onClick={() => select(n)}
                >
                  <span className="nt">{n.title || t.notes.untitled}</span>
                  <span className="np">
                    <span className="d">{ago(n.updated_at)}</span>
                    <span className="prev">{(n.content || "").replace(/\s+/g, " ").trim() || "—"}</span>
                  </span>
                </button>
              ))
            )}
          </div>
        </div>

        <div className="notes-editor">
          {!activeId ? (
            <div className="notes-editor-empty">
              <NoteIcon />
              <h3>{t.notes.emptySelect}</h3>
              <p>{t.notes.emptySelectSub}</p>
              <button className="btn btn-ghost" style={{ marginTop: 10 }} onClick={createNote}>
                <Plus width={14} height={14} /> {t.notes.newNote}
              </button>
            </div>
          ) : (
            <>
              <div className="notes-editor-bar">
                <span className="ts">{savedAt ? ago(savedAt) : ""}</span>
                <span className="save-state">
                  {saveState === "saving" ? (
                    <>
                      <span className="spinner" style={{ width: 11, height: 11, borderWidth: 2 }} /> {t.notes.saving}
                    </>
                  ) : saveState === "saved" ? (
                    <>
                      <span className="dot" /> {t.notes.saved}
                    </>
                  ) : null}
                </span>
                <span style={{ flex: 1 }} />
                <button className="icon-x" onClick={() => removeNote(activeId)} aria-label={t.common.delete}>
                  <Trash width={15} height={15} />
                </button>
              </div>
              <div className="notes-editor-body">
                <input
                  className="notes-editor-title"
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  placeholder={t.notes.titlePh}
                />
                <textarea
                  className="notes-editor-content"
                  value={content}
                  onChange={(e) => setContent(e.target.value)}
                  placeholder={t.notes.contentPh}
                />
              </div>
            </>
          )}
        </div>
      </div>
    </>
  );
}
