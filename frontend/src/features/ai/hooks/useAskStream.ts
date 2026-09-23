import { useCallback, useState } from "react";
import { aiApi } from "@/api/ai";
import { newChatMessage } from "@/lib/chatMessages";
import type { ChatCitation, ResponseStyle } from "@/types/ai";
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
  /** Populated once `citations_resolved` arrives, empty until then. */
  citations: ChatCitation[];
}

interface AskStreamOptions {
  conversationId?: number;
  topK?:           number;
  widen?:          boolean;
  responseStyle?:  ResponseStyle;
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
      let citations: ChatCitation[] = [];
      let sawAnyEvent = false;

      setStreaming({ stage: "searching", foundInfo: null, text: "", citations: [] });

      const finishPartial = (): AskStreamResult => {
        setStreaming(null);
        return {
          message: newChatMessage("assistant", text || INTERRUPTED_TEXT, {
            citations,
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
          } else if (event === "generation_started" || event === "reasoning_delta") {
            setStreaming((s) => (s && s.stage !== "answering" ? { ...s, stage: "thinking" } : s));
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
