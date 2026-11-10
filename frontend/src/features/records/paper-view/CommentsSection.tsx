import { useCallback, useEffect, useId, useMemo, useState, type FormEvent } from "react";

import { recordsApi } from "@/api/records";
import { Modal } from "@/components/ui/Modal";
import { errorDetail } from "@/lib/errorDetail";
import type { PublicComment, PublicCommentReportReason } from "@/types/records";

import { CONTROL_BASE, CONTROL_FILLED, CONTROL_SHAPE } from "./controls";
import { SectionHeading } from "./headings";

const MAX_COMMENT_LENGTH = 2000;

type ReportReason = PublicCommentReportReason;

const REPORT_REASONS: { value: ReportReason; label: string }[] = [
  { value: "spam", label: "Spam" },
  { value: "harassment", label: "Harassment" },
  { value: "off_topic", label: "Off-topic" },
  { value: "other", label: "Other" },
];

function chronological(comments: PublicComment[]): PublicComment[] {
  return [...comments].sort((left, right) => Date.parse(left.created_at) - Date.parse(right.created_at));
}

function timestamp(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? value
    : new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(date);
}

function commentError(err: unknown, fallback: string): string {
  const detail = (err as { response?: { data?: { detail?: unknown } } } | null)?.response?.data?.detail;
  return typeof detail === "string" && detail.trim() ? detail : errorDetail(err, fallback);
}

