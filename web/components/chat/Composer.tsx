"use client";

import { useEffect, useRef, useState } from "react";
import { apiFetch } from "@/lib/api";
import { useStore } from "@/lib/store";
import { tf, useT } from "@/lib/i18n";
import type { ChatMode } from "@/lib/types";
import { Book, Bot, Globe, Mic, Search, Send } from "../Icons";

export interface SendOpts {
  viaVoice?: boolean;
}

export default function Composer({
  mode,
  setMode,
  onSend,
  busy,
  speaking,
}: {
  mode: ChatMode;
  setMode: (m: ChatMode) => void;
  onSend: (text: string, opts?: SendOpts) => void;
  busy: boolean;
  speaking: boolean;
}) {
  const { t } = useT();
  const [text, setText] = useState("");
  const [recording, setRecording] = useState(false);
  const [recSeconds, setRecSeconds] = useState(0);
  const [transcribing, setTranscribing] = useState(false);
  const taRef = useRef<HTMLTextAreaElement>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const kbs = useStore((s) => s.kbs);
  const projects = useStore((s) => s.projects);
  const activeKbId = useStore((s) => s.activeKbId);
  const activeProjectId = useStore((s) => s.activeProjectId);
  const setActiveKb = useStore((s) => s.setActiveKb);
  const setActiveProject = useStore((s) => s.setActiveProject);

  const activeKb = kbs.find((k) => k.id === activeKbId);
  const activeProject = projects.find((p) => p.id === activeProjectId);
  const ragOn = mode === "chat" && (activeKb || activeProject);

  useEffect(() => {
    const ta = taRef.current;
    if (!ta) return;
    ta.style.height = "auto";
    ta.style.height = Math.min(ta.scrollHeight, 160) + "px";
  }, [text]);

  function submit() {
    const t = text.trim();
    if (!t || busy) return;
    onSend(t);
    setText("");
  }

  function onKey(e: React.KeyboardEvent) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  }

  async function startRecording() {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const rec = new MediaRecorder(stream);
      chunksRef.current = [];
      rec.ondataavailable = (e) => e.data.size && chunksRef.current.push(e.data);
      rec.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop());
        const blob = new Blob(chunksRef.current, { type: "audio/webm" });
        await transcribe(blob);
      };
      rec.start();
      recorderRef.current = rec;
      setRecording(true);
      setRecSeconds(0);
      timerRef.current = setInterval(() => setRecSeconds((s) => s + 1), 1000);
    } catch {
      alert(t.chat.micError);
    }
  }

  function stopRecording() {
    recorderRef.current?.stop();
    setRecording(false);
    if (timerRef.current) clearInterval(timerRef.current);
  }

  async function transcribe(blob: Blob) {
    setTranscribing(true);
    try {
      const fd = new FormData();
      fd.append("audio", blob, "voice.webm");
      const res = await apiFetch("/api/v1/voice/stt?language=vi", { method: "POST", body: fd });
      if (res.ok) {
        const { text: t } = await res.json();
        if (t?.trim()) onSend(t.trim(), { viaVoice: true });
      }
    } catch {
      /* ignore */
    } finally {
      setTranscribing(false);
    }
  }

  const modes: { id: ChatMode; label: string; Icon: typeof Book }[] = [
    { id: "chat", label: t.chat.modeChat, Icon: Book },
    { id: "search", label: t.chat.modeSearch, Icon: Search },
    { id: "research", label: t.chat.modeResearch, Icon: Globe },
    { id: "agentic", label: t.chat.modeAgentic, Icon: Bot },
  ];

  const placeholder =
    mode === "search"
      ? t.chat.placeholderSearch
      : mode === "research"
        ? t.chat.placeholderResearch
        : mode === "agentic"
          ? t.chat.placeholderAgentic
          : t.chat.placeholderChat;

  return (
    <div className="composer">
      <div className="composer-inner">
        <div className="modes">
          {modes.map(({ id, label, Icon }) => (
            <button key={id} className={mode === id ? "on" : ""} onClick={() => setMode(id)} type="button">
              <Icon /> {label}
            </button>
          ))}
        </div>

        <div className="cbox">
          {mode === "chat" && activeKb && (
            <span className="kbchip">
              <Book width={11} height={11} /> {activeKb.name}
              <button onClick={() => setActiveKb(null)} aria-label={t.chat.deselectKb}>✕</button>
            </span>
          )}
          {mode === "chat" && activeProject && (
            <span className="kbchip">
              <Book width={11} height={11} /> {activeProject.name}
              <button onClick={() => setActiveProject(null)} aria-label={t.chat.deselectProject}>✕</button>
            </span>
          )}

          <textarea
            ref={taRef}
            rows={1}
            value={text}
            placeholder={placeholder}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={onKey}
          />

          {mode === "chat" && (
            <button
              className={`ibtn${recording ? " rec" : ""}`}
              onClick={recording ? stopRecording : startRecording}
              disabled={transcribing || busy}
              aria-label={recording ? t.chat.stopRecording : t.chat.speak}
              type="button"
            >
              <Mic />
            </button>
          )}
          <button className="ibtn send" onClick={submit} disabled={busy || !text.trim()} aria-label={t.chat.send} type="button">
            <Send />
          </button>
        </div>

        <div className="cfoot">
          {ragOn ? (
            <span>{tf(t.chat.ragOn, { name: activeKb?.name ?? activeProject?.name ?? "" })}</span>
          ) : mode === "chat" ? (
            <span>{t.chat.ragOffChat}</span>
          ) : mode === "agentic" ? (
            <span>{t.chat.agenticHint}</span>
          ) : (
            <span>{mode === "search" ? t.chat.webCiteSearch : t.chat.webCiteResearch}</span>
          )}
          {recording && (
            <span className="rec-ind">
              <span className="pulse" /> {tf(t.chat.recording, { t: fmt(recSeconds) })}
            </span>
          )}
          {transcribing && <span className="rec-ind">{t.chat.transcribing}</span>}
          {speaking && (
            <span className="speak-ind">
              <span className="wave">
                <i /><i /><i /><i />
              </span>{" "}
              {t.chat.speaking}
            </span>
          )}
        </div>
      </div>
    </div>
  );
}

function fmt(s: number) {
  const m = Math.floor(s / 60);
  return `${m}:${String(s % 60).padStart(2, "0")}`;
}
