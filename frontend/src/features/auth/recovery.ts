/**
 * What a failed recovery request means (IR-642, ADR-045 §2, §7).
 *
 * The server's answers are a closed set of `code`s, so the reading is exact
 * rather than guessed from wording. Anything that never reached a working
 * server is `unreachable`, and that is an *unknown* outcome: the request may
 * have been accepted before the connection dropped, so nothing here may say it
 * failed.
 */
import { useEffect, useState } from "react";

export type RecoveryFailure =
  | { kind: "validation"; errors: Record<string, string[]> }
  | { kind: "invalid_link" }
  | { kind: "rate_limited"; retryAfter: number }
  | { kind: "unavailable"; retryAfter: number }
  | { kind: "unreachable" };

interface FailedRequest {
  response?: { status?: number; data?: unknown };
}

function seconds(value: unknown, fallback: number): number {
  return typeof value === "number" && Number.isFinite(value) && value > 0 ? Math.ceil(value) : fallback;
}

export function classifyRecoveryFailure(error: unknown): RecoveryFailure {
  const response = (error as FailedRequest | null)?.response;
  if (!response?.status) return { kind: "unreachable" };
  const data = (response.data ?? {}) as { code?: unknown; errors?: unknown; retry_after?: unknown };

  if (response.status === 429) return { kind: "rate_limited", retryAfter: seconds(data.retry_after, 60) };
  if (data.code === "invalid_link") return { kind: "invalid_link" };
  if (data.code === "validation_error" && data.errors && typeof data.errors === "object") {
    return { kind: "validation", errors: data.errors as Record<string, string[]> };
  }
  if (response.status === 503) return { kind: "unavailable", retryAfter: seconds(data.retry_after, 60) };
  return { kind: "unreachable" };
}

/** The sentence a page shows for a failure that leaves the form in place. */
export function retryMessage(failure: RecoveryFailure): string {
  switch (failure.kind) {
    case "rate_limited":
      return `Too many requests. Try again in ${failure.retryAfter} seconds.`;
    case "unavailable":
      return `IRIS could not take this request right now. Try again in ${failure.retryAfter} seconds.`;
    default:
      // Unknown outcome: it may have been accepted. Retrying is safe.
      return "Your request may not have reached IRIS. Check your connection and try again.";
  }
}

/**
 * Seconds left until ``until`` (a `Date.now()` value), ticking once a second.
 * Zero when there is nothing to wait for.
 */
export function useSecondsUntil(until: number | null): number {
  const remaining = () => (until ? Math.max(0, Math.ceil((until - Date.now()) / 1000)) : 0);
  const [left, setLeft] = useState(remaining);
  useEffect(() => {
    setLeft(remaining());
    if (!until) return undefined;
    const timer = window.setInterval(() => {
      const next = remaining();
      setLeft(next);
      if (next === 0) window.clearInterval(timer);
    }, 1000);
    return () => window.clearInterval(timer);
    // `remaining` reads only `until`.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [until]);
  return left;
}

/**
 * ADR-045 §3: a page holding a recovery token sends no Referer, so neither
 * the token's page nor anything it links to learns where the reader came from.
 */
export function useNoReferrer(): void {
  useEffect(() => {
    const meta = document.createElement("meta");
    meta.name = "referrer";
    meta.content = "no-referrer";
    document.head.appendChild(meta);
    return () => meta.remove();
  }, []);
}
