import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { recordsApi } from "@/api/records";
import { PageHeader } from "@/components/layout/PageHeader";
import { StatusBadge } from "@/components/shared/StatusBadge";
import { EmptyState } from "@/components/shared/EmptyState";
import { useDataTable } from "@/hooks/useDataTable";
import type { RecordListItem } from "@/types/records";
import { formatDate } from "@/lib/utils";

export default function PublishedRecordsPage() {
  const { queryParams, setSearch, page, setPage } = useDataTable("-created_at");
  const [records, setRecords] = useState<RecordListItem[]>([]);
  const [total,   setTotal]   = useState(0);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    recordsApi.list(queryParams)
      .then(({ data }) => { setRecords(data.results); setTotal(data.count); })
      .finally(() => setLoading(false));
  }, [JSON.stringify(queryParams)]);

  return (
    <div>
      <PageHeader title="Published Records" description="Research records approved for public viewing." />

      {/* Search */}
      <div className="bg-white rounded-xl border border-gray-200 p-4 mb-4 flex gap-3">
        <input
          type="text"
          placeholder="Search by title, author, abstract..."
          className="flex-1 border border-gray-200 rounded-lg px-3 py-2 text-[13px] focus:outline-none focus:border-[#6B0F12]"
          onChange={(e) => setSearch(e.target.value)}
        />
        {/* TODO: add filter panel for year, classification, PSCED, record type */}
      </div>

      {/* Table */}
      <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
        {loading ? (
          <div className="p-8 text-center text-gray-400 text-[13px]">Loading...</div>
        ) : records.length === 0 ? (
          <EmptyState title="No records found" message="Try adjusting your search or filters." />
        ) : (
          <table className="w-full text-[13px]">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                <th className="text-left px-4 py-3 font-semibold text-gray-600">Title</th>
                <th className="text-left px-4 py-3 font-semibold text-gray-600">Year</th>
                <th className="text-left px-4 py-3 font-semibold text-gray-600">Classification</th>
                <th className="text-left px-4 py-3 font-semibold text-gray-600">Status</th>
                <th className="text-left px-4 py-3 font-semibold text-gray-600">Date Added</th>
              </tr>
            </thead>
            <tbody>
              {records.map((r) => (
                <tr key={r.id} className="border-b border-gray-100 hover:bg-gray-50">
                  <td className="px-4 py-3">
                    <Link to={`/records/${r.id}`} className="text-[#6B0F12] font-medium hover:underline">
                      {r.title}
                    </Link>
                  </td>
                  <td className="px-4 py-3 text-gray-600">{r.year_accomplished ?? "-"}</td>
                  <td className="px-4 py-3 text-gray-600">{r.classification_name ?? "-"}</td>
                  <td className="px-4 py-3"><StatusBadge status={r.pipeline_status} /></td>
                  <td className="px-4 py-3 text-gray-500">{formatDate(r.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        {/* Pagination -- TODO: extract into a reusable Pagination component */}
        <div className="px-4 py-3 flex items-center justify-between text-[12px] text-gray-500 border-t border-gray-100">
          <span>Showing {records.length} of {total}</span>
          <div className="flex gap-2">
            <button onClick={() => setPage(page - 1)} disabled={page === 1} className="px-2 py-1 border rounded disabled:opacity-40">Prev</button>
            <button onClick={() => setPage(page + 1)} disabled={records.length < 20} className="px-2 py-1 border rounded disabled:opacity-40">Next</button>
          </div>
        </div>
      </div>
    </div>
  );
}
