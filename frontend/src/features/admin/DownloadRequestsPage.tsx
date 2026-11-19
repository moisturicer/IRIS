/**
 * RDCO's download-request queue (ADR-048): the only one. Gated to RDCO by
 * ProtectedRoute in router/index.tsx; the server refuses everyone else anyway.
 *
 * Backend endpoints:
 *   GET  /records/download-requests/                → the queue, 20 a page (?status=, ?page=)
 *   POST /records/download-requests/<id>/approve/   → approve (a time-limited grant)
 *   POST /records/download-requests/<id>/decline/   → decline, with a note
 *   POST /records/download-requests/<id>/revoke/    → end a live grant, with a note
 *
 * Each row shows the reader's note and each grant's expiry. Declining and
 * revoking ask for a note the reader is sent (IR-688); approving takes none.
 */
import { useState } from "react";
import { Link } from "react-router-dom";
import { recordsApi } from "@/api/records";
import { PageHeader }  from "@/components/layout/PageHeader";
import { Button } from "@/components/ui";
import { InterruptedState } from "@/components/shared/InterruptedState";
import { LoadFailedAlert } from "@/components/shared/LoadFailedAlert";
import { LoadMore } from "@/components/shared/LoadMore";
import { failureMessage } from "@/lib/readFailure";
import { useFocusAfterCommit } from "@/hooks/useFocusAfterCommit";
import { pageParam, toPage, usePagedRead } from "@/hooks/usePagedRead";
import { Spinner }     from "@/components/ui/Spinner";
import { ConfirmDialog } from "@/components/shared/ConfirmDialog";
import { EmptyState }  from "@/components/shared/EmptyState";
import { RequestStatusChip } from "@/components/shared/RequestStatusChip";
import { errorDetail } from "@/lib/errorDetail";
import { formatDate }  from "@/lib/utils";
import { useUIStore } from "@/store/ui.store";
import { queueCountsChanged } from "@/lib/queueCounts";
import type { DownloadRequest } from "@/types/records";

import { NO_NOTE, RdcoNoteDialog, RdcoNoteLine } from "./RdcoNoteDialog";

type Filter = "" | "pending" | "approved" | "declined" | "revoked";
const FILTERS: readonly Filter[] = ["pending", "approved", "declined", "revoked", ""];

/** A decline or a revocation: both say why, in a note the reader is sent. */
type NoteAct = { kind: "decline" | "revoke"; request: DownloadRequest };

const NOTE_ACTS = {
  decline: {
    title:  "Decline download request",
    submit: "Decline",
    intro:  "The reader is told in-app and by email, with your note, and may request again.",
    send:   recordsApi.declineDownloadRequest,
  },
  revoke: {
    title:  "Revoke download access",
    submit: "Revoke",
    intro:  "The reader can no longer download this paper. They are told in-app and by email, " +
            "with your note, and may request again.",
    send:   recordsApi.revokeDownloadRequest,
  },
} as const;

/** Under an approved request: until when, or since when it has expired. */
function grantLine(req: DownloadRequest): string | null {
  if (req.status !== "approved" || !req.grant_expires_at) return null;
  const date = formatDate(req.grant_expires_at, "d MMM yyyy");
  return req.grant_live ? `Until ${date}` : `Expired ${date}`;
}

const readerName = (req: DownloadRequest) =>
  req.requested_by_name ?? req.requested_by_email ?? "the reader";

