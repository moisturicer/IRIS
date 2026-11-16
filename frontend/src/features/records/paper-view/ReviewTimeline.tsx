import { useEffect, useId, useRef, useState, type FormEvent, type ReactNode } from "react";
import { createPortal } from "react-dom";

import { recordsApi } from "@/api/records";
import { ClearanceStrip } from "@/components/shared/ClearanceStrip";
import { Button } from "@/components/ui";
import { LABEL, LOAD_ERROR, fieldClasses } from "@/components/ui/fieldClasses";
import { FOCUS_RING } from "@/components/ui/interaction";
import { errorDetail } from "@/lib/errorDetail";
import { isRequestTimeout } from "@/api/requestPolicy";
import { cn, formatDate } from "@/lib/utils";
import { useAuthStore } from "@/store/auth.store";
import { RowMenu } from "@/features/accounts/RowMenu";
import type { ClearanceStripEntry, MentionedPerson, RecordTracker, ReviewComment } from "@/types/records";

import { initials } from "./commentThreads";
import { ReviewStatus, turnLine } from "./ReviewStatus";
import { MentionPicker, MentionedPeople, changedMentions, peopleIn } from "./Mentions";
import { SavedReplies } from "./SavedReplies";
import { timelineEntries, type TimelineEntry, type TimelineKind } from "./timelineEntries";

/** The submission, drawn as the first box of the timeline, as a pull request opens with its description. */
export interface TimelineSubmission {
  /** Who submitted v1, as the server names them. */
  author: string | null;
  at: string | null;
  abstract: string;
}

/** A glyph per kind of entry, beside its words, never instead of them. */
const KIND_ICON: Record<TimelineKind, string> = {
  routing: "fa-route",
  review: "fa-clipboard-check",
  revision: "fa-arrow-rotate-left",
  revision_resolved: "fa-paper-plane",
  document_request: "fa-file-circle-plus",
  version: "fa-code-commit",
  reassignment: "fa-people-arrows",
  extension: "fa-calendar-plus",
  published: "fa-globe",
  comment: "fa-note-sticky",
  thread: "fa-comment-dots",
};

/** What the review discussion lets this viewer do (IR-419). */
interface Discussion {
  /** The server offers `comment_review`: comment and reply. */
  canComment: boolean;
  /** Whose review discussion this is: the mention picker asks who takes part (IR-877). */
  recordId: number;
  post: (body: string, replyTo: number | undefined, mentions: number[]) => Promise<void>;
  /**
   * `mentions`, when given, replaces whom the comment mentions; someone new is
   * notified once. Left out, they stay as they are.
   */
  edit: (commentId: number, body: string, mentions?: number[]) => Promise<void>;
}

/**
 * The Review section's timeline (IR-412; spec §4.7): what has happened in the
 * review, oldest first, each entry saying who did what, as which party, and
 * when. Built from `GET /records/<id>/tracker/` alone (`timelineEntries.ts`).
 *
 * The history marks nothing as current: where the review stands now is
 * `ReviewStatus`'s, drawn above it from the same tracker read (IR-624), and
 * the history never renders a party -- Intake included, which ADR-032
 * retires -- as the present step.
 *
 * **The review discussion** (IR-419; ADR-032 §7) is part of it: comments sit
 * among the other entries, replies under the comment they answer, and the
 * composer is at the bottom, as on a pull request. A comment here is
 * discussion: it posts at once, whoever writes it, and never becomes a review
 * thread (ADR-032 §7 as amended 2026-11-16, IR-1194). Threads are Threads':
 * here a finished review, or a thread sent outside one, is one line pointing
 * there (`onOpenThreads`). Commenting is offered only under `comment_review`;
 * the ⋯ menu's Edit only on a comment the server says is the viewer's. After
 * a comment is sent the tracker is read again, so the timeline shows what the
 * server stored, never a guess at it.
 *
 * The host remounts it (a new `key`) when something it shows has changed.
 *
 * **Its look** (IR-1131) follows a pull request's page: an optional first box
 * for the submission, each comment a box with its replies inside it and a
 * reply field in its foot, every other entry one line with a round badge on
 * the same rail, an optional box saying where the review stands, and the
 * composer as a box. Every word in them is still the server's.
 */
