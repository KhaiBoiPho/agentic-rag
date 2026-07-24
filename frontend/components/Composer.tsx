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

  // Locked while a voice turn is in flight — recording, transcribing, or
  // (via the `disabled` prop) waiting on the chat reply + TTS playback —
  // so typed messages can't interleave with an in-progress voice turn.
  const inputLocked = disabled || recording || transcribing;

  function submit() {
    const value = text.trim();
    if (!value || inputLocked) return;
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
    <div className="bg-canvas px-4 pb-4 pt-1 dark:bg-[#212121]">
      <div className="mx-auto max-w-3xl">
        <div className="mb-2 flex items-center justify-between">
          <div className="flex gap-1 rounded-full bg-gray-100 p-1 dark:bg-slate-800">
            {MODES.map((m) => (
              <button
                key={m.id}
                type="button"
                onClick={() => onModeChange(m.id)}
                className={clsx(
                  'rounded-full px-3 py-1 text-xs font-medium transition',
                  mode === m.id
                    ? 'bg-white text-ink shadow-sm dark:bg-slate-700 dark:text-white'
                    : 'text-ink-mute hover:text-ink dark:hover:text-slate-300',
                )}
              >
                {m.icon} {m.label}
              </button>
            ))}
          </div>
          <span className="truncate text-[11px] text-ink-mute">{scopeLabel}</span>
        </div>

        {voiceError && <p className="mb-1 text-xs text-red-500">{voiceError}</p>}

        <div className="flex items-end gap-2 rounded-3xl border border-hairline bg-canvas px-3 py-2 shadow-[0_2px_10px_rgba(0,0,0,0.06)] dark:border-slate-700 dark:bg-[#2f2f2f]">
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={onKeyDown}
            disabled={inputLocked}
            rows={1}
            placeholder="Nhập câu hỏi… (Enter để gửi, Shift+Enter xuống dòng)"
            className="max-h-40 flex-1 resize-none bg-transparent px-2 py-1.5 text-sm text-ink outline-none disabled:opacity-60 dark:text-slate-100"
          />
          <button
            type="button"
            onClick={recording ? stopRecording : startRecording}
            disabled={disabled || transcribing}
            title={recording ? 'Dừng ghi âm' : 'Nói'}
            className={clsx(
              'flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-base transition',
              recording
                ? 'animate-pulse bg-red-50 text-red-600 dark:bg-red-900/30'
                : 'text-ink-mute hover:bg-gray-100 dark:hover:bg-slate-700',
            )}
          >
            {transcribing ? '⏳' : '🎙️'}
          </button>
          <button
            type="button"
            onClick={submit}
            disabled={inputLocked || !text.trim()}
            className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-ink text-white transition hover:bg-black disabled:opacity-30 dark:bg-white dark:text-black"
            title="Gửi"
          >
            ↑
          </button>
        </div>
      </div>
    </div>
  );
}
