/**
 * Reported comments (IR-693): every Comment on a published paper with an open
 * report, for RDCO and the System Admin, who share it at `/moderation/comments`
 * (ADR-032 §7, amendment 2026-10-31; decisions 2026-11-15).
 *
 * Each item shows the wording as reported and, when the writer has edited it
 * since, the wording now; its paper; the reasons with how many gave each;
 * *Other*'s notes; and when it was first reported. It never names who reported.
 * **Remove** asks for a reason the writer is told; **Dismiss** closes the
 * reports and leaves the comment. If someone else acted first, the server says
 * so, and the queue is read again either way.
 */
import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { moderationApi } from "@/api/moderation";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/Button";
import { Spinner } from "@/components/ui/Spinner";
import { EmptyState } from "@/components/shared/EmptyState";
import { LoadFailedAlert } from "@/components/shared/LoadFailedAlert";
import { errorDetail } from "@/lib/errorDetail";
import { queueCountsChanged } from "@/lib/queueCounts";
import { failureMessage } from "@/lib/readFailure";
import { formatDate } from "@/lib/utils";
import { useUIStore } from "@/store/ui.store";
import { REPORT_REASON_LABELS, type ReportedComment } from "@/types/records";

import { RdcoNoteDialog } from "./RdcoNoteDialog";

type Read =
  | { status: "loading" }
  | { status: "failed"; error: unknown }
  | { status: "ready"; comments: ReportedComment[] };

const QUOTE = "whitespace-pre-wrap break-words rounded-control border-l-2 border-stone-300 bg-stone-50 px-3 py-2 text-body text-stone-800";

export default function ReportedCommentsPage() {
  const addToast = useUIStore((s) => s.addToast);
  const [read, setRead] = useState<Read>({ status: "loading" });
  const [attempt, setAttempt] = useState(0);
  const [removing, setRemoving] = useState<ReportedComment | null>(null);
  const [dismissing, setDismissing] = useState<number | null>(null);

  const reload = useCallback(() => setAttempt((n) => n + 1), []);

  useEffect(() => {
    const controller = new AbortController();
    moderationApi
      .reportedComments({ signal: controller.signal })
      .then(({ data }) => {
        if (!Array.isArray(data?.comments)) throw new Error("Unexpected reported comments response");
        setRead({ status: "ready", comments: data.comments });
      })
      .catch((error) => {
        if (!controller.signal.aborted) setRead({ status: "failed", error });
      });
    return () => controller.abort();
  }, [attempt]);

  /** After any act, success or not: the count and the queue are read again. */
  const settled = () => {
    queueCountsChanged();
    reload();
  };

  const dismiss = async (comment: ReportedComment) => {
    setDismissing(comment.id);
    try {
      await moderationApi.dismissReports(comment.id);
      addToast({ type: "success", message: "Reports dismissed. The comment stays." });
    } catch (err) {
      addToast({ type: "error", message: errorDetail(err, "The reports could not be dismissed. Please try again.") });
    } finally {
      setDismissing(null);
      settled();
    }
  };

  return (
    <div>
      <PageHeader
        title="Reported comments"
        description="Comments readers reported on published papers. Remove one with a reason its writer is told, or dismiss its reports to keep it. Readers who report are never named."
      />

      {read.status === "loading" ? (
        <div className="flex justify-center py-16"><Spinner size="lg" label="Loading reported comments" onRetry={reload} /></div>
      ) : read.status === "failed" ? (
        <LoadFailedAlert
          message={failureMessage(read.error, { lead: "The reported comments didn't load." })}
          onRetry={reload}
        />
      ) : read.comments.length === 0 ? (
        <EmptyState icon="fa-flag" title="No reported comments" message="Nothing waits for a decision." />
      ) : (
        <ol className="space-y-4" aria-label="Reported comments">
          {read.comments.map((comment) => (
            <li key={comment.id}>
              <ReportedItem
                comment={comment}
                busy={dismissing === comment.id}
                onRemove={() => setRemoving(comment)}
                onDismiss={() => void dismiss(comment)}
              />
            </li>
          ))}
        </ol>
      )}

      {removing && (
        <RdcoNoteDialog
          title="Remove comment"
          submitLabel="Remove"
          audience="writer"
          requester={removing.author_name}
          recordTitle={removing.record.title}
          intro="It shows as [removed], its reports close, and its writer is told in-app, with your reason."
          send={(reason) => moderationApi.removeComment(removing.id, reason)}
          onClose={() => {
            setRemoving(null);
            settled();
          }}
          onDone={() => {
            setRemoving(null);
            addToast({ type: "success", message: "Comment removed. Its writer was told why." });
            settled();
          }}
        />
      )}
    </div>
  );
}

function ReportedItem({ comment, busy, onRemove, onDismiss }: {
  comment: ReportedComment;
  busy: boolean;
  onRemove: () => void;
  onDismiss: () => void;
}) {
  const who = `${comment.author_name}'s comment`;
  const reported = comment.reported_texts;
  const edited = comment.current_text !== null && !reported.includes(comment.current_text);
  const count = `${comment.report_count} report${comment.report_count === 1 ? "" : "s"}`;
  return (
    <article
      aria-label={`${who} on ${comment.record.title}`}
      className="space-y-3 rounded-card border border-stone-200 bg-white p-4"
    >
      <header className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <p className="min-w-0 text-body text-stone-700">
          <span className="font-semibold text-stone-900">{comment.author_name}</span>
          {" on "}
          <Link to={`/records/${comment.record.id}`} className="font-medium text-brand hover:underline">
            {comment.record.title}
          </Link>
        </p>
        <p className="text-small text-stone-600">
          {count} · first {formatDate(comment.first_reported_at)}
        </p>
      </header>

      <div className="space-y-2">
        {(edited || reported.length > 1) && <p className="text-small font-semibold text-stone-600">As reported</p>}
        {reported.map((text) => <p key={text} className={QUOTE}>{text}</p>)}
        {edited && (
          <>
            <p className="text-small font-semibold text-stone-600">Now reads</p>
            <p className={QUOTE}>{comment.current_text}</p>
          </>
        )}
        {comment.deletion_kind && (
          <p className="text-small italic text-stone-600">
            {comment.deletion_kind === "writer" ? "Deleted by its writer" : "Removed"}
          </p>
        )}
      </div>

      <ul className="flex flex-wrap gap-2" aria-label="Reasons">
        {comment.reasons.map(({ reason, count: n }) => (
          <li key={reason} className="rounded-full bg-stone-100 px-2.5 py-0.5 text-small text-stone-700">
            {`${REPORT_REASON_LABELS[reason] ?? reason} ${n}`}
          </li>
        ))}
      </ul>
      {comment.notes.length > 0 && (
        <ul className="space-y-1 text-small text-stone-700" aria-label="Notes from readers">
          {comment.notes.map((note, i) => <li key={i} className="break-words">“{note}”</li>)}
        </ul>
      )}

      <div className="flex flex-wrap justify-end gap-2">
        {!comment.deletion_kind && (
          <Button type="button" size="sm" variant="danger" onClick={onRemove} aria-label={`Remove ${who}`}>
            Remove
          </Button>
        )}
        <Button
          type="button"
          size="sm"
          variant="ghost"
          onClick={onDismiss}
          loading={busy}
          aria-label={`Dismiss reports on ${who}`}
        >
          Dismiss
        </Button>
      </div>
    </article>
  );
}
