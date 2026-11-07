import { isRequestTimeout } from "@/api/requestPolicy";

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
