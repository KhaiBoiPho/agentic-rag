/**
 * Turns bare `[n]` citation markers (not already a markdown link, i.e. not
 * immediately followed by `(`) into a pseudo-link `[n](citation:n)` that the
 * Markdown renderer's `a` override turns into a numbered pill.
 */
export function markCitations(markdown: string): string {
  return markdown.replace(/\[(\d+)\](?!\()/g, '[$1](citation:$1)');
}
