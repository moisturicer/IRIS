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
  const rows: { label: string; value: string; emphasis?: boolean }[] = [
    // The API's own wording for where the record stands (IR-259).
    { label: "Pipeline Status", value: record.workflow_state_label, emphasis: true },
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
    {
      label: "Commercialization",
      value: record.for_commercialization ? "Eligible" : "Not flagged",
    },
  ];

  return (
    <section className="bg-white ring-1 ring-stone-200 rounded-2xl p-5 shadow-card">
      <RailHeading className="mb-3">Institutional Governance</RailHeading>
      <dl className="space-y-2">
        {rows.map((row) => (
          <div key={row.label} className="flex items-baseline justify-between gap-3">
            <dt className="text-xs text-stone-500 shrink-0">{row.label}</dt>
            <dd
              className={
                row.emphasis
                  ? "text-xs font-bold text-stone-900 text-right"
                  : "text-xs font-semibold text-stone-700 text-right"
              }
            >
              {row.value}
            </dd>
          </div>
        ))}
      </dl>
    </section>
  );
}
