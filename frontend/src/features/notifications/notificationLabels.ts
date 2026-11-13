/**
 * The small tag under a notification, in plain words (audit US-10).
 *
 * The server's notification types are system names ("New Record (Proposal /
 * Thesis)", "Record Routed"). The sentence above the tag already says what
 * happened, so the tag only names the kind of thing, in sentence case. A type
 * this map has not met falls back to its own name, cut at any bracket or
 * dash and put in sentence case, so a new server type never shows a raw code.
 */
const PLAIN: Record<string, string> = {
  "New Record (Proposal / Thesis)": "New submission",
  "New Record (Project)": "New submission",
  "Record Routed": "Sent for review",
  "New Version Submitted": "New version",
  "Office Review Complete": "Office review finished",
  "Record Advanced": "Moved on",
};

export function notificationTypeLabel(name: string): string {
  const known = PLAIN[name];
  if (known) return known;
  const base = name.split(/\s+[(-]/)[0].trim();
  if (!base) return "";
  // Sentence case, but an acronym ("IERC", "RDCO") keeps its capitals.
  const words = base.split(/\s+/).map((word, i) =>
    word.length > 1 && word === word.toUpperCase() ? word : i === 0 ? word : word.toLowerCase(),
  );
  const first = words[0];
  words[0] = first.length > 1 && first === first.toUpperCase()
    ? first
    : first.charAt(0).toUpperCase() + first.slice(1).toLowerCase();
  return words.join(" ");
}
