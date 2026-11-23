import { useEffect, useId, useState, type ReactNode } from "react";

import { reviewsApi } from "@/api/reviews";
import { Handbook, RAIL_LIST, RailCaption, railItemClass, useSectionInView } from "@/components/layout/Handbook";
import { PageHeader } from "@/components/layout/PageHeader";
import { EmptyState } from "@/components/shared/EmptyState";
import { Button, Input, Select, Skeleton } from "@/components/ui";
import { COLOUR_TRANSITION, FOCUS_RING } from "@/components/ui/interaction";
import { failureMessage } from "@/lib/readFailure";
import { cn } from "@/lib/utils";
import type { AnalyticsTimeInStage, WorkflowAnalytics } from "@/types/reviews";

const formatDate = (value: string) => new Intl.DateTimeFormat("en-US", {
  month: "short", day: "numeric", year: "numeric", timeZone: "Asia/Manila",
}).format(new Date(value.length === 10 ? value + "T00:00:00+08:00" : value));

/**
 * Workflow analytics (IR-626, ADR-043).
 *
 * Every figure is the server's, computed from the workflow audit log
 * (`backend/apps/reviews/analytics.py`); this page only lays it out. It is
 * RDCO's alone, in its own sidebar section, with every party's figures
 * (IR-1216; offices saw their own before). Three things are said
 * on the page rather than left to be assumed: when the log starts (always
 * visible) and, in the "How these numbers are counted" disclosure (IR-1091),
 * that time in stage is elapsed time rather than effort and how many records a
 * cell needs for a median; cells holding too few say so in place. Nothing
 * here names or ranks a reviewer.
 *
 * Laid out as a typeset report (`Handbook`): the range in one stone bar, a
 * Contents rail of the four tables beside the column, and tables ruled with
 * hairlines. Time in stage draws each figure's length beside it, against the
 * longest 90th percentile in the table, so a slow office reads at a glance; the
 * bar is decoration and the figure says it.
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

const SECTIONS = [
  { id: "open-now", title: "Open now" },
  { id: "time-in-stage", title: "Time in stage" },
  { id: "throughput", title: "Records entering and leaving, by week" },
  { id: "revision-cycles", title: "New versions and preserved clearances" },
] as const;

const TABLE = "w-full text-left text-small";
const HEAD = "whitespace-nowrap border-b border-stone-300 bg-stone-50 px-3 py-2 font-medium text-stone-600 first:pl-4 last:pr-4";
const CELL = "border-b border-stone-200 px-3 py-2.5 tabular-nums text-stone-800 first:pl-4 last:pr-4";
// Numbers line up on their right edge, in figures of one width, so a column
// reads down as a comparison (audit LAY-05).
const NUM_HEAD = `${HEAD} text-right`;
const NUM_CELL = `${CELL} text-right`;
const ROW_HEAD = `${CELL} font-semibold text-stone-900`;

/** A count in a table: a zero steps back so the figures that matter stand out. */
function Count({ n, emphasis = false }: { n: number; emphasis?: boolean }) {
  if (n === 0) return <span className="text-stone-500">0</span>;
  return <span className={emphasis ? "font-semibold text-stone-900" : undefined}>{n}</span>;
}

/**
 * How the figures are counted, kept out of the way of the figures themselves.
 * Closed by default and not rendered until opened, so the page opens on
 * numbers. A button and a named region, as the reasoning summary is, so it is
 * found by role and name.
 */
function MethodDisclosure({ children }: { children: ReactNode }) {
  const [open, setOpen] = useState(false);
  const bodyId = useId();
  return (
    <div>
      <button
        type="button"
        aria-expanded={open}
        aria-controls={open ? bodyId : undefined}
        onClick={() => setOpen((wasOpen) => !wasOpen)}
        className={cn(
          "-ml-2 inline-flex items-center gap-1.5 rounded-control px-2 py-1 touch:min-h-11",
          "text-small font-medium text-stone-700 hover:bg-stone-100 hover:text-stone-900",
          COLOUR_TRANSITION,
          FOCUS_RING,
        )}
      >
        <i
          className={cn(
            "fas fa-chevron-right text-2xs transition-transform duration-200 motion-reduce:transition-none",
            open && "rotate-90",
          )}
          aria-hidden
        />
        How these numbers are counted
      </button>
      {open && (
        <div id={bodyId} role="region" aria-label="How these numbers are counted"
             className="mt-3 grid gap-x-8 gap-y-4 border-l border-stone-300 pl-4 text-small text-stone-700 sm:grid-cols-2">
          {children}
        </div>
      )}
    </div>
  );
}

