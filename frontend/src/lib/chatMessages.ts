/**
 * Building `ChatMessage`s from the two shapes a chat surface actually gets:
 * a live answer, and a replayed Turn (IR-298).
 *
 * Shared by Ask IRIS and Paper Chat, which are one Conversation model behind
 * two screens (ADR-019) — a second copy of this mapping is how one screen
 * would quietly render a replayed Turn differently from the other.
 */
import type { ChatMessage } from "@/types/chat";
import type { ConversationTurn } from "@/types/ai";

export function newChatMessage(
  role: ChatMessage["role"],
  content: string,
  grounding: Pick<ChatMessage, "citations" | "sources" | "degraded" | "widened" | "partial"> = {},
): ChatMessage {
  return {
    id:        crypto.randomUUID(),
    role,
    content,
    ...grounding,
    createdAt: new Date().toISOString(),
  };
}

/** A stored Turn is one question and one answer; a transcript needs both as messages. */
export function turnToMessages(turn: ConversationTurn): ChatMessage[] {
  return [
    {
      id:        `${turn.id}-q`,
      role:      "user",
      content:   turn.question,
      createdAt: turn.created_at,
    },
    {
      id:        `${turn.id}-a`,
      role:      "assistant",
      content:   turn.answer ?? turn.message ?? "No readable sources matched that question.",
      citations: turn.citations,
      degraded:  turn.degraded,
      widened:   turn.widened,
      partial:   turn.partial,
      createdAt: turn.created_at,
    },
  ];
}
