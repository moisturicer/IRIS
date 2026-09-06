import { useEffect, useState, useCallback } from "react";
import { Link } from "react-router-dom";
import { recordsApi } from "@/api/records";
import { PageHeader } from "@/components/layout/PageHeader";
import { EmptyState } from "@/components/shared/EmptyState";
import { useAuth } from "@/hooks/useAuth";
import type { RecordListItem } from "@/types/records";
import { formatDate } from "@/lib/utils";
import { Skeleton } from "@/components/ui/Skeleton";

export default function ApprovedProposalsPage() {
  const { user } = useAuth();
  const [records,   setRecords]   = useState<RecordListItem[]>([]);
  const [loading,   setLoading]   = useState(true);
  const [completing, setCompleting] = useState<number | null>(null);
  const [errors,    setErrors]    = useState<Record<number, string>>({});

  const isRDCO = user?.role_name === "RDCO";

  const load = useCallback(() => {
    setLoading(true);
    recordsApi.list({ pipeline_status: "approved", ordering: "-created_at", page_size: 100 })
      .then(({ data }) => setRecords(data.results ?? []))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleComplete = async (id: number) => {
    setCompleting(id);
    setErrors((prev) => { const e = { ...prev }; delete e[id]; return e; });
    try {
      await recordsApi.completeProposal(id);
      setRecords((prev) => prev.filter((r) => r.id !== id));
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
        "Failed to mark as completed.";
      setErrors((prev) => ({ ...prev, [id]: msg }));
    } finally {
      setCompleting(null);
    }
  };

  return (
    <div>
      <PageHeader
        title="Approved Proposals"
        description="Ongoing research proposals awaiting completion mark by RDCO."
      />

      <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
        {loading ? (
          <Skeleton />
        ) : records.length === 0 ? (
          <EmptyState
            icon="fa-check-double"
            title="No approved proposals"
            message="All proposals have been completed or none have been approved yet."
          />
        ) : (
          <table className="w-full text-[13px]">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                <th className="text-left px-4 py-3 font-semibold text-gray-600">Title</th>
                <th className="text-left px-4 py-3 font-semibold text-gray-600">Authors</th>
                <th className="text-left px-4 py-3 font-semibold text-gray-600">Approved</th>
                {isRDCO && (
                  <th className="text-left px-4 py-3 font-semibold text-gray-600">Action</th>
                )}
              </tr>
            </thead>
            <tbody>
              {records.map((r) => (
                <tr key={r.id} className="border-b border-gray-100 hover:bg-gray-50">
                  <td className="px-4 py-3">
                    <Link
                      to={`/records/${r.id}`}
                      className="text-[#6B0F12] font-medium hover:underline"
                    >
                      {r.title}
                    </Link>
                  </td>
                  <td className="px-4 py-3 text-gray-600">
                    {r.authors.length > 0
                      ? r.authors.map((a) => a.name).join(", ")
                      : "—"}
                  </td>
                  <td className="px-4 py-3 text-gray-500">{formatDate(r.created_at)}</td>
                  {isRDCO && (
                    <td className="px-4 py-3">
                      <div className="flex flex-col gap-1">
                        <button
                          type="button"
                          onClick={() => handleComplete(r.id)}
                          disabled={completing === r.id}
                          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-emerald-700 text-white text-[12px] font-semibold hover:bg-emerald-800 transition-colors disabled:opacity-60 whitespace-nowrap"
                        >
                          <i className="fas fa-check-circle text-[11px]" aria-hidden />
                          {completing === r.id ? "Marking..." : "Mark as Completed"}
                        </button>
                        {errors[r.id] && (
                          <p className="text-[11px] text-red-500">{errors[r.id]}</p>
                        )}
                      </div>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
