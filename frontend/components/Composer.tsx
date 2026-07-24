'use client';

import { useRef, useState } from 'react';
import clsx from 'clsx';
import { api, ApiError } from '@/lib/api';
import type { ChatMode } from '@/lib/types';

const MODES: { id: ChatMode; label: string; icon: string }[] = [
  { id: 'chat', label: 'Chat', icon: '💬' },
  { id: 'search', label: 'Search', icon: '🔎' },
  { id: 'research', label: 'Research', icon: '🧪' },
];

export default function Composer({
  mode,
  onModeChange,
  onSend,
  onVoiceText,
  disabled,
  scopeLabel,
}: {
  mode: ChatMode;
  onModeChange: (m: ChatMode) => void;
  onSend: (text: string) => void;
  onVoiceText: (text: string) => void;
  disabled?: boolean;
  scopeLabel: string;
}) {
  const [text, setText] = useState('');
  const [recording, setRecording] = useState(false);
  const [transcribing, setTranscribing] = useState(false);
  const [voiceError, setVoiceError] = useState<string | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);

  function submit() {
    const value = text.trim();
    if (!value || disabled) return;
    onSend(value);
    setText('');
  }

  function onKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  }

  async function startRecording() {
    setVoiceError(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const recorder = new MediaRecorder(stream);
      chunksRef.current = [];
      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data);
      };
      recorder.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop());
        const blob = new Blob(chunksRef.current, { type: 'audio/webm' });
        setTranscribing(true);
        try {
          const form = new FormData();
          form.append('audio', blob, 'voice.webm');
          const res = await api.upload<{ text: string }>('/api/v1/voice/stt?language=vi', form);
          if (res.text?.trim()) {
            onVoiceText(res.text.trim());
          } else {
            setVoiceError('Không nhận diện được giọng nói');
          }
        } catch (err) {
          setVoiceError(err instanceof ApiError ? err.message : 'Lỗi ghi âm');
        } finally {
          setTranscribing(false);
        }
      };
      mediaRecorderRef.current = recorder;
      recorder.start();
      setRecording(true);
    } catch {
      setVoiceError('Không thể truy cập micro');
    }
  }

  function stopRecording() {
    mediaRecorderRef.current?.stop();
    setRecording(false);
  }

  return (
    <div className="border-t border-slate-200 bg-white px-4 py-3 dark:border-slate-800 dark:bg-slate-900">
      <div className="mx-auto max-w-3xl">
        <div className="mb-2 flex items-center justify-between">
          <div className="flex gap-1 rounded-lg bg-slate-100 p-1 dark:bg-slate-800">
            {MODES.map((m) => (
              <button
                key={m.id}
                type="button"
                onClick={() => onModeChange(m.id)}
                className={clsx(
                  'rounded-md px-2.5 py-1 text-xs font-medium transition',
                  mode === m.id
                    ? 'bg-white text-brand-700 shadow-sm dark:bg-slate-700 dark:text-brand-300'
                    : 'text-slate-500 hover:text-slate-700 dark:hover:text-slate-300',
                )}
              >
                {m.icon} {m.label}
              </button>
            ))}
          </div>
          <span className="truncate text-[11px] text-slate-400">{scopeLabel}</span>
        </div>

        {voiceError && <p className="mb-1 text-xs text-red-500">{voiceError}</p>}

        <div className="flex items-end gap-2">
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={onKeyDown}
            disabled={disabled}
            rows={1}
            placeholder="Nhập câu hỏi… (Enter để gửi, Shift+Enter xuống dòng)"
            className="max-h-40 flex-1 resize-none rounded-xl border border-slate-300 bg-transparent px-3 py-2 text-sm outline-none focus:border-brand-600 disabled:opacity-60 dark:border-slate-700"
          />
          <button
            type="button"
            onClick={recording ? stopRecording : startRecording}
            disabled={disabled || transcribing}
            title={recording ? 'Dừng ghi âm' : 'Nói'}
            className={clsx(
              'flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border text-lg transition',
              recording
                ? 'animate-pulse border-red-400 bg-red-50 text-red-600 dark:bg-red-900/30'
                : 'border-slate-300 text-slate-500 hover:bg-slate-100 dark:border-slate-700 dark:hover:bg-slate-800',
            )}
          >
            {transcribing ? '⏳' : '🎙️'}
          </button>
          <button
            type="button"
            onClick={submit}
            disabled={disabled || !text.trim()}
            className="h-10 shrink-0 rounded-full bg-brand-600 px-4 text-sm font-medium text-white transition hover:bg-brand-700 disabled:opacity-50"
          >
            Gửi
          </button>
        </div>
      </div>
    </div>
  );
}
