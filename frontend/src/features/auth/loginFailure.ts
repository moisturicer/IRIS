/**
 * What a failed sign-in means (IR-536, IR-200 defect 2).
 *
 * The rule this exists to hold: **only the server can say the password was
 * wrong.** The old fallback read any failure without a JSON `detail` -- an
 * nginx 502, a 500, a dropped connection -- as "Invalid email or password", so
 * people re-checked a password that was never wrong. A failure is now read as
 * a credentials problem only when the server says so (a 401, or its
 * "Invalid credentials." detail), and anything that never reached a working
 * server is "unreachable", which says nothing about the fields.
 *
 * The order matters: a 5xx is unreachable even when it carries a detail,
 * because a server that is failing has not judged the credentials.
 */

export type LoginFailure =
  | { kind: "credentials" }
  | { kind: "unverified" }
  | { kind: "locked" }
  | { kind: "unreachable" }
  | { kind: "other"; detail: string };

const INVALID_CREDENTIALS_DETAIL = "Invalid credentials.";

interface FailedRequest {
  response?: { status?: number; data?: unknown };
}

/** The server's `detail` string, or `null` when the reply carried none. */
function jsonDetail(data: unknown): string | null {
  if (typeof data !== "object" || data === null) return null;
  const detail = (data as { detail?: unknown }).detail;
  return typeof detail === "string" && detail.trim() ? detail : null;
}

export function classifyLoginFailure(error: unknown): LoginFailure {
  const response = (error as FailedRequest | null)?.response;
  if (!response?.status) return { kind: "unreachable" };

  const { status } = response;
  if (status >= 500) return { kind: "unreachable" };

  const detail = jsonDetail(response.data);
  if (status === 401 || detail === INVALID_CREDENTIALS_DETAIL) return { kind: "credentials" };

  // The server-side lock. django-axes (AXES_FAILURE_LIMIT) replaces the login
  // response with a plain-text 429, "Account locked: too many login
  // attempts…", so it carries no `detail` and would otherwise read as an
  // outage. A DRF throttle is a 429 too, but with a JSON detail, and stays
  // "other".
  if (status === 429 && typeof response.data === "string" && /locked/i.test(response.data)) {
    return { kind: "locked" };
  }

  // Anything below here needs the server's own words. A reply without them --
  // an HTML error page, a proxy's plain-text 404 -- came from something in
  // front of IRIS, not from IRIS.
  if (detail === null) return { kind: "unreachable" };

  const lower = detail.toLowerCase();
  if (status === 403 && lower.includes("locked")) return { kind: "locked" };
  if (status === 403 && lower.includes("not verified")) return { kind: "unverified" };

  return { kind: "other", detail };
}