export function ReviewTimeline({
  recordId, canComment = false, statusTarget, renderStatus, beforeComment, onCommented, submission, statusBox = false, onLoaded,
  onOpenThreads,
}: {
  recordId: number;
  canComment?: boolean;
  /** Show Threads, at one thread when given: a line here links there (IR-1194). Left out, no link. */
  onOpenThreads?: (thread?: number) => void;
  /** A comment was posted: the Threads tab reads its threads again (IR-875). */
  onCommented?: () => void;
  /** Move the status to the workspace sidebar, sharing this tracker read. */
  statusTarget?: HTMLElement | null;
  /** What the sidebar draws from this read; the party status strip by default. */
  renderStatus?: (data: RecordTracker) => ReactNode;
  /** Between the timeline and the comment box: the workspace's Readiness (IR-681). */
  beforeComment?: ReactNode;
  /** The submission's box, first; its "v1 submitted" line is then not repeated. */
  submission?: TimelineSubmission;
  /** Draw where the review stands, from `clearance_strip`, after the timeline. */
  statusBox?: boolean;
  /** Each tracker read, so the host can count the conversation for its tab. */
  onLoaded?: (data: RecordTracker) => void;
}) {
  const headingId = useId();
  const [data, setData] = useState<RecordTracker | null>(null);
  /** Why the read failed (IR-906): a timeout offers Retry, anything else Try again. */
  const [failed, setFailed] = useState<"failed" | "interrupted" | null>(null);
  const [attempt, setAttempt] = useState(0);
  const loadedRef = useRef(onLoaded);
  loadedRef.current = onLoaded;
  const viewer = useAuthStore((s) => s.user);
  const viewerName = viewer ? `${viewer.first_name} ${viewer.last_name}`.trim() : "";

  useEffect(() => {
    let cancelled = false;
    setFailed(null);
    recordsApi
      .tracker(recordId)
      .then(({ data: payload }) => {
        if (cancelled) return;
        setData(payload);
        loadedRef.current?.(payload);
      })
      .catch((error: unknown) => {
        if (!cancelled) setFailed(isRequestTimeout(error) ? "interrupted" : "failed");
      });
    return () => {
      cancelled = true;
    };
  }, [recordId, attempt]);

  const reread = () => setAttempt((n) => n + 1);
  const discussion: Discussion = {
    canComment,
    recordId,
    post: async (body, replyTo, mentions) => {
      // A new comment here is discussion; a reply takes its comment's kind.
      await recordsApi.postReviewComment(recordId, {
        body,
        ...(replyTo === undefined ? { kind: "discussion" as const } : { reply_to: replyTo }),
        ...(mentions.length ? { mentions } : {}),
      });
      onCommented?.();
      reread();
    },
    edit: async (commentId, body, mentions) => {
      await recordsApi.editReviewComment(recordId, commentId, mentions === undefined ? { body } : { body, mentions });
      reread();
    },
  };

  // The submission's own box says it was submitted; its line would repeat it.
  const entries = data ? timelineEntries(data).filter((e) => !(submission && e.key === "version-1")) : [];

  return (
    <div className="space-y-6">
      {data && !failed && (statusTarget === undefined
        ? <ReviewStatus data={data} />
        : statusTarget && createPortal(renderStatus ? renderStatus(data) : <ReviewStatus data={data} />, statusTarget))}
      <section aria-labelledby={headingId} className="space-y-4">
        <h3 id={headingId} className="sr-only">Timeline</h3>

        {failed ? (
          <div className="space-y-2">
            <p role="alert" className="text-small text-stone-700">
              {failed === "interrupted" ? "The review timeline took too long to load." : "Could not load the review timeline."}
            </p>
            <button
              type="button"
              onClick={reread}
              className={cn("text-small font-semibold text-brand hover:underline min-h-11", FOCUS_RING)}
            >
              {failed === "interrupted" ? "Retry" : "Try again"}
            </button>
          </div>
        ) : !data ? (
          <div role="status">
            <span className="sr-only">Loading the review timeline…</span>
            <div aria-hidden className="space-y-3">
              {[0, 1, 2].map((i) => (
                <div key={i} className="h-10 rounded-control bg-stone-100 animate-pulse motion-reduce:animate-none" />
              ))}
            </div>
          </div>
        ) : (
          <>
            {data.routing_recorded_from && (
              <p className="text-2xs text-stone-600">
                Routing recorded from {formatDate(data.routing_recorded_from)}.
              </p>
            )}
            <div className="review-rail">
              {submission && <SubmissionBox submission={submission} />}
              {entries.length === 0 ? (
                !submission && <p className="text-small text-stone-600">Nothing has happened in this review yet.</p>
              ) : (
                <ol aria-label="Review timeline" className="review-tl">
                  {entries.map((entry) => (
                    <TimelineItem key={entry.key} entry={entry} discussion={discussion} onOpenThreads={onOpenThreads} />
                  ))}
                </ol>
              )}
            </div>
            {statusBox && <StatusBox data={data} />}
            {beforeComment}
            {canComment && (
              <div className="review-composer">
                {viewerName ? <Avatar name={viewerName} large /> : <span aria-hidden />}
                <CommentForm
                  label="Comment"
                  submitLabel="Comment"
                  recordId={recordId}
                  onSubmit={(body, mentions) => discussion.post(body, undefined, mentions)}
                  clearOnSuccess
                  boxed
                />
              </div>
            )}
          </>
        )}
      </section>
    </div>
  );
}

