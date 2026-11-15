/**
 * RDCO's delete-request queue: approve or decline what is pending, read what is decided.
 * Accessible to staff roles only (gated by ProtectedRoute in router/index.tsx).
 *
 * Two tabs, never mixed (IR-1076, audit WF-02):
 *   - Pending asks the server for `status=pending` and is the only place the
 *     approve and decline actions appear.
 *   - Decided asks for `status=decided` (approved and declined) and shows each
 *     outcome with the requester's reason, RDCO's note on a decline, and the
 *     date it was decided.
 *   - The API pages at 20; "Load more" reads the next page and appends it.
 *   - The reason column is the requester's ("Requested because"). RDCO's own
 *     reason is its note, shown under the status of a declined row (IR-1099).
 *   - Declining asks for a note, as Download Requests does (IR-688): required,
 *     limited here and by the server, and sent to the requester in-app and by
 *     email. Approving takes none.
 *
 * Notes:
 *   - Only admins can approve deletions (backend: IsAdmin permission).
 *   - Approving soft-deletes the record and notifies the owner.
 *
 * Backend endpoints:
 *   GET  /records/delete-requests/?status=pending|decided → the queue, narrowed
 *   POST /records/delete-requests/<id>/approve/           → approve (soft-deletes record)
 *   POST /records/delete-requests/<id>/decline/           → decline, with a note (restores record)
 */
import { useState } from "react";
import { Link } from "react-router-dom";
import { recordsApi } from "@/api/records";
import { PageHeader }  from "@/components/layout/PageHeader";
import { Button }      from "@/components/ui/Button";
import { WARNING_NOTICE }  from "@/components/ui/fieldClasses";
import { Spinner }     from "@/components/ui/Spinner";
import { ConfirmDialog } from "@/components/shared/ConfirmDialog";
import { EmptyState }  from "@/components/shared/EmptyState";
import { InterruptedState } from "@/components/shared/InterruptedState";
import { LoadFailedAlert } from "@/components/shared/LoadFailedAlert";
import { errorDetail } from "@/lib/errorDetail";
import { failureMessage } from "@/lib/readFailure";
import { useUIStore } from "@/store/ui.store";
import { LoadMore } from "@/components/shared/LoadMore";
import { useFocusAfterCommit } from "@/hooks/useFocusAfterCommit";
import { pageParam, toPage, usePagedRead } from "@/hooks/usePagedRead";
import { RequestStatusChip } from "@/components/shared/RequestStatusChip";
import { formatDate }  from "@/lib/utils";
import type { DeleteRequest } from "@/types/records";

import { RdcoNoteDialog, RdcoNoteLine } from "./RdcoNoteDialog";

const requesterName = (req: DeleteRequest) =>
  req.requested_by_name ?? req.requested_by_email ?? "the requester";

