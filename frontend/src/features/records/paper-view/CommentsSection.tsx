import { useCallback, useEffect, useId, useMemo, useRef, useState, type FormEvent } from "react";

import { recordsApi } from "@/api/records";
import { Modal } from "@/components/ui/Modal";
import { Select } from "@/components/ui/Select";
import { Skeleton } from "@/components/ui/Skeleton";
import { errorDetail } from "@/lib/errorDetail";
import type { PublicComment, PublicCommentReportReason } from "@/types/records";

import { CommentComposer } from "./CommentComposer";
import { CommentItem, type CommentContext } from "./CommentItem";
import { buildThreads, COLLAPSE_ABOVE, PAGE_SIZE, type CommentOrder } from "./commentThreads";
import { CONTROL_BASE, CONTROL_FILLED } from "./controls";
import { SectionHeading } from "./headings";

const MAX_COMMENT_LENGTH = 2000;

type ReportReason = PublicCommentReportReason;

const REPORT_REASONS: { value: ReportReason; label: string }[] = [
  { value: "spam", label: "Spam" },
  { value: "harassment", label: "Harassment" },
  { value: "off_topic", label: "Off-topic" },
  { value: "other", label: "Other" },
];

/**
 * A reply in a thread, joined to the line that runs down from its parent's
 * avatar: an elbow to this reply, and a straight run on to the next one.
 */
const REPLY_ITEM =
  "relative pl-7 pt-3 before:absolute before:left-0 before:top-0 before:h-[27px] before:w-[22px] before:rounded-bl-[14px] before:border-b-2 before:border-l-2 before:border-stone-300 after:absolute after:bottom-0 after:left-0 after:top-[27px] after:border-l-2 after:border-stone-300 last:after:hidden";

const TOGGLE_BUTTON =
  "inline-flex min-h-11 items-center gap-1.5 rounded-lg px-1.5 text-small font-semibold text-stone-700 hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-brand reading-split:min-h-8";

/** How long a comment that was just posted or linked to stays highlighted. */
const HIGHLIGHT_MS = 1600;

function commentError(err: unknown, fallback: string): string {
  const detail = (err as { response?: { data?: { detail?: unknown } } } | null)?.response?.data?.detail;
  return typeof detail === "string" && detail.trim() ? detail : errorDetail(err, fallback);
}

/**
 * Public discussion for a published paper, shown as threads: each top-level
 * comment with its replies beneath it (IR-1024). Review discussion stays separate.
 */
