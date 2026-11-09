import { useEffect, useId, useRef, useState, type FormEvent, type ReactNode } from "react";

import { recordsApi } from "@/api/records";
import { Button } from "@/components/ui";
import { LABEL, fieldClasses } from "@/components/ui/fieldClasses";
import { FOCUS_RING } from "@/components/ui/interaction";
import type { Capability } from "@/features/records/capabilities";
import { errorDetail } from "@/lib/errorDetail";
import { cn, formatDate } from "@/lib/utils";
import type { ResponseLetter, ReviewComment, ThreadSeverity } from "@/types/records";

import type { Passage } from "./passage";
import { ResponseLetterPanel } from "./ResponseLetter";
import { SEVERITY_WORDS, filterThreads, isOpen, threadStatus, type Thread, type ThreadFilter, type ThreadViewer } from "./threadModel";
import type { ReviewThreadsState } from "./useReviewThreads";

/** What the composer comments on: a passage of a Version, or the whole record. */
export type CommentTarget = { kind: "general" } | { kind: "passage"; version: number; passage: Passage };

export interface ReviewThreadsProps {
  recordId: number;
  can: ReadonlySet<Capability>;
  threads: ReviewThreadsState;
  viewer: ThreadViewer;
  /** The composer, opened by the reader's Comment or by *New comment*. */
  composing: CommentTarget | null;
  onCompose: (target: CommentTarget | null) => void;
  /** A thread was changed: re-read the record, so Readiness and the Decision follow. */
  onChanged: () => void;
  /** Bring a thread's passage into view in the reader. */
  onShowInPaper: (thread: Thread) => void;
  /** A party Readiness pointed at ("owner" for the authors), or null for every party. */
  party: string | null;
  onClearParty: () => void;
  /** A thread to scroll to and focus, from a pin; bumped key so a second press works. */
  focus: { id: number; key: number } | null;
  /** The newest response to reviewers, shown first (IR-876); null for none. */
  letter?: ResponseLetter | null;
}

const FILTER_NAMES: Record<ThreadFilter, string> = { open: "Open", yours: "Yours", resolved: "Resolved", all: "All" };

/**
 * The Threads tab (ADR-032 §7, 2026-11-04; IR-875): the composer, the
 * viewer's drafts, and every sent thread under Open / Yours / Resolved / All.
 *
 * **Every control is the server's call.** A thread's Resolve, Reopen, answer,
 * severity and Discard appear exactly where its `can_*` flag is true; the
 * composer's severity choice and its "held as a draft" note appear exactly
 * where `finish_review` is granted, which is when the server holds a new
 * thread as a draft. Nothing here compares a role.
 */
