/**
 * Nests a model's under-indented lists the way it meant them (IR-1306).
 *
 * Markdown nests a line under a list item only when it is indented to that
 * item's text: three spaces under "1. ", four under "10. ". Models usually
 * indent by two, so a sub-list under a numbered item came out as a separate
 * list, the numbering restarted, and continuation lines fell out of their item.
 * Any line indented past an open item's marker is moved to that item's text
 * column; everything else, and fenced code, is left exactly as written.
 */
const ITEM = /^( *)([-*+]|\d{1,9}[.)])( {1,4}|$)(.*)$/;
const FENCE = /^ {0,3}(`{3,}|~{3,})/;

interface Open { indent: number; content: number }

export function nestLists(text: string): string {
  if (!text.includes("\n")) return text;
  const out: string[] = [];
  let open: Open[] = [];
  let fence: string | null = null;

  for (const line of text.split("\n")) {
    const fenced = FENCE.exec(line);
    if (fence) {
      out.push(line);
      if (fenced && fenced[1][0] === fence[0] && fenced[1].length >= fence.length) fence = null;
      continue;
    }
    if (fenced && open.length === 0) {
      fence = fenced[1];
      out.push(line);
      continue;
    }
    if (!line.trim()) { out.push(line); continue; }

    const spaces = line.length - line.trimStart().length;
    const item = ITEM.exec(line);
    if (item) {
      while (open.length && open[open.length - 1].indent >= spaces) open.pop();
      // A child of the item still open, written as far in as that item's text.
      const parent = open[open.length - 1];
      const at = parent ? parent.content : 0;
      const gap = item[3] || " ";
      open.push({ indent: spaces, content: at + item[2].length + gap.length });
      out.push(" ".repeat(at) + item[2] + gap + item[4]);
      continue;
    }
    if (spaces === 0) {
      // Text at the margin ends every list, except a lazy continuation, which Markdown keeps anyway.
      if (out.length && !out[out.length - 1].trim()) open = [];
      out.push(line);
      continue;
    }
    // An indented line belongs to the innermost item it reaches past the marker of.
    while (open.length && open[open.length - 1].indent >= spaces) open.pop();
    const owner = open[open.length - 1];
    out.push(owner ? " ".repeat(owner.content) + line.trimStart() : line);
    if (fenced) fence = fenced[1];
  }
  return out.join("\n");
}
