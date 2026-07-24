'use client';

import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { markCitations } from '@/lib/citations';
import type { SourceItem } from '@/lib/types';

function sourceUrl(sources: SourceItem[] | undefined, n: number): string | null {
  if (!sources) return null;
  const s = sources[n - 1] as any;
  return s?.url ?? null;
}

export default function Markdown({ content, sources }: { content: string; sources?: SourceItem[] }) {
  const marked = markCitations(content);
  return (
    <div className="markdown-body text-sm leading-relaxed">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          a({ href, children, ...props }) {
            if (href?.startsWith('citation:')) {
              const n = parseInt(href.slice('citation:'.length), 10);
              const url = sourceUrl(sources, n);
              return (
                <a
                  href={url ?? '#'}
                  target={url ? '_blank' : undefined}
                  rel={url ? 'noreferrer' : undefined}
                  className="cite-badge"
                  onClick={(e) => {
                    if (!url) e.preventDefault();
                  }}
                >
                  {n}
                </a>
              );
            }
            return (
              <a href={href} target="_blank" rel="noreferrer" {...props}>
                {children}
              </a>
            );
          },
        }}
      >
        {marked}
      </ReactMarkdown>
    </div>
  );
}