export function ReviewThreads(props: ReviewThreadsProps) {
  const { threads, viewer, party, focus } = props;
  const [filter, setFilter] = useState<ThreadFilter>("open");
  const headingId = useId();

  // Readiness pointing at a party shows its open threads.
  useEffect(() => {
    if (party !== null) setFilter("open");
  }, [party]);
  // A pin opens its thread wherever it is filed.
  useEffect(() => {
    if (!focus) return;
    const thread = threads.sent.find((t) => t.root.id === focus.id);
    if (thread && !isOpen(thread)) setFilter("resolved");
    else if (thread) setFilter("open");
    requestAnimationFrame(() => {
      const el = document.getElementById(threadDomId(focus.id));
      el?.scrollIntoView?.({ block: "nearest" });
      el?.focus({ preventScroll: true });
    });
  }, [focus, threads.sent]);

  const ofParty = (list: Thread[]) =>
    party === null ? list : list.filter((t) => (t.root.party ?? "owner") === party);
  const groups = Object.fromEntries(
    (Object.keys(FILTER_NAMES) as ThreadFilter[]).map((f) => [f, ofParty(filterThreads(threads.sent, f, viewer))]),
  ) as Record<ThreadFilter, Thread[]>;
  const shown = groups[filter];
  const canComment = props.can.has("comment_review");

  return (
    <section aria-labelledby={headingId} className="space-y-4">
      <h3 id={headingId} className="sr-only">Threads</h3>
      {props.letter && <ResponseLetterPanel letter={props.letter} />}
      {props.composing
        ? <Composer {...props} target={props.composing} />
        : canComment && (
          <p className="flex items-center justify-between gap-2 text-small text-stone-600">
            <span>Select a passage in the paper and press C, or find one, to comment on it.</span>
            <Button variant="outline" size="sm" onClick={() => props.onCompose({ kind: "general" })}>
              New comment
            </Button>
          </p>
        )}

      <div role="group" aria-label="Filter threads" className="flex flex-wrap gap-1.5">
        {(Object.keys(FILTER_NAMES) as ThreadFilter[]).map((f) => (
          <button
            key={f}
            type="button"
            aria-pressed={filter === f}
            onClick={() => setFilter(f)}
            className={cn(
              "min-h-9 rounded-full px-3 text-small font-semibold ring-1",
              filter === f ? "bg-brand-50 text-brand ring-brand-200" : "text-stone-700 ring-stone-300 hover:text-brand",
              FOCUS_RING,
            )}
          >
            {FILTER_NAMES[f]} {groups[f].length}
          </button>
        ))}
      </div>
      {party !== null && (
        <p className="text-small text-stone-700">
          Showing {party === "owner" ? "the authors'" : `${threads.sent.find((t) => t.root.party === party)?.root.party_label ?? party}'s`} threads.{" "}
          <button type="button" onClick={props.onClearParty} className={cn("font-semibold text-brand hover:underline", FOCUS_RING)}>
            Show every party
          </button>
        </p>
      )}

      {threads.failed && (
        <p role="alert" className="text-small text-stone-700">
          Could not load the threads.{" "}
          <button type="button" onClick={threads.reload} className={cn("font-semibold text-brand hover:underline", FOCUS_RING)}>
            Try again
          </button>
        </p>
      )}

      {threads.drafts.length > 0 && (
        <section aria-label="Your drafts" className="space-y-2">
          <p className="flex justify-between gap-2 text-2xs font-semibold uppercase tracking-wider text-stone-600">
            <span>Your drafts</span>
            <span className="normal-case tracking-normal font-normal">Only you see these until you finish</span>
          </p>
          {threads.drafts.map((t) => <ThreadItem key={t.root.id} thread={t} {...props} />)}
        </section>
      )}

      {threads.loaded && (shown.length === 0 ? (
        <p className="text-small text-stone-600">
          {filter === "resolved" ? "Resolved threads stay here, in the record's history." : "No threads here."}
        </p>
      ) : (
        <div className="space-y-2">
          {shown.map((t) => <ThreadItem key={t.root.id} thread={t} {...props} />)}
        </div>
      ))}
    </section>
  );
}

export const threadDomId = (id: number) => `review-thread-${id}`;

const pinWords = (thread: Thread) => (thread.root.is_draft ? `Draft ${thread.pin}` : `Thread ${thread.pin}`);

function Chip({ children, tone = "quiet" }: { children: ReactNode; tone?: "quiet" | "brand" | "ink" }) {
  return (
    <span className={cn(
      "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-2xs font-semibold",
      tone === "brand" && "bg-brand-50 text-brand ring-1 ring-brand-200",
      tone === "ink" && "bg-stone-900 text-white",
      tone === "quiet" && "text-stone-700 ring-1 ring-stone-300",
    )}>
      {children}
    </span>
  );
}

