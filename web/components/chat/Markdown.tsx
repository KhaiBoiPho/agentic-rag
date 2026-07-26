"use client";

import { memo } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { WebSource } from "@/lib/types";

/**
 * Renders assistant content. While streaming we render PLAIN pre-wrap text —
 * re-parsing the whole markdown AST on every token starves the paint loop and
 * makes long answers "pop in". Full markdown is parsed only once streaming ends.
 *
 * Bare inline citations like `[1]` (not already a link) are turned into small
 * superscript refs pointing at the matching web source.
 */
function MarkdownImpl({
  content,
  streaming,
  webSources = [],
}: {
  content: string;
  streaming?: boolean;
  webSources?: WebSource[];
}) {
  if (streaming) {
    return (
      <div className="md streaming">
        {content}
        <span className="caret-blink" />
      </div>
    );
  }

  const withRefs = linkifyRefs(content, webSources);

  return (
    <div className="md">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          a({ href, children }) {
            const text = String(Array.isArray(children) ? children.join("") : children ?? "");
            // a pure-number link is an inline citation ref
            if (/^\d+$/.test(text.trim())) {
              return (
                <sup>
                  <a className="ref" href={href} target="_blank" rel="noreferrer noopener">
                    {text}
                  </a>
                </sup>
              );
            }
            return (
              <a href={href} target="_blank" rel="noreferrer noopener">
                {children}
              </a>
            );
          },
          table({ children }) {
            return (
              <div className="md-table-scroll">
                <table>{children}</table>
              </div>
            );
          },
        }}
      >
        {withRefs}
      </ReactMarkdown>
    </div>
  );
}

/** Replace bare `[n]` with a markdown link to sources[n-1].url so it renders as a ref. */
function linkifyRefs(md: string, sources: WebSource[]): string {
  if (!sources.length) return md;
  return md.replace(/\[(\d+)\](?!\()/g, (whole, num) => {
    const idx = parseInt(num, 10) - 1;
    const src = sources[idx];
    return src?.url ? `[${num}](${src.url})` : whole;
  });
}

export default memo(MarkdownImpl);
