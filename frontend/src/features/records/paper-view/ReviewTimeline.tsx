import { useEffect, useId, useState, type FormEvent, type ReactNode } from "react";
import { createPortal } from "react-dom";

import { recordsApi } from "@/api/records";
import { Button } from "@/components/ui";
import { LABEL, LOAD_ERROR, fieldClasses } from "@/components/ui/fieldClasses";
import { FOCUS_RING } from "@/components/ui/interaction";
import { errorDetail } from "@/lib/errorDetail";
import { cn, formatDate } from "@/lib/utils";
import type { RecordTracker, ReviewComment } from "@/types/records";

import { RailHeading } from "./headings";
import { ReviewStatus } from "./ReviewStatus";
import { timelineEntries, type TimelineEntry, type TimelineKind } from "./timelineEntries";

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
  comment: "fa-comment",
};

/** What the review discussion lets this viewer do (IR-419). */
interface Discussion {
  /** The server offers `comment_review`: comment and reply. */
  canComment: boolean;
  post: (body: string, replyTo?: number) => Promise<void>;
  edit: (commentId: number, body: string) => Promise<void>;
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
 * composer is at the bottom, as on a pull request. It is offered only under
 * `comment_review`; Edit only on a comment the server says is the viewer's.
 * After a comment is sent the tracker is read again, so the timeline shows
 * what the server stored, never a guess at it.
 *
 * The host remounts it (a new `key`) when something it shows has changed.
 */
export function ReviewTimeline({ recordId, canComment = false, statusTarget }: {
  recordId: number;
  canComment?: boolean;
  /** Move the existing status to the workspace sidebar, sharing this tracker read. */
  statusTarget?: HTMLElement | null;
}) {
  const headingId = useId();
  const [data, setData] = useState<RecordTracker | null>(null);
  const [failed, setFailed] = useState(false);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setFailed(false);
    recordsApi
      .tracker(recordId)
      .then(({ data: payload }) => {
        if (!cancelled) setData(payload);
      })
      .catch(() => {
        if (!cancelled) setFailed(true);
      });
    return () => {
      cancelled = true;
    };
  }, [recordId, attempt]);

  const reread = () => setAttempt((n) => n + 1);
  const discussion: Discussion = {
    canComment,
    post: async (body, replyTo) => {
      await recordsApi.postReviewComment(recordId, replyTo === undefined ? { body } : { body, reply_to: replyTo });
      reread();
    },
    edit: async (commentId, body) => {
      await recordsApi.editReviewComment(recordId, commentId, { body });
      reread();
    },
  };

  const entries = data ? timelineEntries(data) : [];

  return (
    <div className="space-y-6">
      {data && !failed && (statusTarget === undefined
        ? <ReviewStatus data={data} />
        : statusTarget && createPortal(<ReviewStatus data={data} />, statusTarget))}
      <section aria-labelledby={headingId} className="space-y-3">
        <RailHeading id={headingId}>Timeline</RailHeading>

        {failed ? (
          <div className="space-y-2">
            <p role="alert" className="text-small text-stone-700">
              Could not load the review timeline.
            </p>
            <button
              type="button"
              onClick={reread}
              className={cn("text-small font-semibold text-brand hover:underline min-h-11", FOCUS_RING)}
            >
              Try again
            </button>
          </div>
        ) : !data ? (
          <div aria-hidden className="space-y-3">
            {[0, 1, 2].map((i) => (
              <div key={i} className="h-10 rounded-lg bg-stone-100 animate-pulse motion-reduce:animate-none" />
            ))}
          </div>
        ) : (
          <>
            {data.routing_recorded_from && (
              <p className="text-2xs text-stone-600">
                Routing recorded from {formatDate(data.routing_recorded_from)}.
              </p>
            )}
            {entries.length === 0 ? (
              <p className="text-small text-stone-600">Nothing has happened in this review yet.</p>
            ) : (
              <ol aria-label="Review timeline" className="relative space-y-4 border-l border-stone-200 ml-2">
                {entries.map((entry) => (
                  <TimelineItem key={entry.key} entry={entry} discussion={discussion} />
                ))}
              </ol>
            )}
            {canComment && (
              <CommentForm
                label="Comment"
                submitLabel="Comment"
                onSubmit={(body) => discussion.post(body)}
                clearOnSuccess
              />
            )}
          </>
        )}
      </section>
    </div>
  );
}

