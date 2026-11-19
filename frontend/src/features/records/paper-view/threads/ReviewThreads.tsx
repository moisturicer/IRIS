import { useEffect, useId, useRef, useState, type FormEvent, type ReactNode } from "react";

import { recordsApi } from "@/api/records";
import { Button } from "@/components/ui";
import { LABEL, fieldClasses } from "@/components/ui/fieldClasses";
import { FOCUS_RING } from "@/components/ui/interaction";
import type { Capability } from "@/features/records/capabilities";
import { errorDetail } from "@/lib/errorDetail";
import { cn, formatDate } from "@/lib/utils";
import type { MentionedPerson, ResponseLetter, ReviewComment, ThreadDocument, ThreadSeverity } from "@/types/records";

import { RowMenu } from "@/features/accounts/RowMenu";

import { initials } from "../commentThreads";
import { MentionPicker, MentionedPeople, changedMentions, peopleIn } from "../Mentions";
import { SavedReplies } from "../SavedReplies";
import type { Passage } from "./passage";
import { ResponseLetterPanel } from "./ResponseLetter";
import { SEVERITY_WORDS, filterThreads, isOpen, threadStatus, type Thread, type ThreadFilter, type ThreadViewer } from "./threadModel";
import type { ReviewThreadsState } from "./useReviewThreads";

/** What the composer comments on: a passage of a Version, or the whole record. */
export type CommentTarget =
  | { kind: "general" }
  | { kind: "passage"; version: number; passage: Passage }
  /** A supporting document's newest upload, as a whole (IR-1204): "Consent form, v1". */
  | { kind: "document"; upload: number; label: string };

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
  /** Show the document a thread is about in the reader (IR-1204); absent where nothing can. */
  onShowDocument?: (document: ThreadDocument) => void;
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
 * severity, Post and Discard appear exactly where its `can_*` flag is true;
 * the composer's severity choice and its Post / Save as draft pair appear
 * exactly where `finish_review` is granted, which is when the server can hold
 * a new thread as a draft, and *New comment* where `open_general_thread` is.
 * Nothing here compares a role.
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
  // Replying (`comment_review`) outlasts a reviewer's seat; starting a thread
  // on a passage (`start_thread`) does not (IR-1226).
  const canStart = props.can.has("start_thread");
  // A thread on no passage is a reviewer's (IR-1194); the authors comment on a passage.
  const canGeneral = props.can.has("open_general_thread");

  return (
    <section aria-labelledby={headingId} className="space-y-4">
      <h3 id={headingId} className="sr-only">Threads</h3>
      {props.letter && <ResponseLetterPanel letter={props.letter} />}
      {/* The prototype's Threads head (IR-1139): the filter as one segmented
          control with its counts, *New comment* on the right, and how to
          comment on a passage under them. */}
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div role="group" aria-label="Filter threads" className="inline-flex flex-wrap gap-0.5 rounded-control bg-stone-100 p-1">
          {(Object.keys(FILTER_NAMES) as ThreadFilter[]).map((f) => (
            <button
              key={f}
              type="button"
              aria-pressed={filter === f}
              onClick={() => setFilter(f)}
              className={cn(
                "min-h-11 reading-split:min-h-9 rounded-control px-3 text-small font-semibold",
                filter === f ? "bg-surface text-stone-900 ring-1 ring-stone-300" : "text-stone-600 hover:text-stone-900",
                FOCUS_RING,
              )}
            >
              {FILTER_NAMES[f]} <span className="font-normal text-stone-500">{groups[f].length}</span>
            </button>
          ))}
        </div>
        {canGeneral && !props.composing && (
          <Button variant="outline" size="sm" onClick={() => props.onCompose({ kind: "general" })}>
            <i className="fas fa-note-sticky" aria-hidden />
            New comment
          </Button>
        )}
      </div>
      {props.composing
        ? <Composer {...props} target={props.composing} />
        : canStart && (
          <p className="text-small text-stone-600">
            Select a passage in the paper and press{" "}
            <kbd className="rounded-control border border-stone-300 bg-surface px-1.5 font-mono text-2xs text-stone-700">C</kbd>
            {canGeneral ? ", or use New comment." : ". A remark on the whole paper goes in Conversation."}
          </p>
        )}
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
          <p className="flex flex-wrap items-baseline gap-x-2 text-small">
            <span className="font-semibold text-stone-900">Your drafts</span>
            <span className="text-2xs text-stone-600">Only you see these until you post them or finish your review</span>
          </p>
          {threads.drafts.map((t) => <ThreadItem key={t.root.id} thread={t} {...props} />)}
        </section>
      )}

      {threads.loaded && (shown.length === 0 ? (
        <p className="text-small text-stone-600">
          {filter === "resolved" ? "Resolved threads stay here, in the record's history." : "No threads here."}
        </p>
      ) : (
        <div className="space-y-3">
          {shown.map((t) => <ThreadItem key={t.root.id} thread={t} {...props} />)}
        </div>
      ))}
    </section>
  );
}