/** Public discussion for a published paper. Review discussion stays separate. */
export function CommentsSection({
  recordId,
  viewerId,
}: {
  recordId: number;
  viewerId: number | null;
}) {
  const id = useId();
  const [comments, setComments] = useState<PublicComment[]>([]);
  const [count, setCount] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [replyTo, setReplyTo] = useState<PublicComment | null>(null);
  const [editing, setEditing] = useState<PublicComment | null>(null);
  const [editDraft, setEditDraft] = useState("");
  const [confirmDelete, setConfirmDelete] = useState<number | null>(null);
  const [reporting, setReporting] = useState<PublicComment | null>(null);
  const [reportReason, setReportReason] = useState<ReportReason>("spam");
  const [reportNote, setReportNote] = useState("");
  const [reportMessage, setReportMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const commentsById = useMemo(() => new Map(comments.map((comment) => [comment.id, comment])), [comments]);

  const refresh = useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    try {
      const { data } = await recordsApi.publicComments(recordId);
      if (!data || !Array.isArray(data.comments) || typeof data.count !== "number") {
        throw new Error("Unexpected comments response");
      }
      setComments(chronological(data.comments));
      setCount(data.count);
    } catch (err) {
      setLoadError(commentError(err, "Comments could not be loaded. Please try again."));
    } finally {
      setLoading(false);
    }
  }, [recordId]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const submitComment = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const body = draft.trim();
    if (!body || body.length > MAX_COMMENT_LENGTH) return;
    setSaving(true);
    setError(null);
    try {
      await recordsApi.postPublicComment(recordId, {
        body,
        ...(replyTo ? { reply_to: replyTo.id } : {}),
      });
      setDraft("");
      setReplyTo(null);
      await refresh();
    } catch (err) {
      setError(commentError(err, "Your comment could not be posted. Please try again."));
    } finally {
      setSaving(false);
    }
  };

  const saveEdit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!editing) return;
    const body = editDraft.trim();
    if (!body || body.length > MAX_COMMENT_LENGTH) return;
    setSaving(true);
    setError(null);
    try {
      await recordsApi.editPublicComment(recordId, editing.id, { body });
      setEditing(null);
      setEditDraft("");
      await refresh();
    } catch (err) {
      setError(commentError(err, "Your comment could not be edited. Please try again."));
    } finally {
      setSaving(false);
    }
  };

  const deleteComment = async (commentId: number) => {
    setSaving(true);
    setError(null);
    try {
      await recordsApi.deletePublicComment(recordId, commentId);
      setConfirmDelete(null);
      await refresh();
    } catch (err) {
      setError(commentError(err, "Your comment could not be deleted. Please try again."));
    } finally {
      setSaving(false);
    }
  };

  const submitReport = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!reporting || (reportReason === "other" && !reportNote.trim())) return;
    setSaving(true);
    setError(null);
    try {
      await recordsApi.reportPublicComment(recordId, reporting.id, {
        reason: reportReason,
        ...(reportReason === "other" ? { note: reportNote.trim() } : {}),
      });
      setReporting(null);
      setReportNote("");
      setReportMessage("Comment reported");
      window.setTimeout(() => setReportMessage(null), 3500);
    } catch (err) {
      setError(commentError(err, "The comment could not be reported. Please try again."));
    } finally {
      setSaving(false);
    }
  };

  const remaining = MAX_COMMENT_LENGTH - draft.length;

  return (
    <section aria-labelledby={`${id}-heading`} className="border-t border-stone-200 pt-7">
      <SectionHeading id={`${id}-heading`}>
        {count === null ? "Comments" : `Comments (${count})`}
      </SectionHeading>

      {reportMessage && <p role="status" aria-atomic="true" className="mb-4 text-sm text-brand">{reportMessage}</p>}
      {error && <p role="alert" className="mb-4 text-sm text-brand">{error}</p>}
      {loadError && (
        <div className="mb-4 flex flex-wrap items-center gap-3 text-sm text-brand">
          <p role="alert">{loadError}</p>
          <button type="button" className="underline focus-visible:outline focus-visible:outline-2" onClick={() => void refresh()}>
            Retry
          </button>
        </div>
      )}

      {viewerId !== null ? (
        <form onSubmit={submitComment} className="mb-6">
          {replyTo && (
            <div className="mb-2 flex items-center gap-2 text-sm text-stone-600">
              <span>Replying to {replyTo.author_name ?? "[deleted]"}</span>
              <button type="button" className="inline-flex min-h-11 items-center underline" onClick={() => setReplyTo(null)}>Cancel reply</button>
            </div>
          )}
          <label htmlFor={`${id}-draft`} className="sr-only">Add a comment</label>
          <textarea
            id={`${id}-draft`}
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            maxLength={MAX_COMMENT_LENGTH}
            rows={3}
            placeholder="Add a comment…"
            aria-describedby={`${id}-counter`}
            className={`block w-full resize-y border border-stone-300 bg-white px-3.5 py-3 text-sm leading-6 text-stone-900 placeholder:text-stone-500 focus-visible:outline focus-visible:outline-2 focus-visible:outline-brand ${CONTROL_SHAPE}`}
          />
          <div className="mt-2 flex flex-wrap items-center justify-between gap-3">
            <span id={`${id}-counter`} className="text-xs text-stone-600">
              {remaining} characters remaining
            </span>
            <button type="submit" disabled={!draft.trim() || remaining < 0 || saving} className={`${CONTROL_BASE} ${CONTROL_FILLED} px-4`}>
              {saving ? "Posting…" : replyTo ? "Post reply" : "Post comment"}
            </button>
          </div>
        </form>
      ) : (
        <p className="mb-6 text-sm text-stone-600">Sign in to join the discussion.</p>
      )}

      {loading ? (
        <p role="status" className="py-4 text-sm text-stone-600">Loading comments…</p>
      ) : loadError ? null : comments.length === 0 ? (
        <p className="py-4 text-sm text-stone-600">No comments yet. Start the discussion.</p>
      ) : (
        <ol className="space-y-5" aria-label="Comments">
          {comments.map((comment) => {
            const deleted = comment.deletion_kind !== null;
            const parent = comment.reply_to === null ? null : commentsById.get(comment.reply_to);
            const own = comment.can_edit && !deleted;
            return (
              <li key={comment.id}>
                <article id={`comment-${comment.id}`} className="scroll-mt-24 border-b border-stone-100 pb-5">
                  {deleted ? (
                    <p className="text-sm italic text-stone-600">
                      {comment.deletion_kind === "writer" ? "[deleted]" : "[removed]"}
                    </p>
                  ) : (
                    <>
                      <header className="mb-2 flex flex-wrap items-center gap-x-2 gap-y-1 text-sm">
                        <span className="font-semibold text-stone-900">{comment.author_name}</span>
                        {comment.is_author && <span className="rounded-full bg-brand/10 px-2 py-0.5 text-xs font-semibold text-brand">Author</span>}
                        <time dateTime={comment.created_at} className="text-xs text-stone-600">{timestamp(comment.created_at)}</time>
                        {comment.edited_at && <span className="text-xs italic text-stone-600">edited</span>}
                      </header>
                      {parent && (
                        <p className="mb-2 text-xs text-stone-600">
                          In reply to <a className="underline focus-visible:outline focus-visible:outline-2" href={`#comment-${parent.id}`}>
                            {parent.deletion_kind ? "[deleted comment]" : parent.author_name}
                          </a>
                        </p>
                      )}
                      {editing?.id === comment.id ? (
                        <form onSubmit={saveEdit}>
                          <label htmlFor={`${id}-edit-${comment.id}`} className="sr-only">Edit comment</label>
                          <textarea
                            id={`${id}-edit-${comment.id}`}
                            value={editDraft}
                            onChange={(event) => setEditDraft(event.target.value)}
                            maxLength={MAX_COMMENT_LENGTH}
                            rows={3}
                            className="block w-full resize-y rounded-lg border border-stone-300 px-3 py-2 text-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-brand"
                          />
                          <div className="mt-2 flex gap-3">
                            <button type="submit" disabled={!editDraft.trim() || saving} className="inline-flex min-h-11 items-center text-sm font-semibold text-brand underline">Save edit</button>
                            <button type="button" className="inline-flex min-h-11 items-center text-sm text-stone-700 underline" onClick={() => setEditing(null)}>Cancel edit</button>
                          </div>
                        </form>
                      ) : (
                        <p className="whitespace-pre-wrap break-words text-sm leading-6 text-stone-800">{comment.body}</p>
                      )}
                      <div className="mt-3 flex flex-wrap gap-x-4 gap-y-2 text-sm">
                        {viewerId !== null && <button type="button" className="inline-flex min-h-11 items-center text-stone-700 underline" onClick={() => setReplyTo(comment)}>Reply</button>}
                        {own && !editing && <button type="button" className="inline-flex min-h-11 items-center text-stone-700 underline" onClick={() => { setEditing(comment); setEditDraft(comment.body ?? ""); }}>Edit</button>}
                        {own && !editing && confirmDelete !== comment.id && <button type="button" className="inline-flex min-h-11 items-center text-stone-700 underline" onClick={() => setConfirmDelete(comment.id)}>Delete</button>}
                        {viewerId !== null && comment.can_report && !deleted && <button type="button" className="inline-flex min-h-11 items-center text-stone-700 underline" onClick={() => { setReporting(comment); setReportReason("spam"); setReportNote(""); }}>Report</button>}
                      </div>
                    </>
                  )}
                </article>
              </li>
            );
          })}
        </ol>
      )}

      {reporting && (
        <Modal open onClose={() => setReporting(null)} title="Report comment" size="max-w-md">
            <p className="mt-1 text-sm text-stone-700">Choose the reason that best describes this comment.</p>
            <form onSubmit={submitReport} className="mt-4">
              <fieldset className="space-y-2">
                <legend className="sr-only">Reason for reporting</legend>
                {REPORT_REASONS.map((reason) => (
                  <label key={reason.value} className="flex min-h-11 items-center gap-2 text-sm text-stone-800">
                    <input type="radio" name={`${id}-report-reason`} value={reason.value} checked={reportReason === reason.value} onChange={() => setReportReason(reason.value)} />
                    {reason.label}
                  </label>
                ))}
              </fieldset>
              {reportReason === "other" && (
                <div className="mt-3">
                  <label htmlFor={`${id}-report-note`} className="mb-1 block text-sm font-medium text-stone-800">Note</label>
                  <textarea id={`${id}-report-note`} required value={reportNote} onChange={(event) => setReportNote(event.target.value)} rows={3} className="w-full rounded-lg border border-stone-300 px-3 py-2 text-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-brand" />
                </div>
              )}
              <div className="mt-5 flex justify-end gap-3">
                <button type="button" className="inline-flex min-h-11 items-center text-sm text-stone-700 underline" onClick={() => setReporting(null)}>Cancel</button>
                <button type="submit" disabled={saving || (reportReason === "other" && !reportNote.trim())} className={`${CONTROL_BASE} ${CONTROL_FILLED} px-4`}>
                  {saving ? "Submitting…" : "Submit report"}
                </button>
              </div>
            </form>
        </Modal>
      )}

      <Modal open={confirmDelete !== null} onClose={() => setConfirmDelete(null)} title="Delete this comment?" size="max-w-sm">
        <p className="text-sm text-stone-700">This cannot be undone.</p>
        <div className="mt-5 flex justify-end gap-3">
          <button type="button" className="text-sm text-stone-700 underline" onClick={() => setConfirmDelete(null)}>Cancel</button>
          <button type="button" disabled={saving || confirmDelete === null} className="inline-flex min-h-11 items-center text-sm font-semibold text-brand underline" onClick={() => confirmDelete !== null && void deleteComment(confirmDelete)}>Delete comment</button>
        </div>
      </Modal>
    </section>
  );
}