export function CommentsSection({
  recordId,
  viewerId,
  viewerName = null,
}: {
  recordId: number;
  viewerId: number | null;
  /** The reader's own name, for the initials beside their field. */
  viewerName?: string | null;
}) {
  const id = useId();
  const [comments, setComments] = useState<PublicComment[]>([]);
  const [count, setCount] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [order, setOrder] = useState<CommentOrder>("oldest");
  const [visibleRoots, setVisibleRoots] = useState(PAGE_SIZE);
  const [opened, setOpened] = useState<Record<number, boolean>>({});
  const [expandedBodies, setExpandedBodies] = useState<ReadonlySet<number>>(new Set());
  const [menuFor, setMenuFor] = useState<number | null>(null);
  const [target, setTarget] = useState<{ id: number } | null>(null);

  const [draft, setDraft] = useState("");
  const [replyTo, setReplyTo] = useState<PublicComment | null>(null);
  const [replyDrafts, setReplyDrafts] = useState<Record<number, string>>({});
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editDraft, setEditDraft] = useState("");

  const [confirmDelete, setConfirmDelete] = useState<number | null>(null);
  const [reporting, setReporting] = useState<PublicComment | null>(null);
  const [reportReason, setReportReason] = useState<ReportReason>("spam");
  const [reportNote, setReportNote] = useState("");
  const [reportMessage, setReportMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const restoreFocus = useRef<string | null>(null);

  const threads = useMemo(() => buildThreads(comments, order), [comments, order]);
  const commentsById = useMemo(() => new Map(comments.map((item) => [item.id, item])), [comments]);
  const rootOfComment = useMemo(() => {
    const map = new Map<number, number>();
    for (const { root, replies } of threads) {
      map.set(root.id, root.id);
      for (const reply of replies) map.set(reply.id, root.id);
    }
    return map;
  }, [threads]);

  /** `quiet` keeps the list on screen while it is fetched again after a change. */
  const refresh = useCallback(
    async (quiet = false) => {
      if (!quiet) setLoading(true);
      setLoadError(null);
      try {
        const { data } = await recordsApi.publicComments(recordId);
        if (!data || !Array.isArray(data.comments) || typeof data.count !== "number") {
          throw new Error("Unexpected comments response");
        }
        setComments(data.comments);
        setCount(data.count);
      } catch (err) {
        setLoadError(commentError(err, "Comments could not be loaded. Please try again."));
      } finally {
        setLoading(false);
      }
    },
    [recordId],
  );

  useEffect(() => {
    void refresh();
  }, [refresh]);

  // Focus goes back to the control that opened what just closed.
  useEffect(() => {
    const wanted = restoreFocus.current;
    if (!wanted) return;
    restoreFocus.current = null;
    document.getElementById(wanted)?.focus();
  });

  // A comment just posted or linked to is scrolled to and briefly highlighted.
  useEffect(() => {
    if (!target) return;
    const reduce = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
    document.getElementById(`comment-${target.id}`)?.scrollIntoView?.({ block: "center", behavior: reduce ? "auto" : "smooth" });
    const timer = window.setTimeout(() => setTarget(null), HIGHLIGHT_MS);
    return () => window.clearTimeout(timer);
  }, [target]);

  const post = async (body: string, parent: PublicComment | null) => {
    const text = body.trim();
    if (!text || text.length > MAX_COMMENT_LENGTH) return;
    setSaving(true);
    setError(null);
    try {
      const { data: created } = await recordsApi.postPublicComment(recordId, {
        body: text,
        ...(parent ? { reply_to: parent.id } : {}),
      });
      if (parent) {
        const rootId = rootOfComment.get(parent.id);
        if (rootId !== undefined) setOpened((current) => ({ ...current, [rootId]: true }));
        setReplyDrafts((current) => ({ ...current, [parent.id]: "" }));
        setReplyTo(null);
      } else {
        setDraft("");
        setVisibleRoots(Number.MAX_SAFE_INTEGER);
      }
      await refresh(true);
      if (created?.id !== undefined) setTarget({ id: created.id });
    } catch (err) {
      setError(commentError(err, "Your comment could not be posted. Please try again."));
    } finally {
      setSaving(false);
    }
  };

  const saveEdit = async () => {
    if (editingId === null) return;
    const body = editDraft.trim();
    if (!body || body.length > MAX_COMMENT_LENGTH) return;
    setSaving(true);
    setError(null);
    try {
      await recordsApi.editPublicComment(recordId, editingId, { body });
      setEditingId(null);
      setEditDraft("");
      await refresh(true);
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
      await refresh(true);
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

  const cancelReply = () => {
    if (replyTo) restoreFocus.current = `reply-btn-${replyTo.id}`;
    setReplyTo(null);
  };

  const ctx: CommentContext = {
    signedIn: viewerId !== null,
    saving,
    maxLength: MAX_COMMENT_LENGTH,
    now: Date.now(),
    menuFor,
    editingId,
    editDraft,
    highlightId: target?.id ?? null,
    expandedBodies,
    setMenuFor,
    setEditDraft,
    startReply: (comment) => {
      setReplyTo(comment);
      setEditingId(null);
      setMenuFor(null);
    },
    startEdit: (comment) => {
      setEditingId(comment.id);
      setEditDraft(comment.body ?? "");
      setReplyTo(null);
      setMenuFor(null);
    },
    cancelEdit: () => setEditingId(null),
    saveEdit: () => void saveEdit(),
    askDelete: (comment) => {
      setMenuFor(null);
      setConfirmDelete(comment.id);
    },
    askReport: (comment) => {
      setMenuFor(null);
      setReporting(comment);
      setReportReason("spam");
      setReportNote("");
    },
    showWholeBody: (commentId) => setExpandedBodies((current) => new Set(current).add(commentId)),
    jumpTo: (commentId) => setTarget({ id: commentId }),
  };

  const shown = threads.slice(0, visibleRoots);
  const left = threads.length - shown.length;

  return (
    <section aria-labelledby={`${id}-heading`} className="border-t border-stone-200 pt-7">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
        <SectionHeading id={`${id}-heading`}>{count === null ? "Comments" : `Comments (${count})`}</SectionHeading>
        {threads.length > 1 && (
          <Select
            label="Sort by"
            inline
            size="sm"
            value={order}
            onChange={(event) => {
              setOrder(event.target.value as CommentOrder);
              setVisibleRoots(PAGE_SIZE);
            }}
          >
            <option value="oldest">Oldest</option>
            <option value="newest">Newest</option>
          </Select>
        )}
      </div>

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
        <div className="mb-6">
          <CommentComposer
            label="Add a comment"
            placeholder="Write a comment…"
            submitLabel="Post comment"
            value={draft}
            onChange={setDraft}
            onSubmit={() => void post(draft, null)}
            maxLength={MAX_COMMENT_LENGTH}
            saving={saving}
            viewerName={viewerName}
          />
        </div>
      ) : (
        <p className="mb-6 text-sm text-stone-600">Sign in to join the discussion.</p>
      )}

      {loading ? (
        <Skeleton rows={3} label="Loading comments…" />
      ) : loadError ? null : threads.length === 0 ? (
        <p className="py-4 text-sm text-stone-600">No comments yet. Start the discussion.</p>
      ) : (
        <>
          <ol className="space-y-5" aria-label="Comments">
            {shown.map(({ root, replies }) => {
              const composing = replyTo !== null && rootOfComment.get(replyTo.id) === root.id;
              const expanded = composing || (opened[root.id] ?? replies.length <= COLLAPSE_ABOVE);
              const hasBelow = replies.length > 0 || composing;
              const rootName = root.deletion_kind ? "a deleted comment" : root.author_name;
              return (
                <li key={root.id}>
                  <CommentItem comment={root} size="root" answering={null} showRail={hasBelow} ctx={ctx} />
                  {hasBelow && (
                    <ol className="ml-[17px]" aria-label={`Replies to ${rootName}`}>
                      {replies.length > 0 &&
                        (expanded ? (
                          replies.map((reply) => (
                            <li key={reply.id} className={REPLY_ITEM}>
                              <CommentItem
                                comment={reply}
                                size="reply"
                                answering={reply.reply_to !== null && reply.reply_to !== root.id ? (commentsById.get(reply.reply_to) ?? null) : null}
                                showRail={false}
                                ctx={ctx}
                              />
                            </li>
                          ))
                        ) : (
                          <li className={REPLY_ITEM}>
                            <button type="button" aria-expanded="false" className={TOGGLE_BUTTON} onClick={() => setOpened((current) => ({ ...current, [root.id]: true }))}>
                              View {replies.length} {replies.length === 1 ? "reply" : "replies"}
                            </button>
                          </li>
                        ))}
                      {expanded && replies.length > COLLAPSE_ABOVE && !composing && (
                        <li className={REPLY_ITEM}>
                          <button type="button" aria-expanded="true" className={TOGGLE_BUTTON} onClick={() => setOpened((current) => ({ ...current, [root.id]: false }))}>
                            Hide replies
                          </button>
                        </li>
                      )}
                      {composing && replyTo && (
                        <li className={REPLY_ITEM}>
                          <CommentComposer
                            label={`Reply to ${replyTo.author_name}`}
                            placeholder={`Reply to ${replyTo.author_name}…`}
                            submitLabel="Post reply"
                            value={replyDrafts[replyTo.id] ?? ""}
                            onChange={(value) => setReplyDrafts((current) => ({ ...current, [replyTo.id]: value }))}
                            onSubmit={() => void post(replyDrafts[replyTo.id] ?? "", replyTo)}
                            onCancel={cancelReply}
                            maxLength={MAX_COMMENT_LENGTH}
                            saving={saving}
                            viewerName={viewerName}
                            size="sm"
                            autoFocus
                            footer={
                              <div className="mt-1 flex flex-wrap items-center gap-x-2 text-2xs text-stone-600">
                                <span>
                                  Replying to <b className="font-semibold text-stone-800">{replyTo.author_name}</b>
                                </span>
                                <span aria-hidden="true">·</span>
                                <button
                                  type="button"
                                  onClick={cancelReply}
                                  className="inline-flex min-h-11 items-center underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-brand reading-split:min-h-8"
                                >
                                  Cancel reply
                                </button>
                                <span aria-hidden="true">·</span>
                                <span>Ctrl+Enter to post</span>
                              </div>
                            }
                          />
                        </li>
                      )}
                    </ol>
                  )}
                </li>
              );
            })}
          </ol>
          {left > 0 && (
            <button type="button" className={`${TOGGLE_BUTTON} mt-3`} onClick={() => setVisibleRoots((current) => current + PAGE_SIZE)}>
              View {Math.min(left, PAGE_SIZE)} more comment{Math.min(left, PAGE_SIZE) === 1 ? "" : "s"}
            </button>
          )}
        </>
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
        <p className="text-sm text-stone-700">This cannot be undone. If it has replies, they stay and this comment shows as [deleted].</p>
        <div className="mt-5 flex justify-end gap-3">
          <button type="button" className="text-sm text-stone-700 underline" onClick={() => setConfirmDelete(null)}>Cancel</button>
          <button type="button" disabled={saving || confirmDelete === null} className="inline-flex min-h-11 items-center text-sm font-semibold text-brand underline" onClick={() => confirmDelete !== null && void deleteComment(confirmDelete)}>Delete comment</button>
        </div>
      </Modal>
    </section>
  );
}
