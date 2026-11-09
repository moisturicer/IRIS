import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { isAxiosError } from "axios";
import { activeRun, compactionRun, ProtocolMismatch, RELOAD_TO_RECONNECT, retryable, runtimeReader, type Depth, type ReaderConversation, type ReaderRun } from "@/api/runtimeReader";
import type { ChatMessage } from "@/types/chat";
import { cn } from "@/lib/utils";
import { ChatInput } from "./ChatInput";
import { ANSWER_MARKDOWN, CHAT_COLUMN, CHAT_OPENING, CHAT_STREAM_CARET } from "./answerLayout";
import { CitationText } from "./CitationText";
import { ModelPill, type ModelPillOption } from "./ModelPill";
import { ChatMessageBubble } from "./ChatMessageBubble";
import { AskIrisMark } from "./AskIrisIcons";
import { ReasoningBar } from "./ReasoningBar";
import { TokenUsageMeter } from "./TokenUsageMeter";
import { conversationTotals, toMessages, useCitedRecords } from "../runtime/messages";
import { useDraft } from "../runtime/useDraft";

const DEPTHS: readonly ModelPillOption<Depth>[] = [
  { value: "ordinary", short: "Standard", label: "Standard", description: "A shorter search for a quicker answer", icon: "far fa-lightbulb" },
  { value: "deep", short: "Thorough", label: "Thorough research", description: "Searches and reads more before answering", icon: "fas fa-book-open-reader" },
];

const STATES: Record<ReaderRun["state"], string> = {
  queued: "Queued", running: "Research in progress", completed: "Answer ready", cancelled: "Stopped",
  conflict: "Conversation changed. Reconnect before asking again.", expired: "Research ran out of time",
  failed: "IRIS could not finish this question", deleted: "Conversation removed",
};
const TASKS = { pending: "Pending", in_progress: "In progress", done: "Done", blocked: "Blocked" };

export function ResearchProgress({ run }: { run: ReaderRun }) {
  return <section aria-label="Research progress" className="min-w-0 border-l-2 border-brand/30 pl-4 py-1 text-sm text-stone-600">
    <p role="status" aria-live="polite" className="font-medium text-stone-900">{STATES[run.state]}</p>
    {run.awaiting_reader && <p>Reconnect to continue research.</p>}
    {run.sources_available === false && <p>Some sources changed or are no longer readable.</p>}
    {run.plan && run.plan.steps.length > 0 && <>
      <ol aria-label="Research tasks" className="mt-3 space-y-2">
        {run.plan.steps.map(step => <li key={step.id} className="flex flex-wrap items-baseline gap-x-3 gap-y-1 break-words">
          <span className="min-w-0 flex-1 [overflow-wrap:anywhere]">{step.title}</span>
          <span className="text-xs text-stone-500">{TASKS[step.status]}</span>
        </li>)}
      </ol>
      <p className="mt-2 text-xs">Task status is the assistant’s assessment of its work.</p>
    </>}
    {run.compaction && run.compaction.compactions > 0 && <p className="mt-1 text-xs">
      Earlier conversation was condensed into a summary to make room. The original answers are kept, and a
      summary is never used as a source for exact details.</p>}
  </section>;
}

/** Text compared without spacing or citation markers, which the checks renumber. */
const squash = (text: string) => text.replace(/\[\d+\]/g, "").replace(/\s+/g, " ").trim();

const COMPACTION_HELP = "Condenses older answers into a summary to make room. Original answers are kept.";

