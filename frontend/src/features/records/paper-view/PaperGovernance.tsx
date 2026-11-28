import { useId } from "react";

import type { RecordDetail } from "@/types/records";
import { IP_TYPE_LABELS } from "@/types/records";
import { RailHeading } from "./headings";

type Row = { label: string; value: string; /** Says nothing to a reader: shown to `full` viewers only. */ quiet?: boolean };

/**
 * What the record is held under, as a label/value ledger.
 *
 * Every row reads from a field that exists on RecordDetail. A field IRIS does
 * not hold does not get a row — an em dash here means "not set", never
 * "not modelled".
 *
 * Who sees what (IR-1264): those in the record's review (`full`: its owners
 * and reviewers) see every row, the unset and negative ones included, because
 * they may have to act on them. Anyone else sees only rows that say something:
 * no em dash, no "Not declared" IP status, no "Not flagged" commercialization.
 * The page decides `full` by participation, never by role (IR-411).
 *
 * `showStatus` adds where the record stands for a viewer outside its review,
 * who has no Review & routing block to read it from. A published record's
 * status is left out: everything a reader can open in the catalogue is.
 */
export function PaperGovernance({ record, full = false, showStatus = false }: {
  record: RecordDetail;
  full?: boolean;
  showStatus?: boolean;
}) {
  const headingId = useId();
  const unset = (value: string | null | undefined): Row["value"] => value ?? "—";
  // One completion year: the form's, else an import's (IR-1316).
  const completed = record.year_accomplished ?? record.year_completed;
  const rows: Row[] = [
    ...(showStatus && record.pipeline_status !== "published" && record.workflow_state_label
      ? [{ label: "Status", value: record.workflow_state_label }]
      : []),
    { label: "Classification", value: unset(record.classification_name), quiet: !record.classification_name },
    { label: "Record Type", value: unset(record.record_type_name), quiet: !record.record_type_name },
    {
      label: "Year Accomplished",
      value: completed ? String(completed) : "—",
      quiet: !completed,
    },
    // The facts the header used to carry as chips and counters (IR-1089, audit
    // LAY-03): they are held here, once. A field the record lacks gets no row.
    ...(record.psced ? [{ label: "PSCED", value: record.psced }] : []),
    ...(record.publication_year ? [{ label: "Published", value: String(record.publication_year) }] : []),
    ...(record.community_extension ? [{ label: "Community Extension", value: "Yes" }] : []),
    { label: "Views", value: String(record.access_count) },
    {
      label: "IP Status",
      value: record.is_ip
        ? record.ip_type
          ? IP_TYPE_LABELS[record.ip_type]
          : "Declared, untyped"
        : "Not declared",
      quiet: !record.is_ip,
    },
    // ITSO's release (ADR-052 §11; KTTO's until IR-1355): sent only for a marked paper, to the people
    // who see its embargo.
    ...(record.ip_release
      ? [{
          label: "IP Release",
          value: record.ip_release.released ? "Released for the AI" : "Not released for the AI",
        }]
      : []),
    {
      label: "Commercialization",
      value: record.for_commercialization ? "Eligible" : "Not flagged",
      quiet: !record.for_commercialization,
    },
  ];
  const shown = full ? rows : rows.filter((row) => !row.quiet);

  return (
    <section aria-labelledby={headingId} className="bg-white ring-1 ring-stone-200 rounded-card p-5 shadow-card">
      <RailHeading id={headingId} className="mb-3">About this record</RailHeading>
      <dl className="space-y-2">
        {shown.map((row) => (
          <div key={row.label} className="flex items-baseline justify-between gap-3">
            <dt className="text-xs text-stone-500 shrink-0">{row.label}</dt>
            {/* `min-w-0` and anywhere-wrapping: a long Classification name wraps
                inside the row rather than widening the page (IR-921). */}
            <dd className="min-w-0 text-xs font-semibold text-stone-700 text-right [overflow-wrap:anywhere]">{row.value}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}