/** A person's initials in a round chip. Decorative: their name is always written beside it. */
function Avatar({ name, large = false }: { name: string | null; large?: boolean }) {
  return <span aria-hidden className={cn("review-avatar", large && "review-avatar-lg")}>{initials(name)}</span>;
}

/** The submission, as a pull request opens with its description: who, when, and the abstract. */
function SubmissionBox({ submission }: { submission: TimelineSubmission }) {
  const who = submission.author ?? "The authors";
  return (
    <div className="review-tl-cmt">
      <Avatar name={submission.author} large />
      <article className="review-box" aria-label={`Submission by ${who}`}>
        <header className="review-box-head">
          <p>
            <b>{who}</b>{" "}
            submitted v1{submission.at && <> · <time dateTime={submission.at}>{formatDate(submission.at)}</time></>}
          </p>
        </header>
        {submission.abstract.trim() && (
          <div className="review-box-body">
            <p className="review-abstract whitespace-pre-wrap break-words">{submission.abstract}</p>
          </div>
        )}
      </article>
    </div>
  );
}

/**
 * Where the review stands, after the timeline, like the box at the end of a
 * pull request: one line, the server's turn line, and every office's
 * clearance folded under it. The tone follows the strip's kinds; every word
 * is the server's (`turnLine`, `clearance_strip`).
 */
function StatusBox({ data }: { data: RecordTracker }) {
  const id = useId();
  const strip: ClearanceStripEntry[] = Array.isArray(data.clearance_strip) ? data.clearance_strip : [];
  if (strip.length === 0) return null;
  const tone = strip.some((e) => e.kind === "revision" || e.kind === "not_cleared")
    ? { name: "attention", icon: "fa-rotate-left" }
    : strip.every((e) => e.kind === "cleared" || e.kind === "kept")
      ? { name: "settled", icon: "fa-check" }
      : { name: "active", icon: "fa-hourglass-half" };
  const line = turnLine(data);
  return (
    <section aria-labelledby={id} className="review-mbox">
      <div className="review-mbox-head">
        <span aria-hidden className={cn("review-mb-ic", tone.name)}><i className={cn("fas", tone.icon)} /></span>
        <div className="min-w-0">
          <h3 id={id}>{line}</h3>
          {line !== data.workflow_state_label && <p className="text-2xs text-stone-600">{data.workflow_state_label}</p>}
        </div>
      </div>
      <details className="review-mbox-list">
        <summary className={FOCUS_RING}><i className="fas fa-chevron-right text-3xs" aria-hidden />Show all clearances</summary>
        <ClearanceStrip entries={strip} className="flex-col !items-start gap-y-2 px-[14px] pb-3" />
      </details>
    </section>
  );
}

