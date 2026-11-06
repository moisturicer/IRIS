import { useId } from "react";

import type { RecordDetail } from "@/types/records";
import { IP_TYPE_LABELS } from "@/types/records";
import { RailHeading } from "./headings";

/**
 * Institutional governance facts, as a label/value ledger.
 *
 * Every row reads from a field that exists on RecordDetail. A field IRIS does
 * not hold does not get a row — an em dash here means "not set", never
 * "not modelled".
 */
export function PaperGovernance({ record }: { record: RecordDetail }) {
  const headingId = useId();
  const rows: { label: string; value: string }[] = [
    // No status row: the title badge states where the record stands, once (IR-525).
    { label: "Classification", value: record.classification_name ?? "—" },
    { label: "Record Type", value: record.record_type_name ?? "—" },
    { label: "Year Accomplished", value: record.year_accomplished ? String(record.year_accomplished) : "—" },
    {
      label: "IP Status",
      value: record.is_ip
        ? record.ip_type
          ? IP_TYPE_LABELS[record.ip_type]
          : "Declared, untyped"
        : "Not declared",
    },
    // KTTO's release (ADR-052 §11): sent only for a marked paper, to the people
    // who see its embargo.
    ...(record.ip_release
      ? [{
          label: "IP Release",
          value: record.ip_release.released ? "Released for the AI by KTTO" : "Not released for the AI",
        }]
      : []),
    {
      label: "Commercialization",
      value: record.for_commercialization ? "Eligible" : "Not flagged",
    },
  ];

  return (
    <section aria-labelledby={headingId} className="bg-white ring-1 ring-stone-200 rounded-2xl p-5 shadow-card">
      <RailHeading id={headingId} className="mb-3">Institutional Governance</RailHeading>
      <dl className="space-y-2">
        {rows.map((row) => (
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
