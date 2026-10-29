/**
 * The one Conversation client on Ask IRIS (IR-562).
 *
 * It owns what each Conversation the reader has opened is showing: its
 * transcript, its unsent draft, the answer whose sources are selected, and
 * the answer it is still waiting for. Each of those is kept per Conversation,
 * so switching never moves an answer, a draft or a source list from one to
 * another.
 *
 * An answer is bound to the Conversation that asked it and to a request
 * identity minted when it was sent. Its events and its result are applied only
 * while that request is still the Conversation's current one, so a late answer
 * lands in the Conversation that asked even after the reader has moved on, and
 * a superseded one lands nowhere. Moving away does not stop following: an
 * answer cut off by a disconnect would be stored as a fragment, and the reader
 * only went to look at something else. Stop is the reader's explicit
 * cancellation through IR-548's run route.
 *
 * Loading is bound the same way. `open` reads a Conversation through its
 * owned route (IR-548) and drops the result when the reader has asked for
 * another one since, or when an answer landed in that Conversation while it
 * was loading: the copy was taken before that answer existed, and the
 * transcript already held here is newer.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { aiApi } from "@/api/ai";
import { newChatMessage, turnToMessages } from "@/lib/chatMessages";
import type { SSEEvent } from "@/lib/sse";
import type { ConversationDetail } from "@/types/ai";
import type { ChatMessage } from "@/types/chat";

function isNotFound(err: unknown): boolean {
  return (err as { response?: { status?: number } })?.response?.status === 404;
}
import { ENDED_RUN_TEXT, StreamDetached, streamAnswer, type StreamingState } from "./answerStream";

/** What one Conversation is showing, kept while the reader is elsewhere. */
interface Thread {
  messages:   ChatMessage[];
  draft:      string;
  /** The answer whose sources are shown; `null` follows the latest answer. */
  selectedId: string | null;
}

/** The answer a Conversation is waiting for, under the request that asked it. */
interface Answering {
  requestId: string;
  /** The queued run behind it, once known (IR-544): what Stop cancels. */
  runId:     string | null;
  streaming: StreamingState | null;
}

const EMPTY_THREAD: Thread = { messages: [], draft: "", selectedId: null };

export interface ConversationClientEvents {
  /** An answer arrived for `conversationId`; `onScreen` when the reader is looking at it. */
  onAnswered?: (conversationId: number, message: ChatMessage, onScreen: boolean) => void;
  /** Nothing streamed at all: the question could not be answered. */
  onFailed?:   (conversationId: number) => void;
}

/**
 * The transcript a reader opening `conversation` sees: its Turns, then its
 * latest run when no Turn shows for it yet -- the question, and for a run
 * that ended unanswered, why (IR-548).
 */
export function transcriptOf(conversation: ConversationDetail): ChatMessage[] {
  const messages = conversation.turns.flatMap(turnToMessages);
  const run = conversation.latest_run;
  if (!run) return messages;
  messages.push(newChatMessage("user", run.question));
  if (run.state === "cancelled" || run.state === "failed" || run.state === "expired") {
    messages.push(newChatMessage("assistant", ENDED_RUN_TEXT[run.state], {
      endedRun: { id: run.id, state: run.state },
      question: run.question,
      ...(run.state === "cancelled" ? {} : { partial: true }),
    }));
  }
  return messages;
}

/** The answer the reader selected, or the latest one when they selected none. */
function selectedAnswer({ messages, selectedId }: Thread): ChatMessage | null {
  if (selectedId !== null) {
    const chosen = messages.find((m) => m.id === selectedId && m.role === "assistant");
    if (chosen) return chosen;
  }
  for (let i = messages.length - 1; i >= 0; i--) {
    if (messages[i].role === "assistant") return messages[i];
  }
  return null;
}

