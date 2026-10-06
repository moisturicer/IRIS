/**
 * What counts as deciding by role (IR-411; spec §4.8, ui-ux/16 §1).
 *
 * A screen asks the capabilities adapter what a viewer may do with a record.
 * It never compares role names, and never reads `can_act`, which is the
 * adapter's input. Each pattern below is one way that rule has been broken in
 * this codebase before; `role_name` on its own is not one, because the access
 * map (`lib/access.ts`) legitimately takes it to decide which *screens* open.
 *
 * Comments are stripped first, so a comment explaining the rule does not break it.
 */
const PATTERNS: ReadonlyArray<{ name: string; pattern: RegExp }> = [
  { name: "a ROLES constant", pattern: /\bROLES\.[A-Z]+\b/g },
  { name: "a role list", pattern: /\b(?:STAFF|REVIEWER|ALL|AUTHOR|REQUEST_QUEUE|AUDIT_LOG)_ROLES\b/g },
  { name: "a role hook", pattern: /\buseIs(?:Reviewer|Staff)\b/g },
  { name: "a role_name comparison", pattern: /\brole_name\s*[!=]==?|[!=]==?\s*[\w.?]*\brole_name\b/g },
  {
    name: "a role-name literal comparison",
    pattern: /[!=]==?\s*["'](?:Student|Adviser|RDCO|ITSO|IERC|KTTO)["']|["'](?:Student|Adviser|RDCO|ITSO|IERC|KTTO)["']\s*[!=]==?/g,
  },
  { name: "can_act", pattern: /\bcan_act\b/g },
];

/** Line and block comments removed; strings and code kept. */
function withoutComments(source: string): string {
  return source.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:"'`\\])\/\/.*$/gm, "$1");
}

/** Every role decision in `source`, as "<kind>: <text>", in order of appearance. */
export function roleDecisions(source: string): string[] {
  const code = withoutComments(source);
  const found: Array<{ at: number; text: string }> = [];
  for (const { name, pattern } of PATTERNS) {
    for (const match of code.matchAll(pattern)) {
      found.push({ at: match.index ?? 0, text: `${name}: ${match[0].trim()}` });
    }
  }
  return found.sort((a, b) => a.at - b.at).map((f) => f.text);
}
