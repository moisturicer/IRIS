import { useEffect, useState, type ReactNode } from "react";

import { reviewsApi } from "@/api/reviews";
import { PageHeader } from "@/components/layout/PageHeader";
import { EmptyState } from "@/components/shared/EmptyState";
import { Input, Select, Skeleton } from "@/components/ui";
import { formatDate } from "@/lib/utils";
import type { AnalyticsTimeInStage, WorkflowAnalytics } from "@/types/reviews";

/**
 * Workflow analytics (IR-626, ADR-043).
 *
 * Every figure is the server's, computed from the workflow audit log
 * (`backend/apps/reviews/analytics.py`); this page only lays it out. An
 * office sees its own figures and RDCO every party's. Three things are said
 * on the page rather than left to be assumed: when the log starts, that time
 * in stage is elapsed time rather than effort, and which cells hold too few
 * records to show a median. Nothing here names or ranks a reviewer.
 */

const POLICY_LABEL: Record<string, string> = {
  clearance_aware: "Clearance-aware",
  restart_all: "Restart-all",
};

const policyLabel = (policy: string) => POLICY_LABEL[policy] ?? policy;

/** Hours as the reader thinks of them: hours under a day, days after. */
function duration(hours: number): string {
  return hours < 24 ? `${hours.toFixed(1)} h` : `${(hours / 24).toFixed(1)} days`;
}

const TABLE = "w-full text-left text-sm";
const HEAD = "border-b border-stone-200 py-2 pr-4 font-medium text-stone-600";
const CELL = "border-b border-stone-100 py-2 pr-4 tabular-nums";

function Section({ id, title, note, children }: {
  id: string; title: string; note?: ReactNode; children: ReactNode;
}) {
  return (
    <section aria-labelledby={id} className="mb-8">
      <h2 id={id} className="mb-1 text-lg font-semibold text-stone-900">{title}</h2>
      {note && <p className="mb-3 max-w-3xl text-sm text-stone-600">{note}</p>}
      <div className="overflow-x-auto">{children}</div>
    </section>
  );
}

