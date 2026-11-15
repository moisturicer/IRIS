import { useEffect, useState } from "react";
import { accountsApi, type ActiveSession } from "@/api/accounts";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button }     from "@/components/ui/Button";
import { Spinner }    from "@/components/ui/Spinner";
import { ConfirmDialog } from "@/components/shared/ConfirmDialog";
import { LoadFailedAlert } from "@/components/shared/LoadFailedAlert";
import { errorDetail } from "@/lib/errorDetail";
import { failureMessage } from "@/lib/readFailure";
import { formatDate } from "@/lib/utils";
import { useUIStore } from "@/store/ui.store";

const whose = (s: ActiveSession) => s.user_name || s.user_email || "Unknown user";

export default function SessionsPage() {
  const [sessions, setSessions] = useState<ActiveSession[]>([]);
  const [loading,  setLoading]  = useState(true);
  const [error,    setError]    = useState<string | null>(null);
  // The session the revoke dialog is asking about, and whether it is in flight.
  const [revokeTarget, setRevokeTarget] = useState<ActiveSession | null>(null);
  const [revoking,     setRevoking]     = useState(false);
  const addToast = useUIStore((s) => s.addToast);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const { data } = await accountsApi.sessions();
      setSessions(data);
    } catch (err) {
      setError(failureMessage(err, { lead: "The sessions didn't load." }));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  // Asked in ConfirmDialog (IR-1028); the result is a toast either way, with
  // the server's own reason on a refusal.
  const handleRevoke = async () => {
    if (!revokeTarget) return;
    const target = revokeTarget;
    setRevoking(true);
    try {
      await accountsApi.revokeSession(target.jti);
      setSessions(prev => prev.filter(s => s.jti !== target.jti));
      addToast({ type: "success", message: `Session for ${whose(target)} revoked.` });
    } catch (err) {
      addToast({ type: "error", message: errorDetail(err, "Failed to revoke session. Please try again.") });
    } finally {
      setRevoking(false);
      setRevokeTarget(null);
    }
  };

  return (
    <div>
      <PageHeader
        title="Active Sessions"
        description="All currently active JWT sessions. Revoking a session forces the user to log in again."
      />

      {/* Refresh button */}
      <div className="flex justify-end mb-4">
        <Button
          type="button"
          variant="outline"
          onClick={load}
          disabled={loading}
        >
          <i className={`fas fa-sync-alt text-small ${loading ? "animate-spin" : ""}`} aria-hidden />
          Refresh
        </Button>
      </div>

      {/* Error */}
      {error && (
        <LoadFailedAlert message={error} onRetry={load} className="mb-4" />
      )}

      {/* Loading */}
      {loading && (
        <div className="flex justify-center py-16">
          <Spinner size="lg" label="Loading sessions" onRetry={load} />
        </div>
      )}

      {/* Empty state */}
      {!loading && !error && sessions.length === 0 && (
        <div className="flex flex-col items-center justify-center py-16 text-stone-500">
          <i className="fas fa-shield-alt text-4xl mb-3" aria-hidden />
          <p className="text-body font-medium">No active sessions</p>
          <p className="text-small mt-1">All users are currently logged out.</p>
        </div>
      )}

      {/* Sessions table */}
      {!loading && sessions.length > 0 && (
        <div className="bg-white rounded-xl border border-stone-200 overflow-hidden">
          {/* Count badge */}
          <div className="px-4 py-3 border-b border-stone-100 flex items-center justify-between">
            <span className="text-small text-stone-500 font-medium">
              {sessions.length} active session{sessions.length !== 1 ? "s" : ""}
            </span>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-body">
              <thead>
                <tr className="bg-stone-50 border-b border-stone-200 text-left">
                  <th className="px-4 py-3 font-semibold text-stone-600">User</th>
                  <th className="px-4 py-3 font-semibold text-stone-600">Email</th>
                  <th className="px-4 py-3 font-semibold text-stone-600">Issued</th>
                  <th className="px-4 py-3 font-semibold text-stone-600">Expires</th>
                  <th className="px-4 py-3 font-semibold text-stone-600 text-right">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-stone-100">
                {sessions.map(s => (
                  <tr key={s.jti} className="hover:bg-stone-50 transition-colors">
                    <td className="px-4 py-3 font-medium text-stone-800">
                      {s.user_name || <span className="text-stone-500 italic">Unknown</span>}
                    </td>
                    <td className="px-4 py-3 text-stone-500">{s.user_email ?? "—"}</td>
                    <td className="px-4 py-3 text-stone-500">
                      {formatDate(s.created_at, "MMM d, yyyy · HH:mm")}
                    </td>
                    <td className="px-4 py-3 text-stone-500">
                      {formatDate(s.expires_at, "MMM d, yyyy · HH:mm")}
                    </td>
                    <td className="px-4 py-3 text-right">
                      <Button
                        type="button"
                        size="sm"
                        variant="danger"
                        onClick={() => setRevokeTarget(s)}
                      >
                        Revoke
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Names whose session it is, so a slip on the wrong row is seen. */}
      <ConfirmDialog
        open={!!revokeTarget}
        title={revokeTarget ? `Revoke ${whose(revokeTarget)}'s session?` : ""}
        message={
          revokeTarget
            ? `${whose(revokeTarget)} will be logged out on their next request and will need to log in again.`
            : ""
        }
        confirmLabel="Revoke session"
        danger
        focusCancel
        confirming={revoking}
        onConfirm={() => void handleRevoke()}
        onCancel={() => setRevokeTarget(null)}
      />
    </div>
  );
}