function ThreadItem({ thread, ...props }: ReviewThreadsProps & { thread: Thread }) {
  const { root, replies } = thread;
  const ids = useId();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState<null | "reply" | "addressed" | "declined">(null);
  const status = threadStatus(root);
  // Replies and what happened to the thread, in the order they happened. The
  // answer is shown on its own above, so its event is not repeated.
  const history = threadHistory(root, replies);
  const canReply = props.can.has("comment_review") && !root.is_draft && root.state === "open";

  const act = async (run: () => Promise<unknown>, failure: string) => {
    setBusy(true);
    setError(null);
    try {
      await run();
      setForm(null);
      props.threads.reload();
      props.onChanged();
    } catch (err) {
      setError(errorDetail(err, failure));
    } finally {
      setBusy(false);
    }
  };
  const id = props.recordId;
  const otherSeverity: ThreadSeverity = root.severity === "must_fix" ? "suggestion" : "must_fix";

  return (
    <article
      id={threadDomId(root.id)}
      tabIndex={-1}
      aria-labelledby={`${ids}-h`}
      className={cn("rounded-lg border border-stone-200 bg-white px-3 py-3 space-y-2", FOCUS_RING)}
    >
      <header className="flex flex-wrap items-center gap-2">
        <h4 id={`${ids}-h`} className="sr-only">
          {pinWords(thread)}{root.party_label ? `, ${root.party_label}` : ""}
        </h4>
        <span aria-hidden className={cn(
          "inline-grid place-items-center min-w-5 h-5 px-1 rounded-full text-[11px] font-semibold",
          root.is_draft ? "bg-white text-brand ring-1 ring-brand/40" : root.state === "open" ? "bg-brand text-white" : "bg-stone-900 text-white",
        )}>{thread.pin}</span>
        {root.party_label && <span className="text-small font-semibold text-stone-900">{root.party_label}</span>}
        {root.anchor && (
          <span className="text-2xs text-stone-600">p.{root.anchor.page} · v{root.anchor.version}</span>
        )}
        <span className="flex-1" />
        {root.outdated_since != null && <Chip>Outdated since v{root.outdated_since}</Chip>}
        {root.severity && <Chip tone={root.severity === "must_fix" ? "brand" : "quiet"}>{SEVERITY_WORDS[root.severity]}</Chip>}
        {root.is_draft
          ? <Chip><i className="fas fa-pen text-[9px]" aria-hidden />Draft</Chip>
          : status && <Chip tone={root.state === "open" ? "quiet" : "ink"}>{status}</Chip>}
      </header>

      {root.anchor && (
        <button
          type="button"
          onClick={() => props.onShowInPaper(thread)}
          aria-label={`Show in paper: “${root.anchor.quote}”`}
          className={cn("block w-full text-left border-l-2 border-brand/40 pl-2 text-small italic text-stone-700 hover:text-brand", FOCUS_RING)}
        >
          “{root.anchor.quote}”
        </button>
      )}
      <WhereNow root={root} />
      {root.suggestion && <SuggestedWording root={root} />}

      <div className="text-small text-stone-800">
        <p className="text-2xs text-stone-600">
          {root.author_name ?? "Someone"} · {formatDate(root.created_at)}{root.edited_at ? " · edited" : ""}
        </p>
        <p className="whitespace-pre-wrap break-words">{root.body}</p>
      </div>

      {root.answer && (
        <p className="rounded bg-stone-50 px-2 py-1.5 text-small text-stone-800">
          <span className="font-semibold">
            {root.answer.by ?? "The authors"} {root.answer.kind === "addressed" ? "marked it addressed" : "declined it"}:
          </span>{" "}
          <span className="whitespace-pre-wrap">{root.answer.note}</span>
        </p>
      )}
      {root.state === "closed" && root.closed_reason && (
        <p className="text-small text-stone-700">Closed by the Decision: {root.closed_reason}</p>
      )}
      {history.length > 0 && (
        <ol aria-label="Replies and history" className="space-y-1.5 border-l border-stone-200 pl-3">
          {history.map((h) => h.reply
            ? <Reply key={`r${h.reply.id}`} reply={h.reply} />
            : <li key={h.key} className="text-2xs text-stone-600">{eventWords(h.event!)} · {formatDate(h.at)}</li>)}
        </ol>
      )}

      {form === "reply" && (
        <TextForm
          label="Reply" submitLabel="Reply" required busy={busy}
          hint="Posted now, not held with your review."
          onCancel={() => setForm(null)}
          onSubmit={(body) => act(() => recordsApi.postReviewComment(id, { body, reply_to: root.id }), "Your reply could not be sent.")}
        />
      )}
      {(form === "addressed" || form === "declined") && (
        <TextForm
          label={form === "addressed" ? "Where you addressed it" : "Why you're declining it"}
          submitLabel={form === "addressed" ? "Mark addressed" : "Decline"}
          required busy={busy}
          hint={form === "addressed" ? "For example: §4, p. 9. The reviewer checks it and resolves the thread." : undefined}
          onCancel={() => setForm(null)}
          onSubmit={(note) => act(() => recordsApi.answerThread(id, root.id, { answer: form, note }), "Your answer could not be saved.")}
        />
      )}

      {form === null && (
        <div className="flex flex-wrap gap-1.5" role="group" aria-label={`${pinWords(thread)} actions`}>
          {root.can_answer && <>
            {root.suggestion && (
              <Button size="sm" variant="outline" disabled={busy}
                onClick={() => act(() => recordsApi.answerThread(id, root.id, { answer: "addressed", note: "" }), "Your answer could not be saved.")}>
                Accept wording
              </Button>
            )}
            <Button size="sm" variant="outline" onClick={() => setForm("addressed")}>Mark addressed</Button>
            <Button size="sm" variant="outline" onClick={() => setForm("declined")}>Decline</Button>
          </>}
          {root.can_resolve && (
            <Button size="sm" variant="outline" disabled={busy}
              onClick={() => act(() => recordsApi.resolveThread(id, root.id), "The thread could not be resolved.")}>
              Resolve
            </Button>
          )}
          {root.can_reopen && (
            <Button size="sm" variant="outline" disabled={busy}
              onClick={() => act(() => recordsApi.reopenThread(id, root.id), "The thread could not be reopened.")}>
              Reopen
            </Button>
          )}
          {root.can_change_severity && root.severity && (
            <Button size="sm" variant="ghost" disabled={busy}
              onClick={() => act(() => recordsApi.changeThreadSeverity(id, root.id, otherSeverity), "The severity could not be changed.")}>
              Change to {SEVERITY_WORDS[otherSeverity]}
            </Button>
          )}
          {canReply && <Button size="sm" variant="ghost" onClick={() => setForm("reply")}>Reply</Button>}
          {root.can_delete && (
            <Button size="sm" variant="ghost" disabled={busy}
              onClick={() => act(() => recordsApi.deleteReviewComment(id, root.id), "The draft could not be discarded.")}>
              Discard
            </Button>
          )}
        </div>
      )}
      {error && <p role="alert" className="text-small text-brand">{error}</p>}
    </article>
  );
}

