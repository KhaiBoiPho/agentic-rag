import { apiFetch } from "./api";

/**
 * POST a JSON body to an SSE endpoint and invoke `onEvent` for each
 * `data: <json>` line. We cannot use EventSource because it can't set the
 * Authorization header, so we read the ReadableStream and parse lines ourselves.
 */
export async function streamSSE(
  path: string,
  body: unknown,
  onEvent: (data: any) => void,
  signal?: AbortSignal,
): Promise<void> {
  const res = await apiFetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });

  if (!res.ok || !res.body) {
    let detail = `Lỗi ${res.status}`;
    try {
      const j = await res.json();
      if (j?.detail) detail = j.detail;
    } catch {
      /* ignore */
    }
    throw new Error(detail);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });

    // SSE frames are separated by a blank line; a frame may hold multiple
    // `data:` lines. Process complete frames, keep the trailing partial.
    let sep: number;
    while ((sep = buf.indexOf("\n\n")) !== -1) {
      const frame = buf.slice(0, sep);
      buf = buf.slice(sep + 2);
      emitFrame(frame, onEvent);
    }
  }
  // flush any trailing frame without the closing blank line
  if (buf.trim()) emitFrame(buf, onEvent);
}

function emitFrame(frame: string, onEvent: (data: any) => void) {
  for (const line of frame.split("\n")) {
    const trimmed = line.replace(/\r$/, "");
    if (!trimmed.startsWith("data:")) continue;
    const payload = trimmed.slice(5).trim();
    if (!payload || payload === "[DONE]") continue;
    try {
      onEvent(JSON.parse(payload));
    } catch {
      /* skip malformed frame */
    }
  }
}
