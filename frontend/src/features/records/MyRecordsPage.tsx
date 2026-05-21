import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { recordsApi } from "@/api/records";
import { PageHeader } from "@/components/layout/PageHeader";
import { StatusBadge } from "@/components/shared/StatusBadge";
import { EmptyState } from "@/components/shared/EmptyState";
import type { RecordListItem } from "@/types/records";
import { formatDate } from "@/lib/utils";

export default function MyRecordsPage() {
  const [records, setRecords] = useState<RecordListItem[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    recordsApi.mine().then(({ data }) => setRecords(data.results)).finally(() => setLoading(false));
  }, []);

  return (
    <div>
      <PageHeader
        title="My Records"
        description="Records you own or submitted."
        actions={
          <Link to="/records/add" className="bg-[#6B0F12] text-white px-4 py-2 rounded-lg text-[13px] font-semibold hover:bg-[#7d1215]">
            <i className="fas fa-plus mr-1.5" />Add Record
          </Link>
        }
      />

      <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
        {loading ? (
          <div className="p-8 text-center text-gray-400 text-[13px]">Loading...</div>
        ) : records.length === 0 ? (
          <EmptyState icon="fa-folder-open" title="No records yet" message="Start by adding your first record." />
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