function TimelineItem({ entry, discussion, onOpenThreads }: {
  entry: TimelineEntry; discussion: Discussion; onOpenThreads?: (thread?: number) => void;
}) {
  if (entry.comment) return <CommentItem entry={entry} thread={entry.comment} discussion={discussion} />;
  const byline = [entry.actor, entry.party].filter(Boolean) as string[];

  // Every other entry: one line on the rail, with a round badge.
  return (
    <li className="review-tl-ev">
      <span aria-hidden className="review-badge"><i className={cn("fas", KIND_ICON[entry.kind])} /></span>
      <div className="min-w-0">
        <div className="flex items-baseline gap-x-2 gap-y-1 flex-wrap">
          <p className="text-small font-semibold text-stone-900">{entry.act}</p>
          {entry.status && (
            <span className="px-1.5 py-0.5 rounded-control bg-stone-100 text-2xs font-semibold text-stone-700">
              {entry.status}
            </span>
          )}
          <VersionTag version={entry.version} />
        </div>
        <p className="text-2xs text-stone-600 mt-0.5">
          {byline.map((part, i) => (
            <span key={i} className={cn(i === 0 && entry.actor && "font-semibold text-stone-700")}>
              {i > 0 && " · "}
              {part}
            </span>
          ))}
          {byline.length > 0 && " · "}
          {entry.at ? <time dateTime={entry.at}>{formatDate(entry.at)}</time> : "Date not recorded"}
        </p>
        {entry.note && (
          <p className="text-small text-stone-700 leading-relaxed mt-1 break-words">“{entry.note}”</p>
        )}
        {/* By position: two items can read the same (one label, one state). */}
        {entry.details.map((line, i) => (
          <p key={i} className="text-2xs text-stone-600 mt-0.5 break-words">
            {line}
          </p>
        ))}
        {entry.toThreads && onOpenThreads && (
          <button type="button" onClick={() => onOpenThreads(entry.toThreads?.thread)}
            aria-label={`View ${entry.toThreads.name} in Threads`}
            className={cn("text-small font-semibold text-brand hover:underline min-h-11 reading-split:min-h-9", FOCUS_RING)}>
            View in Threads
          </button>
        )}
      </div>
    </li>
  );
}

/**
 * A comment as a box (IR-1131): who wrote it, what they did and when, the
 * party as a small tag, the text, its replies inside the box, and a reply
 * field in its foot for a viewer who may comment.
 */