function MethodNote({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div>
      <p className="font-semibold text-stone-900">{title}</p>
      <p className="mt-0.5 text-justified text-stone-600">{children}</p>
    </div>
  );
}

function Section({ id, title, children, notes, scrollRegionLabel }: {
  id: string; title: string; children: ReactNode; notes?: ReactNode; scrollRegionLabel?: string;
}) {
  return (
    <section aria-labelledby={id} className="scroll-mt-6 py-8 first:pt-0 last:pb-0">
      <h2 id={id} className="mb-4 font-display text-title font-semibold text-stone-900">{title}</h2>
      <div
        className={cn("overflow-x-auto", scrollRegionLabel && FOCUS_RING)}
        {...(scrollRegionLabel
          ? { role: "region" as const, tabIndex: 0, "aria-label": scrollRegionLabel }
          : {})}
      >
        {children}
      </div>
      {notes}
    </section>
  );
}

/** A quiet line under a table, e.g. what could not be measured. */
function Notes({ children }: { children: ReactNode }) {
  return <ul className="mt-3 space-y-1 text-small text-stone-600">{children}</ul>;
}

/** A figure's length against the table's longest: decoration beside the number. */
function Bar({ hours, longest, strong }: { hours: number; longest: number; strong?: boolean }) {
  const share = longest > 0 ? Math.max(2, Math.round((hours / longest) * 100)) : 0;
  return (
    <span aria-hidden className="hidden h-1.5 w-20 overflow-hidden rounded-full bg-stone-100 sm:inline-block">
      <span className={cn("block h-full rounded-full", strong ? "bg-stone-700" : "bg-stone-400")}
            style={{ width: `${share}%` }} />
    </span>
  );
}