/** A compaction's status: the same words live, reconnected and reopened, and never an internal (IR-754). */
export function CompactionStatus({ run }: { run: ReaderRun }) {
  const done = run.state === "completed";
  const message = activeRun(run) ? "Compacting conversation"
    : done && run.compaction?.last === "kept" ? "Nothing older to condense yet"
    : done ? "Conversation compacted"
    : run.state === "cancelled" ? "Compaction stopped"
    : run.state === "conflict" ? "Conversation changed"
    : run.state === "deleted" ? "Conversation removed"
    : "Compaction unavailable";
  return <section aria-label="Conversation compaction" className="min-w-0 border-l-2 border-brand/30 pl-4 py-1 text-sm text-stone-600">
    <p role="status" aria-live="polite" className="font-medium text-stone-900">{message}</p>
    {activeRun(run) && run.awaiting_reader && <p>Reconnect to continue.</p>}
    {activeRun(run) && <p>The conversation stays as it is until this finishes. You can stop it.</p>}
    {done && run.compaction?.last === "compacted" && <p>
      Earlier answers were condensed into a summary to make room. Original answers are kept, and asking for an
      exact detail checks them, since a summary is never a source.</p>}
    {done && run.compaction?.last === "kept" && <p>Your conversation is unchanged.</p>}
    {(run.state === "failed" || run.state === "expired" || run.state === "cancelled") && <p>Your conversation is unchanged.</p>}
    {run.state === "conflict" && <p>Reconnect, then compact again.</p>}
  </section>;
}

/** What went wrong, in the reader's terms, and whether reconnecting can help (IR-863). */
interface Trouble { message: string; retry: boolean; missing?: boolean }

function trouble(failure: unknown): Trouble {
  if (failure instanceof ProtocolMismatch) return { message: failure.message, retry: false };
  const response = isAxiosError(failure) ? failure.response : undefined;
  const code = (response?.data as { status?: unknown } | undefined)?.status;
  if (response?.status === 429 || (response?.status === 503 && code === "busy")) {
    return { message: "IRIS is busy right now. Reconnect in a moment to try again.", retry: true };
  }
  if (response?.status === 401) return { message: "Your session has ended. Sign in again to continue.", retry: false };
  if (response?.status === 403) {
    return { message: "Ask IRIS can't open research for you right now.", retry: false };
  }
  if (response?.status === 404) {
    return { message: "This conversation is not available. It may have been deleted, or the link may be wrong.",
      retry: false, missing: true };
  }
  if (response?.status === 406) return { message: RELOAD_TO_RECONNECT, retry: false };
  if (response && response.status >= 500) {
    return { message: "Ask IRIS is unavailable right now. Reconnect to try again later.", retry: true };
  }
  return { message: "IRIS could not connect. Reconnect to try again.", retry: true };
}

interface Props {
  recordId?: number;
  conversationId?: string;
  /** A question handed over from elsewhere (IR-559): shown as a draft, never sent. */
  initialDraft?: string;
  /** The unsent draft as it changes, so a page can keep it across a close (IR-569). */
  onDraftChange?: (draft: string) => void;
  onConversation?: (id: string) => void;
  /** The narrow Paper Chat density. */
  dense?: boolean;
  /** The answer whose sources a page's panel shows, and how to pick one. */
  selectedId?: string | null;
  onSelectSources?: (message: ChatMessage) => void;
  /** The newest answer, each time one lands: a page shows its sources. */
  onAnswered?: (message: ChatMessage) => void;
  /** Paper Chat's this-paper / all-papers switch, shown beside the depth. */
  scopeToggle?: { allPapers: boolean; onChange: (allPapers: boolean) => void };
}

