import { useCallback, useRef, useState } from "react";
import { aiApi } from "@/api/ai";
import { newChatMessage } from "@/lib/chatMessages";
import type { SSEEvent } from "@/lib/sse";
import type {
  AgentStepEvent, CandidateRow, CandidateState, ChatCitation, ChatLane, RoutingDecision,
} from "@/types/ai";
import type { ChatMessage, EndedRunState } from "@/types/chat";

/**
 * The reader-visible phase of an in-flight answer (IR-329). Deliberately
 * fewer than the event vocabulary -- copy must read as one pipeline step,
 * never parallel agents (ADR-028). `queued` is a queued run waiting for a
 * worker (IR-544).
 */
export type StreamStage = "queued" | "searching" | "found" | "thinking" | "answering";

export interface StreamingState {
  /** The queued run being followed, once known (IR-544) -- what Stop cancels. */
  runId?:   string;
  routing?: RoutingDecision;
  /** The research planner's steps so far, one per position (IR-504). */
  steps?:   AgentStepEvent[];
  /** A listing's candidates, in rank order, one row per paper (IR-546). */
  candidates?: CandidateRow[];
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
  comparisonRecordIds?: number[];
  conversationId?: number;
  topK?:           number;
  widen?:          boolean;
  routeOverride?:  ChatLane;
  routeOverrideTurnId?: number;
}

export interface AskStreamResult {
  message:        ChatMessage;
  conversationId: number | null;
}

const INTERRUPTED_TEXT = "The answer was interrupted before it finished.";
/** What a queued run that ended without its answer says, live or reopened. */
export const ENDED_RUN_TEXT: Record<EndedRunState, string> = {
  expired:   "IRIS ran out of time before it could answer. Please ask again.",
  failed:    "IRIS could not finish this answer. Please ask again.",
  cancelled: "You stopped this question before IRIS answered it.",
};

/**
 * Raised by `ask`/`follow` when `detach` stopped following -- the reader
 * moved to another conversation. The run itself carries on server-side.
 */
export class StreamDetached extends Error {
  constructor() {
    super("Stopped following the answer.");
    this.name = "StreamDetached";
  }
}

/** Reconnections to a queued run in a row that bring no event (IR-544). */
const RECONNECT_LIMIT = 3;
const RECONNECT_BACKOFF_MS = 500;

const wait = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms));

/**
 * Drives one `/ai/ask/stream/` call. Resolves once it's over -- via `done`,
 * or a connection drop after at least one event (IR-328's partial case).
 * Rejects only when nothing ever streamed, matching `aiApi.ask`'s failure shape.
 *
 * When the server queues the question (IR-544) the first event is
 * `run_queued`, and a dropped connection reconnects from the last event `id`
 * instead of ending the answer. When it does not, nothing here differs.
 *
 * `follow` attaches to a run already submitted -- a reopened or refreshed
 * Conversation, or a retry -- replaying it from its first event (IR-548).
 * `cancel` asks the server to stop the run being followed; its terminal
 * `run_cancelled` ends the answer. `detach` only stops listening: the
 * pending call rejects with `StreamDetached` and the run carries on.
 */
