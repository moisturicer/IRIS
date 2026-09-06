/**
 * Admin page — list pending download requests and approve or decline them.
 * Accessible to staff roles only (gated by RoleRoute in router/index.tsx).
 *
 * Backend endpoints:
 *   GET  /records/download-requests/        → list all requests
 *   POST /records/download-requests/<id>/approve/  → approve (emails requester)
 *   POST /records/download-requests/<id>/decline/  → decline (in-app notify)
 */
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { recordsApi } from "@/api/records";
import { PageHeader }  from "@/components/layout/PageHeader";
import { Spinner }     from "@/components/ui/Spinner";
import { EmptyState }  from "@/components/shared/EmptyState";
import { formatDate }  from "@/lib/utils";
import type { DownloadRequest } from "@/types/records";

type ActionType = "approve" | "decline";

const STATUS_STYLES: Record<DownloadRequest["status"], string> = {
  pending:  "bg-amber-50  text-amber-700  border-amber-200",
  approved: "bg-green-50  text-green-700  border-green-200",
  declined: "bg-red-50    text-red-700    border-red-200",
};

export default function DownloadRequestsPage() {
  const [requests, setRequests] = useState<DownloadRequest[]>([]);
  const [loading,  setLoading]  = useState(true);
  const [acting,   setActing]   = useState<Record<number, ActionType | null>>({});
  const [error,    setError]    = useState<string | null>(null);

  const [filterStatus, setFilterStatus] = useState<"" | "pending" | "approved" | "declined">("pending");

  const load = () => {
    setLoading(true);
    setError(null);
    const params: Record<string, unknown> = {};
    if (filterStatus) params.status = filterStatus;
    recordsApi.listDownloadRequests(params)
      .then(({ data }) => setRequests(data.results ?? []))
      .catch(() => setError("Failed to load requests."))
      .finally(() => setLoading(false));
  };

  useEffect(load, [filterStatus]);

  const handleAction = async (id: number, action: ActionType) => {
    if (!confirm(
      action === "approve"
        ? "Approve this download request? An email will be sent to the requester."
        : "Decline this download request? The requester will be notified in-app."
    )) return;

    setActing((prev) => ({ ...prev, [id]: action }));
    try {
      if (action === "approve") {
        await recordsApi.approveDownloadRequest(id);
      } else {
        await recordsApi.declineDownloadRequest(id);
      }
      // Refresh list to reflect new status
      load();
    } catch {
      setError("Action failed. Please try again.");
    } finally {
      setActing((prev) => ({ ...prev, [id]: null }));
    }
  };

  return (
    <div>
      <PageHeader
        title="Download Requests"
        description="Review and approve or decline requests to download restricted records."
      />

      {/* Filter bar */}
      <div className="flex items-center gap-2 mb-4">
        {(["pending", "approved", "declined", ""] as const).map((s) => (
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
          icon="fa-download"
          title="No download requests"
          message={filterStatus === "pending" ? "No requests are currently pending." : "No requests match this filter."}
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
                  <th className="px-4 py-3 font-semibold text-gray-600">Date</th>
                  <th className="px-4 py-3 font-semibold text-gray-600">Status</th>
                  <th className="px-4 py-3 font-semibold text-gray-600 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {requests.map((req) => (
                  <tr key={req.id} className="hover:bg-gray-50 transition-colors">
                    <td className="px-4 py-3">
                      <Link
                        to={`/records/${req.record}`}
                        className="text-[#6B0F12] font-medium hover:underline line-clamp-1"
                      >
                        {req.record_title}
                      </Link>
                    </td>
                    <td className="px-4 py-3">
                      <p className="font-medium text-gray-800">{req.requested_by_name ?? "—"}</p>
                      <p className="text-[11px] text-gray-500">{req.requested_by_email}</p>
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
                        <div className="flex justify-end gap-2">
                          <button
                            type="button"
                            onClick={() => handleAction(req.id, "approve")}
                            disabled={!!acting[req.id]}
                            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-[12px] font-medium
                              text-green-700 border border-green-200 rounded-lg hover:bg-green-50
                              disabled:opacity-50 transition-colors"
                          >
                            {acting[req.id] === "approve"
                              ? <><Spinner size="sm" /> Approving…</>
                              : <><i className="fas fa-check" aria-hidden /> Approve</>}
                          </button>
                          <button
                            type="button"
                            onClick={() => handleAction(req.id, "decline")}
                            disabled={!!acting[req.id]}
                            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-[12px] font-medium
                              text-red-600 border border-red-200 rounded-lg hover:bg-red-50
                              disabled:opacity-50 transition-colors"
                          >
                            {acting[req.id] === "decline"
                              ? <><Spinner size="sm" /> Declining…</>
                              : <><i className="fas fa-times" aria-hidden /> Decline</>}
                          </button>
                        </div>
                      ) : (
                        <span className="text-[12px] text-gray-500 italic">
                          {req.reviewed_at ? formatDate(req.reviewed_at) : "Reviewed"}
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
