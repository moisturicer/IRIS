/**
 * The one Conversation client: Ask IRIS and Paper Chat (IR-562, IR-571).
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
import { readFailureKind } from "@/lib/readFailure";
import type { SSEEvent } from "@/lib/sse";
import type { ConversationDetail } from "@/types/ai";
import type { ComparisonRecord } from "@/types/records";
import type { ChatMessage } from "@/types/chat";

/** Missing and refused read alike (IR-153, IR-906): the API never says which. */
function isUnavailable(err: unknown): boolean {
  return readFailureKind(err) === "unavailable";
}
import { ENDED_RUN_TEXT, StreamDetached, streamAnswer, type StreamingState } from "./answerStream";

/** What one Conversation is showing, kept while the reader is elsewhere. */
interface Thread {
  messages:   ChatMessage[];
  draft:      string;
  /** The answer whose sources are shown; `null` follows the latest answer. */
  selectedId: string | null;
  record: number | null;
  comparisonRecords: ComparisonRecord[];
}

/** The answer a Conversation is waiting for, under the request that asked it. */
interface Answering {
  requestId: string;
  /** The queued run behind it, once known (IR-544): what Stop cancels. */
  runId:     string | null;
  streaming: StreamingState | null;
}

const EMPTY_THREAD: Thread = { messages: [], draft: "", selectedId: null, record: null, comparisonRecords: [] };

/** What one question may carry beyond its text. */
export interface SendOptions {
  /** Paper Chat's "All papers": search past the Conversation's own Record (IR-298). */
  widen?: boolean;
  /**
   * The Conversation to ask in, when it is not the one on screen: Paper Chat
   * started it for a paper the reader has since moved away from.
   */
  conversationId?: number;
}

