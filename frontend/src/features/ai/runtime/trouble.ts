import { isAxiosError } from "axios";
import { ProtocolMismatch, RELOAD_TO_RECONNECT } from "@/api/runtimeReader";

/**
 * Why a request to the Ask IRIS runtime failed, in the groups the reader tells apart.
 *
 * `session`, `reload` and `busy` describe the whole connection, not one request, so
 * when the chat and the conversation list both hit one of them it is said once, in
 * the chat (IR-1238). `missing` is about one conversation, `conflict` about its
 * revision; `refused` and `unreachable` are the rest.
 */
export type TroubleKind = "session" | "reload" | "busy" | "missing" | "refused" | "conflict" | "unavailable" | "unreachable";

/** What went wrong, in the reader's terms, and whether reconnecting can help (IR-863). */
export interface Trouble { kind: TroubleKind; message: string; retry: boolean; missing?: boolean }

/** The kinds that speak for the whole connection: shown in one place however many requests met them. */
export const CONNECTION_WIDE: readonly TroubleKind[] = ["session", "reload", "busy"];

export function trouble(failure: unknown): Trouble {
  if (failure instanceof ProtocolMismatch) return { kind: "reload", message: failure.message, retry: false };
  const response = isAxiosError(failure) ? failure.response : undefined;
  const code = (response?.data as { status?: unknown } | undefined)?.status;
  if (response?.status === 429 || (response?.status === 503 && code === "busy")) {
    return { kind: "busy", message: "IRIS is busy right now. Reconnect in a moment to try again.", retry: true };
  }
  if (response?.status === 401) return { kind: "session", message: "Your session has ended. Sign in again to continue.", retry: false };
  if (response?.status === 403) {
    return { kind: "refused", message: "Ask IRIS can't open research for you right now.", retry: false };
  }
  if (response?.status === 404) {
    return { kind: "missing", message: "This conversation is not available. It may have been deleted, or the link may be wrong.",
      retry: false, missing: true };
  }
  if (response?.status === 406) return { kind: "reload", message: RELOAD_TO_RECONNECT, retry: false };
  if (response && response.status >= 500) {
    return { kind: "unavailable", message: "Ask IRIS is unavailable right now. Reconnect to try again later.", retry: true };
  }
  return { kind: "unreachable", message: "IRIS could not connect. Reconnect to try again.", retry: true };
}
