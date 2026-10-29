import { useCallback, useRef, useState } from "react";
import { aiApi } from "@/api/ai";
import { newChatMessage } from "@/lib/chatMessages";
import type { SSEEvent } from "@/lib/sse";
import type { CandidateRow, CandidateState, ChatCitation } from "@/types/ai";
import type { ChatMessage, EndedRunState } from "@/types/chat";

/** What the server says an answer is doing (IR-595): the whole public vocabulary. */
export type StreamActivity = "waiting" | "thinking" | "preparing";

const ACTIVITY_LABELS: Record<StreamActivity, string> = {
  waiting:   "Waiting…",
  thinking:  "Thinking…",
  preparing: "Preparing your answer…",
};

const isActivity = (value: unknown): value is StreamActivity =>
  typeof value === "string" && Object.prototype.hasOwnProperty.call(ACTIVITY_LABELS, value);

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

interface AskStreamOptions {
  requestId?: string;
  comparisonRecordIds?: number[];
  conversationId?: number;
  topK?:           number;
  widen?:          boolean;
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
      let citations: ChatCitation[] = [];
      let sawAnyEvent = false;
      let runId: string | null = knownRunId;
      let cursor = 0;
      // Replayed records apply once. The server puts `id:` only on a batch's last frame,
      // so an id-less activity frame is deduped by state instead.
      const applied = new Set<string>();

      setStreaming({
        activity: "waiting", label: ACTIVITY_LABELS.waiting,
        ...(knownRunId ? { runId: knownRunId } : { startedAt: Date.now() }),
        text: "", citations: [],
      });

      const ended = (state: EndedRunState, content: string, partial: boolean): AskStreamResult => {
        setStreaming(null);
        return {
          message: newChatMessage("assistant", content, {
            ...(partial ? { partial: true } : {}),
            ...(runId ? { endedRun: { id: runId, state } } : {}),
            question, widened: options.widen,
          }),
          conversationId: options.conversationId ?? null,
        };
      };

      const finishPartial = (): AskStreamResult => {
        setStreaming(null);
        return {
          message: newChatMessage("assistant", text || INTERRUPTED_TEXT, {
            citations,
            partial: true,
            question,
            widened: options.widen,
          }),
          conversationId: options.conversationId ?? null,
        };
      };

      /** One event; the result when it ends the answer, otherwise `null`. */
      const handle = ({ event, data }: SSEEvent): AskStreamResult | null => {
        const payload = (data ?? {}) as Record<string, unknown>;

        if (event === "activity") {
          const state = payload.state;
          if (isActivity(state)) {
            const label = typeof payload.label === "string" && payload.label ? payload.label : ACTIVITY_LABELS[state];
            // Unchanged state returns the same object, so a repeat re-renders nothing.
            setStreaming((s) => (s && (s.activity !== state || s.label !== label) ? { ...s, activity: state, label } : s));
          }
        } else if (event === "run_queued") {
          runId = payload.run_id as string;
          followed.current = runId;
          const queuedRun = runId;
          setStreaming((s) => (s ? { ...s, runId: queuedRun } : s));
        } else if (event === "run_started") {
          // A new attempt answers from the beginning; drop what an earlier,
          // lost attempt had written so far.
          text = "";
          citations = [];
          setStreaming((s) => (s ? { ...s, candidates: undefined, text: "", citations: [] } : s));
        } else if (event === "run_failed") {
          const state: EndedRunState = payload.state === "expired" ? "expired" : "failed";
          return ended(state, ENDED_RUN_TEXT[state], true);
        } else if (event === "run_cancelled") {
          // The reader's own choice, not an interrupted answer.
          return ended("cancelled", ENDED_RUN_TEXT.cancelled, false);
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
        } else if (event === "text_delta") {
          text += payload.text as string;
          const snapshot = text;
          setStreaming((s) => (s ? { ...s, text: snapshot } : s));
        } else if (event === "citations_resolved") {
          citations = payload.citations as ChatCitation[];
          setStreaming((s) => (s ? { ...s, citations } : s));
        } else if (event === "done") {
          const body = (payload.answer ?? payload.message ?? "No readable sources matched that question.") as string;
          const summary = typeof payload.reasoning_summary === "string" ? payload.reasoning_summary.trim() : "";
          const message = newChatMessage("assistant", body, {
            citations: payload.citations as ChatCitation[],
            turnId: payload.turn_id as number | undefined,
            listing: payload.listing as ChatMessage["listing"],
            comparison: payload.comparison as ChatMessage["comparison"],
            question,
            sources:   payload.sources as ChatMessage["sources"],
            degraded:  payload.degraded as boolean,
            widened:   payload.widened as boolean,
            resolvedQuestion: payload.resolved_question as string | null,
            ...(summary ? { reasoningSummary: summary } : {}),
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
              if (record.id !== undefined) {
                const id = Number(record.id);
                const key = `${id}:${record.event}`;
                if (id < cursor || applied.has(key)) continue;
                applied.add(key);
                cursor = id;
              }
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