export interface ConversationClientEvents {
  /** An answer arrived for `conversationId`; `onScreen` when the reader is looking at it. */
  onAnswered?: (conversationId: number, message: ChatMessage, onScreen: boolean) => void;
  /** Nothing streamed at all: the question could not be answered. */
  onFailed?:   (conversationId: number, error: unknown) => void;
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

export function useConversationClient(events: ConversationClientEvents = {}, comparisonLimit?: number) {
  const [activeId, setActiveId] = useState<number | null>(null);
  const [unavailable, setUnavailable] = useState(false);
  /** A Conversation is being fetched and nothing has replaced it yet (IR-906). */
  const [isOpening, setIsOpening] = useState(false);
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
      widen?: boolean,
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
        const { message } = await streamAnswer(question, { conversationId, widen }, open, {
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
        if (!(err instanceof StreamDetached) && current()) eventsRef.current.onFailed?.(conversationId, err);
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
      setIsOpening(false);
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
        return {
          ...thread, messages, selectedId: kept?.id ?? null,
          record: conversation.record,
          comparisonRecords: conversation.record === null ? thread.comparisonRecords : [],
        };
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

  /**
   * Shows no Conversation at all: Paper Chat on a paper that has none yet,
   * whose first question starts one. An answer still arriving for the one
   * left behind stays with it.
   */
  const showEmpty = useCallback(() => {
    opening.current += 1;
    setIsOpening(false);
    activeRef.current = null;
    setActiveId(null);
    setUnavailable(false);
  }, []);

  /** Missing, deleted, malformed or someone else's: one state for all. */
  const showUnavailable = useCallback(() => {
    opening.current += 1;
    setIsOpening(false);
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
      setIsOpening(true);
      const landedAtLoad = landed.current.get(id) ?? 0;
      try {
        const { data } = await aiApi.conversations.get(id);
        if (opening.current === request) show(data, landedAtLoad);
      } catch (err) {
        if (opening.current !== request) return;
        if (!isUnavailable(err)) {
          setIsOpening(false);
          throw err;
        }
        showUnavailable();
      }
    },
    [show, showUnavailable],
  );

  /**
   * Finds a Conversation through `find` and shows it, or shows none when there
   * is none. Dropped the same ways `open` is: the reader asked for another
   * since, or an answer landed in the one found while it was being looked up.
   * A failure rejects, for the caller to say so.
   */
  const openFound = useCallback(
    async (find: () => Promise<ConversationDetail | null>) => {
      const request = ++opening.current;
      setIsOpening(true);
      // The id is unknown until the lookup returns, so every count is kept.
      const landedBefore = new Map(landed.current);
      let found: ConversationDetail | null;
      try {
        found = await find();
      } catch (err) {
        if (opening.current === request) setIsOpening(false);
        throw err;
      }
      if (opening.current !== request) return;
      if (found === null) showEmpty();
      else show(found, landedBefore.get(found.id) ?? 0);
    },
    [show, showEmpty],
  );

  /** Asks `question` in the Conversation on screen, unless it is still answering. */
  const send = useCallback(
    (question: string, { widen, conversationId }: SendOptions = {}) => {
      const id = conversationId ?? activeRef.current;
      if (id === null || flights.current.has(id)) return;
      const thread = threads[id] ?? EMPTY_THREAD;
      const records = thread.comparisonRecords;
      if (records.length && (thread.record !== null || comparisonLimit === undefined ||
        records.length < 2 || records.length > comparisonLimit)) return;
      const comparison = records.length ? { comparisonRecordIds: records.map((r) => r.id) } : {};
      updateThread(id, (thread) => ({
        ...thread,
        draft: "",
        messages: [...thread.messages, newChatMessage("user", question)],
      }));
      const asked = { conversationId: id, requestId: crypto.randomUUID(), widen, ...comparison };
      return answer(id, question, (signal) => aiApi.askStream(question, asked, signal), null, widen);
    },
    [answer, comparisonLimit, threads, updateThread],
  );

  const setComparisonRecords = useCallback((records: ComparisonRecord[]) => {
    const id = activeRef.current;
    if (id === null || flights.current.has(id)) return;
    updateThread(id, (thread) => thread.record !== null ? thread : { ...thread, comparisonRecords: records });
  }, [updateThread]);

  /**
   * Retries the queued question `message` stands for as a new run (IR-548).
   * Throws when the server refuses it, for the page to say so.
   *
   * An answer that was cut off has no run to retry: its question is asked
   * again as a new one (IR-907), with the same scope. The server stored the
   * cut-off Turn, so this is a new question and a new Turn, never a replay.
   */
  const retry = useCallback(
    async (message: ChatMessage) => {
      const run = message.endedRun;
      const id = activeRef.current;
      if (id === null || flights.current.has(id)) return;
      if (!run) {
        if (message.partial && message.question) void send(message.question, { widen: message.widened });
        return;
      }
      const { data } = await aiApi.retryRun(run.id);
      // The notice stays; only its Retry goes, since a second one would
      // return this same retry anyway.
      updateThread(id, (thread) => ({
        ...thread,
        messages: thread.messages.map((m) => (m.id === message.id ? { ...m, endedRun: undefined } : m)),
      }));
      void answer(id, message.question ?? "", (signal) => aiApi.resumeAskRun(data.run_id, 0, signal), data.run_id);
    },
    [answer, send, updateThread],
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

  /**
   * Adds `message` to Conversation `id`'s transcript, wherever the reader is
   * now: a failure notice belongs with the question that failed.
   */
  const note = useCallback(
    (id: number, message: ChatMessage) => updateThread(id, (thread) => ({ ...thread, messages: [...thread.messages, message] })),
    [updateThread],
  );

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
    isOpening,
    messages:    thread.messages,
    draft:       thread.draft,
    record:      thread.record,
    comparisonRecords: thread.comparisonRecords,
    setComparisonRecords,
    /** The answer the sources panel describes. */
    selected,
    isAnswering: live !== undefined,
    streaming:   live?.streaming ?? null,
    isOnScreen,
    open,
    openFound,
    show,
    showEmpty,
    showUnavailable,
    note,
    send,
    retry,
    stop,
    setDraft,
    setDraftFor,
    select,
    forget,
  };
}