function CommentItem({ entry, thread, discussion }: {
  entry: TimelineEntry;
  thread: NonNullable<TimelineEntry["comment"]>;
  discussion: Discussion;
}) {
  const [replying, setReplying] = useState(false);
  const [editing, setEditing] = useState(false);
  const replyLabel = entry.actor ? `Reply to ${entry.actor}` : "Reply to this comment";
  const who = entry.actor ?? "Someone";

  return (
    <li className="review-tl-cmt">
      <Avatar name={entry.actor} large />
      <article className="review-box" aria-label={`Comment by ${who}`}>
        <header className="review-box-head">
          <p>
            <b>{who}</b>{" "}
            {entry.act.charAt(0).toLowerCase() + entry.act.slice(1)}{" "}
            {entry.at ? <time dateTime={entry.at}>{formatDate(entry.at)}</time> : "· date not recorded"}
            {thread.root.edited_at && " · Edited"}{" "}
            <VersionTag version={entry.version} />
          </p>
          <div className="flex shrink-0 items-center gap-2">
            {entry.party && <span className="review-label">{entry.party}</span>}
            {!editing && <EditMenu comment={thread.root} discussion={discussion} name={`${who}'s comment`} onEdit={() => setEditing(true)} />}
          </div>
        </header>
        <div className="review-box-body">
          <EditableComment comment={thread.root} discussion={discussion} editing={editing} onDone={() => setEditing(false)} />
        </div>
        {thread.replies.length > 0 && (
          <ol aria-label={entry.actor ? `Replies to ${entry.actor}` : "Replies"} className="review-box-replies">
            {thread.replies.map((reply) => (
              <Reply key={reply.id} reply={reply} discussion={discussion} />
            ))}
          </ol>
        )}
        {discussion.canComment && (
          <div className="review-box-foot">
            {replying ? (
              <CommentForm
                label={replyLabel}
                submitLabel="Send reply"
                recordId={discussion.recordId}
                onSubmit={async (body, mentions) => {
                  await discussion.post(body, thread.root.id, mentions);
                  setReplying(false);
                }}
                onCancel={() => setReplying(false)}
              />
            ) : (
              <button type="button" aria-label={replyLabel} onClick={() => setReplying(true)}
                className={cn("review-reply-field", FOCUS_RING)}>
                {replyLabel}…
              </button>
            )}
          </div>
        )}
      </article>
    </li>
  );
}

/** A reply, inside the box of the comment it answers. Threads are one level deep. */
function Reply({ reply, discussion }: { reply: ReviewComment; discussion: Discussion }) {
  const [editing, setEditing] = useState(false);
  const who = reply.author_name ?? "Someone";
  return (
    <li className="review-box-rep">
      <Avatar name={reply.author_name} />
      <div className="min-w-0">
        <div className="flex items-start gap-2">
          <p className="min-w-0 flex-1 text-2xs text-stone-600">
            {reply.author_name && <span className="font-semibold text-stone-900">{reply.author_name}</span>}
            {reply.party_label && <> <span className="review-label">{reply.party_label}</span></>}
            {reply.author_name && " · "}
            <time dateTime={reply.created_at}>{formatDate(reply.created_at)}</time>
            {reply.edited_at && " · Edited"}{" "}
            <VersionTag version={reply.version} />
          </p>
          {!editing && <EditMenu comment={reply} discussion={discussion} name={`${who}'s reply`} onEdit={() => setEditing(true)} />}
        </div>
        <EditableComment comment={reply} discussion={discussion} editing={editing} onDone={() => setEditing(false)} />
      </div>
    </li>
  );
}

/** The ⋯ menu on the viewer's own comment or reply, where the server says it is theirs (IR-1194). */
function EditMenu({ comment, discussion, name, onEdit }: {
  comment: ReviewComment; discussion: Discussion; name: string; onEdit: () => void;
}) {
  if (!discussion.canComment || !comment.can_edit) return null;
  return <RowMenu label={`Actions for ${name}`} compact items={[{ key: "edit", label: "Edit", onSelect: onEdit }]} />;
}

/** What someone wrote, or -- while its writer edits it -- the form, in place. */
function EditableComment({ comment, discussion, editing, onDone }: {
  comment: ReviewComment;
  discussion: Discussion;
  editing: boolean;
  onDone: () => void;
}) {
  const before = peopleIn(comment.mentions);

  if (editing) {
    return (
      <CommentForm
        label="Edit your comment"
        submitLabel="Save"
        initial={comment.body}
        initialMentions={before}
        recordId={discussion.recordId}
        onSubmit={async (body, mentions) => {
          await discussion.edit(comment.id, body, changedMentions(before, mentions));
          onDone();
        }}
        onCancel={onDone}
      />
    );
  }
  return (
    <>
      <CommentBody body={comment.body} />
      <MentionedPeople people={comment.mentions} />
    </>
  );
}

