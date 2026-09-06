import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { reviewsApi } from "@/api/reviews";
import { PageHeader } from "@/components/layout/PageHeader";
import { EmptyState }  from "@/components/shared/EmptyState";
import type { RecordListItem } from "@/types/records";
import { formatDate } from "@/lib/utils";
import { Skeleton } from "@/components/ui/Skeleton";

export default function DeclinedRecordsPage() {
  const [records, setRecords] = useState<RecordListItem[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    reviewsApi
      .declined()
      .then(({ data }) => setRecords(data))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div>
      <PageHeader
        title="Declined Records"
        description="Records you have declined."
      />
      <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
        {loading ? (
          <Skeleton />
        ) : records.length === 0 ? (
          <EmptyState icon="fa-times-circle" title="No declined records." />
        ) : (
          <table className="w-full text-[13px]">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                <th className="text-left px-4 py-3 font-semibold text-gray-600">Title</th>
                <th className="text-left px-4 py-3 font-semibold text-gray-600">Date Declined</th>
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
