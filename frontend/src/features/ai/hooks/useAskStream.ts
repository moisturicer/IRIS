import { useCallback, useState } from "react";
import { aiApi } from "@/api/ai";
import { newChatMessage } from "@/lib/chatMessages";
import type { ChatCitation } from "@/types/ai";
import type { ChatMessage } from "@/types/chat";

/**
 * The reader-visible phase of an in-flight answer (IR-329). Deliberately
 * fewer than the event vocabulary -- copy must read as one pipeline step,
 * never parallel agents (ADR-028).
 */
export type StreamStage = "searching" | "found" | "thinking" | "answering";

export interface StreamingState {
  stage:     StreamStage;
  foundInfo: { passageCount: number; recordCount: number } | null;
  /** The raw, still-unresolved answer text accumulated so far. */
  text:      string;
  /**
   * The model's reasoning accumulated so far (IR-381), on its own channel.
   * Never joined into `text`: only `text` is scanned for citation markers and
   * only `text` becomes the stored answer. Empty until a `reasoning_delta`
   * arrives, which for a task with reasoning switched off is never.
   */
  reasoning: string;
  /** Populated once `citations_resolved` arrives, empty until then. */
  citations: ChatCitation[];
}

interface AskStreamOptions {
  conversationId?: number;
  topK?:           number;
  widen?:          boolean;
}

export interface AskStreamResult {
  message:        ChatMessage;
  conversationId: number | null;
}

const INTERRUPTED_TEXT = "The answer was interrupted before it finished.";

/**
 * Drives one `/ai/ask/stream/` call. Resolves once it's over -- via `done`,
 * or a connection drop after at least one event (IR-328's partial case).
 * Rejects only when nothing ever streamed, matching `aiApi.ask`'s failure shape.
 */
export function useAskStream() {
  const [streaming, setStreaming] = useState<StreamingState | null>(null);

  const ask = useCallback(
    async (question: string, options: AskStreamOptions = {}): Promise<AskStreamResult> => {
      let text = "";
      let reasoning = "";
      let citations: ChatCitation[] = [];
      let sawAnyEvent = false;

      setStreaming({ stage: "searching", foundInfo: null, text: "", reasoning: "", citations: [] });

      const finishPartial = (): AskStreamResult => {
        setStreaming(null);
        return {
          message: newChatMessage("assistant", text || INTERRUPTED_TEXT, {
            citations,
            // Whatever working arrived before the cutoff is still worth
            // showing -- the server stored the same text on the Turn.
            reasoning: reasoning || null,
            partial: true,
          }),
          conversationId: options.conversationId ?? null,
        };
      };

      try {
        for await (const { event, data } of aiApi.askStream(question, options)) {
          sawAnyEvent = true;
          const payload = (data ?? {}) as Record<string, unknown>;

          if (event === "retrieval_started") {
            setStreaming((s) => (s ? { ...s, stage: "searching" } : s));
          } else if (event === "retrieval_finished") {
            setStreaming((s) =>
              s
                ? {
                    ...s,
                    stage: "found",
                    foundInfo: {
                      passageCount: payload.passage_count as number,
                      recordCount:  payload.record_count as number,
                    },
                  }
                : s,
            );
          } else if (event === "generation_started") {
            setStreaming((s) => (s && s.stage !== "answering" ? { ...s, stage: "thinking" } : s));
          } else if (event === "reasoning_delta") {
            reasoning += payload.text as string;
            const snapshot = reasoning;
            setStreaming((s) =>
              s
                ? {
                    ...s,
                    // Reasoning arriving while the answer is already writing
                    // must not pull the stage back -- the answer is the thing
                    // on screen by then.
                    stage:     s.stage === "answering" ? s.stage : "thinking",
                    reasoning: snapshot,
                  }
                : s,
            );
          } else if (event === "text_delta") {
            text += payload.text as string;
            const snapshot = text;
            setStreaming((s) => (s ? { ...s, stage: "answering", text: snapshot } : s));
          } else if (event === "citations_resolved") {
            citations = payload.citations as ChatCitation[];
            setStreaming((s) => (s ? { ...s, citations } : s));
          } else if (event === "done") {
            const body = (payload.answer ?? payload.message ?? "No readable sources matched that question.") as string;
            const message = newChatMessage("assistant", body, {
              citations: payload.citations as ChatCitation[],
              sources:   payload.sources as ChatMessage["sources"],
              degraded:  payload.degraded as boolean,
              widened:   payload.widened as boolean,
              resolvedQuestion: payload.resolved_question as string | null,
              // The server's joined text, not the deltas this hook
              // accumulated: one source, so a reopened Turn and a watched
              // one render the same panel (IR-381).
              reasoning: (payload.reasoning as string | null) ?? (reasoning || null),
            });
            setStreaming(null);
            return {
              message,
              conversationId: (payload.conversation_id as number | null) ?? null,
            };
          }
        }
      } catch (err) {
        if (!sawAnyEvent) {
          setStreaming(null);
          throw err;
        }
        return finishPartial();
      }

      // The generator ended cleanly with no `done` -- the same partial case,
      // reached through a closed connection rather than a thrown error.
      return finishPartial();
    },
    [],
  );

  return { streaming, ask };
}
