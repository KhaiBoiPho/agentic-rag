"use client";

import { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import { MODEL_TIERS, modelLabel } from "@/lib/models";
import { usd, vnd } from "@/lib/format";
import { tf, useT } from "@/lib/i18n";
import TopBar from "@/components/TopBar";
import type { Usage } from "@/lib/types";

// Tier → semantic color, reusing the design system's existing tokens (not a
// new hue): Budget reads as "cheap/good", Premium as "costly/caution".
const TIER_COLOR: Record<string, string> = {
  Budget: "var(--good)",
  Standard: "var(--brand)",
  Premium: "var(--warn)",
};
const MODEL_TIER: Record<string, string> = Object.fromEntries(
  MODEL_TIERS.flatMap((tier) => tier.models.map((m) => [m.id, tier.tier])),
);
function tierOf(modelId: string): string {
  return MODEL_TIER[modelId] ?? "Standard";
}
function tierColor(modelId: string): string {
  return TIER_COLOR[tierOf(modelId)] ?? "var(--brand)";
}

export default function UsagePage() {
  const { t, lang } = useT();
  const [usage, setUsage] = useState<Usage | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api
      .get<Usage>("/api/v1/usage")
      .then(setUsage)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const byModel = useMemo(() => {
    if (!usage) return [];
    const map = new Map<string, number>();
    for (const h of usage.history) map.set(h.model, (map.get(h.model) ?? 0) + h.cost_usd);
    const total = [...map.values()].reduce((a, b) => a + b, 0) || 1;
    return [...map.entries()]
      .map(([model, cost]) => ({ model, cost, pct: (cost / total) * 100 }))
      .sort((a, b) => b.cost - a.cost)
      .slice(0, 6);
  }, [usage]);

  if (loading) {
    return (
      <>
        <TopBar title={t.usage.title} />
        <div className="center-load">
          <span className="spinner" />
        </div>
      </>
    );
  }
  if (!usage) {
    return (
      <>
        <TopBar title={t.usage.title} />
        <div className="empty">{t.usage.empty}</div>
      </>
    );
  }

  const maxDaily = Math.max(...usage.daily.map((d) => d.cost_usd), 0.0001);
  const avgDaily = usage.daily.length
    ? usage.daily.reduce((a, d) => a + d.cost_usd, 0) / usage.daily.length
    : 0;
  const avgY = 100 - Math.min((avgDaily / maxDaily) * 100, 100);

  const today = usage.daily[usage.daily.length - 1];
  const yesterday = usage.daily[usage.daily.length - 2];
  let deltaPct: number | null = null;
  if (today && yesterday) {
    deltaPct = yesterday.cost_usd > 0 ? ((today.cost_usd - yesterday.cost_usd) / yesterday.cost_usd) * 100 : today.cost_usd > 0 ? 100 : 0;
  }

  const locale = lang === "vi" ? "vi-VN" : "en-US";

  return (
    <>
      <TopBar title={t.usage.title} />
      <div className="page">
        <div className="page-inner">
          <div className="page-head">
            <div>
              <h2>{t.usage.title}</h2>
              <p>{t.usage.subtitle}</p>
            </div>
          </div>

          <div className="tiles">
            <div className="tile">
              <div className="k">{t.usage.totalCost}</div>
              <div className="v">{usd(usage.total_cost_usd)}</div>
              <div className="u">≈ {vnd(usage.total_cost_usd * 25400)} ₫</div>
              {deltaPct !== null && (
                <div className={`delta ${deltaPct > 0.5 ? "up" : deltaPct < -0.5 ? "down" : "flat"}`}>
                  {deltaPct > 0.5 ? "▲" : deltaPct < -0.5 ? "▼" : "·"}{" "}
                  {Math.abs(deltaPct) < 0.5 ? t.usage.noChange : `${Math.abs(deltaPct).toFixed(0)}% ${t.usage.vsYesterday}`}
                </div>
              )}
            </div>
            <div className="tile">
              <div className="k">{t.usage.messages}</div>
              <div className="v">{usage.total_messages.toLocaleString(locale)}</div>
              <div className="u">{tf(t.usage.avgPerTurn, { s: (usage.avg_duration_ms / 1000).toFixed(1) })}</div>
            </div>
            <div className="tile">
              <div className="k">{t.usage.tokensIn}</div>
              <div className="v">{compact(usage.total_prompt_tokens)}</div>
              <div className="u">prompt</div>
            </div>
            <div className="tile">
              <div className="k">{t.usage.tokensOut}</div>
              <div className="v">{compact(usage.total_completion_tokens)}</div>
              <div className="u">completion</div>
            </div>
          </div>

          {byModel.length > 0 && (
            <div className="settings-group">
              <h3>{t.usage.byModel}</h3>
              <p className="sub">{t.usage.byModelSub}</p>
              <div className="modelmix">
                {byModel.map((m) => (
                  <div className="modelbar-row" key={m.model}>
                    <div className="modelbar-label">
                      <span className="dot" style={{ background: tierColor(m.model) }} />
                      {modelLabel(m.model)}
                    </div>
                    <div className="modelbar-track">
                      <div className="modelbar-fill" style={{ width: `${m.pct}%`, background: tierColor(m.model) }} />
                    </div>
                    <div className="modelbar-val">
                      <b>{usd(m.cost)}</b> · {m.pct.toFixed(0)}%
                    </div>
                  </div>
                ))}
              </div>
              <div className="tier-legend">
                {(["Budget", "Standard", "Premium"] as const).map((tier) => (
                  <span key={tier}>
                    <span className="dot" style={{ background: TIER_COLOR[tier] }} /> {tier}
                  </span>
                ))}
              </div>
            </div>
          )}

          <div className="settings-group">
            <h3>{t.usage.dailyCost}</h3>
            <p className="sub">{tf(t.usage.lastNDays, { n: usage.daily.length })}</p>
            <div
              className="chart"
              style={{ "--avg-y": `${avgY}%` } as React.CSSProperties}
              data-avg-label={`${t.usage.avgLine} ${usd(avgDaily)}`}
            >
              {usage.daily.map((d, i) => (
                <div
                  key={d.date}
                  className={`bar${i === usage.daily.length - 1 ? " hi" : ""}`}
                  style={{ height: `${Math.max((d.cost_usd / maxDaily) * 100, 3)}%` }}
                  title={`${d.date}: ${usd(d.cost_usd)} · ${d.messages}`}
                />
              ))}
            </div>
            <div className="chart-x">
              <span>{usage.daily[0]?.date}</span>
              <span>{usage.daily[usage.daily.length - 1]?.date}</span>
            </div>
          </div>

          <div className="settings-group">
            <h3>{t.usage.history}</h3>
            <p className="sub">{tf(t.usage.lastNTurns, { n: Math.min(usage.history.length, 30) })}</p>
            <div style={{ overflowX: "auto" }}>
              <table className="usage-table">
                <thead>
                  <tr>
                    <th>{t.usage.thModel}</th>
                    <th className="num">{t.usage.thIn}</th>
                    <th className="num">{t.usage.thOut}</th>
                    <th className="num">{t.usage.thCost}</th>
                    <th className="num">{t.usage.thTime}</th>
                  </tr>
                </thead>
                <tbody>
                  {usage.history.slice(0, 30).map((h) => (
                    <tr key={h.id}>
                      <td>
                        <span
                          style={{
                            display: "inline-block",
                            width: 7,
                            height: 7,
                            borderRadius: 2,
                            background: tierColor(h.model),
                            marginRight: 8,
                          }}
                        />
                        {modelLabel(h.model)}
                      </td>
                      <td className="num">{h.prompt_tokens.toLocaleString(locale)}</td>
                      <td className="num">{h.completion_tokens.toLocaleString(locale)}</td>
                      <td className="num">{usd(h.cost_usd)}</td>
                      <td className="num">{(h.duration_ms / 1000).toFixed(1)}s</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </div>
    </>
  );
}

function compact(n: number): string {
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + "M";
  if (n >= 1_000) return (n / 1_000).toFixed(1) + "K";
  return String(n);
}