export default function DownloadRequestsPage() {
  const addToast = useUIStore((s) => s.addToast);
  // The request the approval dialog is asking about, and whether it is in flight.
  const [approveTarget, setApproveTarget] = useState<DownloadRequest | null>(null);
  const [approving,     setApproving]     = useState(false);
  const [noteAct,  setNoteAct]  = useState<NoteAct | null>(null);

  const [filterStatus, setFilterStatus] = useState<Filter>("pending");
  // The row an action came from is gone after the reload, so focus goes to the filter.
  const filterFocus = useFocusAfterCommit<HTMLButtonElement>();

  // The API pages at 20; "Load more" reads the next page. Changing the filter
  // cancels the read in flight and starts again from the first page (IR-914).
  const read = usePagedRead(
    (page, signal) =>
      recordsApi
        .listDownloadRequests({ ...(filterStatus ? { status: filterStatus } : {}), ...pageParam(page) }, { signal })
        .then(({ data }) => toPage(data)),
    [filterStatus],
  );
  const requests = read.rows;
  const loading = read.status === "loading";

  // Asked in ConfirmDialog (IR-1028); the result is a toast either way, with
  // the server's own reason on a refusal.
  const handleApprove = async () => {
    if (!approveTarget) return;
    const req = approveTarget;
    setApproving(true);
    try {
      await recordsApi.approveDownloadRequest(req.id);
      addToast({ type: "success", message: `Download request from ${readerName(req)} approved.` });
      queueCountsChanged();
      read.retry();
      filterFocus.focusNext();
    } catch (err) {
      addToast({ type: "error", message: errorDetail(err, "Action failed. Please try again.") });
    } finally {
      setApproving(false);
      setApproveTarget(null);
    }
  };

  return (
    <div>
      <PageHeader
        title="Download Requests"
        description="Requests for a PDF copy of a paper. Reading in IRIS needs no approval."
      />

      {/* Filter bar */}
      <div className="flex flex-wrap items-center gap-2 mb-4">
        {FILTERS.map((s) => (
          <Button
            key={s}
            ref={filterStatus === s ? filterFocus.ref : undefined}
            type="button"
            onClick={() => setFilterStatus(s)}
            aria-pressed={filterStatus === s}
            variant="ghost"
            size="sm"
          >
            {s === "" ? "All" : s.charAt(0).toUpperCase() + s.slice(1)}
          </Button>
        ))}
        <Button
          type="button"
          onClick={read.retry}
          disabled={loading}
          variant="outline"
          size="sm"
          className="w-full justify-center sm:ml-auto sm:w-auto"
        >
          <i className={`fas fa-sync-alt text-label ${loading ? "animate-spin" : ""}`} aria-hidden />
          Refresh
        </Button>
      </div>

      {read.status === "failed" && (
        <LoadFailedAlert
          message={failureMessage(read.error, { lead: "The download requests didn't load." })}
          onRetry={read.retry}
          className="mb-4"
        />
      )}

      {read.status === "interrupted" ? (
        <InterruptedState what="download requests" onRetry={read.retry} />
      ) : loading ? (
        <div className="flex justify-center py-16"><Spinner size="lg" label="Loading download requests" onRetry={read.retry} /></div>
      ) : read.status === "failed" ? null : requests.length === 0 ? (
        <EmptyState
          icon="fa-download"
          title="No download requests"
          message={filterStatus === "pending" ? "No requests are currently pending." : "No requests match this filter."}
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
                  <th className="px-4 py-3 font-semibold text-stone-600">Requested by</th>
                  <th className="px-4 py-3 font-semibold text-stone-600">Reader's note</th>
                  <th className="px-4 py-3 font-semibold text-stone-600">Date</th>
                  <th className="px-4 py-3 font-semibold text-stone-600">Status</th>
                  <th className="px-4 py-3 font-semibold text-stone-600 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-stone-100">
                {requests.map((req) => {
                  const grant = grantLine(req);
                  const endedByRdco = req.status === "declined" || req.status === "revoked";
                  return (
                    <tr key={req.id} className="hover:bg-stone-50 transition-colors align-top">
                      <td className="px-4 py-3">
                        <Link
                          to={`/records/${req.record}`}
                          className="text-brand font-medium hover:underline line-clamp-1"
                        >
                          {req.record_title}
                        </Link>
                      </td>
                      <td className="px-4 py-3">
                        <p className="font-medium text-stone-800">{req.requested_by_name ?? "—"}</p>
                        <p className="text-label text-stone-500">{req.requested_by_email}</p>
                      </td>
                      <td className="px-4 py-3 max-w-xs">
                        {req.note
                          ? <p className="text-justified text-stone-700 whitespace-pre-line break-words">{req.note}</p>
                          : <p className="text-stone-500 italic">{NO_NOTE}</p>}
                      </td>
                      <td className="px-4 py-3 text-stone-500 whitespace-nowrap">
                        {formatDate(req.created_at)}
                      </td>
                      <td className="px-4 py-3">
                        <RequestStatusChip
                          state={req.status}
                          expired={!req.grant_live && !!req.grant_expires_at}
                        />
                        {grant && <p className="mt-1 text-label text-stone-600 whitespace-nowrap">{grant}</p>}
                        {endedByRdco && <RdcoNoteLine note={req.rdco_note} />}
                      </td>
                      <td className="px-4 py-3 text-right">
                        {req.status === "pending" ? (
                          <div className="flex justify-end gap-2">
                            <Button
                              type="button"
                              size="sm"
                              variant="primary"
                              onClick={() => setApproveTarget(req)}
                            >
                              <i className="fas fa-check" aria-hidden /> Approve
                            </Button>
                            <Button
                              type="button"
                              size="sm"
                              variant="ghost"
                              onClick={() => setNoteAct({ kind: "decline", request: req })}
                            >
                              Decline
                            </Button>
                          </div>
                        ) : req.grant_live ? (
                          <Button
                            type="button"
                            size="sm"
                            variant="danger"
                            onClick={() => setNoteAct({ kind: "revoke", request: req })}
                          >
                            Revoke
                          </Button>
                        ) : (
                          <span className="text-small text-stone-500 italic">
                            {req.revoked_at ? formatDate(req.revoked_at)
                              : req.cancelled_at ? `Cancelled ${formatDate(req.cancelled_at)}`
                              : req.reviewed_at ? formatDate(req.reviewed_at) : "Reviewed"}
                          </span>
                        )}
                      </td>
                    </tr>
                  );
                })}
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

      {/* Names the reader and the paper, so a slip on the wrong row is seen. */}
      <ConfirmDialog
        open={!!approveTarget}
        title={approveTarget ? `Approve ${readerName(approveTarget)}'s download request?` : ""}
        message={
          approveTarget
            ? `${readerName(approveTarget)} will be able to download "${approveTarget.record_title}" ` +
              "for a limited time, and is told in-app and by email."
            : ""
        }
        confirmLabel="Approve request"
        focusCancel
        confirming={approving}
        onConfirm={() => void handleApprove()}
        onCancel={() => setApproveTarget(null)}
      />

      {noteAct && (
        <RdcoNoteDialog
          title={NOTE_ACTS[noteAct.kind].title}
          submitLabel={NOTE_ACTS[noteAct.kind].submit}
          audience="reader"
          requester={noteAct.request.requested_by_name ?? noteAct.request.requested_by_email ?? "The reader"}
          recordTitle={noteAct.request.record_title}
          intro={NOTE_ACTS[noteAct.kind].intro}
          send={(note) => NOTE_ACTS[noteAct.kind].send(noteAct.request.id, note)}
          onClose={() => setNoteAct(null)}
          onDone={() => {
            // A refusal stays inside the dialog with the note; only success is a toast.
            addToast({
              type: "success",
              message: noteAct.kind === "decline"
                ? `Download request from ${readerName(noteAct.request)} declined.`
                : `Download access for ${readerName(noteAct.request)} revoked.`,
            });
            setNoteAct(null);
            queueCountsChanged();
            read.retry();
            filterFocus.focusNext();
          }}
        />
      )}
    </div>
  );
}