export function useAskStream() {
  const [streaming, setStreaming] = useState<StreamingState | null>(null);
  const controller = useRef<AbortController | null>(null);
  const followed = useRef<string | null>(null);

  const drive = useCallback(
    async (
      question: string,
      options: AskStreamOptions,
      open: (signal: AbortSignal) => AsyncGenerator<SSEEvent>,
      knownRunId: string | null = null,
    ): Promise<AskStreamResult> => {
      // One answer is followed at a time; starting another stops the last.
      controller.current?.abort();
      const abort = new AbortController();
      controller.current = abort;
      followed.current = knownRunId;

      let text = "";
      let reasoning = "";
      let citations: ChatCitation[] = [];
      let routing: RoutingDecision | undefined;
      let sawAnyEvent = false;
      let runId: string | null = knownRunId;
      let cursor = 0;

      setStreaming({
        stage: knownRunId ? "queued" : "searching", ...(knownRunId ? { runId: knownRunId } : {}),
        foundInfo: null, text: "", reasoning: "", citations: [],
      });

      const ended = (state: EndedRunState, content: string, partial: boolean): AskStreamResult => {
        setStreaming(null);
        return {
          message: newChatMessage("assistant", content, {
            ...(partial ? { partial: true } : {}),
            ...(runId ? { endedRun: { id: runId, state } } : {}),
            routing, question, widened: options.widen,
          }),
          conversationId: options.conversationId ?? null,
        };
      };

      const finishPartial = (): AskStreamResult => {
        setStreaming(null);
        return {
          message: newChatMessage("assistant", text || INTERRUPTED_TEXT, {
            citations,
            // Whatever working arrived before the cutoff is still worth
            // showing -- the server stored the same text on the Turn.
            reasoning: reasoning || null,
            partial: true,
            routing,
            question,
            widened: options.widen,
          }),
          conversationId: options.conversationId ?? null,
        };
      };

      /** One event; the result when it ends the answer, otherwise `null`. */
      const handle = ({ event, data }: SSEEvent): AskStreamResult | null => {
        const payload = (data ?? {}) as Record<string, unknown>;

        if (event === "run_queued") {
          runId = payload.run_id as string;
          followed.current = runId;
          const queuedRun = runId;
          setStreaming((s) => (s ? { ...s, stage: "queued", runId: queuedRun } : s));
        } else if (event === "run_started") {
          // A new attempt answers from the beginning; drop what an earlier,
          // lost attempt had written so far.
          text = "";
          reasoning = "";
          citations = [];
          setStreaming((s) =>
            s
              ? {
                  ...s, stage: "searching", steps: undefined, candidates: undefined,
                  foundInfo: null, text: "", reasoning: "", citations: [],
                }
              : s,
          );
        } else if (event === "run_failed") {
          const state: EndedRunState = payload.state === "expired" ? "expired" : "failed";
          return ended(state, ENDED_RUN_TEXT[state], true);
        } else if (event === "run_cancelled") {
          // The reader's own choice, not an interrupted answer.
          return ended("cancelled", ENDED_RUN_TEXT.cancelled, false);
        } else if (event === "routing_decided") {
          routing = payload.routing as RoutingDecision;
          setStreaming((s) => (s ? { ...s, routing } : s));
        } else if (event === "agent_step") {
          const step = payload as unknown as AgentStepEvent;
          setStreaming((s) =>
            s
              ? {
                  ...s,
                  // A step arrives `running`, then again with its outcome.
                  steps: [...(s.steps ?? []).filter((known) => known.position !== step.position), step]
                    .sort((a, b) => a.position - b.position),
                }
              : s,
          );
        } else if (event === "candidates_selected") {
          // The preview: shown as pending, and a replayed one replaces it.
          const rows = (payload.candidates as CandidateRow[]) ?? [];
          setStreaming((s) => (s ? { ...s, candidates: rows } : s));
        } else if (event === "candidates_updated") {
          // By stable record id, so a repeat or a replay never adds a card.
          const next = new Map(
            ((payload.candidates as { record_id: number; state: CandidateState }[]) ?? [])
              .map((row) => [row.record_id, row.state]),
          );
          setStreaming((s) =>
            s?.candidates
              ? { ...s, candidates: s.candidates.map((row) => (next.has(row.record_id) ? { ...row, state: next.get(row.record_id)! } : row)) }
              : s,
          );
        } else if (event === "retrieval_started") {
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
            turnId: payload.turn_id as number | undefined,
            routing: (payload.routing as RoutingDecision | undefined) ?? routing,
            listing: payload.listing as ChatMessage["listing"],
            comparison: payload.comparison as ChatMessage["comparison"],
            research: payload.research as ChatMessage["research"],
            question,
            sources:   payload.sources as ChatMessage["sources"],
            degraded:  payload.degraded as boolean,
            widened:   payload.widened as boolean,
            resolvedQuestion: payload.resolved_question as string | null,
            // The server's joined text, not the deltas this hook
            // accumulated: one source, so a reopened Turn and a watched
            // one render the same panel (IR-381). A queued run sends none.
            reasoning: (payload.reasoning as string | null) ?? (reasoning || null),
            // A queued run cut off at its deadline keeps its fragment.
            ...(payload.partial === true ? { partial: true } : {}),
          });
          setStreaming(null);
          return {
            message,
            conversationId: (payload.conversation_id as number | null) ?? null,
          };
        }
        // Any other event name is one this client does not know yet.
        return null;
      };

      // Whoever detached has already cleared the screen; touch nothing.
      const detached = () => abort.signal.aborted;

      try {
        let source = open(abort.signal);
        let quietReconnects = 0;
        for (;;) {
          let sawEventHere = false;
          try {
            for await (const record of source) {
              if (detached()) throw new StreamDetached();
              sawAnyEvent = true;
              sawEventHere = true;
              if (record.id !== undefined) cursor = Number(record.id);
              const result = handle(record);
              if (result) return result;
            }
          } catch (err) {
            if (detached()) throw new StreamDetached();
            if (!sawAnyEvent) {
              setStreaming(null);
              throw err;
            }
          }
          if (detached()) throw new StreamDetached();

          // The connection ended with no final event. A request-bound answer
          // is over (the server stored it as `partial`); a queued one is not.
          if (sawEventHere) quietReconnects = 0;
          if (runId === null || quietReconnects >= RECONNECT_LIMIT) return finishPartial();
          await wait(RECONNECT_BACKOFF_MS * quietReconnects);
          if (detached()) throw new StreamDetached();
          quietReconnects += 1;
          source = aiApi.resumeAskRun(runId, cursor, abort.signal);
        }
      } finally {
        if (controller.current === abort) {
          controller.current = null;
          followed.current = null;
        }
      }
    },
    [],
  );

  const ask = useCallback(
    (question: string, options: AskStreamOptions = {}) =>
      drive(question, options, (signal) => aiApi.askStream(question, options, signal)),
    [drive],
  );

  /** Follow run `runId`, already submitted, from its first event (IR-548). */
  const follow = useCallback(
    (runId: string, question: string, options: AskStreamOptions = {}) =>
      drive(question, options, (signal) => aiApi.resumeAskRun(runId, 0, signal), runId),
    [drive],
  );

  /** Stop listening; the run carries on and its Turn is stored as usual. */
  const detach = useCallback(() => {
    const current = controller.current;
    controller.current = null;
    followed.current = null;
    if (current) {
      current.abort();
      setStreaming(null);
    }
  }, []);

  /** Ask the server to stop the run being followed. Its `run_cancelled`
   *  -- or, if it finished first, its `done` -- ends the answer. */
  const cancel = useCallback(async () => {
    const runId = followed.current;
    if (!runId) return;
    try {
      await aiApi.cancelRun(runId);
    } catch {
      // Already over: its own terminal event is on its way.
    }
  }, []);

  return { streaming, ask, follow, cancel, detach };
}
