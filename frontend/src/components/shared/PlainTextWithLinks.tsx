/**
 * Plain text with its web links made clickable (ADR-063 decision 10, IR-971).
 *
 * Descriptions RDCO writes on Setup are plain text: line breaks are kept, there
 * is no formatting, and an `http://` or `https://` address becomes a link that
 * opens in a new tab. Nothing else is interpreted, so `<b>` shows as typed.
 */
const URL_PATTERN = /(https?:\/\/[^\s<>"]+[^\s<>".,;:!?)\]'])/g;

export function linkParts(text: string): { text: string; href?: string }[] {
  const parts: { text: string; href?: string }[] = [];
  let last = 0;
  for (const match of text.matchAll(URL_PATTERN)) {
    const at = match.index ?? 0;
    if (at > last) parts.push({ text: text.slice(last, at) });
    parts.push({ text: match[0], href: match[0] });
    last = at + match[0].length;
  }
  if (last < text.length) parts.push({ text: text.slice(last) });
  return parts;
}

export function PlainTextWithLinks({ text, className }: { text: string; className?: string }) {
  return (
    <p className={`whitespace-pre-line ${className ?? ""}`}>
      {linkParts(text).map((part, i) =>
        part.href ? (
          <a
            key={i}
            href={part.href}
            target="_blank"
            rel="noopener noreferrer"
            className="font-medium text-brand underline underline-offset-2 break-all"
          >
            {part.text}
          </a>
        ) : (
          <span key={i}>{part.text}</span>
        ),
      )}
    </p>
  );
}
