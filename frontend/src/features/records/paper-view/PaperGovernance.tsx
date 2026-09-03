import type { RecordDetail } from "@/types/records";
import { IP_TYPE_LABELS } from "@/types/records";
import { pipelineLabel } from "@/lib/utils";

/**
 * Institutional governance facts, as a label/value ledger.
 *
 * Every row reads from a field that exists on RecordDetail. A field IRIS does
 * not hold does not get a row — an em dash here means "not set", never
 * "not modelled".
 */
export function PaperGovernance({ record }: { record: RecordDetail }) {
  const rows: { label: string; value: string; emphasis?: boolean }[] = [
    { label: "Pipeline Status", value: pipelineLabel(record.pipeline_status), emphasis: true },
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
    <section className="bg-white border border-stone-200 rounded-2xl p-5">
      <h2 className="text-[11px] font-bold uppercase tracking-wider text-stone-400 mb-3">
        Institutional Governance
      </h2>
      <dl className="space-y-2">
        {rows.map((row) => (
          <div key={row.label} className="flex items-baseline justify-between gap-3">
            <dt className="text-[12px] text-stone-500 shrink-0">{row.label}</dt>
            <dd
              className={
                row.emphasis
                  ? "text-[12px] font-bold text-stone-900 text-right"
                  : "text-[12px] font-semibold text-stone-700 text-right"
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
