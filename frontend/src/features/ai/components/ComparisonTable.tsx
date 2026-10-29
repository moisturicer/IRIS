import { useId } from "react";
import { Link } from "react-router-dom";
import type { AnswerComparison, Citation, ComparisonCell, ComparisonCitation } from "@/types/ai";
import { openCitationLabel, useCitationLink } from "@/lib/citedPage";

const COVERAGE_LABELS = {
  read_fully: "Read in full",
  read_by_section: "Read by section",
  could_not_read: "Could not read",
  not_permitted: "Not permitted to read",
};

const REASON_LABELS: Record<string, string> = {
  reading_unavailable: "Reading was unavailable.",
  not_enabled: "Reading was unavailable.",
  generating: "The paper is being prepared for reading.",
  context_window_unknown: "The paper could not be read safely in one answer.",
  admission_required: "Reading was unavailable.",
  stale_or_forbidden: "The paper is no longer available to read.",
  invalid_brief: "The paper facts could not be checked.",
  generation_unavailable: "Reading was unavailable.",
  queue_unavailable: "Reading was unavailable.",
  not_indexed: "The paper is not ready to read.",
  no_text: "No readable text was available.",
  no_readable_text: "No readable text was available.",
  context_limit: "Only selected sections could be read.",
  section_budget: "Only selected sections could be read.",
  timeout: "Reading ran out of time.",
  unavailable: "Reading was unavailable.",
  changed: "The paper changed during reading.",
};

function PageCitation({ source, record }: {
  source: ComparisonCitation;
  record: AnswerComparison["records"][number];
}) {
  const citation: Citation = {
    ...source, marker: source.marker ?? 0, record_id: record.record_id,
    record_title: record.title, text: source.quote, context_path: [], regions: [],
  };
  const label = openCitationLabel(citation);
  // A comparison's markers are not the answer's citation markers, so the
  // link names its answer but no citation to re-read (IR-578).
  const { to, state } = useCitationLink(citation, { resolvable: false });
  return (
    <Link to={to} state={state}
      aria-label={label} title={label}
      className="inline-flex rounded px-1.5 py-0.5 text-xs font-medium text-brand bg-brand/10 hover:bg-brand/20 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/40">
      {source.page === null ? "Source" : `p. ${source.page}`}
    </Link>
  );
}

function Cell({ cell, record, unavailable }: {
  cell?: ComparisonCell;
  record: AnswerComparison["records"][number];
  unavailable: boolean;
}) {
  if (unavailable) return <span className="text-stone-600">Unavailable</span>;
  if (cell?.state === "not_reported") return <span className="text-stone-600">Not reported</span>;
  if (!cell) return <span className="text-stone-600">Unverified</span>;
  const checked = cell.values.filter((value) => value.citations.length > 0);
  if (checked.length === 0) return <span className="text-stone-600">Unverified</span>;
  return (
    <div>
      <ul className="space-y-2">
      {checked.map((value, index) => (
        <li key={index}>
          <span className="whitespace-pre-wrap">{value.value}</span>
          <span className="ml-1 inline-flex flex-wrap gap-1">
            {value.citations.map((source, sourceIndex) => <PageCitation key={sourceIndex} source={source} record={record} />)}
          </span>
        </li>
      ))}
      </ul>
      {cell.state === "unsupported" && <p className="mt-1 text-xs text-stone-600">Some claims could not be verified.</p>}
    </div>
  );
}

export function ComparisonTable({ comparison }: { comparison: AnswerComparison }) {
  const captionId = useId();
  const restricted = new Set(comparison.coverage.filter((item) => item.state === "not_permitted").map((item) => item.record_id));
  const unavailable = new Set(comparison.coverage.filter((item) => item.state === "could_not_read").map((item) => item.record_id));
  const records = comparison.records.filter((record) => !restricted.has(record.record_id));
  return (
    <div className="mb-5">
      {records.length > 0 && (
        <div role="region" aria-labelledby={captionId} tabIndex={0}
          className="max-w-full overflow-x-auto rounded-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/40">
          <table className="w-full border-collapse text-left text-sm text-stone-800">
            <caption id={captionId} className="pb-3 text-left font-semibold text-stone-800">Paper comparison</caption>
            <thead className="bg-stone-50">
              <tr className="border-y border-stone-200">
                <th scope="col" className="min-w-[9rem] px-3 py-3 font-medium">Dimension</th>
                {records.map((record) => (
                  <th key={record.record_id} scope="col" className="min-w-[12rem] px-3 py-3 font-medium">
                    <Link to={`/records/${record.record_id}`} className="text-brand hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/40">{record.title}</Link>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {comparison.rows.map((row) => (
                <tr key={row.dimension} className="border-b border-stone-200 align-top">
                  <th scope="row" className="px-3 py-3 font-medium">{row.label}</th>
                  {records.map((record) => (
                    <td key={record.record_id} className="px-3 py-3">
                      <Cell cell={row.cells.find((cell) => cell.record_id === record.record_id)} record={record} unavailable={unavailable.has(record.record_id)} />
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <aside aria-label="Comparison coverage" className="mt-3 text-xs text-stone-600">
        <p className="font-medium text-stone-700">Reading coverage</p>
        <ul className="mt-1 space-y-1">
          {comparison.coverage.map((item, index) => {
            const record = records.find((entry) => entry.record_id === item.record_id);
            return (
              <li key={index}>
                {item.state !== "not_permitted" && record && <span>{record.title}: </span>}
                {COVERAGE_LABELS[item.state]}
                {item.state !== "not_permitted" && item.reason && REASON_LABELS[item.reason] && ` · ${REASON_LABELS[item.reason]}`}
              </li>
            );
          })}
        </ul>
        {comparison.removed_claims > 0 && <p className="mt-2">{comparison.removed_claims} unsupported {comparison.removed_claims === 1 ? "claim" : "claims"} removed.</p>}
      </aside>
    </div>
  );
}
