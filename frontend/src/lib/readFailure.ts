import { isRequestTimeout } from "@/api/requestPolicy";

import { errorDetail } from "./errorDetail";

/**
 * What a failed read means to the reader (IR-906):
 *
 * - `interrupted`: no answer in time. Nothing is known about the server, so
 *   the one thing offered is Retry (IR-914, ADR-061).
 * - `unavailable`: the server refused (403) or found nothing (404). IRIS
 *   answers a hidden Record and a missing id alike and never says which
 *   (IR-153), so this screen must not either. It is also what a Record
 *   becomes when access is revoked while it is open.
 * - `failed`: anything else; the network or the server broke.
 */
export type ReadFailureKind = "interrupted" | "unavailable" | "failed";

export function readFailureKind(err: unknown): ReadFailureKind {
  if (isRequestTimeout(err)) return "interrupted";
  const status = (err as { response?: { status?: number } } | null)?.response?.status;
  return status === 403 || status === 404 ? "unavailable" : "failed";
}

/**
 * Who failed (IR-1078, audit US-05): the reader's connection, or IRIS.
 *
 * - `offline`: the browser says it is offline and nothing answered.
 * - `slow`: a timeout or a 5xx. It is IRIS's side, so the message must not send
 *   the reader off to check their own connection.
 * - `unreached`: nothing answered, no timeout fired, and the browser believes it
 *   is online (a refused connection, a dropped socket).
 * - `rejected`: a 4xx. IRIS answered and refused; its own reason is the message.
 */
export type FailureCause = "offline" | "slow" | "unreached" | "rejected";

/** The one place the words for "your connection" live. */
export const OFFLINE_MESSAGE = "Check your connection and try again.";
export const SLOW_MESSAGE = "IRIS took too long to answer. Try again.";
export const UNREACHED_MESSAGE = "We couldn't reach IRIS. Try again.";
export const REFUSED_MESSAGE = "IRIS couldn't complete that. Try again.";

export function failureCause(err: unknown): FailureCause {
  const status = (err as { response?: { status?: number } } | null)?.response?.status;
  if (typeof status === "number") return status >= 400 && status < 500 ? "rejected" : "slow";
  // No answer at all. `onLine` is only trusted when it says offline: a browser
  // on a network with no route out still reports online, and "we couldn't reach
  // IRIS" is true either way. A timeout is IRIS being slow, never the connection
  // alone, so it is read before the unreached case.
  if (typeof navigator !== "undefined" && navigator.onLine === false) return "offline";
  return isRequestTimeout(err) ? "slow" : "unreached";
}

interface FailureMessageOptions {
  /** What was being done, in the reader's words, put in front: "The notice didn't load." */
  lead?: string;
  /** Said for a 4xx that carries no reason of its own. */
  rejected?: string;
  /** Said when nothing answered: a write that may not have arrived says so here. */
  unreached?: string;
}

/**
 * The one helper that picks the sentence for a failed request. Offline blames
 * the connection; a timeout or 5xx blames IRIS and says to try again; a 4xx
 * says what the server said. Every screen asks here, so none writes its own.
 */
export function failureMessage(err?: unknown, options: FailureMessageOptions = {}): string {
  const cause = failureCause(err);
  const body = cause === "offline"
    ? OFFLINE_MESSAGE
    : cause === "slow"
      ? SLOW_MESSAGE
      : cause === "unreached"
        ? options.unreached ?? UNREACHED_MESSAGE
        : errorDetail(err, options.rejected ?? REFUSED_MESSAGE);
  return options.lead ? `${options.lead} ${body}` : body;
}

/**
 * Try again for a wait with no read of its own to repeat (the session check, a
 * route's bundle): start the page over. Kept here so a test can stand in for it.
 */
export function reloadPage(): void {
  window.location.reload();
}