/** Both reader surfaces use the same persisted snapshot and transport (IR-730). */
export function RuntimeReader({ recordId, conversationId, initialDraft, onDraftChange, onConversation, dense = false,
  selectedId = null, onSelectSources, onAnswered, scopeToggle }: Props) {
  const api = useMemo(() => runtimeReader(recordId), [recordId]);
  const [conversation, setConversation] = useState<ReaderConversation>();
  const [run, setRun] = useState<ReaderRun>();
  const [depth, setDepth] = useState<Depth>("ordinary");
  const [draft, setDraft] = useState(initialDraft ?? "");
  const reportDraft = useRef(onDraftChange);
  reportDraft.current = onDraftChange;
  useEffect(() => { reportDraft.current?.(draft); }, [draft]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<Trouble>();
  const generation = useRef(0);
  const pending = useRef<{ question: string; depth: Depth; key: string; conversation?: ReaderConversation }>();
  const pendingCompact = useRef<{ key: string; conversation: ReaderConversation }>();
  const pendingRetry = useRef<{ key: string; run: ReaderRun }>();
  const sending = useRef(false);

  const fail = useCallback((failure: unknown) => setError(trouble(failure)), []);
  const reopen = useCallback(async (id: string, version = generation.current) => {
    const next = await api.reopen(id);
    if (version !== generation.current) return;
    setConversation(next);
    setRun(next.runs[next.runs.length - 1]);
    setError(undefined);
    return next;
  }, [api]);

  useEffect(() => {
    const version = ++generation.current;
    setConversation(undefined); setRun(undefined); setError(undefined);
    pending.current = undefined; pendingCompact.current = undefined; pendingRetry.current = undefined;
    if (conversationId) {
      setBusy(true);
      void reopen(conversationId, version).catch((failure) => {
        if (version === generation.current) fail(failure);
      }).finally(() => { if (version === generation.current) setBusy(false); });
    }
    const epoch = generation;
    return () => { ++epoch.current; };
    // A scope/address change detaches; it never asks the worker to cancel.
  }, [api, conversationId, fail, reopen]);

  useEffect(() => {
    if (!run || !activeRun(run) || error) return;
    const version = generation.current;
    const timer = setTimeout(() => {
      void api.status(run.id).then(async next => {
        if (version !== generation.current) return;
        setRun(next);
        if (!activeRun(next)) await reopen(next.conversation_id, version);
      }).catch((failure) => { if (version === generation.current) fail(failure); });
    }, 1000);
    return () => clearTimeout(timer);
  }, [api, run, error, fail, reopen]);

  const send = async (question: string, retry = false) => {
    if (sending.current) return;
    const request = retry ? pending.current : { question, depth, key: crypto.randomUUID(), conversation };
    if (!request) return;
    pending.current = request;
    sending.current = true;
    setBusy(true); setError(undefined);
    const version = generation.current;
    try {
      const next = await api.submit(request.question, request.depth, request.key, request.conversation);
      if (version !== generation.current) return;
      pending.current = undefined;
      setRun(next);
      await reopen(next.conversation_id, version);
      if (version !== generation.current) return;
      onConversation?.(next.conversation_id);
    } catch (failure) {
      if (version !== generation.current) return;
      if (isAxiosError(failure) && failure.response?.status === 409) {
        pending.current = undefined;
        setDraft(request.question);
        if (request.conversation) {
          try { await reopen(request.conversation.id, version); } catch (reopenFailure) { fail(reopenFailure); }
        }
        if (version === generation.current) {
          setError({ message: "This conversation changed. Reconnect, then send your question again.", retry: true });
        }
      } else {
        const next = trouble(failure);
        // Only a request that may still succeed is kept for Reconnect.
        if (!next.retry) pending.current = undefined;
        setError(next);
      }
    }
    finally {
      sending.current = false;
      if (version === generation.current) setBusy(false);
    }
  };

  /** The reader asks to condense the conversation: one run, however many times it is clicked. */
  const compact = async (retry = false) => {
    if (sending.current) return;
    const request = retry ? pendingCompact.current
      : conversation && { key: crypto.randomUUID(), conversation };
    if (!request) return;
    pendingCompact.current = request;
    sending.current = true;
    setBusy(true); setError(undefined);
    const version = generation.current;
    try {
      const next = await api.compact(request.conversation, request.key);
      if (version !== generation.current) return;
      pendingCompact.current = undefined;
      setRun(next);
      await reopen(next.conversation_id, version);
    } catch (failure) {
      if (version !== generation.current) return;
      if (isAxiosError(failure) && failure.response?.status === 409) {
        // Another run is active, or the conversation moved on: show what is true now, not a guess.
        pendingCompact.current = undefined;
        try {
          const latest = await reopen(request.conversation.id, version);
          const last = latest?.runs[latest.runs.length - 1];
          if (version === generation.current && !(last && activeRun(last))) {
            setError({ message: "This conversation changed. Reconnect, then compact it again.", retry: true });
          }
        } catch (reopenFailure) { fail(reopenFailure); }
      } else {
        const next = trouble(failure);
        if (!next.retry) pendingCompact.current = undefined;
        setError(next);
      }
    } finally {
      sending.current = false;
      if (version === generation.current) setBusy(false);
    }
  };

  /** The reader asks the same question again: a new run linked to this one, however many times it is clicked. */
  const retryRun = async (again = false) => {
    if (sending.current) return;
    const request = again ? pendingRetry.current : run && { key: crypto.randomUUID(), run };
    if (!request) return;
    pendingRetry.current = request;
    sending.current = true;
    setBusy(true); setError(undefined);
    const version = generation.current;
    try {
      const next = await api.retry(request.run.id, request.key);
      if (version !== generation.current) return;
      pendingRetry.current = undefined;
      setRun(next);
      await reopen(next.conversation_id, version);
    } catch (failure) {
      if (version !== generation.current) return;
      if (isAxiosError(failure) && failure.response?.status === 409) {
        // Another run is active, or the conversation moved on: show what is true now.
        pendingRetry.current = undefined;
        try { await reopen(request.run.conversation_id, version); } catch (reopenFailure) { fail(reopenFailure); }
        if (version === generation.current) {
          setError({ message: "This conversation changed. Reconnect, then ask your question again.", retry: true });
        }
      } else {
        const next = trouble(failure);
        if (!next.retry) pendingRetry.current = undefined;
        setError(next);
      }
    } finally {
      sending.current = false;
      if (version === generation.current) setBusy(false);
    }
  };

  const stop = async () => {
    if (!run) return;
    const version = ++generation.current;
    setBusy(true);
    try {
      const next = await api.stop(run.id);
      if (version !== generation.current) return;
      setRun(next); setError(undefined);
      // A final answer can win the Stop race. Reopen that committed outcome.
      if (next.state === "completed") await reopen(next.conversation_id, version);
    } catch (failure) { if (version === generation.current) fail(failure); }
    finally { if (version === generation.current) setBusy(false); }
  };

  const reconnect = async () => {
    if (pending.current) return send(pending.current.question, true);
    if (pendingCompact.current) return compact(true);
    if (pendingRetry.current) return retryRun(true);
    const id = run?.conversation_id ?? conversationId;
    if (!id) return;
    setBusy(true);
    try { await reopen(id); } catch (failure) { fail(failure); }
    finally { setBusy(false); }
  };

  // Only for the latest run, when it ended without an answer and the conversation is still as it asked.
  const canRetry = !!conversation && !!run && !error && !busy && retryable(run)
    && conversation.revision === run.base_revision
    && conversation.runs[conversation.runs.length - 1]?.id === run.id;

  // Only where the deployment can condense, once there is something to condense, and never beside an active run.
  const canCompact = !!conversation && conversation.turns.length > 0 && !error && !!run
    && !activeRun(run) && run.capabilities?.manual_compaction === true;

  const centered = !conversation?.runs.length && !run && !busy && !error;
  const records = useCitedRecords(conversation);
  const live = useDraft(run, recordId);
  // What each run streamed, to say when the checked answer differs from what the reader watched.
  const streamed = useRef<Record<string, string>>({});
  if (run && live.text) streamed.current[run.id] = live.text;
  const messages = useMemo(() => toMessages(conversation, run, records), [conversation, run, records]);
  const usage = useMemo(() => conversationTotals(conversation, run), [conversation, run]);
  const latestAnswer = [...messages].reverse().find(m => m.role === "assistant" && !m.endedRun);
  const answered = useRef(onAnswered);
  answered.current = onAnswered;
  const answeredKey = latestAnswer ? `${latestAnswer.id}:${latestAnswer.sources?.length ?? 0}` : "";
  useEffect(() => {
    if (latestAnswer) answered.current?.(latestAnswer);
    // Once per answer, and again when its paper cards arrive.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [answeredKey]);

  const runs = [...(conversation?.runs ?? [])];
  if (run && !runs.some(item => item.id === run.id)) runs.push(run);

  // Follows the newest text while the reader is at the bottom; scrolling up lets go until they return.
  const scroller = useRef<HTMLDivElement>(null);
  const pinned = useRef(true);
  const followKey = `${messages.length}:${run?.state}:${run?.activity?.label}:${run?.activity?.step?.label}:${live.text.length}`;
  const column = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const box = scroller.current;
    if (box && pinned.current) box.scrollTop = box.scrollHeight;
  }, [followKey]);
  // Late growth -- source cards, math, a revised answer -- keeps the bottom in view too.
  useEffect(() => {
    const box = scroller.current;
    const inner = column.current;
    if (!box || !inner || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(() => { if (pinned.current) box.scrollTop = box.scrollHeight; });
    observer.observe(inner);
    return () => observer.disconnect();
  }, []);

  return <div className={`flex h-full max-h-full min-h-0 min-w-0 flex-col bg-canvas ${centered ? CHAT_OPENING : "overflow-hidden"}`}>
    <div ref={scroller} onScroll={e => {
      const box = e.currentTarget;
      pinned.current = box.scrollHeight - box.scrollTop - box.clientHeight < 80;
    }} className={cn(dense ? "px-4 py-5" : "px-4 py-6 sm:px-6",
      centered ? "shrink-0 pb-1 text-center" : "flex-1 min-h-0 overflow-y-auto overflow-x-hidden scrollbar-thin")}>
      <div ref={column} className={cn(dense ? "space-y-5" : `${CHAT_COLUMN} space-y-6`)}>
        {centered && <p className={cn("font-display text-stone-900", dense ? "text-xl text-left" : "text-2xl")}>
          {recordId ? "Ask about this paper." : "What would you like to investigate?"}</p>}
        {runs.map(item => {
          const current = item.id === run?.id ? run : item;
          if (compactionRun(item)) return <CompactionStatus key={item.id} run={current} />;
          return <div key={item.id} className="space-y-5">
            {messages.filter(m => m.id === `q:${item.id}` || m.id === `a:${item.id}`).map(m => <div key={m.id}>
              <ChatMessageBubble message={m} compact={dense} inlineSources
                sourcesSelected={m.id === selectedId} onSelectSources={onSelectSources} />
              {m.role === "assistant" && !m.endedRun && streamed.current[item.id]
                && squash(streamed.current[item.id]) !== squash(m.content)
                && <p className={cn("mt-1 text-[12px] italic text-stone-500", dense ? "pl-9" : "pl-11")}>
                  Revised after checking its citations.</p>}
            </div>)}
            {(() => {
              // The streamed draft stays up until the checked answer lands, so it never blinks out between the two.
              const isLatest = item.id === run?.id;
              const draftText = isLatest ? live.text || streamed.current[item.id] || "" : "";
              const hasAnswer = messages.some(m => m.id === `a:${item.id}`);
              const showDraft = !!draftText && !hasAnswer && (current.state === "running" || current.state === "completed");
              if (!activeRun(current) && !showDraft) return null;
              const active = activeRun(current);
              return <div className={cn("flex", dense ? "gap-2.5" : "gap-3")}>
                <div className={cn("rounded-full shrink-0 flex items-center justify-center bg-brand/10 text-brand", dense ? "w-7 h-7" : "w-8 h-8")}>
                  <AskIrisMark className={dense ? "w-4 h-4" : "w-[18px] h-[18px]"} />
                </div>
                <div className="min-w-0 flex-1">
                  {active && <ReasoningBar compact={dense}
                    activity={current.activity ?? { phase: current.state === "queued" ? "waiting" : "working",
                      label: current.state === "queued" ? "Waiting to start" : "Thinking",
                      since: current.created_at ?? new Date().toISOString(), step: null }}
                    runStartedAt={current.created_at} />}
                  {showDraft && <CitationText text={draftText} citations={[]} streaming={active}
                    className={cn(ANSWER_MARKDOWN, active && CHAT_STREAM_CARET, active && "mt-3", dense ? "text-sm" : "text-md")} />}
                  {current.awaiting_reader && <p className="mt-2 text-sm text-stone-600">Reconnect to continue research.</p>}
                </div>
              </div>;
            })()}
          </div>;
        })}
        {busy && !run && <p role="status" className="text-sm text-stone-600">Connecting to Ask IRIS…</p>}
        {error && <div role="alert" className="space-y-2 text-sm text-stone-700">
          <p>{error.message}</p>
          {error.retry && <button type="button" disabled={busy} onClick={() => void reconnect()} className="min-h-11 underline text-brand">Reconnect</button>}
          {error.missing && <Link to="/ai" className="inline-flex min-h-11 items-center underline text-brand">Start a new conversation</Link>}
        </div>}
        {canRetry && <button type="button" onClick={() => void retryRun()}
          className="min-h-11 rounded-full border border-stone-300 px-5 text-sm text-stone-800 focus-visible:outline-brand">
          Try this question again</button>}
        {run && activeRun(run) && compactionRun(run) && <button type="button" onClick={() => void stop()} disabled={busy}
          className="min-h-11 rounded-full border border-stone-300 px-5 text-sm text-stone-800 focus-visible:outline-brand">
          Stop compaction</button>}
      </div>
    </div>
    {canCompact && <div className="mx-auto flex w-full max-w-3xl flex-wrap items-center gap-x-4 gap-y-1 px-4 pt-2 text-sm text-stone-700">
      <button type="button" disabled={busy} onClick={() => void compact()} aria-describedby="compact-help"
        className="min-h-11 rounded-full border border-stone-300 px-5 text-sm text-stone-800 focus-visible:outline-brand disabled:opacity-60">
        Compact conversation</button>
      <p id="compact-help" className="min-w-0 flex-1 basis-56 text-xs text-stone-600">{COMPACTION_HELP}</p>
    </div>}
    <ChatInput centered={centered} onSend={text => void send(text)} draft={draft} onDraftChange={setDraft}
      onStop={run && activeRun(run) && !compactionRun(run) && !busy ? () => void stop() : undefined}
      maxLength={4000}
      placeholder={recordId ? "Ask about this paper…" : "Ask about the research corpus…"}
      disabled={busy || !!error || !!(run && activeRun(run))} label={recordId ? "Ask about this paper" : "Ask about the research corpus"}>
      <ModelPill name="Research depth" value={depth} options={DEPTHS} onChange={setDepth}
        note="IRIS chooses the model for each answer." />
      {scopeToggle && <button type="button" onClick={() => scopeToggle.onChange(!scopeToggle.allPapers)}
        aria-pressed={scopeToggle.allPapers}
        aria-label={scopeToggle.allPapers ? "Searching all papers. Search only this paper" : "Searching this paper. Search all papers"}
        title={scopeToggle.allPapers ? "All papers" : "This paper"}
        className={cn("inline-flex h-8 items-center gap-1.5 rounded-full px-2.5 text-[12px] font-medium transition-colors focus-visible:outline-brand",
          scopeToggle.allPapers ? "bg-brand text-white hover:bg-brand-dark" : "text-stone-600 hover:bg-stone-100")}>
        <i aria-hidden className={cn("text-[11px]", scopeToggle.allPapers ? "fas fa-layer-group" : "far fa-file-lines")} />
        {scopeToggle.allPapers ? "All papers" : "This paper"}
      </button>}
      {usage.latest && <TokenUsageMeter usage={usage.latest} />}
    </ChatInput>
  </div>;
}
