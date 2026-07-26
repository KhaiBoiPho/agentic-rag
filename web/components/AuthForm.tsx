"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { api } from "@/lib/api";
import { setTokens } from "@/lib/auth";
import { useT } from "@/lib/i18n";
import type { TokenResponse } from "@/lib/types";
import { Logo } from "./Icons";
import LanguageToggle from "./LanguageToggle";
import ThemeToggle from "./ThemeToggle";

export default function AuthForm({ mode }: { mode: "login" | "register" }) {
  const router = useRouter();
  const { t } = useT();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const isRegister = mode === "register";

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setErr(null);
    setBusy(true);
    try {
      const path = isRegister ? "/api/v1/auth/register" : "/api/v1/auth/login";
      const body = isRegister
        ? { email, password, full_name: fullName || undefined }
        : { email, password };
      const res = await api.post<TokenResponse>(path, body, false);
      setTokens(res.access_token, res.refresh_token);
      router.replace("/chat");
    } catch (e: any) {
      setErr(e?.message || t.auth.loginFailed);
      setBusy(false);
    }
  }

  return (
    <div className="auth-wrap">
      <div style={{ position: "fixed", top: 18, right: 18, display: "flex", gap: 8 }}>
        <LanguageToggle />
        <ThemeToggle />
      </div>
      <div className="auth-card reg">
        <span className="m tl" /><span className="m tr" /><span className="m bl" /><span className="m br" />
        <div className="auth-brand">
          <span className="mark">
            <Logo stroke="#fff" />
          </span>
          <span className="nm">
            C<span className="accent">ố</span>t
          </span>
        </div>
        <p className="auth-sub">{t.auth.tagline}</p>

        <form className="auth-form" onSubmit={submit}>
          {err && <div className="auth-err">{err}</div>}

          {isRegister && (
            <div className="field">
              <label>{t.auth.fullName}</label>
              <input
                className="control"
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                placeholder={t.auth.fullNamePh}
                autoComplete="name"
              />
            </div>
          )}
          <div className="field">
            <label>
              {t.auth.email} <span className="req">*</span>
            </label>
            <input
              className="control"
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder={t.auth.emailPh}
              autoComplete="email"
            />
          </div>
          <div className="field">
            <label>
              {t.auth.password} <span className="req">*</span>
            </label>
            <input
              className="control"
              type="password"
              required
              minLength={6}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
              autoComplete={isRegister ? "new-password" : "current-password"}
            />
          </div>

          <button className="btn btn-primary" disabled={busy} type="submit">
            {busy ? <span className="spinner" style={{ borderTopColor: "#fff", borderColor: "rgba(255,255,255,.4)" }} /> : null}
            {isRegister ? t.auth.register : t.auth.login}
          </button>

          <div className="divider">{t.common.or}</div>
          <div className="oauth-row">
            <a className="btn btn-ghost" href="/api/v1/auth/oauth/google">Google</a>
            <a className="btn btn-ghost" href="/api/v1/auth/oauth/github">GitHub</a>
          </div>
        </form>

        <p className="auth-switch">
          {isRegister ? (
            <>
              {t.auth.haveAccount} <Link href="/login">{t.auth.login}</Link>
            </>
          ) : (
            <>
              {t.auth.noAccount} <Link href="/register">{t.auth.register}</Link>
            </>
          )}
        </p>
      </div>
    </div>
  );
}
