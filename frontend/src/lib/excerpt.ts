/** The opening of a quoted passage, short enough to scan: a sentence, or words up to `max`. */
export function excerpt(text: string, max = 180): string {
  const flat = text.replace(/\$\$[\s\S]*?\$\$/g, "…").replace(/\s+/g, " ").trim();
  if (flat.length <= max) return flat;
  const head = flat.slice(0, max);
  const sentence = head.match(/^.*[.!?](?=\s)/);
  if (sentence && sentence[0].length >= max / 3) return sentence[0];
  const space = head.lastIndexOf(" ");
  return `${(space > 0 ? head.slice(0, space) : head).replace(/[\s,;:]+$/, "")}…`;
}
