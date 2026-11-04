import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { isAxiosError } from "axios";
import { activeRun, ProtocolMismatch, RELOAD_TO_RECONNECT, runtimeReader, type Depth, type ReaderConversation, type ReaderRun } from "@/api/runtimeReader";
import { ChatInput } from "./ChatInput";
import { CHAT_OPENING } from "./answerLayout";

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
    <p className="mt-2 text-xs">{run.context
      ? `Estimated context: ${run.context.used_tokens.toLocaleString()} of ${run.context.capacity_tokens.toLocaleString()} tokens`
      : "Context estimate unavailable"}</p>
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
  onConversation?: (id: string) => void;
}

/** Both reader surfaces use the same persisted snapshot and transport (IR-730). */
export function RuntimeReader({ recordId, conversationId, onConversation }: Props) {
  const api = useMemo(() => runtimeReader(recordId), [recordId]);
  const [conversation, setConversation] = useState<ReaderConversation>();
  const [run, setRun] = useState<ReaderRun>();
  const [depth, setDepth] = useState<Depth>("deep");
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<Trouble>();
  const generation = useRef(0);
  const pending = useRef<{ question: string; depth: Depth; key: string; conversation?: ReaderConversation }>();
  const sending = useRef(false);

  const fail = useCallback((failure: unknown) => setError(trouble(failure)), []);
  const reopen = useCallback(async (id: string, version = generation.current) => {
    const next = await api.reopen(id);
    if (version !== generation.current) return;
    setConversation(next);
    setRun(next.runs[next.runs.length - 1]);
    setError(undefined);
  }, [api]);

  useEffect(() => {
    const version = ++generation.current;
    setConversation(undefined); setRun(undefined); setError(undefined);
    pending.current = undefined;
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
    const id = run?.conversation_id ?? conversationId;
    if (!id) return;
    setBusy(true);
    try { await reopen(id); } catch (failure) { fail(failure); }
    finally { setBusy(false); }
  };

  const centered = !conversation?.runs.length && !run && !busy && !error;

  return <div className={`flex h-full min-h-0 min-w-0 flex-col bg-canvas ${centered ? CHAT_OPENING : ""}`}>
    <div className={`px-4 py-6 sm:px-6 ${centered ? "shrink-0 pb-1 text-center" : "flex-1 min-h-0 overflow-y-auto"}`}>
      <div className="mx-auto max-w-3xl space-y-6">
        {centered && <p className="font-display text-2xl text-stone-900">What would you like to investigate?</p>}
        {conversation?.runs.map(item => {
          const turn = conversation.turns.find(t => t.run_id === item.id);
          const current = item.id === run?.id ? run : item;
          return <article key={item.id} aria-label="Research question" className="min-w-0 space-y-4">
            <p className="font-medium text-stone-900 [overflow-wrap:anywhere]">{item.question}</p>
            <ResearchProgress run={current} />
            {turn && <div className="space-y-3">
              <p className="whitespace-pre-wrap leading-relaxed text-stone-800 [overflow-wrap:anywhere]">{turn.answer}</p>
              {turn.citations.length > 0 && <ol aria-label="Cited passages" className="space-y-3 text-sm">
                {turn.citations.map((citation, index) => <li key={index}>
                  <Link className="text-brand underline" to={`/records/${citation.record_id}?page=${citation.page}`}>[{index + 1}] Page {citation.page}</Link>
                  <blockquote className="mt-1 border-l border-stone-300 pl-3 text-stone-600 [overflow-wrap:anywhere]">{citation.quote}</blockquote>
                </li>)}
              </ol>}
            </div>}
          </article>;
        })}
        {run && !conversation?.runs.some(item => item.id === run.id) && <ResearchProgress run={run} />}
        {busy && !run && <p role="status">Connecting to Ask IRIS…</p>}
        {error && <div role="alert" className="space-y-2 text-sm text-stone-700">
          <p>{error.message}</p>
          {error.retry && <button type="button" disabled={busy} onClick={() => void reconnect()} className="min-h-11 underline text-brand">Reconnect</button>}
          {error.missing && <Link to="/ai" className="inline-flex min-h-11 items-center underline text-brand">Start a new conversation</Link>}
        </div>}
        {run && activeRun(run) && <button type="button" onClick={() => void stop()} disabled={busy}
          className="min-h-11 rounded-full border border-stone-300 px-5 text-sm text-stone-800 focus-visible:outline-brand">Stop research</button>}
      </div>
    </div>
    <ChatInput centered={centered} onSend={text => void send(text)} draft={draft} onDraftChange={setDraft}
      maxLength={4000}
      placeholder={recordId ? "Ask about this paper…" : "Ask about the research corpus…"}
      disabled={busy || !!error || !!(run && activeRun(run))} label={recordId ? "Ask about this paper" : "Ask about the research corpus"}>
      <label className="inline-flex min-h-11 items-center gap-2 text-sm text-stone-700">
        <input type="checkbox" checked={depth === "deep"} onChange={e => setDepth(e.target.checked ? "deep" : "ordinary")}
          className="h-4 w-4 accent-brand" /> Thorough research
      </label>
    </ChatInput>
  </div>;
}
