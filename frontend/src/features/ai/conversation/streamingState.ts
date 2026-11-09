/**
 * The live state of an answer as the transcript shows it (IR-329, IR-595).
 *
 * Django's streamed answers are retired (IR-957); the shape stays because the
 * message list still renders it.
 */
import type { CandidateRow, ChatCitation } from "@/types/ai";

/** What the server says an answer is doing (IR-595): the whole public vocabulary. */
export type StreamActivity = "waiting" | "thinking" | "preparing";

export interface StreamingState {
  /** The queued run being followed, once known (IR-544) -- what Stop cancels. */
  runId?:   string;
  activity: StreamActivity;
  label:    string;
  /** When the question was submitted; absent for a run followed after a reopen. */
  startedAt?: number;
  /** A listing's candidates, in rank order, one row per paper (IR-546). */
  candidates?: CandidateRow[];
  /** The raw, still-unresolved answer text accumulated so far. */
  text:      string;
  /** Populated once `citations_resolved` arrives, empty until then. */
  citations: ChatCitation[];
}
