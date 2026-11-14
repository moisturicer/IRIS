import { useEffect, useMemo, useState, type ReactNode } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { auditApi, type AuditListParams } from "@/api/audit";
import { PageHeader } from "@/components/layout/PageHeader";
import { DataTable } from "@/components/shared/DataTable";
import { Input } from "@/components/ui/Input";
import { Button } from "@/components/ui/Button";
import { Select } from "@/components/ui/Select";
import type { ColumnDef } from "@tanstack/react-table";
import { AUDIT_EVENT_LABELS, type AuditEvent } from "@/types/audit";
import { groupAuditEventTypes, type AuditEventTypeOption } from "@/lib/auditEventGroups";

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

/**
 * The Event column's name for a type: the frontend's own wording where it has
 * one, else the server's label (a type added since this page was last edited,
 * IR-913), else the code made readable.
 */
function eventName(type: string, serverLabels: ReadonlyMap<string, string>): string {
  return (AUDIT_EVENT_LABELS as Record<string, string>)[type] ?? serverLabels.get(type) ?? label(type);
}

function columnsFor(serverLabels: ReadonlyMap<string, string>): ColumnDef<AuditEvent, unknown>[] {
  return [
  { header: "Time", accessorKey: "created_at", cell: ({ row }) => <time dateTime={row.original.created_at}>{new Date(row.original.created_at).toLocaleString()}</time> },
  { header: "Event", accessorKey: "event_type", cell: ({ row }) => eventName(row.original.event_type, serverLabels) },
  { header: "Actor", cell: ({ row: { original: e } }) => e.user_name || (e.user ? `Account #${e.user} (unavailable)` : "System / anonymous") },
  { header: "Record", cell: ({ row: { original: e } }) => e.record_title ? <Link className="underline" to={`/records/${e.record}`}>{e.record_title}</Link> : e.record ? `Record #${e.record} (unavailable)` : "—" },
  { header: "Details", cell: ({ row }) => Object.keys(row.original.metadata).length ? <dl className="min-w-48 text-sm break-words">{Object.entries(row.original.metadata).map(([k, v]) => <div key={k} className="mb-2"><dt className="font-medium">{label(k)}</dt><dd>{readable(v)}</dd></div>)}</dl> : "No details recorded" },
  ];
}

export default function AuditLogPage() {
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  // `?event_type=` opens the log already filtered: an old link to the Notices
  // page lands here on Notice publications (IR-972). Read once, on arrival.
  const [searchParams] = useSearchParams();
  const [initialEventType] = useState(() => searchParams.get("event_type") ?? "");
  const [eventType, setEventType] = useState(initialEventType);
  // The filter's options come from the server (IR-913), so a new backend event
  // type is filterable with no frontend change. Until they arrive, or if they
  // never do, the select offers only "All events" and the log still works.
  const [typeOptions, setTypeOptions] = useState<AuditEventTypeOption[]>([]);
  const [typesFailed, setTypesFailed] = useState(false);
  const [record, setRecord] = useState("");
  const [user, setUser] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [filters, setFilters] = useState<AuditListParams>(initialEventType ? { event_type: initialEventType } : {});
  const [error, setError] = useState("");
  const [exporting, setExporting] = useState(false);

  useEffect(() => {
    let active = true;
    auditApi.eventTypes().then(({ data }) => {
      if (!active) return;
      // An answer that is not a list is a failed request, not a reason to crash the
      // page: the shape is the server's to keep, and the log works without it.
      if (Array.isArray(data)) { setTypeOptions(data); setTypesFailed(false); }
      else { setTypeOptions([]); setTypesFailed(true); }
    }).catch(() => {
      if (active) { setTypeOptions([]); setTypesFailed(true); }
    });
    return () => { active = false; };
  }, []);

  const typeGroups = useMemo(() => groupAuditEventTypes(typeOptions), [typeOptions]);
  const columns = useMemo(
    () => columnsFor(new Map(typeOptions.map((option) => [option.type, option.label]))),
    [typeOptions],
  );

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
    <p className="mb-4 text-sm text-stone-600">Only observed events are shown. Earlier activity and events that failed to log cannot be reconstructed; missing events do not prove that no action occurred.</p>
    <form className="flex flex-wrap items-end gap-3 mb-4" onSubmit={(e) => {
      e.preventDefault();
      if (from && to && from > to) { setError("From date must be on or before To date."); return; }
      setPage(1);
      setFilters({ event_type: eventType || undefined, record: record ? Number(record) : undefined, user: user ? Number(user) : undefined, from: from || undefined, to: to || undefined });
    }}>
      <Select label="Event type" value={eventType} onChange={(e) => setEventType(e.target.value)} aria-describedby={typesFailed ? "audit-event-types-note" : undefined}>
        <option value="">All events</option>
        {/* A type the address chose but the server didn't list (or the list failed): still named, so the filter shown is the one applied. */}
        {eventType && !typeOptions.some((option) => option.type === eventType) && (
          <option value={eventType}>{eventName(eventType, new Map())}</option>
        )}
        {typeGroups.map(({ group, types }) => <optgroup key={group} label={group}>{types.map(({ type, label: text }) => <option key={type} value={type}>{text}</option>)}</optgroup>)}
      </Select>
      <Input label="Record ID" type="number" min="1" step="1" value={record} onChange={(e) => setRecord(e.target.value)} />
      <Input label="Actor ID" type="number" min="1" step="1" value={user} onChange={(e) => setUser(e.target.value)} />
      <Input label="From date" type="date" value={from} onChange={(e) => setFrom(e.target.value)} />
      <Input label="To date" type="date" value={to} onChange={(e) => setTo(e.target.value)} />
      <Button type="submit" variant="secondary">Filter</Button>
      <Button type="button" variant="secondary" disabled={exporting || loading} onClick={exportCsv}>{exporting ? "Exporting…" : "Export CSV"}</Button>
    </form>
    {typesFailed && <p id="audit-event-types-note" className="mb-3 text-sm text-stone-600">Event types could not be loaded, so the log cannot be filtered by type. Reload the page to try again.</p>}
    <p className="mb-3 text-sm text-stone-600">Filter applies the fields above. CSV exports every row matching the applied filters, across all pages.</p>
    {error && <p role="alert" className="mb-4 text-danger">{error}</p>}
    <div className="bg-white rounded-xl border border-stone-200 overflow-hidden"><DataTable caption="Audit log events" data={events} columns={columns} loading={loading} page={page} pageSize={20} totalCount={total} onPageChange={setPage} /></div>
  </div>;
}
