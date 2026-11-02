import { apiClient } from "./client";

export const READER_PROTOCOL = "runs-reader-1";
export const runtimeReaderEnabled = import.meta.env.VITE_AI_RUNTIME_READER_ENABLED === "true";
export type Depth = "ordinary" | "deep";
export interface ReaderRun {
  protocol: typeof READER_PROTOCOL;
  id: string;
  conversation_id: string;
  state: "queued" | "running" | "completed" | "cancelled" | "conflict" | "expired" | "failed" | "deleted";
  question: string;
  base_revision: number;
  version: number;
  depth: Depth;
  awaiting_reader: boolean;
  sources_available: boolean;
  plan: null | { revision: number; steps: { id: string; title: string; status: "pending" | "in_progress" | "done" | "blocked" }[] };
  context: null | { estimated: true; used_tokens: number; capacity_tokens: number };
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

function checked<T extends { protocol: string }>(data: T): T {
  if (data.protocol !== READER_PROTOCOL) throw new Error("Please reload to reconnect to Ask IRIS.");
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
    async reopen(id: string) {
      const { data } = await apiClient.get<ReaderConversation>(`${base}/conversations/${encodeURIComponent(id)}`, config);
      return checked(data);
    },
  };
}
