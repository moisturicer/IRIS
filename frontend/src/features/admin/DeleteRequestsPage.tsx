/**
 * RDCO's delete-request queue: approve what is pending, read what is decided.
 * Accessible to staff roles only (gated by ProtectedRoute in router/index.tsx).
 *
 * Two tabs, never mixed (IR-1076, audit WF-02):
 *   - Pending asks the server for `status=pending` and is the only place the
 *     approve action appears.
 *   - Decided asks for `status=decided` (approved and declined) and shows each
 *     outcome with the requester's reason and the date it was decided.
 *   - The API pages at 20; "Load more" reads the next page and appends it.
 *   - The reason column is the requester's ("Requested because"). RDCO's own
 *     reason, and a Decline action, are IR-1099.
 *
 * Notes:
 *   - Only admins can approve deletions (backend: IsAdmin permission).
 *   - Approving soft-deletes the record and notifies the owner.
 *
 * Backend endpoints:
 *   GET  /records/delete-requests/?status=pending|decided → the queue, narrowed
 *   POST /records/delete-requests/<id>/approve/           → approve (soft-deletes record)
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
import { LoadFailedAlert } from "@/components/shared/LoadFailedAlert";
import { failureMessage } from "@/lib/readFailure";
import { useApiRead } from "@/hooks/useApiRead";
import { RequestStatusChip } from "@/components/shared/RequestStatusChip";
import { formatDate }  from "@/lib/utils";
import type { DeleteRequest } from "@/types/records";

/** One page of the queue, and whether the server has another after it. */
type QueuePage = { results: DeleteRequest[]; next: string | null };

/**
 * The pages read after the first, kept with the first page they follow. When a
 * tab change or a reload brings a new first page, these no longer follow it and
 * are ignored, so nothing stale is ever shown beside a fresh read.
 */
type LaterPages = { after: QueuePage; rows: DeleteRequest[]; page: number; next: string | null };

export default function DeleteRequestsPage() {
  const [approving,    setApproving]    = useState<number | null>(null);
  const [error,        setError]        = useState<string | null>(null);
  const [tab, setTab] = useState<"pending" | "decided">("pending");
  const [later,        setLater]        = useState<LaterPages | null>(null);
  const [loadingMore,  setLoadingMore]  = useState(false);
  const [moreError,    setMoreError]    = useState<string | null>(null);

  // Cancelled when the filter changes or the page closes, so a slow earlier
  // answer cannot replace the one the reader is waiting for (IR-914).
  const read = useApiRead(
    (signal) =>
      recordsApi
        .listDeleteRequests({ status: tab }, { signal })
        .then(({ data }): QueuePage => ({ results: data.results ?? [], next: data.next ?? null })),
    [tab],
  );
  const loading = read.status === "loading";
  const firstPage = read.data;
  const following = later && later.after === firstPage ? later : null;
  const requests = [...(firstPage?.results ?? []), ...(following?.rows ?? [])];
  const hasMore = (following ? following.next : firstPage?.next) != null;

  // Reads the page after the last one shown (the API pages at 20). A tab change
  // or reload while it is in flight leaves its answer ignored, as above.
  const loadMore = async () => {
    if (!firstPage) return;
    const page = (following?.page ?? 1) + 1;
    setLoadingMore(true);
    setMoreError(null);
    try {
      const { data } = await recordsApi.listDeleteRequests({ status: tab, page });
      setLater({
        after: firstPage,
        rows: [...(following?.rows ?? []), ...(data.results ?? [])],
        page,
        next: data.next ?? null,
      });
    } catch {
      setMoreError("Could not load more requests. Please try again.");
    } finally {
      setLoadingMore(false);
    }
  };

  // Reading again also clears an earlier failed approval, as it always has.
  const reload = () => {
    setError(null);
    setMoreError(null);
    read.retry();
  };

  const handleApprove = async (req: DeleteRequest) => {
    if (!confirm(
      `Approve deletion of "${req.record_title}"? This will permanently remove the record and cannot be undone.`
    )) return;

    setApproving(req.id);
    setError(null);
    try {
      await recordsApi.approveDeleteRequest(req.id);
      reload();
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

      {/* Pending and Decided: a request is in exactly one of them */}
      <div className="flex flex-wrap items-center gap-2 mb-4">
        {(["pending", "decided"] as const).map((s) => (
          <Button
            key={s}
            type="button"
            onClick={() => { setTab(s); setMoreError(null); }}
            aria-pressed={tab === s}
            variant="ghost"
            size="sm"
          >
            {s === "pending" ? "Pending" : "Decided"}
          </Button>
        ))}
        <Button
          type="button"
          onClick={reload}
          disabled={loading}
          variant="outline"
          size="sm"
          className="ml-auto"
        >
          <i className={`fas fa-sync-alt text-[12px] ${loading ? "animate-spin" : ""}`} aria-hidden />
          Refresh
        </Button>
      </div>

      {error && (
        <div role="alert" className={`mb-4 ${LOAD_ERROR}`}>
          <i className="fas fa-circle-exclamation mt-0.5" aria-hidden />
          {error}
        </div>
      )}
      {!error && read.status === "failed" && (
        <LoadFailedAlert
          message={failureMessage(read.error, { lead: "The delete requests didn't load." })}
          onRetry={reload}
          className="mb-4"
        />
      )}

      {read.status === "interrupted" ? (
        <InterruptedState what="delete requests" onRetry={reload} />
      ) : loading ? (
        <div className="flex justify-center py-16"><Spinner size="lg" label="Loading delete requests" onRetry={reload} /></div>
      ) : read.status === "failed" ? null : requests.length === 0 ? (
        <EmptyState
          icon="fa-trash-alt"
          title="No delete requests"
          message={tab === "pending" ? "No deletions are pending approval." : "No requests have been decided yet."}
        />
      ) : (
        <div className="bg-white rounded-xl border border-stone-200 overflow-hidden">
          <div className="px-4 py-3 border-b border-stone-100">
            <span className="text-[13px] text-stone-500 font-medium">
              {requests.length} request{requests.length !== 1 ? "s" : ""}{hasMore ? " shown" : ""}
            </span>
          </div>

          <div className="relative overflow-x-auto">
            <table className="w-full text-[14px]">
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
                          {req.reviewed_at ? formatDate(req.reviewed_at) : "—"}
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {(hasMore || moreError) && (
            <div className="flex flex-col items-center gap-2 border-t border-stone-100 px-4 py-3">
              {moreError && (
                <p role="alert" className="text-small text-stone-700">{moreError}</p>
              )}
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={loadMore}
                loading={loadingMore}
              >
                Load more
              </Button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
