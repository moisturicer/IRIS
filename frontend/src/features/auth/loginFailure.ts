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

/**
 * Which lock refused the sign-in (IR-555). Only the server knows when its own
 * lock lifts, so `unlockAt` is the time it sent, or `null` when it sent none.
 * RDCO's lock never lifts on its own and carries no time at all.
 */
export type AccountLock =
  | { by: "attempts"; unlockAt: number | null }
  | { by: "admin" };

export type LoginFailure =
  | { kind: "credentials" }
  | { kind: "unverified" }
  | { kind: "locked"; lock: AccountLock }
  | { kind: "unreachable" }
  | { kind: "other"; detail: string };

const INVALID_CREDENTIALS_DETAIL = "Invalid credentials.";

interface FailedRequest {
  response?: { status?: number; data?: unknown };
}

/** A string field of a JSON reply, or `null` when the reply carried none. */
function jsonField(data: unknown, field: string): string | null {
  if (typeof data !== "object" || data === null) return null;
  const value = (data as Record<string, unknown>)[field];
  return typeof value === "string" && value.trim() ? value : null;
}

/** The server's `detail` string, or `null` when the reply carried none. */
function jsonDetail(data: unknown): string | null {
  return jsonField(data, "detail");
}

export function classifyLoginFailure(error: unknown): LoginFailure {
  const response = (error as FailedRequest | null)?.response;
  if (!response?.status) return { kind: "unreachable" };

  const { status } = response;
  if (status >= 500) return { kind: "unreachable" };

  // The server names its lock (IR-555), and that is read before any wording.
  const code = jsonField(response.data, "code");
  if (status === 429 && code === "too_many_attempts") {
    const unlockAt = Date.parse(jsonField(response.data, "unlock_at") ?? "");
    return { kind: "locked", lock: { by: "attempts", unlockAt: Number.isNaN(unlockAt) ? null : unlockAt } };
  }
  if (status === 403 && code === "locked_by_admin") return { kind: "locked", lock: { by: "admin" } };

  const detail = jsonDetail(response.data);
  if (status === 401 || detail === INVALID_CREDENTIALS_DETAIL) return { kind: "credentials" };

  // The server-side lock. django-axes (AXES_FAILURE_LIMIT) replaces the login
  // response with a plain-text 429, "Account locked: too many login
  // attempts…", so it carries no `detail` and would otherwise read as an
  // outage. A DRF throttle is a 429 too, but with a JSON detail, and stays
  // "other". This is an older server's reply, kept so it still opens the
  // dialog; it gives no time, so the dialog shows none.
  if (status === 429 && typeof response.data === "string" && /locked/i.test(response.data)) {
    return { kind: "locked", lock: { by: "attempts", unlockAt: null } };
  }

  // Anything below here needs the server's own words. A reply without them --
  // an HTML error page, a proxy's plain-text 404 -- came from something in
  // front of IRIS, not from IRIS.
  if (detail === null) return { kind: "unreachable" };

  const lower = detail.toLowerCase();
  // An older server's manual lock: the only 403 that says "locked".
  if (status === 403 && lower.includes("locked")) return { kind: "locked", lock: { by: "admin" } };
  if (status === 403 && lower.includes("not verified")) return { kind: "unverified" };

  return { kind: "other", detail };
}
