import { useEffect, useState } from "react";

import { recordsApi } from "@/api/records";
import { cn, formatDate } from "@/lib/utils";
import type {
  RecordTracker,
  TrackerPartyRow,
  TrackerPartyState,
  TrackerRoutingGroup,
} from "@/types/records";

interface ReviewRoutingTrackerProps {
  recordId: number;
}

/**
 * Presentation only: glyph and colour per state (workflow_routing_architecture.md
 * §9.1). Every *word* on this panel -- party names, states, outcomes -- comes
 * from the server, so an institution can rename one without a release and the
 * student/staff wording of Intake stays the server's call.
 */
const STATE_META: Record<TrackerPartyState, { glyph: string; tone: string; muted: boolean }> = {
  completed:     { glyph: "✓", tone: "text-emerald-700", muted: false },
  active:        { glyph: "●", tone: "text-brand",       muted: false },
  withdrawn:     { glyph: "–", tone: "text-stone-500",   muted: true },
  awaiting:      { glyph: "○", tone: "text-stone-500",   muted: true },
  not_requested: { glyph: "○", tone: "text-stone-500",   muted: true },
};

/** Outcome colour. Pending is not an outcome worth colouring. */
const OUTCOME_TONE: Record<string, string> = {
  cleared: "text-emerald-700",
  approved: "text-emerald-700",
  declined: "text-amber-700",
  not_cleared: "text-red-700",
  negative_finding: "text-red-700",
  rejected: "text-red-700",
};

const HEADING_ID = "review-routing-tracker-heading";

/**
 * The Review & Routing Tracker (IR-258, ADR-021 §14).
 *
 * Replaces the per-office clearance track. It answers who holds the record
 * now, who has finished and how, who was never asked, where the record was
 * routed, and what revisions were asked for -- all read from
 * `GET /records/<id>/tracker/`, nothing derived here.
 *
 * The **Preserved** badge is carried over from `ClearanceTrack` verbatim: it is
 * the one place the thesis contribution -- a clearance surviving another
 * office's resubmission request -- is visible on screen.
 */
export function ReviewRoutingTracker({ recordId }: ReviewRoutingTrackerProps) {
  const [data, setData] = useState<RecordTracker | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setData(null);
    setFailed(false);
    recordsApi
      .tracker(recordId)
      .then(({ data: payload }) => {
        if (!cancelled) setData(payload);
      })
      .catch(() => {
        if (!cancelled) setFailed(true);
      });
    return () => {
      cancelled = true;
    };
  }, [recordId]);

  return (
    <section
      aria-labelledby={HEADING_ID}
      className="bg-white border border-stone-200 rounded-2xl p-5"
    >
      <div className="flex items-center justify-between gap-3 mb-3">
        <h2
          id={HEADING_ID}
          className="text-[11px] font-bold uppercase tracking-wider text-stone-500"
        >
          Review &amp; Routing
        </h2>
        {data && (
          <span className="px-2 py-0.5 rounded-md bg-stone-100 text-[11px] font-bold text-stone-700">
            {data.workflow_state_label}
          </span>
        )}
      </div>

      {failed ? (
        <p role="alert" className="text-[12px] text-stone-600">
          Could not load the review tracker. Reload the page to try again.
        </p>
      ) : !data ? (
        <div aria-hidden className="space-y-2">
          {[0, 1, 2, 3].map((i) => (
            <div key={i} className="h-4 rounded bg-stone-100 animate-pulse" />
          ))}
        </div>
      ) : (
        <TrackerBody data={data} />
      )}
    </section>
  );
}

