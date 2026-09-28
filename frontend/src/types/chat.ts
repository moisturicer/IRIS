/**
 * Chat-screen message shape, shared by Ask IRIS and Paper Chat (IR-298).
 *
 * A thin view over the backend's Conversation/Turn wire shapes
 * (`types/ai.ts`) rather than a second source of truth: a live answer maps
 * straight onto one of these, and so does a replayed Turn, which is what
 * lets both surfaces render through the same `ChatMessageBubble`.
 */
import type { ChatCitation, SemanticSearchResult } from "./ai";

export type ChatRole = "user" | "assistant";

export interface ChatMessage {
  id:         string;
  role:       ChatRole;
  content:    string;
  /**
   * The Passages this reply cited (IR-284). A live answer's citations carry
   * the quote and the record's title; a replayed Turn's carry only the
   * pointer (record, chunk, page) until IR-299 re-resolves the text.
   */
  citations?: ChatCitation[];
  /**
   * The Record cards for those Passages, as the answer returned them.
   *
   * Stored with the reply rather than held in screen state: state reset to
   * `[]` on every conversation switch and did not survive a reload, so the
   * sources panel showed passages whose authors had gone missing — or, worse,
   * cards left over from the previous conversation.
   */
  sources?:   SemanticSearchResult[];
  /** True when retrieval fell back to keyword matching for this reply. */
  degraded?:  boolean;
  /**
   * True when this reply left its Conversation's Record scope because the
   * reader asked to search all papers (IR-298, ADR-026 §9). Undefined for a
   * user message, and for an assistant message in an unscoped Conversation.
   */
  widened?:   boolean;
  /**
   * The standalone question retrieval actually searched with, when this
   * reply answered a rewritten follow-up (IR-296/IR-383). Undefined when
   * resolution did not run or changed nothing -- the reader then saw
   * exactly what they typed searched.
   */
  resolvedQuestion?: string | null;
  /**
   * True when the stream that produced this reply never reached its
   * terminal event — the connection dropped, the vendor timed out, the
   * server restarted (IR-328) — so `content` is whatever text arrived
   * before the cutoff, not the model's complete answer (IR-329).
   */
  partial?:   boolean;
  /**
   * The model's working behind this reply (IR-381), shown in a panel that is
   * collapsed by default and never folded into `content` — the two arrived on
   * separate channels and only `content` was scanned for citation markers.
   * Undefined when the model reasoned nothing, or when the task that answered
   * has reasoning switched off in its Profile.
   */
  reasoning?: string | null;
  createdAt:  string;
}
