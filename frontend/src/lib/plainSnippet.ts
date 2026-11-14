/**
 * A passage's text as plain words, for a place that shows a snippet rather than
 * rendering Markdown (IR-1090). Extraction hands over chunk text with its
 * headings, emphasis, links and table pipes still in it; a snippet that shows
 * `**` and `[x](y)` reads as broken.
 *
 * Only what is Markdown goes. `$$...$$` display formulas are kept exactly, so
 * the caller can still typeset them, and `snake_case` and a lone `*` are left
 * alone: dropping real characters is worse than showing a stray one.
 */

const DISPLAY_MATH = /\$\$[\s\S]+?\$\$/g;
const MATH_SENTINEL = "\u0000";

export function plainSnippet(text: string): string {
  const math: string[] = [];
  let out = text.replace(DISPLAY_MATH, (formula) => {
    math.push(formula);
    return `${MATH_SENTINEL}${math.length - 1}${MATH_SENTINEL}`;
  });

  out = out
    // A fenced block keeps its code and loses its fences.
    .replace(/```[^\n]*\n?([\s\S]*?)```/g, "$1")
    .replace(/!\[([^\]]*)\]\([^)]*\)/g, "$1")
    .replace(/\[([^\]]+)\]\([^)]*\)/g, "$1")
    .replace(/\[([^\]]+)\]\[[^\]]*\]/g, "$1")
    .replace(/\[\^[^\]]+\]/g, "")
    .replace(/<\/?[a-zA-Z][^>]*>/g, "")
    .split("\n")
    .map(plainLine)
    .filter((line) => line !== "")
    .join(" ");

  out = out
    .replace(/(\*\*|__)(?=\S)([\s\S]*?\S)\1/g, "$2")
    .replace(/(^|[^*\w])\*(?=\S)([^*]*?\S)\*(?!\*)/g, "$1$2")
    .replace(/(^|[^\w])_(?=\S)([^_]*?\S)_(?![\w])/g, "$1$2")
    .replace(/~~([\s\S]*?)~~/g, "$1")
    .replace(/`([^`]*)`/g, "$1")
    .replace(/\\([\\`*_{}[\]()#+\-.!|>~])/g, "$1")
    .replace(/\s+/g, " ")
    .trim();

  return out.replace(new RegExp(`${MATH_SENTINEL}(\\d+)${MATH_SENTINEL}`, "g"), (_, index: string) => math[Number(index)]);
}

/** One line without its block markers: heading, quote, list, rule, or table row. */
function plainLine(raw: string): string {
  const line = raw.trim();
  if (/^([-*_]\s*){3,}$/.test(line)) return "";
  if (/^\|?[\s:|-]+\|?$/.test(line) && line.includes("-") && line.includes("|")) return "";
  if (line.startsWith("|")) {
    return line.replace(/^\|/, "").replace(/\|$/, "").split("|").map((cell) => cell.trim()).filter(Boolean).join(" · ");
  }
  return line
    .replace(/^#{1,6}\s+/, "")
    .replace(/^>+\s?/, "")
    .replace(/^([-*+]|\d+[.)])\s+/, "");
}