function TimelineItem({ entry, discussion }: { entry: TimelineEntry; discussion: Discussion }) {
  const byline = [entry.actor, entry.party].filter(Boolean) as string[];
  const thread = entry.comment;
  const [replying, setReplying] = useState(false);
  const replyLabel = entry.actor ? `Reply to ${entry.actor}` : "Reply to this comment";

  return (
    <li className="relative pl-6">
      <span
        aria-hidden
        className="absolute -left-3 top-0 w-6 h-6 rounded-full bg-white ring-1 ring-stone-200 flex items-center justify-center"
      >
        <i className={cn("fas text-2xs text-stone-600", KIND_ICON[entry.kind])} />
      </span>
      <div className="flex items-baseline gap-x-2 gap-y-1 flex-wrap">
        <p className="text-small font-semibold text-stone-900">{entry.act}</p>
        {entry.status && (
          <span className="px-1.5 py-0.5 rounded bg-stone-100 text-2xs font-semibold text-stone-700">
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
        {thread?.root.edited_at && " · Edited"}
      </p>

      {thread ? (
        <EditableComment
          comment={thread.root}
          discussion={discussion}
          action={<TextAction label="Reply" name={replyLabel} onClick={() => setReplying(true)} />}
        />
      ) : (
        entry.note && (
          <p className="text-small text-stone-700 leading-relaxed mt-1 break-words">“{entry.note}”</p>
        )
      )}
      {/* By position: two items can read the same (one label, one state). */}
      {entry.details.map((line, i) => (
        <p key={i} className="text-2xs text-stone-600 mt-0.5 break-words">
          {line}
        </p>
      ))}

      {thread && thread.replies.length > 0 && (
        <ol
          aria-label={entry.actor ? `Replies to ${entry.actor}` : "Replies"}
          className="mt-3 space-y-3 border-l border-stone-200 pl-4"
        >
          {thread.replies.map((reply) => (
            <Reply key={reply.id} reply={reply} discussion={discussion} />
          ))}
        </ol>
      )}

      {thread && replying && (
        <CommentForm
          label={replyLabel}
          submitLabel="Send reply"
          onSubmit={async (body) => {
            await discussion.post(body, thread.root.id);
            setReplying(false);
          }}
          onCancel={() => setReplying(false)}
        />
      )}
    </li>
  );
}

/** A reply, under the comment it answers. Threads are one level deep. */
function Reply({ reply, discussion }: { reply: ReviewComment; discussion: Discussion }) {
  return (
    <li>
      <p className="text-2xs text-stone-600">
        {reply.author_name && <span className="font-semibold text-stone-700">{reply.author_name}</span>}
        {reply.author_name && " · "}
        <time dateTime={reply.created_at}>{formatDate(reply.created_at)}</time>
        {reply.edited_at && " · Edited"}{" "}
        <VersionTag version={reply.version} />
      </p>
      <EditableComment comment={reply} discussion={discussion} />
    </li>
  );
}

/**
 * What someone wrote, and -- to a viewer who may comment -- `action` (Reply,
 * on a comment that starts a thread) and Edit, where the server says the
 * comment is theirs. Editing swaps the text for the form in place.
 */
function EditableComment({
  comment,
  discussion,
  action,
}: {
  comment: ReviewComment;
  discussion: Discussion;
  action?: ReactNode;
}) {
  const [editing, setEditing] = useState(false);
  const canEdit = discussion.canComment && comment.can_edit;

  if (editing) {
    return (
      <CommentForm
        label="Edit your comment"
        submitLabel="Save"
        initial={comment.body}
        onSubmit={async (body) => {
          await discussion.edit(comment.id, body);
          setEditing(false);
        }}
        onCancel={() => setEditing(false)}
      />
    );
  }
  return (
    <>
      <CommentBody body={comment.body} />
      {discussion.canComment && (action || canEdit) && (
        <div className="flex gap-3 mt-1">
          {action}
          {canEdit && <TextAction label="Edit" name="Edit your comment" onClick={() => setEditing(true)} />}
        </div>
      )}
    </>
  );
}

function VersionTag({ version }: { version: number | null }) {
  if (version === null) return null;
  return (
    <span className="px-1.5 py-0.5 rounded ring-1 ring-stone-200 text-2xs font-semibold text-stone-700 tabular-nums">
      <span className="sr-only">Made against </span>v{version}
    </span>
  );
}

/** What someone wrote, verbatim, as plain text with its line breaks. */
function CommentBody({ body }: { body: string }) {
  return <p className="text-small text-stone-800 leading-relaxed mt-1 whitespace-pre-wrap break-words">{body}</p>;
}

function TextAction({ label, name, onClick }: { label: string; name: string; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={name}
      className={cn("text-small font-semibold text-brand hover:underline min-h-11", FOCUS_RING)}
    >
      {label}
    </button>
  );
}

interface CommentFormProps {
  label: string;
  submitLabel: string;
  initial?: string;
  onSubmit: (body: string) => Promise<void>;
  onCancel?: () => void;
  /** Empty the box once the server has it (the composer, not an edit). */
  clearOnSuccess?: boolean;
}

/**
 * A comment being written: the composer, a reply, or an edit. A refusal is
 * the server's own words, and what was written stays in the box.
 */
function CommentForm({ label, submitLabel, initial = "", onSubmit, onCancel, clearOnSuccess }: CommentFormProps) {
  const id = useId();
  const [body, setBody] = useState(initial);
  const [error, setError] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  const ready = body.trim() !== "";

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!ready || sending) return;
    setError(null);
    setSending(true);
    try {
      await onSubmit(body.trim());
      if (clearOnSuccess) setBody("");
    } catch (err) {
      setError(`${errorDetail(err, "Your comment could not be sent. Please try again.")} What you wrote is kept.`);
    } finally {
      setSending(false);
    }
  };

  return (
    <form onSubmit={submit} noValidate className="mt-3 space-y-2">
      <label htmlFor={id} className={LABEL}>
        {label}
      </label>
      <textarea
        id={id}
        rows={3}
        value={body}
        onChange={(e) => setBody(e.target.value)}
        className={fieldClasses(false)}
      />
      {error && (
        <p role="alert" className={LOAD_ERROR}>
          <i className="fas fa-circle-exclamation mt-0.5" aria-hidden />
          {error}
        </p>
      )}
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
    </form>
  );
}
