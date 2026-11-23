import { useId } from "react";

import { StatusBadge } from "@/components/shared/StatusBadge";
import { FOCUS_RING } from "@/components/ui/interaction";
import type { Capability } from "@/features/records/capabilities";
import { cn } from "@/lib/utils";
import type { RecordDetail } from "@/types/records";

import type { ReviewTarget } from "../reviewTarget";
import { useRecordTracker } from "../useRecordTracker";
import { branchRows } from "./branches";
import { OwnerAnswer } from "./OwnerAnswer";
import { ReviewBranches } from "./ReviewBranches";
import { useOwnerRequests } from "./useOwnerRequests";

interface ReviewOverviewProps {
  record: RecordDetail;
  can: ReadonlySet<Capability>;
  userIsOwner: boolean;
  /** Bumped when something about the review changed. */
  trackerVersion: number;
  /** Opens Review, at a tab where one is named. */
  onOpenReview: (target?: ReviewTarget) => void;
  onSubmitNewVersion: () => void;
  /** A file was stored: the page re-reads what derives from it. */
  onDocumentsChanged: () => Promise<void> | void;
}

/**
 * The review on the Overview: a summary, of which Review is the detail. Who
 * has the paper and what each has decided, the request of whoever asks for
 * something, and, for the owner, the files they were asked for. Reading a
 * request whole and answering a comment are Review's, one link away.
 */
export function ReviewOverview({
  record, can, userIsOwner, trackerVersion, onOpenReview, onSubmitNewVersion, onDocumentsChanged,
}: ReviewOverviewProps) {
  const headingId = useId();
  const { data, failed, retry } = useRecordTracker(record.id, trackerVersion);
  const requests = useOwnerRequests(record.id, userIsOwner);
  const revisions = record.revision.open;

  // Null where the viewer may not read them (IR-349): nothing to show.
  const documents = userIsOwner ? requests.shown : data?.document_requests ?? [];
  const rows = branchRows(data, revisions, documents);
  const stored = async () => {
    await requests.reload();
    await onDocumentsChanged();
  };
  const answer = userIsOwner && (revisions.length > 0 || requests.shown.length > 0) ? (
    <OwnerAnswer
      record={record}
      can={can}
      requests={requests.shown}
      refreshFailed={requests.refreshFailed}
      onStored={stored}
      onOpenReview={onOpenReview}
      onSubmitNewVersion={onSubmitNewVersion}
    />
  ) : null;

  return (
    <section aria-labelledby={headingId} className="space-y-5">
      <h2 id={headingId} className="sr-only">Review &amp; Routing</h2>
      <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
        <StatusBadge state={record.workflow_state} label={record.workflow_state_label} compact />
        <button
          type="button"
          onClick={() => onOpenReview()}
          className={cn("inline-flex min-h-11 reading-split:min-h-9 items-center gap-1.5 rounded-control text-small font-semibold text-brand hover:underline underline-offset-[3px]", FOCUS_RING)}
        >
          See review history
          <i className="fas fa-arrow-right text-3xs" aria-hidden />
        </button>
      </div>

      {failed && (
        <div role="alert" className="flex flex-wrap items-center gap-x-3 text-small text-stone-700">
          <p>{failed === "interrupted" ? "The review took too long to load." : "Could not load where the review stands."}</p>
          <button type="button" onClick={retry} className={cn("min-h-11 rounded-control font-semibold text-brand hover:underline", FOCUS_RING)}>
            {failed === "interrupted" ? "Retry" : "Try again"}
          </button>
        </div>
      )}
      {requests.failed && <p role="alert" className="text-small text-brand">{requests.failed}</p>}
      {!data && !failed && (
        <div role="status">
          <span className="sr-only">Loading where the review stands…</span>
          <div aria-hidden className="h-12 rounded-card bg-stone-100 motion-safe:animate-pulse" />
        </div>
      )}

      {(rows.length > 0 || answer) && <ReviewBranches rows={rows} answer={answer} onOpenReview={onOpenReview} />}
      {rows.length === 0 && !answer && data && <p className="text-small text-stone-600">No routing recorded yet.</p>}
    </section>
  );
}
