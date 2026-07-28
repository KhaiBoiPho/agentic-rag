"use client";

import { memo } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";
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

  const withRefs = linkifyRefs(normalizeMathDelimiters(content), webSources);

  return (
    <div className="md">
      <ReactMarkdown
        remarkPlugins={[remarkGfm, remarkMath]}
        rehypePlugins={[rehypeKatex]}
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

/** LLMs commonly emit LaTeX-style \(...\)/\[...\] delimiters instead of the
 * $...$/$$...$$ that remark-math actually parses — CommonMark then treats
 * the backslash as an escape and silently drops it, leaving bare brackets
 * on screen. Convert to dollar delimiters before the markdown parser sees it. */
function normalizeMathDelimiters(md: string): string {
  return md
    .replace(/\\\[([\s\S]*?)\\\]/g, (_, expr) => `$$${expr}$$`)
    .replace(/\\\(([\s\S]*?)\\\)/g, (_, expr) => `$${expr}$`);
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