function TrackerBody({ data }: { data: RecordTracker }) {
  return (
    <div className="space-y-4">
      {data.current_holders.length > 0 && (
        <div>
          <p id="tracker-holders-label" className="text-[11px] font-semibold text-stone-500 mb-1">
            Currently with
          </p>
          <ul aria-labelledby="tracker-holders-label" className="flex flex-wrap gap-1.5">
            {data.current_holders.map((h) => (
              <li
                key={h.party}
                className="px-2 py-0.5 rounded-md bg-brand-50 text-brand text-[12px] font-bold"
              >
                {h.label}
              </li>
            ))}
          </ul>
        </div>
      )}

      <table className="w-full text-left border-collapse">
        <caption className="sr-only">Parties</caption>
        <thead className="sr-only">
          <tr>
            <th scope="col">Party</th>
            <th scope="col">Status</th>
            <th scope="col">Date</th>
          </tr>
        </thead>
        <tbody>
          {data.parties.map((row) => (
            <PartyRow key={row.party} row={row} />
          ))}
        </tbody>
      </table>

      <RoutingHistory
        groups={data.routing_history}
        recordedFrom={data.routing_recorded_from}
      />

      {data.resubmissions.length > 0 && (
        <div>
          <h3
            id="tracker-resubmissions-label"
            className="text-[11px] font-bold uppercase tracking-wider text-stone-500 mb-1.5"
          >
            Resubmission history
          </h3>
          <ol aria-labelledby="tracker-resubmissions-label" className="space-y-2">
            {data.resubmissions.map((r) => (
              <li key={r.id} className="text-[12px] text-stone-700">
                <span className="font-bold text-stone-900">{r.label}</span> asked for changes
                {" · "}
                <span className="font-semibold">{r.state_label}</span>
                <span className="text-stone-500"> · {formatDate(r.created_at, "MMM d")}</span>
                {r.reason && (
                  <p className="text-stone-600 mt-0.5 leading-relaxed">“{r.reason}”</p>
                )}
              </li>
            ))}
          </ol>
        </div>
      )}
    </div>
  );
}

function PartyRow({ row }: { row: TrackerPartyRow }) {
  const meta = STATE_META[row.state];
  // An outcome is shown once there is one. "Pending" is not a conclusion.
  const outcome = row.outcome && row.outcome !== "pending" ? row : null;

  return (
    <tr className="border-t border-stone-100 first:border-t-0 align-top">
      <th scope="row" className="py-1.5 pr-2 font-normal">
        <span className="flex items-center gap-2">
          <span aria-hidden className={cn("w-3 text-center text-[12px] leading-none", meta.tone)}>
            {meta.glyph}
          </span>
          <span
            className={cn(
              "text-[13px]",
              meta.muted ? "text-stone-500" : "font-bold text-stone-900",
            )}
          >
            {row.label}
          </span>
        </span>
      </th>
      <td className="py-1.5 pr-2">
        <span className="flex items-center gap-1.5 flex-wrap text-[11px]">
          <span className={cn("font-semibold", meta.tone)}>{row.state_label}</span>
          {outcome && (
            <span className={cn("font-semibold", OUTCOME_TONE[outcome.outcome ?? ""] ?? "text-stone-700")}>
              · {outcome.outcome_label}
            </span>
          )}
          {row.preserved && (
            <span
              className="px-1.5 py-0.5 rounded bg-emerald-50 text-emerald-700 border border-emerald-200 text-[10px] font-bold flex items-center gap-1"
              title="Cleared before the current submission and carried over — this office will not review again"
            >
              <i className="fas fa-shield-halved text-[8px]" aria-hidden />
              Preserved
            </span>
          )}
        </span>
      </td>
      <td className="py-1.5 text-right text-[11px] text-stone-500 whitespace-nowrap">
        {row.at ? formatDate(row.at, "MMM d") : ""}
      </td>
    </tr>
  );
}

function RoutingHistory({
  groups,
  recordedFrom,
}: {
  groups: TrackerRoutingGroup[];
  recordedFrom: string | null;
}) {
  return (
    <div>
      <h3
        id="tracker-routing-label"
        className="text-[11px] font-bold uppercase tracking-wider text-stone-500 mb-1.5"
      >
        Routing history
      </h3>
      {groups.length === 0 ? (
        <p className="text-[12px] text-stone-500">No routing recorded yet.</p>
      ) : (
        <ol aria-labelledby="tracker-routing-label" className="space-y-2">
          {groups.map((g) => (
            <li key={g.group_id} className="text-[12px] text-stone-700">
              <span className="font-semibold text-stone-900">
                {g.from_label
                  ? `${g.from_label} → ${g.to_labels.join(" + ")}`
                  : `Submitted to ${g.to_labels.join(" + ")}`}
              </span>
              <span className="text-stone-500">
                {" · "}
                {formatDate(g.at, "MMM d")}
                {g.actor && ` · ${g.actor}`}
              </span>
              {g.reason && (
                <p className="text-stone-600 mt-0.5 leading-relaxed">“{g.reason}”</p>
              )}
            </li>
          ))}
        </ol>
      )}
      {recordedFrom && (
        <p className="text-[11px] text-stone-500 mt-2">
          Routing recorded from {formatDate(recordedFrom)}.
        </p>
      )}
    </div>
  );
}