export default function DeleteRequestsPage() {
  const addToast = useUIStore((s) => s.addToast);
  // The request the approval dialog is asking about, and whether it is in flight.
  const [approveTarget, setApproveTarget] = useState<DeleteRequest | null>(null);
  const [approving,     setApproving]     = useState(false);
  const [declining,    setDeclining]    = useState<DeleteRequest | null>(null);
  const [tab, setTab] = useState<"pending" | "decided">("pending");
  // The row an approval came from is gone after the reload, so focus goes to the tab.
  const tabFocus = useFocusAfterCommit<HTMLButtonElement>();

  // Cancelled when the filter changes or the page closes, so a slow earlier
  // answer cannot replace the one the reader is waiting for (IR-914). The API
  // pages at 20; "Load more" reads the next page and appends it (IR-1076).
  const read = usePagedRead(
    (page, signal) =>
      recordsApi
        .listDeleteRequests({ status: tab, ...pageParam(page) }, { signal })
        .then(({ data }) => toPage(data)),
    [tab],
  );
  const loading = read.status === "loading";
  const requests = read.rows;

  // Asked in ConfirmDialog (IR-1028); the result is a toast either way, with
  // the server's own reason on a refusal.
  const handleApprove = async () => {
    if (!approveTarget) return;
    const req = approveTarget;
    setApproving(true);
    try {
      await recordsApi.approveDeleteRequest(req.id);
      addToast({ type: "success", message: `Deletion of "${req.record_title}" approved.` });
      read.retry();
      tabFocus.focusNext();
    } catch (err) {
      addToast({
        type: "error",
        message: errorDetail(err, "Failed to approve deletion. You may need admin privileges."),
      });
    } finally {
      setApproving(false);
      setApproveTarget(null);
    }
  };

  return (
    <div>
      <PageHeader
        title="Delete Requests"
        description="Review requests to permanently remove records: approve them, or decline with a note."
      />

      {/* Danger notice */}
      <div className={`mb-4 ${WARNING_NOTICE}`}>
        <i className="fas fa-exclamation-triangle mt-0.5 flex-shrink-0" aria-hidden />
        <span>
          Approving a deletion <strong>permanently removes</strong> the record from the system.
          Only approve when you are certain the record should be removed.
          Only RDCO can approve it.
        </span>
      </div>

      {/* Pending and Decided: a request is in exactly one of them */}
      <div className="flex flex-wrap items-center gap-2 mb-4">
        {(["pending", "decided"] as const).map((s) => (
          <Button
            key={s}
            ref={tab === s ? tabFocus.ref : undefined}
            type="button"
            onClick={() => setTab(s)}
            aria-pressed={tab === s}
            variant="ghost"
            size="sm"
          >
            {s === "pending" ? "Pending" : "Decided"}
          </Button>
        ))}
        <Button
          type="button"
          onClick={read.retry}
          disabled={loading}
          variant="outline"
          size="sm"
          className="ml-auto"
        >
          <i className={`fas fa-sync-alt text-label ${loading ? "animate-spin" : ""}`} aria-hidden />
          Refresh
        </Button>
      </div>

      {read.status === "failed" && (
        <LoadFailedAlert
          message={failureMessage(read.error, { lead: "The delete requests didn't load." })}
          onRetry={read.retry}
          className="mb-4"
        />
      )}

      {read.status === "interrupted" ? (
        <InterruptedState what="delete requests" onRetry={read.retry} />
      ) : loading ? (
        <div className="flex justify-center py-16"><Spinner size="lg" label="Loading delete requests" onRetry={read.retry} /></div>
      ) : read.status === "failed" ? null : requests.length === 0 ? (
        <EmptyState
          icon="fa-trash-alt"
          title="No delete requests"
          message={tab === "pending" ? "No deletions are pending approval." : "No requests have been decided yet."}
        />
      ) : (
        <div className="bg-white rounded-card border border-stone-200 overflow-hidden">
          <div className="px-4 py-3 border-b border-stone-100">
            <span className="text-small text-stone-500 font-medium">
              {requests.length} request{requests.length !== 1 ? "s" : ""}{read.hasMore ? " shown" : ""}
            </span>
          </div>

          <div className="relative overflow-x-auto">
            <table className="w-full text-body">
              <thead>
                <tr className="bg-stone-50 border-b border-stone-200 text-left">
                  <th className="px-4 py-3 font-semibold text-stone-600">Record</th>
                  <th className="px-4 py-3 font-semibold text-stone-600">Requested By</th>
                  <th className="px-4 py-3 font-semibold text-stone-600">Requested because</th>
                  <th className="px-4 py-3 font-semibold text-stone-600">Date</th>
                  <th className="px-4 py-3 font-semibold text-stone-600">Status</th>
                  <th className="px-4 py-3 font-semibold text-stone-600 text-right">
                    {tab === "pending" ? "Action" : "Decided on"}
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-stone-100">
                {requests.map((req) => (
                  <tr key={req.id} className="hover:bg-stone-50 transition-colors">
                    <td className="px-4 py-3 max-w-[200px]">
                      {/* Record may already be soft-deleted; link still works for detail if accessible */}
                      <Link
                        to={`/records/${req.record}`}
                        className="text-brand font-medium hover:underline line-clamp-2 leading-snug"
                      >
                        {req.record_title}
                      </Link>
                    </td>
                    <td className="px-4 py-3">
                      <p className="font-medium text-stone-800">{req.requested_by_name ?? "—"}</p>
                      <p className="text-label text-stone-500">{req.requested_by_email}</p>
                    </td>
                    <td className="px-4 py-3 max-w-[180px]">
                      {req.reason ? (
                        <p className="text-stone-600 line-clamp-2 text-small">{req.reason}</p>
                      ) : (
                        <span className="text-stone-500 italic text-small">No reason given</span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-stone-500 whitespace-nowrap">
                      {formatDate(req.created_at)}
                    </td>
                    <td className="px-4 py-3">
                      <RequestStatusChip state={req.status} />
                      {req.status === "declined" && <RdcoNoteLine note={req.rdco_note} />}
                    </td>
                    <td className="px-4 py-3 text-right">
                      {req.status === "pending" ? (
                        <div className="flex justify-end gap-2">
                          <Button
                            type="button"
                            size="sm"
                            variant="danger"
                            onClick={() => setApproveTarget(req)}
                          >
                            Approve Deletion
                          </Button>
                          <Button
                            type="button"
                            size="sm"
                            variant="outline"
                            onClick={() => setDeclining(req)}
                          >
                            Decline
                          </Button>
                        </div>
                      ) : (
                        <span className="text-small text-stone-500 italic">
                          {req.reviewed_at ? formatDate(req.reviewed_at) : "—"}
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <LoadMore
            hasMore={read.hasMore}
            error={read.moreError}
            loading={read.loadingMore}
            onLoadMore={read.loadMore}
            className="border-t border-stone-100 px-4 py-3"
          />
        </div>
      )}

      {/* Names the paper and the requester, so a slip on the wrong row is seen. */}
      <ConfirmDialog
        open={!!approveTarget}
        title={approveTarget ? `Approve deletion of "${approveTarget.record_title}"?` : ""}
        message={
          approveTarget
            ? `"${approveTarget.record_title}", requested by ${requesterName(approveTarget)}, ` +
              "will be permanently removed. This cannot be undone."
            : ""
        }
        confirmLabel="Approve deletion"
        danger
        focusCancel
        confirming={approving}
        onConfirm={() => void handleApprove()}
        onCancel={() => setApproveTarget(null)}
      />

      {declining && (
        <RdcoNoteDialog
          title="Decline delete request"
          submitLabel="Decline"
          audience="requester"
          requester={requesterName(declining)}
          recordTitle={declining.record_title}
          intro="The record is restored. The requester is told in-app and by email, with your note."
          send={(note) => recordsApi.declineDeleteRequest(declining.id, note)}
          onClose={() => setDeclining(null)}
          onDone={() => {
            // A refusal stays inside the dialog with the note; only success is a toast.
            addToast({ type: "success", message: `Deletion of "${declining.record_title}" declined.` });
            setDeclining(null);
            read.retry();
            tabFocus.focusNext();
          }}
        />
      )}
    </div>
  );
}
