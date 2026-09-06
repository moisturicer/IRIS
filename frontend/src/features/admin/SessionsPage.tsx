import { useEffect, useState } from "react";
import { accountsApi, type ActiveSession } from "@/api/accounts";
import { PageHeader } from "@/components/layout/PageHeader";
import { Spinner }    from "@/components/ui/Spinner";
import { formatDate } from "@/lib/utils";

export default function SessionsPage() {
  const [sessions, setSessions] = useState<ActiveSession[]>([]);
  const [loading,  setLoading]  = useState(true);
  const [error,    setError]    = useState<string | null>(null);
  const [revoking, setRevoking] = useState<string | null>(null);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const { data } = await accountsApi.sessions();
      setSessions(data);
    } catch {
      setError("Failed to load sessions. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const handleRevoke = async (jti: string) => {
    if (!confirm("Revoke this session? The user will be logged out on their next request.")) return;
    setRevoking(jti);
    try {
      await accountsApi.revokeSession(jti);
      setSessions(prev => prev.filter(s => s.jti !== jti));
    } catch {
      alert("Failed to revoke session. Please try again.");
    } finally {
      setRevoking(null);
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
        <button
          onClick={load}
          disabled={loading}
          className="flex items-center gap-2 px-4 py-2 text-[13px] font-medium text-gray-600
            bg-white border border-gray-200 rounded-lg hover:bg-gray-50 disabled:opacity-50 transition-colors"
        >
          <i className={`fas fa-sync-alt text-[12px] ${loading ? "animate-spin" : ""}`} aria-hidden />
          Refresh
        </button>
      </div>

      {/* Error */}
      {error && (
        <div className="mb-4 px-4 py-3 bg-red-50 border border-red-200 rounded-xl text-[13px] text-red-700">
          {error}
        </div>
      )}

      {/* Loading */}
      {loading && (
        <div className="flex justify-center py-16">
          <Spinner size="lg" />
        </div>
      )}

      {/* Empty state */}
      {!loading && !error && sessions.length === 0 && (
        <div className="flex flex-col items-center justify-center py-16 text-gray-500">
          <i className="fas fa-shield-alt text-4xl mb-3" aria-hidden />
          <p className="text-[13px] font-medium">No active sessions</p>
          <p className="text-[12px] mt-1">All users are currently logged out.</p>
        </div>
      )}

      {/* Sessions table */}
      {!loading && sessions.length > 0 && (
        <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
          {/* Count badge */}
          <div className="px-4 py-3 border-b border-gray-100 flex items-center justify-between">
            <span className="text-[12px] text-gray-500 font-medium">
              {sessions.length} active session{sessions.length !== 1 ? "s" : ""}
            </span>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-[13px]">
              <thead>
                <tr className="bg-gray-50 border-b border-gray-200 text-left">
                  <th className="px-4 py-3 font-semibold text-gray-600">User</th>
                  <th className="px-4 py-3 font-semibold text-gray-600">Email</th>
                  <th className="px-4 py-3 font-semibold text-gray-600">Issued</th>
                  <th className="px-4 py-3 font-semibold text-gray-600">Expires</th>
                  <th className="px-4 py-3 font-semibold text-gray-600 text-right">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {sessions.map(s => (
                  <tr key={s.jti} className="hover:bg-gray-50 transition-colors">
                    <td className="px-4 py-3 font-medium text-gray-800">
                      {s.user_name || <span className="text-gray-500 italic">Unknown</span>}
                    </td>
                    <td className="px-4 py-3 text-gray-500">{s.user_email ?? "—"}</td>
                    <td className="px-4 py-3 text-gray-500">
                      {formatDate(s.created_at, "MMM d, yyyy · HH:mm")}
                    </td>
                    <td className="px-4 py-3 text-gray-500">
                      {formatDate(s.expires_at, "MMM d, yyyy · HH:mm")}
                    </td>
                    <td className="px-4 py-3 text-right">
                      <button
                        onClick={() => handleRevoke(s.jti)}
                        disabled={revoking === s.jti}
                        className="inline-flex items-center gap-1.5 px-3 py-1.5 text-[12px] font-medium
                          text-red-600 border border-red-200 rounded-lg hover:bg-red-50
                          disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                      >
                        {revoking === s.jti ? (
                          <><Spinner size="sm" /> Revoking…</>
                        ) : (
                          <><i className="fas fa-sign-out-alt" aria-hidden /> Revoke</>
                        )}
                      </button>
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