export function useConversationClient(events: ConversationClientEvents = {}) {
  const [activeId, setActiveId] = useState<number | null>(null);
  const [unavailable, setUnavailable] = useState(false);
  const [threads, setThreads] = useState<Record<number, Thread>>({});
  const [answering, setAnswering] = useState<Record<number, Answering>>({});

  // Read after an await, where state from the render that started it is stale.
  const activeRef = useRef<number | null>(null);
  const flights = useRef(new Map<number, { requestId: string; controller: AbortController }>());
  // How many answers have landed in each Conversation: what a load started
  // before one of them cannot know about.
  const landed = useRef(new Map<number, number>());
  // The latest load; an earlier one that resolves after it is dropped.
  const opening = useRef(0);
  const mounted = useRef(true);
  const eventsRef = useRef(events);
  useEffect(() => {
    eventsRef.current = events;
  });

  const updateThread = useCallback((id: number, update: (thread: Thread) => Thread) => {
    setThreads((all) => ({ ...all, [id]: update(all[id] ?? EMPTY_THREAD) }));
  }, []);

  /** Follows one answer for `conversationId`, opened by `open`, to its end. */
  const answer = useCallback(
    async (
      conversationId: number,
      question: string,
      open: (signal: AbortSignal) => AsyncGenerator<SSEEvent>,
      knownRunId: string | null = null,
    ) => {
      // One answer per Conversation: a new request supersedes the last one.
      flights.current.get(conversationId)?.controller.abort();
      const requestId = crypto.randomUUID();
      const controller = new AbortController();
      flights.current.set(conversationId, { requestId, controller });
      const current = () => flights.current.get(conversationId)?.requestId === requestId;
      const patch = (update: (live: Answering) => Answering) =>
        setAnswering((all) =>
          all[conversationId]?.requestId === requestId
            ? { ...all, [conversationId]: update(all[conversationId]) }
            : all);

      setAnswering((all) => ({ ...all, [conversationId]: { requestId, runId: knownRunId, streaming: null } }));
      try {
        const { message } = await streamAnswer(question, { conversationId }, open, {
          signal: controller.signal,
          knownRunId,
          onState: (next) =>
            patch((live) => ({ ...live, streaming: typeof next === "function" ? next(live.streaming) : next })),
          onRunId: (runId) => patch((live) => ({ ...live, runId })),
        });
        if (!current() || !mounted.current) return;
        landed.current.set(conversationId, (landed.current.get(conversationId) ?? 0) + 1);
        updateThread(conversationId, (thread) => ({
          ...thread,
          // A new answer is the one whose sources show, cited or not.
          selectedId: null,
          // A replayed run whose Turn is already in the transcript adds nothing.
          messages:
            message.turnId !== undefined && thread.messages.some((m) => m.turnId === message.turnId)
              ? thread.messages
              : [...thread.messages, message],
        }));
        eventsRef.current.onAnswered?.(conversationId, message, activeRef.current === conversationId);
      } catch (err) {
        if (!(err instanceof StreamDetached) && current()) eventsRef.current.onFailed?.(conversationId);
      } finally {
        if (current() && mounted.current) {
          flights.current.delete(conversationId);
          setAnswering((all) => {
            if (all[conversationId]?.requestId !== requestId) return all;
            const rest = { ...all };
            delete rest[conversationId];
            return rest;
          });
        }
      }
    },
    [updateThread],
  );

  /**
   * Puts `conversation`, as its owned route returned it, on screen. One still
   * answering here keeps the transcript it has, which already holds the
   * question being answered, and so does one whose answer landed after
   * `landedAtLoad` was read; a run the server is still answering, and this
   * client is not yet following, is followed from its first event.
   */
  const show = useCallback(
    (conversation: ConversationDetail, landedAtLoad?: number) => {
      const id = conversation.id;
      opening.current += 1;
      activeRef.current = id;
      setActiveId(id);
      setUnavailable(false);
      if (flights.current.has(id)) return;
      if (landedAtLoad !== undefined && (landed.current.get(id) ?? 0) !== landedAtLoad) return;
      const messages = transcriptOf(conversation);
      updateThread(id, (thread) => {
        // A live answer's id is not its Turn's, so a selection is carried by Turn.
        const chosen = thread.messages.find((m) => m.id === thread.selectedId);
        const kept = chosen?.turnId !== undefined
          ? messages.find((m) => m.role === "assistant" && m.turnId === chosen.turnId)
          : messages.find((m) => m.id === thread.selectedId);
        return { ...thread, messages, selectedId: kept?.id ?? null };
      });
      const run = conversation.latest_run;
      if (run && (run.state === "queued" || run.state === "running")) {
        void answer(id, run.question, (signal) => aiApi.resumeAskRun(run.id, 0, signal), run.id);
      }
    },
    [answer, updateThread],
  );

  /** Whether Conversation `id` is the one on screen, as of now rather than the last render. */
  const isOnScreen = useCallback((id: number) => activeRef.current === id, []);

  /** Missing, deleted, malformed or someone else's: one state for all. */
  const showUnavailable = useCallback(() => {
    opening.current += 1;
    activeRef.current = null;
    setActiveId(null);
    setUnavailable(true);
  }, []);

  /**
   * Loads Conversation `id` through its owned route and shows it; one that is
   * missing or someone else's shows as unavailable. Rejects on any other
   * failure, for the page to say so.
   */
  const open = useCallback(
    async (id: number) => {
      const request = ++opening.current;
      const landedAtLoad = landed.current.get(id) ?? 0;
      try {
        const { data } = await aiApi.conversations.get(id);
        if (opening.current === request) show(data, landedAtLoad);
      } catch (err) {
        if (opening.current !== request) return;
        if (!isNotFound(err)) throw err;
        showUnavailable();
      }
    },
    [show, showUnavailable],
  );

  /** Asks `question` in the Conversation on screen, unless it is still answering. */
  const send = useCallback(
    (question: string) => {
      const id = activeRef.current;
      if (id === null || flights.current.has(id)) return;
      updateThread(id, (thread) => ({
        ...thread,
        draft: "",
        messages: [...thread.messages, newChatMessage("user", question)],
      }));
      return answer(id, question, (signal) => aiApi.askStream(question, { conversationId: id }, signal));
    },
    [answer, updateThread],
  );

  /**
   * Retries the queued question `message` stands for as a new run (IR-548).
   * Throws when the server refuses it, for the page to say so.
   */
  const retry = useCallback(
    async (message: ChatMessage) => {
      const run = message.endedRun;
      const id = activeRef.current;
      if (!run || id === null || flights.current.has(id)) return;
      const { data } = await aiApi.retryRun(run.id);
      // The notice stays; only its Retry goes, since a second one would
      // return this same retry anyway.
      updateThread(id, (thread) => ({
        ...thread,
        messages: thread.messages.map((m) => (m.id === message.id ? { ...m, endedRun: undefined } : m)),
      }));
      void answer(id, message.question ?? "", (signal) => aiApi.resumeAskRun(data.run_id, 0, signal), data.run_id);
    },
    [answer, updateThread],
  );

  /** Asks the server to stop the run the Conversation on screen is waiting for. */
  const stop = useCallback(async () => {
    const id = activeRef.current;
    const runId = id === null ? null : answering[id]?.runId;
    if (!runId) return;
    try {
      await aiApi.cancelRun(runId);
    } catch {
      // Already over: its own terminal event is on its way.
    }
  }, [answering]);

  /** The unsent draft of Conversation `id`; nothing is sent until Send. */
  const setDraftFor = useCallback(
    (id: number, draft: string) => updateThread(id, (thread) => ({ ...thread, draft })),
    [updateThread],
  );

  const setDraft = useCallback((draft: string) => {
    if (activeRef.current !== null) setDraftFor(activeRef.current, draft);
  }, [setDraftFor]);

  /** Shows the sources of answer `messageId` in the Conversation on screen. */
  const select = useCallback((messageId: string) => {
    if (activeRef.current !== null) {
      updateThread(activeRef.current, (thread) => ({ ...thread, selectedId: messageId }));
    }
  }, [updateThread]);

  /** A deleted Conversation: stop following its answer and drop what it showed. */
  const forget = useCallback((id: number) => {
    const flight = flights.current.get(id);
    flights.current.delete(id);
    flight?.controller.abort();
    setAnswering((all) => {
      if (!(id in all)) return all;
      const rest = { ...all };
      delete rest[id];
      return rest;
    });
    setThreads((all) => {
      if (!(id in all)) return all;
      const rest = { ...all };
      delete rest[id];
      return rest;
    });
  }, []);

  // Stop following every answer when the page goes away; the runs carry on.
  useEffect(() => {
    mounted.current = true;
    const following = flights.current;
    return () => {
      mounted.current = false;
      following.forEach((flight) => flight.controller.abort());
      following.clear();
    };
  }, []);

  const thread = (activeId !== null && threads[activeId]) || EMPTY_THREAD;
  const live = activeId !== null ? answering[activeId] : undefined;
  const selected = useMemo(() => selectedAnswer(thread), [thread]);

  return {
    activeId,
    unavailable,
    messages:    thread.messages,
    draft:       thread.draft,
    /** The answer the sources panel describes. */
    selected,
    isAnswering: live !== undefined,
    streaming:   live?.streaming ?? null,
    isOnScreen,
    open,
    show,
    showUnavailable,
    send,
    retry,
    stop,
    setDraft,
    setDraftFor,
    select,
    forget,
  };
}
