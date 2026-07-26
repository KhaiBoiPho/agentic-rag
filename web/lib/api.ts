import { clearTokens, getAccess, getRefresh, setTokens } from "./auth";
import type { TokenResponse } from "./types";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

/** Extract `{ detail }` (or a plain string) from an error response body. */
async function errorDetail(res: Response): Promise<string> {
  try {
    const body = await res.json();
    if (typeof body?.detail === "string") return body.detail;
    if (Array.isArray(body?.detail)) return body.detail.map((d: any) => d.msg).join("; ");
    return JSON.stringify(body);
  } catch {
    return res.statusText || `Lỗi ${res.status}`;
  }
}

let refreshing: Promise<boolean> | null = null;

/** POST the refresh token for a new pair. De-duplicated across concurrent 401s. */
async function refreshTokens(): Promise<boolean> {
  if (refreshing) return refreshing;
  refreshing = (async () => {
    const refresh_token = getRefresh();
    if (!refresh_token) return false;
    try {
      const res = await fetch("/api/v1/auth/refresh", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token }),
      });
      if (!res.ok) return false;
      const data: TokenResponse = await res.json();
      setTokens(data.access_token, data.refresh_token);
      return true;
    } catch {
      return false;
    } finally {
      refreshing = null;
    }
  })();
  return refreshing;
}

function authHeaders(extra?: HeadersInit): Headers {
  const h = new Headers(extra);
  const access = getAccess();
  if (access) h.set("Authorization", `Bearer ${access}`);
  return h;
}

interface ReqOpts extends Omit<RequestInit, "headers"> {
  headers?: HeadersInit;
  auth?: boolean; // default true
  raw?: boolean; // return Response, don't parse
}

/** Authenticated fetch with a one-shot refresh-and-retry on 401. */
export async function apiFetch(path: string, opts: ReqOpts = {}): Promise<Response> {
  const { auth = true, headers, ...rest } = opts;
  const doFetch = () =>
    fetch(path, { ...rest, headers: auth ? authHeaders(headers) : new Headers(headers) });

  let res = await doFetch();
  if (res.status === 401 && auth) {
    const ok = await refreshTokens();
    if (ok) {
      res = await doFetch();
    } else {
      clearTokens();
      if (typeof window !== "undefined" && !location.pathname.startsWith("/login")) {
        location.href = "/login";
      }
    }
  }
  return res;
}

/** JSON GET/POST/PATCH/PUT/DELETE helpers. */
async function json<T>(path: string, method: string, body?: unknown, auth = true): Promise<T> {
  const res = await apiFetch(path, {
    method,
    auth,
    headers: body !== undefined ? { "Content-Type": "application/json" } : undefined,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) throw new ApiError(res.status, await errorDetail(res));
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export const api = {
  get: <T>(p: string) => json<T>(p, "GET"),
  post: <T>(p: string, b?: unknown, auth = true) => json<T>(p, "POST", b, auth),
  patch: <T>(p: string, b?: unknown) => json<T>(p, "PATCH", b),
  put: <T>(p: string, b?: unknown) => json<T>(p, "PUT", b),
  del: <T = void>(p: string) => json<T>(p, "DELETE"),
};
