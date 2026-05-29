/**
 * Role Requests page — staff/admin only.
 * Lists pending role requests and allows approve / decline.
 */
import { useEffect, useState } from "react";
import { accountsApi }   from "@/api/accounts";
import { useUIStore }    from "@/store/ui.store";
import { PageHeader }    from "@/components/layout/PageHeader";
import { Badge }         from "@/components/ui/Badge";
import { Button }        from "@/components/ui/Button";
import { ConfirmDialog } from "@/components/shared/ConfirmDialog";
import type { RoleRequest } from "@/types/auth";

export default function RoleRequestsPage() {
  const addToast = useUIStore((s) => s.addToast);

  const [requests,  setRequests]  = useState<RoleRequest[]>([]);
  const [loading,   setLoading]   = useState(true);
  const [target,    setTarget]    = useState<{ req: RoleRequest; action: "approve" | "decline" } | null>(null);
  const [_acting,   setActing]    = useState(false);

  const load = () => {
    setLoading(true);
    accountsApi
      .roleRequests()
      .then(({ data }) => setRequests(data.results))
      .catch(() => addToast({ type: "error", message: "Failed to load role requests." }))
      .finally(() => setLoading(false));
  };

  useEffect(() => { load(); }, []);

  const handleDecide = async () => {
    if (!target) return;
    setActing(true);
    try {
      await accountsApi.decideRequest(target.req.id, target.action);
      addToast({
        type:    "success",
        message: `Role request ${target.action === "approve" ? "approved" : "declined"}.`,
      });
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
        title="Role Requests"
        description="Review and approve pending role requests from new users."
      />

      {loading ? (
        <div className="text-[13px] text-gray-400 py-10 text-center">Loading…</div>
      ) : requests.length === 0 ? (
        <div className="bg-white rounded-xl border border-gray-200 py-16 text-center">
          <i className="fas fa-check-circle text-[32px] text-green-400 mb-3 block" />
          <p className="text-[14px] font-medium text-gray-700">All caught up!</p>
          <p className="text-[12px] text-gray-400 mt-1">No pending role requests.</p>
        </div>
      ) : (
        <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
          <table className="w-full text-[13px]">
            <thead>
              <tr className="border-b border-gray-100 bg-gray-50">
                <th className="text-left px-5 py-3 font-semibold text-gray-600">User</th>
                <th className="text-left px-5 py-3 font-semibold text-gray-600">Requested Role</th>
                <th className="text-left px-5 py-3 font-semibold text-gray-600">Submitted</th>
                <th className="text-left px-5 py-3 font-semibold text-gray-600">Status</th>
                <th className="px-5 py-3" />
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {requests.map((req) => (
                <tr key={req.id} className="hover:bg-gray-50 transition-colors">
                  <td className="px-5 py-3.5">
                    <div className="font-medium text-gray-900">{req.user_name}</div>
                  </td>
                  <td className="px-5 py-3.5">
                    <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-semibold bg-red-50 text-[#6B0F12] border border-red-100">
                      {req.role_name}
                    </span>
                  </td>
                  <td className="px-5 py-3.5 text-gray-500">
                    {new Date(req.created_at).toLocaleDateString("en-PH", {
                      year: "numeric", month: "short", day: "numeric",
                    })}
                  </td>
                  <td className="px-5 py-3.5">
                    <Badge variant={
                      req.status === "approved" ? "success"
                      : req.status === "declined" ? "danger"
                      : "neutral"
                    }>
                      {req.status.charAt(0).toUpperCase() + req.status.slice(1)}
                    </Badge>
                  </td>
                  <td className="px-5 py-3.5">
                    {req.status === "pending" && (
                      <div className="flex gap-2 justify-end">
                        <Button
                          size="sm"
                          onClick={() => setTarget({ req, action: "approve" })}
                        >
                          Approve
                        </Button>
                        <Button
                          size="sm"
                          variant="danger"
                          onClick={() => setTarget({ req, action: "decline" })}
                        >
                          Decline
                        </Button>
                      </div>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <ConfirmDialog
        open={!!target}
        title={target?.action === "approve" ? "Approve role request?" : "Decline role request?"}
        message={
          target?.action === "approve"
            ? `${target.req.user_name} will be assigned the ${target.req.role_name} role and can access the system.`
            : `${target?.req.user_name}'s request for ${target?.req.role_name} will be declined.`
        }
        confirmLabel={target?.action === "approve" ? "Approve" : "Decline"}
        danger={target?.action === "decline"}
        onConfirm={handleDecide}
        onCancel={() => !acting && setTarget(null)}
        confirming={acting}
      />
    </div>
  );
}
