import { useEffect, useState } from "react";
import { recordsApi } from "@/api/records";
import { useUIStore } from "@/store/ui.store";
import { PageHeader } from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { ConfirmDialog } from "@/components/shared/ConfirmDialog";
import { formatDate } from "@/lib/utils";
import type { DownloadRequest } from "@/types/records";
import { Skeleton } from "@/components/ui/Skeleton";

export default function AccessRequestsPage() {
  const addToast = useUIStore((s) => s.addToast);

  const [requests, setRequests] = useState<DownloadRequest[]>([]);
  const [loading, setLoading]   = useState(true);
  const [target, setTarget]     = useState<{ req: DownloadRequest; action: "approve" | "decline" } | null>(null);
  const [acting, setActing]     = useState(false);
  const [lastLink, setLastLink] = useState<string | null>(null);

  const load = () => {
    setLoading(true);
    recordsApi
      .listDownloadRequests({ status: "pending" })
      .then(({ data }) => setRequests(data.results ?? []))
      .catch(() => addToast({ type: "error", message: "Failed to load access requests." }))
      .finally(() => setLoading(false));
  };

  useEffect(() => { load(); }, []);

  const handleDecide = async () => {
    if (!target) return;
    setActing(true);
    try {
      const { data } = await recordsApi.decideDownloadRequest(target.req.id, target.action);
      if (target.action === "approve" && data.download_url) {
        setLastLink(data.download_url);
        try {
          await navigator.clipboard.writeText(data.download_url);
          addToast({
            type:    "success",
            message: "Approved. Download link copied to clipboard.",
          });
        } catch {
          addToast({
            type:    "success",
            message: "Approved. Copy the download link below and send it to the requester.",
          });
        }
      } else {
        addToast({
          type:    "success",
          message: `Download request ${target.action === "approve" ? "approved" : "declined"}.`,
        });
      }
      load();
    } catch {
      addToast({ type: "error", message: "Action failed. Please try again." });
    } finally {
      setActing(false);
      setTarget(null);
    }
  };

  return (
    <div>
      <PageHeader
        title="Access Requests"
        description="Review download requests for published records."
      />

      {lastLink && (
        <div className="mb-4 p-4 bg-green-50 border border-green-100 rounded-xl text-[12px] text-green-900">
          <p className="font-semibold mb-1">Latest approved download link (24h)</p>
          <a href={lastLink} className="break-all text-[#6B0F12] hover:underline">{lastLink}</a>
        </div>
      )}

      {loading ? (
        <Skeleton />
      ) : requests.length === 0 ? (
        <div className="text-[13px] text-gray-500 py-10 text-center bg-white rounded-xl border border-gray-200">
          No pending download requests.
        </div>
      ) : (
        <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
          <table className="w-full text-[13px]">
            <thead className="bg-gray-50 text-left text-gray-600">
              <tr>
                <th className="px-4 py-3 font-semibold">Record</th>
                <th className="px-4 py-3 font-semibold">Requester</th>
                <th className="px-4 py-3 font-semibold">Requested</th>
                <th className="px-4 py-3 font-semibold text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {requests.map((req) => (
                <tr key={req.id}>
                  <td className="px-4 py-3 font-medium text-gray-900">{req.record_title ?? `#${req.record}`}</td>
                  <td className="px-4 py-3 text-gray-600">
                    {req.requested_by_name ?? "—"}
                    {req.requested_by_email && (
                      <span className="block text-[11px] text-gray-500">{req.requested_by_email}</span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-gray-500">{formatDate(req.created_at)}</td>
                  <td className="px-4 py-3 text-right space-x-2">
                    <Badge variant="warning">Pending</Badge>
                    <Button
                      size="sm"
                      variant="primary"
                      onClick={() => setTarget({ req, action: "approve" })}
                    >
                      Approve
                    </Button>
                    <Button
                      size="sm"
                      variant="secondary"
                      onClick={() => setTarget({ req, action: "decline" })}
                    >
                      Decline
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <ConfirmDialog
        open={!!target}
        title={target?.action === "approve" ? "Approve download?" : "Decline request?"}
        message={
          target?.action === "approve"
            ? `Grant download access for "${target.req.record_title}"? A secure link will be generated.`
            : `Decline the download request for "${target?.req.record_title}"?`
        }
        confirmLabel={target?.action === "approve" ? "Approve" : "Decline"}
        onConfirm={handleDecide}
        onCancel={() => setTarget(null)}
        confirming={acting}
      />
    </div>
  );
}