function VersionTag({ version }: { version: number | null }) {
  if (version === null) return null;
  return (
    <span className="px-1.5 py-0.5 rounded-control ring-1 ring-stone-200 text-2xs font-semibold text-stone-700 tabular-nums">
      <span className="sr-only">Made against </span>v{version}
    </span>
  );
}

/** What someone wrote, verbatim, as plain text with its line breaks. */
function CommentBody({ body }: { body: string }) {
  return <p className="text-small text-stone-800 leading-relaxed mt-1 whitespace-pre-wrap break-words">{body}</p>;
}

interface CommentFormProps {
  label: string;
  submitLabel: string;
  initial?: string;
  /** Whose review discussion: whom the box may mention (IR-877). */
  recordId: number;
  /** An edit starts from whom the comment already mentions. */
  initialMentions?: MentionedPerson[];
  onSubmit: (body: string, mentions: number[]) => Promise<void>;
  onCancel?: () => void;
  /** Empty the box once the server has it (the composer, not an edit). */
  clearOnSuccess?: boolean;
  /** Drawn as a box: the label in its head, the field in its body, the controls in its foot (IR-1131). */
  boxed?: boolean;
}

/**
 * A comment being written: the composer, a reply, or an edit. A refusal is
 * the server's own words, and what was written stays in the box.
 */
function CommentForm({
  label, submitLabel, initial = "", recordId, initialMentions = [], onSubmit, onCancel, clearOnSuccess, boxed = false,
}: CommentFormProps) {
  const id = useId();
  const [body, setBody] = useState(initial);
  const [mentioned, setMentioned] = useState<MentionedPerson[]>(initialMentions);
  const [error, setError] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  const ready = body.trim() !== "";
  const ref = useRef<HTMLTextAreaElement>(null);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!ready || sending) return;
    setError(null);
    setSending(true);
    try {
      await onSubmit(body.trim(), mentioned.map((p) => p.id));
      if (clearOnSuccess) {
        setBody("");
        setMentioned([]);
      }
    } catch (err) {
      setError(`${errorDetail(err, "Your comment could not be sent. Please try again.")} What you wrote is kept.`);
    } finally {
      setSending(false);
    }
  };

  const field = (
    <textarea
      ref={ref}
      id={id}
      rows={3}
      value={body}
      onChange={(e) => setBody(e.target.value)}
      className={fieldClasses(false)}
    />
  );
  const alert = error && (
    <p role="alert" className={LOAD_ERROR}>
      <i className="fas fa-circle-exclamation mt-0.5" aria-hidden />
      {error}
    </p>
  );
  const buttons = (
    <div className="flex justify-end gap-2">
      {onCancel && (
        <Button type="button" variant="secondary" onClick={onCancel} disabled={sending}>
          Cancel
        </Button>
      )}
      <Button type="submit" disabled={!ready} loading={sending}>
        {submitLabel}
      </Button>
    </div>
  );

  if (boxed) {
    return (
      <form onSubmit={submit} noValidate className="review-box">
        <div className="review-box-head">
          <label htmlFor={id} className="font-semibold text-stone-900">{label}</label>
        </div>
        <div className="review-box-body space-y-2">
          {field}
          <SavedReplies textareaRef={ref} value={body} onChange={setBody} />
          <MentionPicker recordId={recordId} value={mentioned} onChange={setMentioned} />
          {alert}
        </div>
        <div className="review-box-foot">{buttons}</div>
      </form>
    );
  }

  return (
    <form onSubmit={submit} noValidate className="mt-3 space-y-2">
      <label htmlFor={id} className={LABEL}>
        {label}
      </label>
      {field}
      <SavedReplies textareaRef={ref} value={body} onChange={setBody} />
      <MentionPicker recordId={recordId} value={mentioned} onChange={setMentioned} />
      {alert}
      {buttons}
    </form>
  );
}
