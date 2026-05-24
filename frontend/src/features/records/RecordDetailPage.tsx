import { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { recordsApi } from "@/api/records";
import { PageHeader } from "@/components/layout/PageHeader";
import { StatusBadge } from "@/components/shared/StatusBadge";
import type { RecordDetail } from "@/types/records";
import { formatDate } from "@/lib/utils";

export default function RecordDetailPage() {
  const { id }             = useParams<{ id: string }>();
  const [record, setRecord] = useState<RecordDetail | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!id) return;
    recordsApi.detail(Number(id)).then(({ data }) => setRecord(data)).finally(() => setLoading(false));
    recordsApi.incrementAccess(Number(id)).catch(() => {});
  }, [id]);

  if (loading) return <div className="p-8 text-gray-400 text-[13px]">Loading...</div>;
  if (!record)  return <div className="p-8 text-gray-500 text-[13px]">Record not found.</div>;

  return (
    <div>
      <PageHeader title={record.title} description={`Added ${formatDate(record.created_at)}`} />

      <div className="bg-white rounded-xl border border-gray-200 p-6 space-y-4">
        <div className="flex items-center gap-3">
          <StatusBadge status={record.pipeline_status} />
          {record.is_ip              && <span className="px-2 py-0.5 bg-blue-50 text-blue-700 rounded-full text-[11px] font-semibold">Intellectual Property</span>}
          {record.for_commercialization && <span className="px-2 py-0.5 bg-green-50 text-green-700 rounded-full text-[11px] font-semibold">For Commercialization</span>}
          {record.community_extension   && <span className="px-2 py-0.5 bg-purple-50 text-purple-700 rounded-full text-[11px] font-semibold">Community Extension</span>}
        </div>

        <div className="grid grid-cols-2 gap-4 text-[13px]">
          <div><span className="font-semibold text-gray-700">Year:</span> <span className="text-gray-600">{record.year_accomplished ?? "-"}</span></div>
          <div><span className="font-semibold text-gray-700">Classification:</span> <span className="text-gray-600">{record.classification ?? "-"}</span></div>
          <div><span className="font-semibold text-gray-700">Type:</span> <span className="text-gray-600">{record.record_type ?? "-"}</span></div>
          <div><span className="font-semibold text-gray-700">PSCED:</span> <span className="text-gray-600">{record.psced ?? "-"}</span></div>
        </div>

        {record.abstract && (
          <div>
            <p className="text-[12px] font-semibold text-gray-700 mb-1">Abstract</p>
            <p className="text-[13px] text-gray-600 leading-relaxed">{record.abstract}</p>
          </div>
        )}

        <div>
          <p className="text-[12px] font-semibold text-gray-700 mb-2">Authors</p>
          <div className="flex flex-wrap gap-2">
            {record.authors.map((a) => (
              <span key={a.id} className="px-2 py-0.5 bg-gray-100 rounded text-[12px] text-gray-700">{a.name}</span>
            ))}
          </div>
        </div>

        <div>
          <p className="text-[12px] font-semibold text-gray-700 mb-2">Owners</p>
          <div className="flex flex-wrap gap-2">
            {record.owners.map((o) => (
              <span key={o.id} className="px-2 py-0.5 bg-gray-100 rounded text-[12px] text-gray-700">
                {o.full_name}{o.is_primary ? " (primary)" : ""}
              </span>
            ))}
          </div>
        </div>

        {/* Documents link */}
        <div className="pt-2 border-t border-gray-100 flex gap-2">
          <Link
            to={`/records/${id}/documents`}
            className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-[#6B0F12] text-white text-[13px] font-semibold hover:bg-[#7d1215] transition-colors"
          >
            <i className="fas fa-folder-open text-[12px]" />
            View Documents
          </Link>
        </div>

        {/* TODO: add Review History section for staff/reviewer roles */}
      </div>
    </div>
  );
}
