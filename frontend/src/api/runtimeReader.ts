import { apiClient } from "./client";

export const READER_PROTOCOL = "runs-reader-1";

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
  created_at?: string;
  finished_at?: string | null;
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
  /** What the run is doing now: a coarse phase and its latest step. Null once it ends. */
  activity?: null | ReaderActivity;
  /** Tokens the provider reported for this run's model calls. */
  usage?: null | ReaderUsage;
  /** Older context condensed into a summary; the original Turns stay (IR-735). Absent from older servers. */
  compaction?: null | { compactions: number; turns_compacted: number; last: "compacted" | "kept" };
  capabilities: { manual_compaction: boolean };
}
export interface ReaderActivity {
  phase: "waiting" | "working";
  label: string;
  /** When this phase began (ISO). */
  since: string;
  step: null | { kind: "read" | "search" | "catalogue" | "recall"; label: string; detail: string[] };
}
export interface ReaderUsage {
  calls: number;
  input_tokens: number;
  output_tokens: number;
  cost_usd: number;
  /** The latest call's prompt: how full the model's context window is. */
  context_tokens: number;
  capacity_tokens: number | null;
  /** Held back for the answer. */
  reserved_tokens: number | null;
}
export interface ReaderConversationSummary { id: string; title: string; record_id: number | null; updated_at: string }
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
    async list() {
      const { data } = await apiClient.get<{ protocol: string; conversations: ReaderConversationSummary[] }>(
        `${base}/conversations`, config);
      return checked(data).conversations;
    },
    async remove(id: string) {
      await apiClient.delete(`${base}/conversations/${encodeURIComponent(id)}`, config);
    },
    async reopen(id: string) {
      const { data } = await apiClient.get<ReaderConversation>(`${base}/conversations/${encodeURIComponent(id)}`, config);
      return checked(data);
    },
  };
}