export default function ReviewAnalyticsPage() {
  const [reload, setReload] = useState(0);
  const [office, setOffice] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [data, setData] = useState<WorkflowAnalytics | null>(null);
  // The offices the reader may choose from, kept from the unfiltered answer:
  // a narrowed answer names only the office asked for.
  const [offices, setOffices] = useState<WorkflowAnalytics["parties"]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const reading = useSectionInView(data ? SECTIONS.map((s) => s.id) : []);

  const invalidRange = Boolean(from && to && from > to);

  useEffect(() => {
    if (invalidRange) {
      setLoading(false);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setLoadError(null);
    reviewsApi.analytics({ office, from, to })
      .then(({ data: next }) => {
        if (cancelled) return;
        setData(next);
        if (!office) setOffices(next.parties);
      })
      .catch((err: unknown) => {
        if (!cancelled) setLoadError(failureMessage(err));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [office, from, to, reload, invalidRange]);

  const label = (party: string) =>
    data?.parties.find((p) => p.party === party)?.label ?? party.toUpperCase();

  const longest = Math.max(0, ...(data?.time_in_stage ?? []).map((c) => c.p90_hours ?? c.median_hours ?? 0));

  const figure = (cell: AnalyticsTimeInStage, which: "median" | "p90",
                  thresholds: WorkflowAnalytics["thresholds"]) => {
    const hours = which === "median" ? cell.median_hours : cell.p90_hours;
    if (hours != null) {
      return (
        <span className="inline-flex items-center justify-end gap-3">
          <Bar hours={hours} longest={longest} strong={which === "median"} />
          <span className="whitespace-nowrap">{duration(hours)}</span>
        </span>
      );
    }
    const needed = thresholds[which];
    return <span className="text-stone-500">Too few records ({cell.records} of {needed})</span>;
  };

  return (
    <div>
      <PageHeader
        title="Workflow analytics"
        description="How long each office holds a record, what is open and overdue now, and how many new versions kept a clearance."
      />

      <div className="mb-3 flex flex-wrap items-end gap-x-4 gap-y-3 rounded-card bg-stone-100 px-4 py-3">
        {offices.length > 1 && (
          <div className="w-full sm:w-48">
            <Select label="Office" value={office} onChange={(e) => setOffice(e.target.value)}>
              <option value="">Every office</option>
              {offices.map((p) => <option key={p.party} value={p.party}>{p.label}</option>)}
            </Select>
          </div>
        )}
        <div className="min-w-0 flex-1 sm:w-44 sm:flex-none">
          <Input label="From" type="date" value={from} onChange={(e) => setFrom(e.target.value)} />
        </div>
        <div className="min-w-0 flex-1 sm:w-44 sm:flex-none">
          <Input label="To" type="date" value={to} onChange={(e) => setTo(e.target.value)} />
        </div>
        {loading && data && (
          <p role="status" className="flex items-center gap-2 pb-2 text-small text-stone-600 sm:ml-auto">
            <i className="fas fa-circle-notch fa-spin text-stone-500 motion-reduce:animate-none" aria-hidden />
            Updating…
          </p>
        )}
      </div>

      {invalidRange && <p role="alert" className="mb-4 text-small text-brand">From must be on or before To.</p>}

      {loadError ? (
        <EmptyState tone="error" icon="fa-triangle-exclamation" title="Workflow analytics could not be loaded"
                    message={loadError}
                    action={<Button type="button" onClick={() => setReload((n) => n + 1)}>Try again</Button>} />
      ) : loading && !data ? (
        <div role="status" aria-label="Loading workflow analytics"><Skeleton className="h-64 w-full" onRetry={() => setReload((n) => n + 1)} /></div>
      ) : data && (
        <div aria-busy={loading} className="space-y-6">
          <div className="space-y-2">
            <p className="flex items-start gap-2 text-small text-stone-700">
              <i className="fas fa-clock-rotate-left mt-1 text-stone-500" aria-hidden />
              <span>
                {data.data_since
                  ? <>Figures start on {formatDate(data.data_since)}, the first workflow event recorded for {data.parties.length > 1 ? "these offices" : "this office"}. Work before then was never logged, so it is absent from these figures, not counted as zero.</>
                  : <>No workflow events have been recorded yet, so there is nothing to measure.</>}
              </span>
            </p>

            <MethodDisclosure>
              <MethodNote title="Open now">
                Overdue counts only assignments with a due date whose clock is running. A clock waiting on the owner is paused. Older assignments and offices without a configured turnaround may have no due date; these are listed separately, never counted as on time.
              </MethodNote>
              <MethodNote title="Time in stage">
                Elapsed time from an office receiving a record to its turn closing, including nights, weekends and waits on the author. It is not hands-on effort. A cell needs {data.thresholds.median} records for a median and {data.thresholds.p90} for a 90th percentile. &ldquo;Still open&rdquo; means open now.
              </MethodNote>
              <MethodNote title="Records entering and leaving, by week">
                Counts office visits. A record returning to the same office in one week counts again.
              </MethodNote>
              <MethodNote title="New versions and preserved clearances">
                A new version answering a revision request, and how many offices&rsquo; clearances it kept. These counts describe the workflow in use; they do not measure how much time clearance preservation saved.
              </MethodNote>
              <MethodNote title="Dates and times">
                Times are Asia/Manila; weeks start on Monday.
              </MethodNote>
            </MethodDisclosure>
          </div>

          <Handbook
            rail={
              <nav aria-label="Report sections">
                <RailCaption>In this report</RailCaption>
                <ul className={RAIL_LIST}>
                  {SECTIONS.map((s) => (
                    <li key={s.id}>
                      <a href={`#${s.id}`} aria-current={reading === s.id ? "location" : undefined}
                         className={railItemClass(reading === s.id)}>
                        {s.title}
                      </a>
                    </li>
                  ))}
                </ul>
              </nav>
            }
          >
            <div className="divide-y divide-stone-200">
              <Section id="open-now" title="Open now" scrollRegionLabel="Open now table">
                <table className={TABLE} aria-labelledby="open-now">
                  <thead>
                    <tr>
                      {["Office", "Open", "In pool", "Open seats", "Overdue", "Overdue seats", "Paused", "No due date"]
                        .map((h, i) => <th key={h} scope="col" className={i === 0 ? HEAD : NUM_HEAD}>{h}</th>)}
                    </tr>
                  </thead>
                  <tbody>
                    {data.open_now.map((row) => (
                      <tr key={row.party}>
                        <th scope="row" className={ROW_HEAD}>{label(row.party)}</th>
                        <td className={NUM_CELL}><Count n={row.open_count} emphasis /></td>
                        <td className={NUM_CELL}><Count n={row.unseated} /></td>
                        <td className={NUM_CELL}><Count n={row.open_seats} /></td>
                        <td className={NUM_CELL}><Count n={row.overdue} emphasis /></td>
                        <td className={NUM_CELL}><Count n={row.overdue_seats} /></td>
                        <td className={NUM_CELL}><Count n={row.paused} /></td>
                        <td className={NUM_CELL}><Count n={row.undated} /></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </Section>

              <Section
                id="time-in-stage"
                title="Time in stage"
                scrollRegionLabel="Time in stage table"
                notes={data.unmeasured.length > 0 && (
                  <Notes>
                    {data.unmeasured.map((u) => (
                      <li key={u.party}>
                        Not measured for {label(u.party)}: {u.started_before_log} began before the log,{" "}
                        {u.ended_not_completed} ended by a decision or withdrawal, {u.still_open} still open.
                      </li>
                    ))}
                  </Notes>
                )}
              >
                {data.time_in_stage.length === 0 ? (
                  <p className="text-small text-stone-600">No completed turns in this range.</p>
                ) : (
                  <table className={TABLE} aria-labelledby="time-in-stage">
                    <thead>
                      <tr>
                        {["Office", "Record type", "Records", "Median", "90th percentile"]
                          .map((h, i) => <th key={h} scope="col" className={i < 2 ? HEAD : NUM_HEAD}>{h}</th>)}
                      </tr>
                    </thead>
                    <tbody>
                      {data.time_in_stage.map((cell) => (
                        <tr key={`${cell.party}:${cell.record_type ?? ""}`}>
                          <th scope="row" className={ROW_HEAD}>{label(cell.party)}</th>
                          <td className={cn(CELL, !cell.record_type && "text-stone-600")}>{cell.record_type ?? "All record types"}</td>
                          <td className={NUM_CELL}>{cell.records}</td>
                          <td className={NUM_CELL}>{figure(cell, "median", data.thresholds)}</td>
                          <td className={NUM_CELL}>{figure(cell, "p90", data.thresholds)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </Section>

              <Section id="throughput" title="Records entering and leaving, by week">
                {data.throughput.length === 0 ? (
                  <p className="text-small text-stone-600">No records entered or left in this range.</p>
                ) : (
                  <table className={TABLE} aria-labelledby="throughput">
                    <thead>
                      <tr>
                        {["Week of", "Office", "Entered", "Left"]
                          .map((h, i) => <th key={h} scope="col" className={i < 2 ? HEAD : NUM_HEAD}>{h}</th>)}
                      </tr>
                    </thead>
                    <tbody>
                      {data.throughput.map((row) => (
                        <tr key={`${row.week_start}:${row.party}`}>
                          <th scope="row" className={ROW_HEAD}>{formatDate(row.week_start)}</th>
                          <td className={CELL}>{label(row.party)}</td>
                          <td className={NUM_CELL}><Count n={row.entered} /></td>
                          <td className={NUM_CELL}><Count n={row.left} /></td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </Section>

              <Section
                id="revision-cycles"
                title="New versions and preserved clearances"
                notes={data.preserved_by_office.length > 0 && (
                  <Notes>
                    {data.preserved_by_office.map((row) => (
                      <li key={`${row.party}:${row.policy}`}>
                        {label(row.party)}&rsquo;s clearance kept {row.preserved_clearances}{" "}
                        {row.preserved_clearances === 1 ? "time" : "times"} ({policyLabel(row.policy)}).
                      </li>
                    ))}
                  </Notes>
                )}
              >
                {data.revision_cycles.length === 0 ? (
                  <p className="text-small text-stone-600">No new versions in this range.</p>
                ) : (
                  <table className={TABLE} aria-labelledby="revision-cycles">
                    <thead>
                      <tr>
                        {["Policy", "New versions", "Kept a clearance", "Clearances kept"]
                          .map((h, i) => <th key={h} scope="col" className={i === 0 ? HEAD : NUM_HEAD}>{h}</th>)}
                      </tr>
                    </thead>
                    <tbody>
                      {data.revision_cycles.map((row) => (
                        <tr key={row.policy}>
                          <th scope="row" className={ROW_HEAD}>{policyLabel(row.policy)}</th>
                          <td className={NUM_CELL}><Count n={row.cycles} /></td>
                          <td className={NUM_CELL}><Count n={row.cycles_preserving} /></td>
                          <td className={NUM_CELL}><Count n={row.preserved_clearances} emphasis /></td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </Section>
            </div>
          </Handbook>
        </div>
      )}
    </div>
  );
}
