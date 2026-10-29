import { useEffect, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { auditApi, type AuditListParams } from "@/api/audit";
import { PageHeader } from "@/components/layout/PageHeader";
import { DataTable } from "@/components/shared/DataTable";
import { Input } from "@/components/ui/Input";
import { Button } from "@/components/ui/Button";
import type { ColumnDef } from "@tanstack/react-table";
import { AUDIT_EVENT_GROUPS, AUDIT_EVENT_LABELS, type AuditEvent, type AuditEventType } from "@/types/audit";

const WORDS: Record<string, string> = {
  adviser: "Adviser", itso: "ITSO", ierc: "IERC", ktto: "KTTO", rdco: "RDCO",
  clearance_aware: "Clearance aware", restart_all: "Restart all", accepted_and_routed: "Accepted and routed",
  keep_unlisted: "Keep unlisted", closed_by_decision: "Closed by decision",
  requesting_party: "Requesting party", record_withdrawn: "Record withdrawn",
};
function label(value: string) {
  return WORDS[value] ?? value.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase());
}
function readable(value: unknown): ReactNode {
  if (value == null) return "Not recorded";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (Array.isArray(value)) return value.length ? <ul className="list-disc pl-4">{value.map((v, i) => <li key={i}>{readable(v)}</li>)}</ul> : "None";
  if (typeof value === "object") return <dl>{Object.entries(value).map(([k, v]) => <div key={k}><dt className="font-medium">{label(k)}</dt><dd>{readable(v)}</dd></div>)}</dl>;
  return typeof value === "string" ? WORDS[value] ?? value : String(value);
}

const COLUMNS: ColumnDef<AuditEvent, unknown>[] = [
  { header: "Time", accessorKey: "created_at", cell: ({ row }) => <time dateTime={row.original.created_at}>{new Date(row.original.created_at).toLocaleString()}</time> },
  { header: "Event", accessorKey: "event_type", cell: ({ row }) => AUDIT_EVENT_LABELS[row.original.event_type] ?? label(row.original.event_type) },
  { header: "Actor", cell: ({ row: { original: e } }) => e.user_name || (e.user ? `Account #${e.user} (unavailable)` : "System / anonymous") },
  { header: "Record", cell: ({ row: { original: e } }) => e.record_title ? <Link className="underline" to={`/records/${e.record}`}>{e.record_title}</Link> : e.record ? `Record #${e.record} (unavailable)` : "—" },
  { header: "Details", cell: ({ row }) => Object.keys(row.original.metadata).length ? <dl className="min-w-48 text-sm break-words">{Object.entries(row.original.metadata).map(([k, v]) => <div key={k} className="mb-2"><dt className="font-medium">{label(k)}</dt><dd>{readable(v)}</dd></div>)}</dl> : "No details recorded" },
];

export default function AuditLogPage() {
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [eventType, setEventType] = useState<AuditEventType | "">("");
  const [record, setRecord] = useState("");
  const [user, setUser] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [filters, setFilters] = useState<AuditListParams>({});
  const [error, setError] = useState("");
  const [exporting, setExporting] = useState(false);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError("");
    auditApi.list({ ...filters, page, page_size: 20 }).then(({ data }) => {
      if (active) { setEvents(data.results); setTotal(data.count); }
    }).catch(() => {
      if (active) { setEvents([]); setTotal(0); setError("Could not load the audit log. Try filtering again."); }
    }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [filters, page]);

  async function exportCsv() {
    setExporting(true);
    setError("");
    try {
      const { data } = await auditApi.exportCsv(filters);
      const url = URL.createObjectURL(data);
      const link = document.createElement("a");
      link.href = url;
      link.download = "iris-audit.csv";
      link.click();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch { setError("Could not export the audit log. Please try again."); }
    finally { setExporting(false); }
  }

  return <div>
    <PageHeader title="Audit Log" description="Read-only system activity and workflow history." />
    <p className="mb-4 text-sm text-gray-600">Only observed events are shown. Earlier activity and events that failed to log cannot be reconstructed; missing events do not prove that no action occurred.</p>
    <form className="flex flex-wrap items-end gap-3 mb-4" onSubmit={(e) => {
      e.preventDefault();
      if (from && to && from > to) { setError("From date must be on or before To date."); return; }
      setPage(1);
      setFilters({ event_type: eventType || undefined, record: record ? Number(record) : undefined, user: user ? Number(user) : undefined, from: from || undefined, to: to || undefined });
    }}>
      <label className="flex flex-col gap-1 text-sm">Event type
        <select className="border border-gray-300 rounded-lg px-3 py-2" value={eventType} onChange={(e) => setEventType(e.target.value as AuditEventType | "")}>
          <option value="">All events</option>
          {Object.entries(AUDIT_EVENT_GROUPS).map(([group, types]) => <optgroup key={group} label={group}>{Object.entries(types).map(([type, text]) => <option key={type} value={type}>{text}</option>)}</optgroup>)}
        </select>
      </label>
      <Input label="Record ID" type="number" min="1" step="1" value={record} onChange={(e) => setRecord(e.target.value)} />
      <Input label="Actor ID" type="number" min="1" step="1" value={user} onChange={(e) => setUser(e.target.value)} />
      <Input label="From date" type="date" value={from} onChange={(e) => setFrom(e.target.value)} />
      <Input label="To date" type="date" value={to} onChange={(e) => setTo(e.target.value)} />
      <Button type="submit" variant="secondary">Filter</Button>
      <Button type="button" variant="secondary" disabled={exporting || loading} onClick={exportCsv}>{exporting ? "Exporting…" : "Export CSV"}</Button>
    </form>
    <p className="mb-3 text-sm text-gray-600">Filter applies the fields above. CSV exports every row matching the applied filters, across all pages.</p>
    {error && <p role="alert" className="mb-4 text-danger">{error}</p>}
    <div className="bg-white rounded-xl border border-gray-200 overflow-hidden"><DataTable data={events} columns={COLUMNS} loading={loading} page={page} pageSize={20} totalCount={total} onPageChange={setPage} /></div>
  </div>;
}
