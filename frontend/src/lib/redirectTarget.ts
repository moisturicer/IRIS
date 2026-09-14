/**
 * Where a sign-in is allowed to send you (IR-236).
 *
 * The route guard records the page an unauthenticated visitor asked for, and
 * the login screen navigates there once they sign in. That is a redirect whose
 * destination came from outside the code — a `?next=` on a link someone was
 * sent, or router state — so **every destination passes through here first**,
 * and there is deliberately only one of these functions. A second copy of this
 * rule, spelled slightly differently, is how an open redirector gets shipped.
 *
 * The rule itself: a destination is a path *inside this app*, or it is
 * discarded in favour of the caller's default. Nothing absolute, nothing
 * protocol-relative, nothing with a scheme, and not the auth screens
 * themselves.
 */

/**
 * Screens that are never a destination. Landing back on `/login` after signing
 * in is a loop, and `/signup` is the same mistake wearing a different name.
 */
const AUTH_PATHS = new Set(["/login", "/signup"]);

/**
 * The part of a location that identifies a page — path, query and fragment.
 *
 * A destination is all three or it is not the page someone asked for: the query
 * carries a queue's filters and the fragment carries the row they were pointed
 * at. Both `window.location` and react-router's `Location` satisfy this shape,
 * which is the point — the route guard and the idle-timeout redirect read from
 * different objects and must agree on what "the page they were on" means.
 */
export function wholePath(location: {
  pathname: string;
  search: string;
  hash: string;
}): string {
  return `${location.pathname}${location.search}${location.hash}`;
}

/** Highest code point a browser strips out of a URL (the C0 control range). */
const LAST_C0_CONTROL = 0x1f;
/** DEL, stripped alongside the C0 range. */
const DEL = 0x7f;

/**
 * Remove the characters a browser drops from a URL before parsing it — tab,
 * newline, carriage return and the rest of the C0 controls, plus DEL.
 *
 * This matters more than it looks. `"/<tab>/evil.example"` fails a naive
 * `startsWith("//")` check and then navigates to `//evil.example` anyway,
 * because the browser removed the tab first. Validating a string the browser
 * will not act on is not validation.
 */
function stripUrlControlCharacters(value: string): string {
  let out = "";
  for (const char of value) {
    const code = char.codePointAt(0) ?? 0;
    if (code > LAST_C0_CONTROL && code !== DEL) out += char;
  }
  return out;
}

/**
 * Does this read as "same scheme, different host"?
 *
 * `//host` is the classic open-redirect payload, and `/\host` is the same thing
 * spelled with a backslash — WHATWG URL parsing treats the two alike for
 * http(s), so anything checking one must check the other.
 */
function looksProtocolRelative(path: string): boolean {
  return path.startsWith("//") || path.startsWith("/\\");
}

/**
 * Return `candidate` as an in-app path to navigate to, or `null` if it is not
 * one. Callers fall back to their own default on `null` — this function never
 * invents a destination.
 *
 * Accepts `unknown` on purpose: the two real callers read it out of router
 * state and a query string, neither of which TypeScript can vouch for.
 */
export function safeRedirectPath(candidate: unknown): string | null {
  if (typeof candidate !== "string") return null;

  const cleaned = stripUrlControlCharacters(candidate).trim();

  // A destination starts at the app root. This rejects bare relative paths
  // ("records/42", "../admin/audit"), which resolve against whatever the
  // current URL happens to be, and every scheme — "https:", "javascript:",
  // "data:" — in one line.
  if (!cleaned.startsWith("/")) return null;

  // Both spellings of "same scheme, different host", refused up front so the
  // common case never reaches the parser.
  if (looksProtocolRelative(cleaned)) return null;

  let url: URL;
  try {
    url = new URL(cleaned, window.location.origin);
  } catch {
    return null;
  }

  // The backstop. Anything that resolved off-origin, however it was spelled,
  // stops here.
  if (url.origin !== window.location.origin) return null;

  // **Checked again, on the output this time, and this is not belt-and-braces.**
  // `new URL` resolves `/..` by popping a segment, and popping the *empty
  // leading* segment rewrites `/..//evil.example` into the pathname
  // `//evil.example`. The input never started with `//` and the origin is still
  // ours, so both checks above pass while the string handed back is
  // protocol-relative. Validating what is returned is the only check that
  // cannot be walked around by making the parser do the assembling.
  if (looksProtocolRelative(url.pathname)) return null;

  if (AUTH_PATHS.has(url.pathname)) return null;

  // Query and fragment are part of the destination: a deep link into the review
  // queue carries its filters, and an anchor carries the row someone was told
  // to look at.
  return `${url.pathname}${url.search}${url.hash}`;
}