/**
 * Where the passage is in the newest Version it was looked for in (IR-876):
 * found there (moved), changed (shown beside the original), or removed. A
 * thread found in its own Version says nothing.
 */
function WhereNow({ root }: { root: ReviewComment }) {
  const ids = useId();
  const place = root.place;
  if (!place || !root.anchor) return null;
  if (place.outcome === "removed") {
    return <p className="text-small text-stone-700">Passage removed in v{place.version}.</p>;
  }
  if (place.outcome === "found" && root.outdated_since == null) {
    return <p className="text-small text-stone-700">Found on p. {place.page} of v{place.version}.</p>;
  }
  const label = `Now in v${place.version}, p. ${place.page}`;
  return (
    <section aria-labelledby={`${ids}-now`} className="space-y-0.5">
      <p id={`${ids}-now`} className="text-2xs font-semibold text-stone-600">{label}</p>
      <blockquote className="border-l-2 border-stone-300 pl-2 text-small text-stone-800">“{place.text}”</blockquote>
    </section>
  );
}

/**
 * A reviewer's replacement text (IR-876). Accepting it is a promise, since
 * IRIS can't edit the PDF; once accepted, the next Version says whether the
 * wording appears. That is a hint: the reviewer still resolves the thread.
 */
function SuggestedWording({ root }: { root: ReviewComment }) {
  const ids = useId();
  const place = root.place;
  const accepted = root.answer?.kind === "addressed";
  return (
    <section aria-labelledby={`${ids}-wording`} className="rounded bg-stone-50 px-2 py-1.5 space-y-0.5">
      <p id={`${ids}-wording`} className="text-2xs font-semibold text-stone-600">Suggested wording</p>
      <p className="text-small text-stone-900 whitespace-pre-wrap break-words">“{root.suggestion}”</p>
      {accepted && place && (
        <p className="text-2xs text-stone-700">
          {place.suggestion_page != null
            ? `Suggested wording found on p. ${place.suggestion_page} of v${place.version}.`
            : `Suggested wording not found in v${place.version}.`}
        </p>
      )}
    </section>
  );
}

