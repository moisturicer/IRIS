/**
 * Audit log page -- admin/staff only.
 * Shows AuditEvent rows with filters for event_type, user, and date range.
 * TODO: add CSV export button.
 * TODO: add record link when event has a record_id.
 */
import { useEffect, useState } from "react";
import { auditApi }      from "@/api/audit";
import { PageHeader }    from "@/components/layout/PageHeader";
import { DataTable }     from "@/components/shared/DataTable";
import { Input }         from "@/components/ui/Input";
import { Button }        from "@/components/ui/Button";
import { Badge }         from "@/components/ui/Badge";
import { formatDate }    from "@/lib/utils";
import type { ColumnDef } from "@tanstack/react-table";
import type { AuditEvent, AuditEventType } from "@/types/audit";

const EVENT_COLORS: Record<string, Parameters<typeof Badge>[0]["variant"]> = {
  LOGIN:    "success",
  LOGOUT:   "neutral",
  ACCESS:   "info",
  UPLOAD:   "info",
  DOWNLOAD: "info",
  DELETE:   "danger",
  RENAME:   "warning",
};

const COLUMNS: ColumnDef<AuditEvent, unknown>[] = [
  {
    header: "Time",
    accessorKey: "created_at",
    cell: ({ getValue }) => (
      <span className="text-gray-500 text-[12px] whitespace-nowrap">
        {formatDate(getValue<string>())}
      </span>
    ),
  },
  {
    header: "Event",
    accessorKey: "event_type",
    cell: ({ getValue }) => {
      const t = getValue<string>();
      return <Badge variant={EVENT_COLORS[t] ?? "default"}>{t}</Badge>;
    },
  },
  {
    header: "User",
    accessorKey: "user_display",
    cell: ({ getValue }) => (
      <span className="text-gray-700">{getValue<string>() ?? "-"}</span>
    ),
  },
  {
    header: "Record",
    accessorKey: "record_title",
    cell: ({ getValue }) => (
      <span className="text-gray-600 truncate max-w-[200px] block">
        {getValue<string>() ?? "-"}
      </span>
    ),
  },
  {
    header: "Details",
    accessorKey: "metadata",
    cell: ({ getValue }) => {
      const meta = getValue<Record<string, unknown>>();
      if (!meta || Object.keys(meta).length === 0) return <span className="text-gray-400">-</span>;
      return (
        <span className="text-[12px] text-gray-500 font-mono truncate max-w-[180px] block">
          {JSON.stringify(meta)}
        </span>
      );
    },
  },
];

export default function AuditLogPage() {
  const [events, setEvents]     = useState<AuditEvent[]>([]);
  const [loading, setLoading]   = useState(true);
  const [total, setTotal]       = useState(0);
  const [page, setPage]         = useState(1);
  const [search, setSearch]     = useState("");
  const [eventType, setEventType] = useState<AuditEventType | "">("");

  const load = (p = page) => {
    setLoading(true);
    auditApi
      .list({ page: p, search, event_type: (eventType || undefined) as AuditEventType | undefined })
      .then(({ data }) => {
        setEvents(data.results);
        setTotal(data.count);
      })
      .finally(() => setLoading(false));
  };

  // Re-load when page or filters change
  useEffect(() => { load(page); }, [page]);

  const handleSearch = () => {
    setPage(1);
    load(1);
  };

  return (
    <div>
      <PageHeader title="Audit Log" description="System activity and access events." />

      {/* Filters */}
      <div className="flex gap-3 mb-4">
        <Input
          placeholder="Search user or record..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleSearch()}
          leading={<i className="fa fa-search text-[13px]" />}
          className="max-w-xs"
        />
        <select
          value={eventType}
          onChange={(e) => { setEventType(e.target.value as AuditEventType | ""); setPage(1); }}
          className="border border-gray-300 rounded-lg px-3 text-[13px] text-gray-700 outline-none
            focus:border-[#6B0F12] focus:ring-1 focus:ring-[#6B0F12]"
        >
          <option value="">All events</option>
          {["LOGIN","LOGOUT","ACCESS","UPLOAD","DOWNLOAD","DELETE","RENAME"].map((t) => (
            <option key={t} value={t}>{t}</option>
          ))}
        </select>
        <Button variant="secondary" size="sm" onClick={handleSearch}>
          Filter
        </Button>
      </div>

      <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
        <DataTable
          data={events}
          columns={COLUMNS}
          loading={loading}
          page={page}
          pageSize={20}
          totalCount={total}
          onPageChange={setPage}
        />
      </div>
    </div>
  );
}
