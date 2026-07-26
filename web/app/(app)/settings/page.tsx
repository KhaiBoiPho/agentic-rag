"use client";

import { useState } from "react";
import { useStore } from "@/lib/store";
import { MODEL_TIERS } from "@/lib/models";
import { useT } from "@/lib/i18n";
import TopBar from "@/components/TopBar";

const VOICES = ["Alloy", "Coral", "Verse", "Sage"];
const ACCENTS = [
  { name: "Cobalt", hex: "#2648D8", active: true },
  { name: "Violet", hex: "#7C4DE0" },
  { name: "Teal", hex: "#0E8F82" },
  { name: "Rose", hex: "#C23B6B" },
  { name: "Amber", hex: "#B87317" },
];

function Switch({ on, onClick }: { on: boolean; onClick: () => void }) {
  return <button className={`switch${on ? " on" : ""}`} onClick={onClick} role="switch" aria-checked={on} type="button" />;
}

export default function SettingsPage() {
  const { t } = useT();
  const settings = useStore((s) => s.settings);
  const setSettings = useStore((s) => s.setSettings);
  const lang = useStore((s) => s.lang);
  const setLang = useStore((s) => s.setLang);
  const clearConversations = useStore((s) => s.clearConversations);

  const [toast, setToast] = useState<string | null>(null);
  function flash(msg: string) {
    setToast(msg);
    setTimeout(() => setToast(null), 1400);
  }

  function update<K extends keyof typeof settings>(k: K, v: (typeof settings)[K]) {
    setSettings({ [k]: v } as any);
    flash(t.settings.saved);
  }

  // decorative-only local state — visual filler per the settings page, not wired to a backend
  const [voice, setVoice] = useState(VOICES[0]);
  const [voiceSpeed, setVoiceSpeed] = useState(1);
  const [notifDesktop, setNotifDesktop] = useState(true);
  const [notifSound, setNotifSound] = useState(true);
  const [notifDigest, setNotifDigest] = useState(false);
  const [localHistory, setLocalHistory] = useState(true);
  const [anonUsage, setAnonUsage] = useState(false);
  const [accent, setAccent] = useState("Cobalt");

  function clearHistory() {
    if (!confirm(t.settings.clearHistoryConfirm)) return;
    clearConversations();
    flash(t.settings.clearedToast);
  }

  return (
    <>
      <TopBar title={t.settings.title} />
      <div className="page">
        <div className="page-inner">
          <div className="page-head">
            <div>
              <h2>{t.settings.title}</h2>
              <p>{t.settings.subtitle}</p>
            </div>
          </div>

          <div className="settings-group">
            <h3>{t.settings.langTitle}</h3>
            <p className="sub">{t.settings.langSub}</p>
            <div className="model-opts">
              <button className={`model-opt${lang === "vi" ? " on" : ""}`} onClick={() => setLang("vi")} type="button">
                Tiếng Việt<span className="mid">VI</span>
              </button>
              <button className={`model-opt${lang === "en" ? " on" : ""}`} onClick={() => setLang("en")} type="button">
                English<span className="mid">EN</span>
              </button>
            </div>
          </div>

          <div className="settings-group">
            <h3>{t.settings.modelTitle}</h3>
            <p className="sub">{t.settings.modelSub}</p>
            {MODEL_TIERS.map((tier) => (
              <div className="model-tier" key={tier.tier}>
                <div className="tlabel">{tier.tier}</div>
                <div className="model-opts">
                  {tier.models.map((m) => (
                    <button
                      key={m.id}
                      className={`model-opt${settings.model === m.id ? " on" : ""}`}
                      onClick={() => update("model", m.id)}
                      type="button"
                    >
                      {m.label}
                      <span className="mid">{m.id}</span>
                    </button>
                  ))}
                </div>
              </div>
            ))}
          </div>

          <div className="settings-group">
            <h3>{t.settings.tuneTitle}</h3>
            <p className="sub">{t.settings.tuneSub}</p>
            <div className="slider-row">
              <label>{t.settings.temperature}</label>
              <input
                type="range"
                min={0}
                max={2}
                step={0.1}
                value={settings.temperature}
                onChange={(e) => update("temperature", Number(e.target.value))}
              />
              <span className="val">{settings.temperature.toFixed(1)}</span>
            </div>
            <div className="slider-row">
              <label>{t.settings.maxTokens}</label>
              <input
                type="range"
                min={256}
                max={8192}
                step={256}
                value={settings.max_tokens}
                onChange={(e) => update("max_tokens", Number(e.target.value))}
              />
              <span className="val">{settings.max_tokens}</span>
            </div>
            <div className="slider-row">
              <label>{t.settings.topK}</label>
              <input
                type="range"
                min={1}
                max={20}
                step={1}
                value={settings.top_k}
                onChange={(e) => update("top_k", Number(e.target.value))}
              />
              <span className="val">{settings.top_k}</span>
            </div>
          </div>

          <div className="settings-group">
            <h3>{t.settings.voiceTitle}</h3>
            <p className="sub">{t.settings.voiceSub}</p>
            <div className="model-tier">
              <div className="tlabel">{t.settings.voiceLabel}</div>
              <div className="model-opts">
                {VOICES.map((v) => (
                  <button key={v} className={`model-opt${voice === v ? " on" : ""}`} onClick={() => setVoice(v)} type="button">
                    {v}
                  </button>
                ))}
              </div>
            </div>
            <div className="slider-row" style={{ marginTop: 4 }}>
              <label>{t.settings.voiceSpeed}</label>
              <input type="range" min={0.5} max={2} step={0.1} value={voiceSpeed} onChange={(e) => setVoiceSpeed(Number(e.target.value))} />
              <span className="val">{voiceSpeed.toFixed(1)}×</span>
            </div>
          </div>

          <div className="settings-group">
            <h3>{t.settings.notifTitle}</h3>
            <p className="sub">{t.settings.notifSub}</p>
            <div className="switch-row">
              <span className="lbl">
                {t.settings.notifDesktop}
                <span className="d">{t.settings.notifDesktopD}</span>
              </span>
              <Switch on={notifDesktop} onClick={() => setNotifDesktop((v) => !v)} />
            </div>
            <div className="switch-row">
              <span className="lbl">
                {t.settings.notifSound}
                <span className="d">{t.settings.notifSoundD}</span>
              </span>
              <Switch on={notifSound} onClick={() => setNotifSound((v) => !v)} />
            </div>
            <div className="switch-row">
              <span className="lbl">
                {t.settings.notifDigest}
                <span className="d">{t.settings.notifDigestD}</span>
              </span>
              <Switch on={notifDigest} onClick={() => setNotifDigest((v) => !v)} />
            </div>
          </div>

          <div className="settings-group">
            <h3>{t.settings.privacyTitle}</h3>
            <p className="sub">{t.settings.privacySub}</p>
            <div className="switch-row">
              <span className="lbl">
                {t.settings.privacyLocalHistory}
                <span className="d">{t.settings.privacyLocalHistoryD}</span>
              </span>
              <Switch on={localHistory} onClick={() => setLocalHistory((v) => !v)} />
            </div>
            <div className="switch-row">
              <span className="lbl">
                {t.settings.privacyAnonUsage}
                <span className="d">{t.settings.privacyAnonUsageD}</span>
              </span>
              <Switch on={anonUsage} onClick={() => setAnonUsage((v) => !v)} />
            </div>
            <div style={{ display: "flex", gap: 10, marginTop: 16 }}>
              <button className="btn btn-ghost" onClick={() => flash(t.settings.saved)}>{t.settings.exportData}</button>
              <button className="btn btn-danger" onClick={clearHistory}>{t.settings.clearHistory}</button>
            </div>
          </div>

          <div className="settings-group">
            <h3>{t.settings.accentTitle}</h3>
            <p className="sub">{t.settings.accentSub}</p>
            <div className="row" style={{ display: "flex", gap: 10 }}>
              {ACCENTS.map((a) => (
                <button
                  key={a.name}
                  className="model-opt"
                  style={{
                    flexDirection: "row",
                    alignItems: "center",
                    gap: 8,
                    borderColor: accent === a.name ? "var(--brand)" : undefined,
                    background: accent === a.name ? "var(--brand-soft)" : undefined,
                  }}
                  onClick={() => {
                    if (a.name === "Cobalt") {
                      setAccent(a.name);
                    } else {
                      flash(lang === "vi" ? "Sắp ra mắt" : "Coming soon");
                    }
                  }}
                  type="button"
                >
                  <span style={{ width: 14, height: 14, borderRadius: "50%", background: a.hex, flex: "none" }} />
                  {a.name}
                </button>
              ))}
            </div>
          </div>

          <div className="settings-group">
            <h3>{t.settings.shortcutsTitle}</h3>
            <p className="sub">{t.settings.shortcutsSub}</p>
            <table className="usage-table">
              <tbody>
                <tr>
                  <td>{t.settings.scNew}</td>
                  <td className="num"><kbd className="mono">⌘K</kbd></td>
                </tr>
                <tr>
                  <td>{t.settings.scSend}</td>
                  <td className="num"><kbd className="mono">Enter</kbd></td>
                </tr>
                <tr>
                  <td>{t.settings.scNewline}</td>
                  <td className="num"><kbd className="mono">Shift+Enter</kbd></td>
                </tr>
                <tr>
                  <td>{t.settings.scSidebar}</td>
                  <td className="num"><kbd className="mono">⌘\\</kbd></td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>
      {toast && <div className="toast">{toast}</div>}
    </>
  );
}