type HistoryItem = { key: string; at: string; reply?: ReviewComment; event?: NonNullable<ReviewComment["events"]>[number] };

/** A thread's replies and events, oldest first; a tie keeps a reply before an event. */
export function threadHistory(root: ReviewComment, replies: ReviewComment[]): HistoryItem[] {
  const items: HistoryItem[] = [
    ...replies.map((r) => ({ key: `r${r.id}`, at: r.created_at, reply: r })),
    ...(root.events ?? []).filter((e) => e.kind !== "answered").map((e, i) => ({ key: `e${i}`, at: e.at, event: e })),
  ];
  const time = (h: HistoryItem) => Date.parse(h.at) || 0;
  return items.sort((a, b) => time(a) - time(b) || (a.reply ? -1 : 0) - (b.reply ? -1 : 0));
}

function eventWords(e: NonNullable<ReviewComment["events"]>[number]): string {
  const who = e.actor_name ?? "Someone";
  switch (e.kind) {
    case "severity_changed":
      return `${who} changed it to ${e.to ? SEVERITY_WORDS[e.to as ThreadSeverity] ?? e.to : "another severity"}`;
    case "resolved":
      return `${who} resolved it`;
    case "reopened":
      return `${who} reopened it`;
    case "closed_by_decision":
      return "Closed by the Decision";
    default:
      return `${who} answered it`;
  }
}

function Reply({ reply }: { reply: ReviewComment }) {
  return (
    <li className="text-small text-stone-800">
      <p className="text-2xs text-stone-600">
        {reply.author_name ?? "Someone"} · {formatDate(reply.created_at)}{reply.edited_at ? " · edited" : ""}
      </p>
      <p className="whitespace-pre-wrap break-words">{reply.body}</p>
    </li>
  );
}

function TextForm({ label, submitLabel, hint, required, busy, onSubmit, onCancel }: {
  label: string; submitLabel: string; hint?: string; required?: boolean; busy: boolean;
  onSubmit: (text: string) => void; onCancel: () => void;
}) {
  const id = useId();
  const [text, setText] = useState("");
  const ref = useRef<HTMLTextAreaElement>(null);
  useEffect(() => ref.current?.focus(), []);
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (text.trim() || !required) onSubmit(text.trim());
  };
  return (
    <form onSubmit={submit} className="space-y-1.5">
      <label htmlFor={id} className={LABEL}>{label}</label>
      <textarea ref={ref} id={id} rows={3} value={text} onChange={(e) => setText(e.target.value)}
        aria-describedby={hint ? `${id}-hint` : undefined} className={fieldClasses(false)} />
      {hint && <p id={`${id}-hint`} className="text-2xs text-stone-600">{hint}</p>}
      <div className="flex justify-end gap-2">
        <Button type="button" size="sm" variant="secondary" onClick={onCancel} disabled={busy}>Cancel</Button>
        <Button type="submit" size="sm" disabled={busy || (required && !text.trim())}>{submitLabel}</Button>
      </div>
    </form>
  );
}

/**
 * Comment on a passage, or the record as a whole. Where `finish_review` is
 * granted the server holds a new thread as a draft, so the reviewer chooses
 * its severity -- *Suggestion* unless they say *Must fix* (decided for IR-875)
 * -- and is told it waits for *Finish review*.
 */
