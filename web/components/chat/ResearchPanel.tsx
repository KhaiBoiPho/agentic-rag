"use client";

import { memo, useState } from "react";
import { useT } from "@/lib/i18n";
import type { ResearchStep } from "@/lib/types";
import { Check, Loader } from "../Icons";

/** Memoized so it doesn't re-render on every answer token (paint starvation). */
function ResearchPanelImpl({
  steps,
  progress,
  running,
}: {
  steps: ResearchStep[];
  progress: number;
  running: boolean;
}) {
  const [open, setOpen] = useState(true);
  const { t } = useT();

  const NODE_LABELS: Record<string, string> = {
    start: t.research.start,
    pre_search: t.research.preSearch,
    prompt_expander: t.research.expand,
    web_searcher: t.research.webSearch,
    content_aggregator: t.research.aggregate,
    quality_checker: t.research.quality,
    response_generator: t.research.respond,
    done: t.research.done,
  };
  function stepLabel(node: string) {
    return NODE_LABELS[node] ?? node;
  }

  // collapse duplicate nodes, keep the latest status per node, preserve order
  const ordered: { node: string; status: string }[] = [];
  const seen = new Map<string, number>();
  for (const s of steps) {
    if (s.node === "response_generator" && s.status === "streaming") continue;
    if (seen.has(s.node)) {
      ordered[seen.get(s.node)!].status = s.status;
    } else {
      seen.set(s.node, ordered.length);
      ordered.push({ node: s.node, status: s.status });
    }
  }

  const pct = Math.round(Math.min(progress, 1) * 100);
  const current = ordered[ordered.length - 1];

  return (
    <div className="rpanel">
      <button className={`rph${open ? " open" : ""}`} onClick={() => setOpen((o) => !o)} type="button">
        <span className="caret" />
        <strong>
          {running ? t.chat.researching : t.chat.research}
          {current ? ` · ${stepLabel(current.node)}` : ""}
        </strong>
        <span className="rprog">
          <span className="bar">
            <i style={{ width: `${pct}%` }} />
          </span>
          {pct}%
        </span>
      </button>
      {open && (
        <div className="rsteps">
          {ordered.map(({ node, status }, i) => {
            const isDone = status === "completed" || status === "ready" || (!running && i < ordered.length);
            const isRunning = running && i === ordered.length - 1 && !isDone;
            return (
              <div className={`rstep${!isDone && !isRunning ? " pending" : ""}`} key={node}>
                <span className={`st ${isDone ? "done" : isRunning ? "run" : "wait"}`}>
                  {isDone ? <Check width={9} height={9} /> : isRunning ? <Loader width={9} height={9} className="spin" /> : null}
                </span>
                {stepLabel(node)}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

export default memo(ResearchPanelImpl);
