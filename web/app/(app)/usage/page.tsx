"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { modelLabel } from "@/lib/models";
import { usd, vnd } from "@/lib/format";
import { tf, useT } from "@/lib/i18n";
import TopBar from "@/components/TopBar";
import type { Usage } from "@/lib/types";

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
            </div>
            <div className="tile">
              <div className="k">{t.usage.messages}</div>
              <div className="v">{usage.total_messages.toLocaleString(lang === "vi" ? "vi-VN" : "en-US")}</div>
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

          <div className="settings-group">
            <h3>{t.usage.dailyCost}</h3>
            <p className="sub">{tf(t.usage.lastNDays, { n: usage.daily.length })}</p>
            <div className="chart">
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
                      <td>{modelLabel(h.model)}</td>
                      <td className="num">{h.prompt_tokens.toLocaleString(lang === "vi" ? "vi-VN" : "en-US")}</td>
                      <td className="num">{h.completion_tokens.toLocaleString(lang === "vi" ? "vi-VN" : "en-US")}</td>
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
