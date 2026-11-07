/**
 * How long `apiClient` waits, and what it does when a request never answers
 * (IR-914, ADR-061).
 *
 * **Values are proposed, not approved.** ADR-061 is `Proposed`; the team sets
 * these two numbers by accepting it or amending them. They live here, and only
 * here, so changing one is a one-line edit.
 *
 * **Retry rule.** `apiClient` never retries a request on its own. The one
 * exception predates this file: a 401 is answered by one token refresh and one
 * replay (the server refused it, so nothing ran). A timed-out request is not
 * known to have been refused -- a write may have been applied -- so a write is
 * never sent again without a person asking, and a read is sent again only by
 * the reader's Retry (`useApiRead`).
 */
import type { AxiosError } from "axios";

/** An ordinary request: a list, a detail, a small write. */
export const DEFAULT_TIMEOUT_MS = 30_000;

/** An upload or a blob download, which is bounded by the size of the file, not the server. */
export const TRANSFER_TIMEOUT_MS = 300_000;

/**
 * A request that got no answer within its timeout. The UI shows it as the
 * "interrupted" state with a Retry, never as a server refusal: nothing is known
 * about whether the server acted.
 */
export class RequestTimeoutError extends Error {
  readonly timeoutMs: number;
  readonly method: string | undefined;
  readonly url: string | undefined;
  /** The axios error that carried the timeout. */
  readonly cause: unknown;

  constructor(timeoutMs: number, method?: string, url?: string, cause?: unknown) {
    super(`The request did not finish within ${timeoutMs / 1000} seconds.`);
    this.name = "RequestTimeoutError";
    this.timeoutMs = timeoutMs;
    this.method = method;
    this.url = url;
    this.cause = cause;
  }
}

export function isRequestTimeout(err: unknown): err is RequestTimeoutError {
  return err instanceof RequestTimeoutError;
}

/** The typed error for an axios timeout, or `null` for any other failure. */
export function asTimeoutError(error: AxiosError): RequestTimeoutError | null {
  // `code` alone, so this module (imported by every screen that reads) loads no
  // axios at run time; only `client.ts` needs it.
  if (error?.code !== "ETIMEDOUT") return null;
  return new RequestTimeoutError(
    error.config?.timeout ?? DEFAULT_TIMEOUT_MS,
    error.config?.method?.toLowerCase(),
    error.config?.url,
    error,
  );
}

/** A call that carries a file in either direction gets the longer timeout. */
export function isTransfer(config: { responseType?: string; data?: unknown }): boolean {
  return config.responseType === "blob" || config.data instanceof FormData;
}