function Composer({ recordId, can, target, onCompose, threads, onChanged }: ReviewThreadsProps & { target: CommentTarget }) {
  const ids = useId();
  const drafting = can.has("finish_review");
  const [body, setBody] = useState("");
  const [severity, setSeverity] = useState<ThreadSeverity>("suggestion");
  const [wording, setWording] = useState("");
  // Only a reviewer's thread on a passage carries wording (IR-876).
  const canSuggest = drafting && target.kind === "passage";
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const ref = useRef<HTMLTextAreaElement>(null);
  useEffect(() => ref.current?.focus(), [target]);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!body.trim() || busy) return;
    setBusy(true);
    setError(null);
    try {
      await recordsApi.postReviewComment(recordId, {
        body: body.trim(),
        ...(drafting ? { severity } : {}),
        ...(canSuggest && wording.trim() ? { suggestion: wording.trim() } : {}),
        ...(target.kind === "passage" ? {
          anchor: {
            version: target.version, page: target.passage.page, quote: target.passage.quote,
            prefix: target.passage.prefix, suffix: target.passage.suffix, regions: target.passage.regions,
          },
        } : {}),
      });
      onCompose(null);
      threads.reload();
      onChanged();
    } catch (err) {
      setError(`${errorDetail(err, "Your comment could not be saved.")} Your text is kept.`);
    } finally {
      setBusy(false);
    }
  };

  return (
    <form onSubmit={submit} aria-label="New comment" className="rounded-lg border border-stone-300 bg-white p-3 space-y-2">
      <p className="text-2xs text-stone-600">
        {target.kind === "passage"
          ? <>Comment on <b className="text-stone-800">p.{target.passage.page}</b> of v{target.version}</>
          : "Comment on the record as a whole"}
      </p>
      {target.kind === "passage" && (
        <blockquote className="border-l-2 border-brand/40 pl-2 text-small italic text-stone-700">“{target.passage.quote}”</blockquote>
      )}
      <label htmlFor={`${ids}-body`} className="sr-only">Comment</label>
      <textarea ref={ref} id={`${ids}-body`} rows={3} value={body} onChange={(e) => setBody(e.target.value)}
        placeholder="What should the authors look at here?" className={fieldClasses(false)} />
      {drafting && (
        <fieldset className="flex flex-wrap items-center gap-3">
          <legend className="sr-only">Severity</legend>
          {(["must_fix", "suggestion"] as const).map((s) => (
            <label key={s} className="inline-flex items-center gap-1.5 text-small text-stone-800 min-h-9">
              <input type="radio" name={`${ids}-severity`} value={s} checked={severity === s}
                onChange={() => setSeverity(s)} className="accent-brand" />
              {SEVERITY_WORDS[s]}
            </label>
          ))}
        </fieldset>
      )}
      {canSuggest && (
        <div className="space-y-1">
          <label htmlFor={`${ids}-wording`} className={LABEL}>Suggested wording (optional)</label>
          <textarea id={`${ids}-wording`} rows={2} value={wording} onChange={(e) => setWording(e.target.value)}
            aria-describedby={`${ids}-wording-hint`} className={fieldClasses(false)} />
          <p id={`${ids}-wording-hint`} className="text-2xs text-stone-600">
            The text you&rsquo;d put in its place. You can change it until you finish your review.
          </p>
        </div>
      )}
      {error && <p role="alert" className="text-small text-brand">{error}</p>}
      <div className="flex justify-end gap-2">
        <Button type="button" size="sm" variant="secondary" onClick={() => onCompose(null)} disabled={busy}>Cancel</Button>
        <Button type="submit" size="sm" disabled={busy || !body.trim()}>{drafting ? "Add to review" : "Comment"}</Button>
      </div>
      {drafting && <p className="text-2xs text-stone-600">Held as a draft until you finish your review.</p>}
    </form>
  );
}
