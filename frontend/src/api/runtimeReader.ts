import { useEffect, useState } from "react";
import { apiClient } from "./client";

export const READER_PROTOCOL = "runs-reader-1";

/** Which path answers Ask IRIS: the deployment's choice, never the browser's (IR-863). */
export type ReaderPath = "runtime" | "django";
let knownPath: ReaderPath | undefined;
let readingPath: Promise<ReaderPath> | undefined;

/**
 * Reads `AI_RUNTIME_READER` once per page load. Unreadable means Django, the
 * path that answered before the switch existed; that is not remembered, so the
 * next surface to open asks again.
 */
export function loadReaderPath(): Promise<ReaderPath> {
  readingPath ??= apiClient.get<{ path: string }>("/ai/reader/").then(
    ({ data }) => (knownPath = data.path === "runtime" ? "runtime" : "django"),
    () => { readingPath = undefined; return "django" as const; },
  );
  return readingPath;
}

/** `undefined` until the switch has been read. */
export function useReaderPath(): ReaderPath | undefined {
  const [path, setPath] = useState(knownPath);
  useEffect(() => {
    if (path) return;
    let current = true;
    void loadReaderPath().then((next) => { if (current) setPath(next); });
    return () => { current = false; };
  }, [path]);
  return path;
}

/** Forget the switch, so the next surface reads it again. */
export function resetReaderPath() {
  knownPath = undefined;
  readingPath = undefined;
}
export type Depth = "ordinary" | "deep";
export interface ReaderRun {
  protocol: typeof READER_PROTOCOL;
  id: string;
  conversation_id: string;
  /** What the run is for: a question, or the reader's request to condense the conversation (IR-754). Absent from older servers. */
  kind?: "ask" | "compact";
  state: "queued" | "running" | "completed" | "cancelled" | "conflict" | "expired" | "failed" | "deleted";
  question: string;
  base_revision: number;
  version: number;
  depth: Depth;
  awaiting_reader: boolean;
  sources_available: boolean;
  /** The run this one retries, and the run that retried this one (IR-726). Absent from older servers. */
  retry_of?: string | null;
  retried_by?: string | null;
  /** Where this view ends in the run's journal: a reconnect asks for what came after it (IR-726). */
  cursor?: number;
  plan: null | { revision: number; steps: { id: string; title: string; status: "pending" | "in_progress" | "done" | "blocked" }[] };
  context: null | { estimated: true; used_tokens: number; capacity_tokens: number };
  /** Older context condensed into a summary; the original Turns stay (IR-735). Absent from older servers. */
  compaction?: null | { compactions: number; turns_compacted: number; last: "compacted" | "kept" };
  capabilities: { manual_compaction: boolean };
}
export interface ReaderConversation {
  protocol: typeof READER_PROTOCOL;
  id: string;
  revision: number;
  runs: ReaderRun[];
  turns: { id: string; run_id: string; ordinal: number; question: string; answer: string; kind: string;
    citations: { record_id: number; page: number; quote: string; revision: string }[] }[];
}

export const activeRun = (run: ReaderRun) => run.state === "queued" || run.state === "running";
/** Ended without an answer, so the reader may ask the same question again. */
export const retryable = (run: ReaderRun) =>
  (run.state === "cancelled" || run.state === "expired" || run.state === "failed")
  && run.kind !== "compact" && !run.retried_by;
export const compactionRun = (run: ReaderRun) => run.kind === "compact";

export const RELOAD_TO_RECONNECT = "Please reload to reconnect to Ask IRIS.";

/** The server speaks a reader protocol this page does not. */
export class ProtocolMismatch extends Error {}

function checked<T extends { protocol: string }>(data: T): T {
  if (data.protocol !== READER_PROTOCOL) throw new ProtocolMismatch(RELOAD_TO_RECONNECT);
  return data;
}

/** Same-origin edge injects server credentials; none are held by the browser. */
export function runtimeReader(recordId?: number) {
  const config = { baseURL: "/api/v1", headers: { "X-IRIS-Protocol": READER_PROTOCOL,
    ...(recordId ? { "X-IRIS-Record": String(recordId) } : {}) } };
  const base = "/ai/runtime";
  return {
    async submit(question: string, depth: Depth, key: string, conversation?: ReaderConversation) {
      const { data } = await apiClient.post<ReaderRun>(`${base}/runs`, {
        question, depth, ...(conversation ? { conversation_id: conversation.id, base_revision: conversation.revision } : {}),
      }, { ...config, headers: { ...config.headers, "Idempotency-Key": key } });
      return checked(data);
    },
    async status(id: string) {
      const { data } = await apiClient.get<ReaderRun>(`${base}/runs/${encodeURIComponent(id)}`, config);
      return checked(data);
    },
    async stop(id: string) {
      const { data } = await apiClient.post<ReaderRun>(`${base}/runs/${encodeURIComponent(id)}/cancel`, {}, config);
      return checked(data);
    },
    /** Ask again after a run ended without an answer: a new run linked to the first; the key makes a repeated click one request. */
    async retry(id: string, key: string) {
      const { data } = await apiClient.post<ReaderRun>(`${base}/runs/${encodeURIComponent(id)}/retry`, {},
        { ...config, headers: { ...config.headers, "Idempotency-Key": key } });
      return checked(data);
    },
    /** Condense an owned conversation as a run of its own; the key makes a repeated click one request. */
    async compact(conversation: ReaderConversation, key: string) {
      const { data } = await apiClient.post<ReaderRun>(
        `${base}/conversations/${encodeURIComponent(conversation.id)}/compact`,
        { base_revision: conversation.revision },
        { ...config, headers: { ...config.headers, "Idempotency-Key": key } });
      return checked(data);
    },
    async reopen(id: string) {
      const { data } = await apiClient.get<ReaderConversation>(`${base}/conversations/${encodeURIComponent(id)}`, config);
      return checked(data);
    },
  };
}
