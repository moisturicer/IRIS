import { useCallback, useRef, useState } from "react";
import { aiApi } from "@/api/ai";
import type { SSEEvent } from "@/lib/sse";
import {
  streamAnswer,
  type AskStreamOptions,
  type AskStreamResult,
  type StreamingState,
} from "../conversation/answerStream";

export {
  ENDED_RUN_TEXT,
  StreamDetached,
  type AskStreamResult,
  type StreamActivity,
  type StreamingState,
} from "../conversation/answerStream";


/**
 * One answer at a time, for a surface with one Conversation on screen: Paper
 * Chat. The event handling itself is `streamAnswer`, shared with Ask IRIS's
 * Conversation client (IR-562); IR-571 moves Paper Chat onto that client too.
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
      try {
        return await streamAnswer(question, options, open, {
          signal: abort.signal,
          onState: setStreaming,
          onRunId: (runId) => { followed.current = runId; },
          knownRunId,
        });
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