export const threadDomId = (id: number) => `review-thread-${id}`;

const pinWords = (thread: Thread) => (thread.root.is_draft ? `Draft ${thread.pin}` : `Thread ${thread.pin}`);

type ChipTone = "quiet" | "brand" | "ink" | "answered";

/** The icon an answer is marked by, on its badge and its history row: never colour alone (IR-1191). */
const ANSWER_ICON: Record<ThreadAnswer["kind"], string> = { addressed: "fa-check", declined: "fa-xmark" };

/** A settled thread inked; an open one outlined dark once answered, else quiet. */
function statusTone(root: ReviewComment): ChipTone {
  if (root.state !== "open") return "ink";
  return root.answer ? "answered" : "quiet";
}

function Chip({ children, tone = "quiet" }: { children: ReactNode; tone?: ChipTone }) {
  return (
    <span className={cn(
      "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-2xs font-semibold",
      // Must fix, filled, as the prototype's card has it (IR-1191).
      tone === "brand" && "bg-brand text-white",
      tone === "ink" && "bg-stone-900 text-white",
      tone === "answered" && "bg-surface text-stone-900 ring-1 ring-stone-900",
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
  // Replies, the answer and what happened to the thread, in the order they happened.
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
  // The thread a pin opened: its passage on the paper and its quote here share one colour.
  const now = props.focus?.id === root.id;
  const otherSeverity: ThreadSeverity = root.severity === "must_fix" ? "suggestion" : "must_fix";

  // Whether the foot has anything to hold: the box draws no empty foot.
  const anyAction = root.can_answer || root.can_resolve || root.can_reopen
    || (root.can_change_severity && Boolean(root.severity)) || canReply || root.can_post || root.can_delete;

  // The same box as the Conversation's comments (IR-1131): who and which
  // party in its head, the passage and what was said in its body, and the
  // actions in its foot. A draft's box is dashed.
  return (
    <article
      id={threadDomId(root.id)}
      tabIndex={-1}
      aria-labelledby={`${ids}-h`}
      className={cn("review-box", root.is_draft && "review-box-draft", FOCUS_RING)}
    >
      <header className="review-box-head">
        <h4 id={`${ids}-h`} className="sr-only">
          {pinWords(thread)}{root.party_label ? `, ${root.party_label}` : ""}
        </h4>
        <span aria-hidden className={cn(
          "inline-grid place-items-center min-w-5 h-5 px-1 rounded-full text-label font-semibold",
          root.is_draft || root.state !== "open" ? "bg-white text-pen ring-1 ring-pen" : "bg-pen text-white",
        )}>{thread.pin}</span>
        <p>
          <b>{root.author_name ?? "Someone"}</b>
          {root.party_label && <> · {root.party_label}</>}
          {" · "}{formatDate(root.created_at)}{root.edited_at ? " · edited" : ""}
        </p>
        {root.anchor && (
          // The place as a link, as the prototype's card has it (IR-1139): it
          // goes to the passage, where the quote below does too.
          <button type="button" onClick={() => props.onShowInPaper(thread)}
            aria-label={`Go to page ${root.anchor.page} of v${root.anchor.version}`}
            className={cn("whitespace-nowrap font-semibold text-brand underline underline-offset-2 hover:text-brand-dark", FOCUS_RING)}>
            p. {root.anchor.page} · v{root.anchor.version}
          </button>
        )}
        {root.document && <DocumentPlace document={root.document} onShow={props.onShowDocument} />}
      </header>

      <div className="review-box-body space-y-2">
      <p className="flex flex-wrap items-center gap-1.5">
        {root.severity && (
          <Chip tone={root.severity === "must_fix" ? "brand" : "quiet"}>
            {root.severity === "must_fix" && <i className="fas fa-triangle-exclamation text-label" aria-hidden />}
            {SEVERITY_WORDS[root.severity]}
          </Chip>
        )}
        {root.is_draft
          ? <Chip><i className="fas fa-pen text-label" aria-hidden />Draft</Chip>
          : status && (
            <Chip tone={statusTone(root)}>
              {root.state === "open" && root.answer && (
                <i className={cn("fas text-label", ANSWER_ICON[root.answer.kind])} aria-hidden />
              )}
              {status}
            </Chip>
          )}
        {root.outdated_since != null && <Chip>Outdated since v{root.outdated_since}</Chip>}
        {root.document?.earlier && <Chip>From an earlier upload</Chip>}
      </p>

      {root.anchor && (
        <button
          type="button"
          onClick={() => props.onShowInPaper(thread)}
          aria-label={`Show in paper: “${root.anchor.quote}”`}
          className={cn("block w-full rounded-control bg-stone-100 px-3 py-2 text-left font-display text-small italic text-stone-800 hover:text-brand", now && "bg-pen-now", FOCUS_RING)}
        >
          “{root.anchor.quote}”
        </button>
      )}
      <WhereNow root={root} />
      {typeof root.not_followed?.message === "string" && (
        <p className="text-2xs text-stone-700">{root.not_followed.message}</p>
      )}
      {root.suggestion && <SuggestedWording root={root} />}

      <div className="text-small text-stone-800">
        <p className="text-justified whitespace-pre-wrap break-words">{root.body}</p>
        <MentionedPeople people={root.mentions} />
      </div>

      {root.state === "closed" && root.closed_reason && (
        <p className="text-small text-stone-700">Closed by the Decision: {root.closed_reason}</p>
      )}
      </div>

      {/* Replies, the authors' answer and what happened to the thread, in the
          order they happened (IR-1191), each row in the Conversation's shape
          (IR-1192). */}
      {history.length > 0 && (
        <ol aria-label="Replies and history" className="review-box-replies">
          {history.map((h) => {
            if (h.reply) {
              return <Reply key={h.key} reply={h.reply} recordId={id} canComment={props.can.has("comment_review")}
                onEdited={() => { props.threads.reload(); props.onChanged(); }} />;
            }
            if (h.answer) return <AnswerRow key={h.key} answer={h.answer} at={h.at} />;
            return (
              <li key={h.key} className="review-box-rep review-box-event">
                <span aria-hidden className="review-event-ic"><i className="fas fa-circle-info" /></span>
                <p className="text-2xs text-stone-600">{eventWords(h.event!)} · {formatDate(h.at)}</p>
              </li>
            );
          })}
        </ol>
      )}

      {(form !== null || error) && (
      <div className="review-box-body space-y-2 border-t border-stone-200">
      {form === "reply" && (
        <TextForm
          label="Reply" submitLabel="Reply" required busy={busy} savedReplies mentionsRecordId={id}
          hint="Posted now, not held with your review."
          onCancel={() => setForm(null)}
          onSubmit={(body, mentions) => act(() => recordsApi.postReviewComment(id, {
            body, reply_to: root.id, ...(mentions.length ? { mentions } : {}),
          }), "Your reply could not be sent.")}
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
      {error && <p role="alert" className="text-small text-brand">{error}</p>}
      </div>
      )}

      {form === null && anyAction && (
        <div className="review-box-foot flex flex-wrap gap-1.5" role="group" aria-label={`${pinWords(thread)} actions`}>
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
          {canReply && (
            // How many replies the thread has, on its Reply control (IR-1192).
            <Button size="sm" variant="ghost" onClick={() => setForm("reply")}
              aria-label={replies.length ? `Reply, ${replies.length} ${replies.length === 1 ? "reply" : "replies"}` : undefined}>
              Reply
              {replies.length > 0 && <span aria-hidden className="review-count ml-0">{replies.length}</span>}
            </Button>
          )}
          {root.can_post && (
            // One draft sent on its own, before *Finish review* (IR-1194).
            <Button size="sm" variant="outline" disabled={busy}
              onClick={() => act(() => recordsApi.postThread(id, root.id), "The draft could not be posted.")}>
              Post
            </Button>
          )}
          {root.can_delete && (
            <Button size="sm" variant="ghost" disabled={busy}
              onClick={() => act(() => recordsApi.deleteReviewComment(id, root.id), "The draft could not be discarded.")}>
              Discard
            </Button>
          )}
        </div>
      )}
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
  const check = root.wording_check;
  return (
    <section aria-labelledby={`${ids}-wording`} className="rounded-control bg-stone-50 px-2 py-1.5 space-y-0.5">
      <p id={`${ids}-wording`} className="text-2xs font-semibold text-stone-600">Suggested wording</p>
      <p className="text-justified text-small text-stone-900 whitespace-pre-wrap break-words">“{root.suggestion}”</p>
      {check && (
        <p className="text-2xs text-stone-700">
          {check.page != null
            ? `Suggested wording found on p. ${check.page} of v${check.version}.`
            : `Suggested wording not found in v${check.version}.`}
        </p>
      )}
    </section>
  );
}

type ThreadAnswer = NonNullable<ReviewComment["answer"]>;
type HistoryItem = {
  key: string;
  /** When it happened; null for an answer with no time, which goes last. */
  at: string | null;
  reply?: ReviewComment;
  answer?: ThreadAnswer;
  event?: NonNullable<ReviewComment["events"]>[number];
};

/**
 * A thread's replies, its answer and its events, oldest first (IR-1191). The
 * current answer is one row, at the time it was given: its own `at`, else the
 * latest "answered" event's, else last of all. That event is not listed
 * besides, so the answer is said once; an earlier answer, since replaced or
 * cleared, stays as its event line. A tie keeps a reply first.
 */
export function threadHistory(root: ReviewComment, replies: ReviewComment[]): HistoryItem[] {
  const events = root.events ?? [];
  const lastAnswered = root.answer ? events.map((e) => e.kind).lastIndexOf("answered") : -1;
  const answeredAt = root.answer ? root.answer.at ?? events[lastAnswered]?.at ?? null : null;
  const items: HistoryItem[] = [
    ...replies.map((r) => ({ key: `r${r.id}`, at: r.created_at, reply: r })),
    ...events.flatMap((e, i) => (i === lastAnswered ? [] : [{ key: `e${i}`, at: e.at, event: e }])),
    ...(root.answer ? [{ key: "answer", at: answeredAt, answer: root.answer }] : []),
  ];
  const time = (h: HistoryItem) => (h.at === null ? Infinity : Date.parse(h.at) || 0);
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

/**
 * The authors' answer as a row of the history (IR-1191). Still a formal act,
 * not a reply: it is told apart by its icon -- a check for Addressed, a cross
 * for Declined -- and its wording, not by colour alone.
 */
function AnswerRow({ answer, at }: { answer: ThreadAnswer; at: string | null }) {
  const addressed = answer.kind === "addressed";
  const who = answer.by ?? "The authors";
  return (
    <li className="review-box-rep review-box-answer">
      <span aria-hidden className="review-event-ic">
        <i className={cn("fas", ANSWER_ICON[answer.kind])} />
      </span>
      <div className="min-w-0">
        <p className="text-small text-stone-700">
          <b className="font-semibold text-stone-900">{who}</b>{" "}
          {addressed ? <>marked this <b className="font-semibold text-stone-900">Addressed</b></> : "declined this"}
          {at && <> <time dateTime={at} className="text-2xs text-stone-600">{formatDate(at)}</time></>}
        </p>
        <p className="text-justified whitespace-pre-wrap break-words text-small text-stone-800">
          {answer.note || <span className="italic text-stone-600">No answer given.</span>}
        </p>
      </div>
    </li>
  );
}

/**
 * A reply, in the Conversation's shape (IR-1192): an avatar, the writer, who
 * they are in this review as the server words it, and the date. Where the
 * server says the reply is the viewer's, a ⋯ menu at its far right offers Edit,
 * which swaps the text for a form in place.
 */
function Reply({ reply, recordId, canComment, onEdited }: {
  reply: ReviewComment; recordId: number; canComment: boolean; onEdited: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const who = reply.author_name ?? "Someone";
  const canEdit = canComment && reply.can_edit;
  const before = peopleIn(reply.mentions);

  const save = async (body: string, mentions: number[]) => {
    setBusy(true);
    setError(null);
    try {
      const changed = changedMentions(before, mentions);
      await recordsApi.editReviewComment(recordId, reply.id, changed ? { body, mentions: changed } : { body });
      setEditing(false);
      onEdited();
    } catch (err) {
      setError(errorDetail(err, "Your reply could not be saved."));
    } finally {
      setBusy(false);
    }
  };

  return (
    <li className="review-box-rep">
      <span aria-hidden className="review-avatar review-avatar-brand">{initials(reply.author_name)}</span>
      <div className="min-w-0">
        <div className="flex items-start gap-2">
          <p className="flex min-w-0 flex-1 flex-wrap items-center gap-x-1.5 gap-y-0.5 text-2xs text-stone-600">
            <span className="text-small font-semibold text-stone-900">{who}</span>
            {reply.party_label && <span className="review-label">{reply.party_label}</span>}
            <time dateTime={reply.created_at}>{formatDate(reply.created_at)}</time>
            {reply.edited_at && <span>· edited</span>}
          </p>
          {canEdit && !editing && (
            <RowMenu label={`Actions for ${who}'s reply`} compact
              items={[{ key: "edit", label: "Edit", onSelect: () => setEditing(true) }]} />
          )}
        </div>
        {editing ? (
          <TextForm
            label="Edit your reply" submitLabel="Save" required busy={busy}
            initial={reply.body} initialMentions={before} mentionsRecordId={recordId}
            onCancel={() => { setEditing(false); setError(null); }}
            onSubmit={save}
          />
        ) : (
          <>
            <p className="text-justified whitespace-pre-wrap break-words text-small text-stone-800">{reply.body}</p>
            <MentionedPeople people={reply.mentions} />
          </>
        )}
        {error && <p role="alert" className="text-small text-brand">{error}</p>}
      </div>
    </li>
  );
}

/**
 * Where a document thread points (IR-1204): its document and upload, as a link
 * that shows it in the reader. A slot's upload is served as a PDF, so another
 * stored type, or a page with no reader, names it without the link.
 */
function DocumentPlace({ document, onShow }: { document: ThreadDocument; onShow?: (document: ThreadDocument) => void }) {
  // A document's name can be long, so it wraps within the card (the Full Text Rule, IR-1218).
  const place = "min-w-0 break-words text-left font-semibold";
  if (!onShow || document.extension !== "pdf") return <span className={cn(place, "text-stone-700")}>{document.label}</span>;
  return (
    <button type="button" onClick={() => onShow(document)} aria-label={`Open ${document.label}`}
      className={cn(place, "text-brand underline underline-offset-2 hover:text-brand-dark", FOCUS_RING)}>
      {document.label}
    </button>
  );
}

function TextForm({ label, submitLabel, hint, required, busy, savedReplies, mentionsRecordId, initial = "", initialMentions, onSubmit, onCancel }: {
  label: string; submitLabel: string; hint?: string; required?: boolean; busy: boolean;
  /** Offer saved replies (IR-877): a reply is a comment; an answer's note is not. */
  savedReplies?: boolean;
  /** Offer mentions on this record (IR-877): a reply's, never an answer note's. */
  mentionsRecordId?: number;
  /** What an edit starts from (IR-1192). */
  initial?: string;
  initialMentions?: MentionedPerson[];
  onSubmit: (text: string, mentions: number[]) => void; onCancel: () => void;
}) {
  const id = useId();
  const [text, setText] = useState(initial);
  const [mentioned, setMentioned] = useState<MentionedPerson[]>(initialMentions ?? []);
  const ref = useRef<HTMLTextAreaElement>(null);
  useEffect(() => ref.current?.focus(), []);
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (text.trim() || !required) onSubmit(text.trim(), mentioned.map((p) => p.id));
  };
  return (
    <form onSubmit={submit} className="space-y-1.5">
      <label htmlFor={id} className={LABEL}>{label}</label>
      <textarea ref={ref} id={id} rows={3} value={text} onChange={(e) => setText(e.target.value)}
        aria-describedby={hint ? `${id}-hint` : undefined} className={fieldClasses(false)} />
      {hint && <p id={`${id}-hint`} className="text-2xs text-stone-600">{hint}</p>}
      {savedReplies && <SavedReplies textareaRef={ref} value={text} onChange={setText} />}
      {mentionsRecordId !== undefined && <MentionPicker recordId={mentionsRecordId} value={mentioned} onChange={setMentioned} />}
      <div className="flex justify-end gap-2">
        <Button type="button" size="sm" variant="secondary" onClick={onCancel} disabled={busy}>Cancel</Button>
        <Button type="submit" size="sm" disabled={busy || (required && !text.trim())}>{submitLabel}</Button>
      </div>
    </form>
  );
}

/**
 * Comment on a passage, or the record as a whole. Where `finish_review` is
 * granted the reviewer chooses its severity -- *Suggestion* unless they say
 * *Must fix* (decided for IR-875) -- and whether to **Post** it now, which
 * tells the authors, or **Save as draft** for their next *Finish review*
 * (ADR-032 §7 as amended 2026-11-16, IR-1194).
 */
function Composer({ recordId, can, target, onCompose, threads, onChanged }: ReviewThreadsProps & { target: CommentTarget }) {
  const ids = useId();
  const drafting = can.has("finish_review");
  const [body, setBody] = useState("");
  const [severity, setSeverity] = useState<ThreadSeverity>("suggestion");
  const [wording, setWording] = useState("");
  const [mentioned, setMentioned] = useState<MentionedPerson[]>([]);
  // Only a reviewer's thread on a passage carries wording (IR-876).
  const canSuggest = drafting && target.kind === "passage";
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const ref = useRef<HTMLTextAreaElement>(null);
  useEffect(() => ref.current?.focus(), [target]);

  const send = async (postNow: boolean) => {
    if (!body.trim() || busy) return;
    setBusy(true);
    setError(null);
    try {
      await recordsApi.postReviewComment(recordId, {
        body: body.trim(),
        kind: "thread",
        ...(drafting ? { severity, post_now: postNow } : {}),
        ...(canSuggest && wording.trim() ? { suggestion: wording.trim() } : {}),
        ...(mentioned.length ? { mentions: mentioned.map((p) => p.id) } : {}),
        ...(target.kind === "passage" ? {
          anchor: {
            version: target.version, page: target.passage.page, quote: target.passage.quote,
            prefix: target.passage.prefix, suffix: target.passage.suffix, regions: target.passage.regions,
          },
        } : {}),
        ...(target.kind === "document" ? { document: target.upload } : {}),
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
  // Enter, or the primary button, posts: the comment is meant to be read.
  const submit = (e: FormEvent) => {
    e.preventDefault();
    void send(true);
  };

  return (
    <form onSubmit={submit} aria-label="New comment" className="rounded-control border border-stone-300 bg-white p-3 space-y-2">
      <p className="text-2xs text-stone-600">
        {target.kind === "passage"
          ? <>Comment on <b className="text-stone-800">p.{target.passage.page}</b> of v{target.version}</>
          : target.kind === "document"
            ? <>Comment on <b className="text-stone-800">{target.label}</b></>
            : "Comment on the record as a whole"}
      </p>
      {target.kind === "passage" && (
        <blockquote className="border-l-2 border-brand/40 pl-2 text-small italic text-stone-700">“{target.passage.quote}”</blockquote>
      )}
      <label htmlFor={`${ids}-body`} className="sr-only">Comment</label>
      <textarea ref={ref} id={`${ids}-body`} rows={3} value={body} onChange={(e) => setBody(e.target.value)}
        placeholder="What should the authors look at here?" className={fieldClasses(false)} />
      <SavedReplies textareaRef={ref} value={body} onChange={setBody} />
      <MentionPicker recordId={recordId} value={mentioned} onChange={setMentioned} />
      {drafting && (
        <fieldset className="flex flex-wrap items-center gap-3">
          <legend className="sr-only">Severity</legend>
          {(["must_fix", "suggestion"] as const).map((s) => (
            <label key={s} className="inline-flex items-center gap-1.5 text-small text-stone-800 min-h-11 reading-split:min-h-9">
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
            The text you&rsquo;d put in its place. You can change it while the comment is a draft.
          </p>
        </div>
      )}
      {error && <p role="alert" className="text-small text-brand">{error}</p>}
      <div className="flex justify-end gap-2">
        <Button type="button" size="sm" variant="secondary" onClick={() => onCompose(null)} disabled={busy}>Cancel</Button>
        {drafting && (
          <Button type="button" size="sm" variant="outline" disabled={busy || !body.trim()} onClick={() => void send(false)}>
            Save as draft
          </Button>
        )}
        <Button type="submit" size="sm" disabled={busy || !body.trim()}>{drafting ? "Post" : "Comment"}</Button>
      </div>
      {drafting && (
        <p className="text-2xs text-stone-600">
          Post sends it now and tells the authors. A draft is seen only by you until you send it or finish your review.
        </p>
      )}
    </form>
  );
}
