/**
 * Admin page — list pending delete requests and approve them.
 * Accessible to staff roles only (gated by RoleRoute in router/index.tsx).
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
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { recordsApi } from "@/api/records";
import { PageHeader }  from "@/components/layout/PageHeader";
import { Spinner }     from "@/components/ui/Spinner";
import { EmptyState }  from "@/components/shared/EmptyState";
import { formatDate }  from "@/lib/utils";
import type { DeleteRequest } from "@/types/records";

const STATUS_STYLES: Record<DeleteRequest["status"], string> = {
  pending:  "bg-amber-50  text-amber-700  border-amber-200",
  approved: "bg-green-50  text-green-700  border-green-200",
  declined: "bg-red-50    text-red-700    border-red-200",
};

export default function DeleteRequestsPage() {
  const [requests,     setRequests]     = useState<DeleteRequest[]>([]);
  const [loading,      setLoading]      = useState(true);
  const [approving,    setApproving]    = useState<number | null>(null);
  const [error,        setError]        = useState<string | null>(null);
  const [filterStatus, setFilterStatus] = useState<"" | "pending" | "approved">("pending");

  const load = () => {
    setLoading(true);
    setError(null);
    const params: Record<string, unknown> = {};
    if (filterStatus) params.status = filterStatus;
    recordsApi.listDeleteRequests(params)
      .then(({ data }) => setRequests(data.results ?? []))
      .catch(() => setError("Failed to load delete requests."))
      .finally(() => setLoading(false));
  };

  useEffect(load, [filterStatus]);

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
      <div className="mb-4 px-4 py-3 bg-red-50 border border-red-200 rounded-xl text-[13px] text-red-700 flex items-start gap-2">
        <i className="fas fa-exclamation-triangle mt-0.5 flex-shrink-0" aria-hidden />
        <span>
          Approving a deletion <strong>permanently removes</strong> the record from the system.
          Only approve when you are certain the record should be removed.
          This action requires administrator privileges.
        </span>
      </div>

      {/* Filter tabs */}
      <div className="flex items-center gap-2 mb-4">
        {(["pending", "approved", ""] as const).map((s) => (
          <button
            key={s}
            type="button"
            onClick={() => setFilterStatus(s)}
            className={`px-3 py-1.5 rounded-lg text-[12px] font-semibold border transition-colors ${
              filterStatus === s
                ? "bg-[#6B0F12] text-white border-[#6B0F12]"
                : "bg-white text-gray-600 border-gray-200 hover:border-gray-300"
            }`}
          >
            {s === "" ? "All" : s.charAt(0).toUpperCase() + s.slice(1)}
          </button>
        ))}
        <button
          type="button"
          onClick={load}
          disabled={loading}
          className="ml-auto flex items-center gap-1.5 px-3 py-1.5 text-[12px] text-gray-500 border border-gray-200 rounded-lg bg-white hover:bg-gray-50 disabled:opacity-50"
        >
          <i className={`fas fa-sync-alt text-[11px] ${loading ? "animate-spin" : ""}`} aria-hidden />
          Refresh
        </button>
      </div>

      {error && (
        <div className="mb-4 px-4 py-3 bg-red-50 border border-red-200 rounded-xl text-[13px] text-red-700">
          {error}
        </div>
      )}

      {loading ? (
        <div className="flex justify-center py-16"><Spinner size="lg" /></div>
      ) : requests.length === 0 ? (
        <EmptyState
          icon="fa-trash-alt"
          title="No delete requests"
          message={filterStatus === "pending" ? "No deletions are pending approval." : "No requests match this filter."}
        />
      ) : (
        <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
          <div className="px-4 py-3 border-b border-gray-100">
            <span className="text-[12px] text-gray-500 font-medium">
              {requests.length} request{requests.length !== 1 ? "s" : ""}
            </span>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-[13px]">
              <thead>
                <tr className="bg-gray-50 border-b border-gray-200 text-left">
                  <th className="px-4 py-3 font-semibold text-gray-600">Record</th>
                  <th className="px-4 py-3 font-semibold text-gray-600">Requested By</th>
                  <th className="px-4 py-3 font-semibold text-gray-600">Reason</th>
                  <th className="px-4 py-3 font-semibold text-gray-600">Date</th>
                  <th className="px-4 py-3 font-semibold text-gray-600">Status</th>
                  <th className="px-4 py-3 font-semibold text-gray-600 text-right">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {requests.map((req) => (
                  <tr key={req.id} className="hover:bg-gray-50 transition-colors">
                    <td className="px-4 py-3 max-w-[200px]">
                      {/* Record may already be soft-deleted; link still works for detail if accessible */}
                      <Link
                        to={`/records/${req.record}`}
                        className="text-[#6B0F12] font-medium hover:underline line-clamp-2 leading-snug"
                      >
                        {req.record_title}
                      </Link>
                    </td>
                    <td className="px-4 py-3">
                      <p className="font-medium text-gray-800">{req.requested_by_name ?? "—"}</p>
                      <p className="text-[11px] text-gray-500">{req.requested_by_email}</p>
                    </td>
                    <td className="px-4 py-3 max-w-[180px]">
                      {req.reason ? (
                        <p className="text-gray-600 line-clamp-2 text-[12px]">{req.reason}</p>
                      ) : (
                        <span className="text-gray-500 italic text-[12px]">No reason given</span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-gray-500 whitespace-nowrap">
                      {formatDate(req.created_at)}
                    </td>
                    <td className="px-4 py-3">
                      <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-semibold border ${STATUS_STYLES[req.status]}`}>
                        {req.status.charAt(0).toUpperCase() + req.status.slice(1)}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-right">
                      {req.status === "pending" ? (
                        <button
                          type="button"
                          onClick={() => handleApprove(req)}
                          disabled={approving === req.id}
                          className="inline-flex items-center gap-1.5 px-3 py-1.5 text-[12px] font-medium
                            text-red-600 border border-red-200 rounded-lg hover:bg-red-50
                            disabled:opacity-50 transition-colors"
                        >
                          {approving === req.id
                            ? <><Spinner size="sm" /> Deleting…</>
                            : <><i className="fas fa-trash-alt" aria-hidden /> Approve Deletion</>}
                        </button>
                      ) : (
                        <span className="text-[12px] text-gray-500 italic">
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
