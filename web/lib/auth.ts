import type { JwtPayload } from "./types";

const ACCESS = "cot.access";
const REFRESH = "cot.refresh";

export function getAccess(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(ACCESS);
}
export function getRefresh(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(REFRESH);
}
export function setTokens(access: string, refresh: string) {
  localStorage.setItem(ACCESS, access);
  localStorage.setItem(REFRESH, refresh);
}
export function clearTokens() {
  localStorage.removeItem(ACCESS);
  localStorage.removeItem(REFRESH);
}
export function isAuthed(): boolean {
  return !!getAccess();
}

/** Decode a JWT payload client-side (no verification — display only). */
export function decodeJwt(token: string | null): JwtPayload | null {
  if (!token) return null;
  try {
    const part = token.split(".")[1];
    const json = atob(part.replace(/-/g, "+").replace(/_/g, "/"));
    return JSON.parse(json) as JwtPayload;
  } catch {
    return null;
  }
}

export function currentEmail(): string {
  const p = decodeJwt(getAccess());
  return p?.email ?? "";
}

/** Two-letter initials from an email, for the avatar. */
export function initials(email: string): string {
  const name = email.split("@")[0] || "?";
  const parts = name.split(/[.\-_ ]+/).filter(Boolean);
  if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase();
  return name.slice(0, 2).toUpperCase();
}
