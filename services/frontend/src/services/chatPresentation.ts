export interface ChatSource {
  id: string;
  label: string;
}

/** Keep the validated wire text intact in state, but present prose without citation machinery. */
export function presentChatAnswer(text: string): { body: string; sources: ChatSource[] } {
  const footer = /(?:^|\n)Sources:\s*\n/i.exec(text);
  const body = footer ? text.slice(0, footer.index) : text;
  const references = footer ? text.slice(footer.index + footer[0].length) : '';
  const sources = [...references.matchAll(/^\s*-?\s*\[(S\d+)\]\s+(.+?)\s*$/gm)].map((match) => {
    const filename = match[2].replace(/\\/g, '/').split('/').pop() || match[2];
    return { id: match[1], label: filename.replace(/\.(md|txt|pdf)$/i, '').replace(/[_-]+/g, ' ') };
  });
  return {
    body: body.replace(/\[S\d+(?:\s*,\s*S\d+)*\]/g, '').replace(/[ \t]+([.,;:!?])/g, '$1').trim(),
    sources,
  };
}
