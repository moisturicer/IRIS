import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { recordsApi } from "@/api/records";
import { PageHeader } from "@/components/layout/PageHeader";
import { StatusBadge } from "@/components/shared/StatusBadge";
import { EmptyState } from "@/components/shared/EmptyState";
import type { RecordListItem } from "@/types/records";
import { formatDate } from "@/lib/utils";
import { Skeleton } from "@/components/ui/Skeleton";

interface Props {
  /** "library" shows only published records; "workspace" shows all statuses */
  mode?: "library" | "workspace";
}

export default function MyRecordsPage({ mode = "workspace" }: Props) {
  const [records, setRecords] = useState<RecordListItem[]>([]);
  const [loading, setLoading] = useState(true);

  const isLibrary = mode === "library";

  useEffect(() => {
    const params = isLibrary ? { pipeline_status: "published,approved,completed" } : undefined;
    recordsApi.mine(params)
      .then(({ data }) => {
        setRecords(Array.isArray(data) ? data : ((data as unknown as { results: RecordListItem[] }).results ?? []));
      })
      .finally(() => setLoading(false));
  }, [isLibrary]);

  return (
    <div>
      <PageHeader
        title={isLibrary ? "My Library" : "My Workspace"}
        description={
          isLibrary
            ? "Your published research records."
            : "All your records — drafts, in review, and published."
        }
        actions={
          !isLibrary && (
            <Link to="/records/add" className="bg-[#6B0F12] text-white px-4 py-2 rounded-lg text-[13px] font-semibold hover:bg-[#7d1215]">
              <i className="fas fa-plus mr-1.5" aria-hidden />Add Record
            </Link>
          )
        }
      />

      <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
        {loading ? (
          <Skeleton />
        ) : records.length === 0 ? (
          <EmptyState
            icon="fa-folder-open"
            title={isLibrary ? "No published records yet" : "No records yet"}
            message={isLibrary ? "Your published records will appear here." : "Start by adding your first record."}
          />
        ) : (
          <table className="w-full text-[13px]">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                <th className="text-left px-4 py-3 font-semibold text-gray-600">Title</th>
                <th className="text-left px-4 py-3 font-semibold text-gray-600">Type</th>
                <th className="text-left px-4 py-3 font-semibold text-gray-600">Pipeline Status</th>
                <th className="text-left px-4 py-3 font-semibold text-gray-600">Date Added</th>
              </tr>
            </thead>
            <tbody>
              {records.map((r) => (
                <tr key={r.id} className="border-b border-gray-100 hover:bg-gray-50">
                  <td className="px-4 py-3">
                    <Link to={`/records/${r.id}`} className="text-[#6B0F12] font-medium hover:underline">{r.title}</Link>
                  </td>
                  <td className="px-4 py-3 text-gray-600">{r.record_type_name ?? "-"}</td>
                  <td className="px-4 py-3"><StatusBadge status={r.pipeline_status} /></td>
                  <td className="px-4 py-3 text-gray-500">{formatDate(r.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