export default function ReviewAnalyticsPage() {
  const [office, setOffice] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [data, setData] = useState<WorkflowAnalytics | null>(null);
  // The offices the reader may choose from, kept from the unfiltered answer:
  // a narrowed answer names only the office asked for.
  const [offices, setOffices] = useState<WorkflowAnalytics["parties"]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setLoadError(null);
    reviewsApi.analytics({ office, from, to })
      .then(({ data: next }) => {
        if (cancelled) return;
        setData(next);
        if (!office) setOffices(next.parties);
      })
      .catch(() => {
        if (!cancelled) setLoadError("Workflow analytics could not be loaded.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [office, from, to]);

  const label = (party: string) =>
    data?.parties.find((p) => p.party === party)?.label ?? party.toUpperCase();

  const figure = (cell: AnalyticsTimeInStage, which: "median" | "p90",
                  thresholds: WorkflowAnalytics["thresholds"]) => {
    const hours = which === "median" ? cell.median_hours : cell.p90_hours;
    if (hours != null) return duration(hours);
    const needed = thresholds[which];
    return <span className="text-stone-500">Too few records ({cell.records} of {needed})</span>;
  };

  return (
    <div>
      <PageHeader
        title="Workflow Analytics"
        description="How long each office holds a record, what is open and overdue now, and how many new versions kept a clearance."
      />

      <div className="mb-6 flex flex-wrap items-end gap-4">
        {offices.length > 1 && (
          <div className="w-48">
            <Select label="Office" value={office} onChange={(e) => setOffice(e.target.value)}>
              <option value="">Every office</option>
              {offices.map((p) => <option key={p.party} value={p.party}>{p.label}</option>)}
            </Select>
          </div>
        )}
        <div className="w-44">
          <Input label="From" type="date" value={from} onChange={(e) => setFrom(e.target.value)} />
        </div>
        <div className="w-44">
          <Input label="To" type="date" value={to} onChange={(e) => setTo(e.target.value)} />
        </div>
      </div>

      {loadError ? (
        <EmptyState tone="error" icon="fa-triangle-exclamation" title={loadError}
                    message="Try again in a moment." />
      ) : loading && !data ? (
        <Skeleton className="h-64 w-full" />
      ) : data && (
        <div aria-busy={loading}>
          {loading && <p role="status" className="mb-3 text-sm text-stone-600">Updating…</p>}
          <p className="mb-6 max-w-3xl rounded-md bg-stone-50 p-3 text-sm text-stone-700">
            {data.data_since
              ? <>Figures start on {formatDate(data.data_since)}, the first workflow event recorded for {data.parties.length > 1 ? "these offices" : "this office"}. Work before then was never logged, so it is absent from these figures, not counted as zero.</>
              : <>No workflow events have been recorded yet, so there is nothing to measure.</>}
            {" "}Times are Asia/Manila; weeks start on Monday.
          </p>

          <Section id="open-now" title="Open now"
                   note="Overdue counts only assignments with a due date whose clock is running. A clock waiting on the owner is paused. Due dates exist only on assignments opened since they were introduced (IR-619), or for an office with a configured turnaround; the rest are under No due date, never counted as on time.">
            <table className={TABLE} aria-labelledby="open-now">
              <thead>
                <tr>
                  {["Office", "Open", "In pool", "Open seats", "Overdue", "Overdue seats", "Paused", "No due date"]
                    .map((h) => <th key={h} scope="col" className={HEAD}>{h}</th>)}
                </tr>
              </thead>
              <tbody>
                {data.open_now.map((row) => (
                  <tr key={row.party}>
                    <th scope="row" className={`${CELL} font-medium`}>{label(row.party)}</th>
                    {[row.open, row.unseated, row.open_seats, row.overdue, row.overdue_seats,
                      row.paused, row.undated].map((n, i) => <td key={i} className={CELL}>{n}</td>)}
                  </tr>
                ))}
              </tbody>
            </table>
          </Section>

          <Section id="time-in-stage" title="Time in stage"
                   note={<>Elapsed time from an office receiving a record to its turn closing, including nights, weekends and waits on the author. It is not hands-on effort. A cell needs {data.thresholds.median} records for a median and {data.thresholds.p90} for a 90th percentile. &ldquo;Still open&rdquo; means open now.</>}>
            {data.time_in_stage.length === 0 ? (
              <p className="text-sm text-stone-600">No completed turns in this range.</p>
            ) : (
              <table className={TABLE} aria-labelledby="time-in-stage">
                <thead>
                  <tr>
                    {["Office", "Record type", "Records", "Median", "90th percentile"]
                      .map((h) => <th key={h} scope="col" className={HEAD}>{h}</th>)}
                  </tr>
                </thead>
                <tbody>
                  {data.time_in_stage.map((cell) => (
                    <tr key={`${cell.party}:${cell.record_type ?? ""}`}>
                      <th scope="row" className={`${CELL} font-medium`}>{label(cell.party)}</th>
                      <td className={CELL}>{cell.record_type ?? "All record types"}</td>
                      <td className={CELL}>{cell.records}</td>
                      <td className={CELL}>{figure(cell, "median", data.thresholds)}</td>
                      <td className={CELL}>{figure(cell, "p90", data.thresholds)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
            <ul className="mt-3 space-y-1 text-sm text-stone-600">
              {data.unmeasured.map((u) => (
                <li key={u.party}>
                  Not measured for {label(u.party)}: {u.started_before_log} began before the log,{" "}
                  {u.ended_not_completed} ended by a decision or withdrawal, {u.still_open} still open.
                </li>
              ))}
            </ul>
          </Section>

          <Section id="throughput" title="Records entering and leaving, by week">
            {data.throughput.length === 0 ? (
              <p className="text-sm text-stone-600">No records entered or left in this range.</p>
            ) : (
              <table className={TABLE} aria-labelledby="throughput">
                <thead>
                  <tr>
                    {["Week of", "Office", "Entered", "Left"]
                      .map((h) => <th key={h} scope="col" className={HEAD}>{h}</th>)}
                  </tr>
                </thead>
                <tbody>
                  {data.throughput.map((row) => (
                    <tr key={`${row.week_start}:${row.party}`}>
                      <th scope="row" className={`${CELL} font-medium`}>{formatDate(row.week_start)}</th>
                      <td className={CELL}>{label(row.party)}</td>
                      <td className={CELL}>{row.entered}</td>
                      <td className={CELL}>{row.left}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </Section>

          <Section id="revision-cycles" title="New versions and preserved clearances"
                   note="A new version answering a revision request, and how many offices' clearances it kept. These are operational counts, not the ADR-004 comparison.">
            {data.revision_cycles.length === 0 ? (
              <p className="text-sm text-stone-600">No new versions in this range.</p>
            ) : (
              <table className={TABLE} aria-labelledby="revision-cycles">
                <thead>
                  <tr>
                    {["Policy", "New versions", "Kept a clearance", "Clearances kept"]
                      .map((h) => <th key={h} scope="col" className={HEAD}>{h}</th>)}
                  </tr>
                </thead>
                <tbody>
                  {data.revision_cycles.map((row) => (
                    <tr key={row.policy}>
                      <th scope="row" className={`${CELL} font-medium`}>{policyLabel(row.policy)}</th>
                      <td className={CELL}>{row.cycles}</td>
                      <td className={CELL}>{row.cycles_preserving}</td>
                      <td className={CELL}>{row.preserved_clearances}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
            {data.preserved_by_office.length > 0 && (
              <ul className="mt-3 space-y-1 text-sm text-stone-600">
                {data.preserved_by_office.map((row) => (
                  <li key={`${row.party}:${row.policy}`}>
                    {label(row.party)}&rsquo;s clearance kept {row.preserved_clearances}{" "}
                    {row.preserved_clearances === 1 ? "time" : "times"} ({policyLabel(row.policy)}).
                  </li>
                ))}
              </ul>
            )}
          </Section>
        </div>
      )}
    </div>
  );
}
