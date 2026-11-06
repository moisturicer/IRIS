/**
 * Admin page — list pending delete requests and approve them.
 * Accessible to staff roles only (gated by ProtectedRoute in router/index.tsx).
 *
 * Notes:
 *   - Only admins can approve deletions (backend: IsAdmin permission).
 *   - There is no "decline" action on the backend for DeleteRequest —
 *     an admin simply does not approve, or the owner must re-request.
 *   - Approving soft-deletes the record and notifies the owner.
 *
 * Backend endpoints:
 *   GET  /records/delete-requests/              → list all requests
 *   POST /records/delete-requests/<id>/approve/ → approve (soft-deletes record)
 */
import { useState } from "react";
import { Link } from "react-router-dom";
import { recordsApi } from "@/api/records";
import { PageHeader }  from "@/components/layout/PageHeader";
import { Button }      from "@/components/ui/Button";
import { LOAD_ERROR, WARNING_NOTICE }  from "@/components/ui/fieldClasses";
import { Spinner }     from "@/components/ui/Spinner";
import { EmptyState }  from "@/components/shared/EmptyState";
import { InterruptedState } from "@/components/shared/InterruptedState";
import { useApiRead } from "@/hooks/useApiRead";
import { RequestStatusChip } from "@/components/shared/RequestStatusChip";
import { formatDate }  from "@/lib/utils";
import type { DeleteRequest } from "@/types/records";

export default function DeleteRequestsPage() {
  const [approving,    setApproving]    = useState<number | null>(null);
  const [error,        setError]        = useState<string | null>(null);
  const [filterStatus, setFilterStatus] = useState<"" | "pending" | "approved">("pending");

  // Cancelled when the filter changes or the page closes, so a slow earlier
  // answer cannot replace the one the reader is waiting for (IR-914).
  const read = useApiRead(
    (signal) =>
      recordsApi
        .listDeleteRequests(filterStatus ? { status: filterStatus } : {}, { signal })
        .then(({ data }) => data.results ?? []),
    [filterStatus],
  );
  const loading = read.status === "loading";
  const requests = read.data ?? [];
  const load = read.retry;

  const handleApprove = async (req: DeleteRequest) => {
    if (!confirm(
      `Approve deletion of "${req.record_title}"? This will permanently remove the record and cannot be undone.`
    )) return;

    setApproving(req.id);
    setError(null);
    try {
      await recordsApi.approveDeleteRequest(req.id);
      load();
    } catch {
      setError("Failed to approve deletion. You may need admin privileges.");
    } finally {
      setApproving(null);
    }
  };

  return (
    <div>
      <PageHeader
        title="Delete Requests"
        description="Review and approve requests to permanently remove records."
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

      {/* Filter tabs */}
      <div className="flex flex-wrap items-center gap-2 mb-4">
        {(["pending", "approved", ""] as const).map((s) => (
          <Button
            key={s}
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
          onClick={load}
          disabled={loading}
          variant="outline"
          size="sm"
          className="ml-auto"
        >
          <i className={`fas fa-sync-alt text-[12px] ${loading ? "animate-spin" : ""}`} aria-hidden />
          Refresh
        </Button>
      </div>

      {(error || read.status === "failed") && (
        <div role="alert" className={`mb-4 ${LOAD_ERROR}`}>
          <i className="fas fa-circle-exclamation mt-0.5" aria-hidden />
          {error ?? "Failed to load delete requests."}
        </div>
      )}

      {read.status === "interrupted" ? (
        <InterruptedState what="delete requests" onRetry={read.retry} />
      ) : loading ? (
        <div className="flex justify-center py-16"><Spinner size="lg" label="Loading delete requests" /></div>
      ) : read.status === "failed" ? null : requests.length === 0 ? (
        <EmptyState
          icon="fa-trash-alt"
          title="No delete requests"
          message={filterStatus === "pending" ? "No deletions are pending approval." : "No requests match this filter."}
        />
      ) : (
        <div className="bg-white rounded-xl border border-stone-200 overflow-hidden">
          <div className="px-4 py-3 border-b border-stone-100">
            <span className="text-[13px] text-stone-500 font-medium">
              {requests.length} request{requests.length !== 1 ? "s" : ""}
            </span>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-[14px]">
              <thead>
                <tr className="bg-stone-50 border-b border-stone-200 text-left">
                  <th className="px-4 py-3 font-semibold text-stone-600">Record</th>
                  <th className="px-4 py-3 font-semibold text-stone-600">Requested By</th>
                  <th className="px-4 py-3 font-semibold text-stone-600">Reason</th>
                  <th className="px-4 py-3 font-semibold text-stone-600">Date</th>
                  <th className="px-4 py-3 font-semibold text-stone-600">Status</th>
                  <th className="px-4 py-3 font-semibold text-stone-600 text-right">Action</th>
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
                      <p className="text-[12px] text-stone-500">{req.requested_by_email}</p>
                    </td>
                    <td className="px-4 py-3 max-w-[180px]">
                      {req.reason ? (
                        <p className="text-stone-600 line-clamp-2 text-[13px]">{req.reason}</p>
                      ) : (
                        <span className="text-stone-500 italic text-[13px]">No reason given</span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-stone-500 whitespace-nowrap">
                      {formatDate(req.created_at)}
                    </td>
                    <td className="px-4 py-3">
                      <RequestStatusChip state={req.status} />
                    </td>
                    <td className="px-4 py-3 text-right">
                      {req.status === "pending" ? (
                        <Button
                          type="button"
                          size="sm"
                          variant="danger"
                          onClick={() => handleApprove(req)}
                          loading={approving === req.id}
                        >
                          {approving === req.id ? "Deleting…" : "Approve Deletion"}
                        </Button>
                      ) : (
                        <span className="text-[13px] text-stone-500 italic">
                          {req.reviewed_at ? formatDate(req.reviewed_at) : "Processed"}
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
