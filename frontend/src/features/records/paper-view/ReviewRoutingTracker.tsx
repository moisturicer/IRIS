import { useEffect, useState } from "react";

import { recordsApi } from "@/api/records";
import { cn, formatDate } from "@/lib/utils";
import type {
  RecordTracker,
  TrackerPartyRow,
  TrackerOutcome,
  TrackerPartyState,
  TrackerRoutingGroup,
} from "@/types/records";
import { RailHeading } from "./headings";

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
  completed:     { glyph: "✓", tone: "text-stone-900", muted: false },
  active:        { glyph: "●", tone: "text-brand",       muted: false },
  withdrawn:     { glyph: "–", tone: "text-stone-500",   muted: true },
  awaiting:      { glyph: "○", tone: "text-stone-500",   muted: true },
  not_requested: { glyph: "○", tone: "text-stone-500",   muted: true },
};

/** Outcome colour. Exhaustive, so an unstyled outcome fails `tsc`. */
const OUTCOME_TONE: Record<TrackerOutcome, string> = {
  pending: "text-stone-700",
  cleared: "text-stone-900",
  approved: "text-stone-900",
  declined: "text-brand",
  not_cleared: "text-brand",
  negative_finding: "text-brand",
  rejected: "text-brand",
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
      className="bg-white ring-1 ring-stone-200 rounded-2xl p-5 shadow-card"
    >
      <div className="flex items-center justify-between gap-3 mb-3">
        <RailHeading id={HEADING_ID}>Review &amp; Routing</RailHeading>
        {data && (
          <span className="px-2 py-0.5 rounded-md bg-stone-100 text-2xs font-bold text-stone-700">
            {data.workflow_state_label}
          </span>
        )}
      </div>

      {failed ? (
        <p role="alert" className="text-xs text-stone-600">
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
          <p id="tracker-holders-label" className="text-2xs font-semibold text-stone-500 mb-1">
            Currently with
          </p>
          <ul aria-labelledby="tracker-holders-label" className="flex flex-wrap gap-1.5">
            {data.current_holders.map((h) => (
              <li
                key={h.party}
                className="px-2 py-0.5 rounded-md bg-brand-50 text-brand text-xs font-bold"
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

      {data.document_requests && data.document_requests.length > 0 && (
        <div>
          <h3
            id="tracker-document-requests-label"
            className="text-2xs font-semibold uppercase tracking-[0.14em] text-stone-600 mb-1.5"
          >
            Document requests
          </h3>
          <ol aria-labelledby="tracker-document-requests-label" className="space-y-2">
            {data.document_requests.map((r) => (
              <li key={r.id} className="text-xs text-stone-700">
                <span className="font-bold text-stone-900">{r.label}</span> asked for{" "}
                {/* Each item with its state: accepted, still missing... (IR-263). */}
                {r.items.map((i) => `${i.label} (${i.state_label})`).join(", ")}
                {" · "}
                <span className="font-semibold">{r.state_label}</span>
                <span className="text-stone-500"> · {formatDate(r.created_at, "MMM d")}</span>
                {r.message && (
                  <p className="text-stone-600 mt-0.5 leading-relaxed break-words">“{r.message}”</p>
                )}
                {r.items
                  .filter((i) => i.rejection_reason)
                  .map((i) => (
                    <p key={i.id} className="text-stone-600 mt-0.5 leading-relaxed break-words">
                      {r.label} rejected an upload of {i.label}: “{i.rejection_reason}”
                    </p>
                  ))}
              </li>
            ))}
          </ol>
        </div>
      )}

      {data.resubmissions.length > 0 && (
        <div>
          <h3
            id="tracker-resubmissions-label"
            className="text-2xs font-semibold uppercase tracking-[0.14em] text-stone-600 mb-1.5"
          >
            Resubmission history
          </h3>
          <ol aria-labelledby="tracker-resubmissions-label" className="space-y-2">
            {data.resubmissions.map((r) => (
              <li key={r.id} className="text-xs text-stone-700">
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

/**
 * §9.1's ◐: the party asked the owner for a document and is waiting on it
 * (ADR-022). Overrides the state's glyph, not its words.
 */
const AWAITING_DOCUMENT_META = { glyph: "◐", tone: "text-brand", muted: false };

function PartyRow({ row }: { row: TrackerPartyRow }) {
  const meta = row.awaiting_document ? AWAITING_DOCUMENT_META : STATE_META[row.state];
  // An outcome is shown once there is one. "Pending" is not a conclusion.
  const outcome = row.outcome && row.outcome !== "pending" ? row.outcome : null;

  return (
    <tr className="border-t border-stone-100 first:border-t-0 align-top">
      <th scope="row" className="py-1.5 pr-2 font-normal">
        <span className="flex items-center gap-2">
          <span aria-hidden className={cn("w-3 text-center text-xs leading-none", meta.tone)}>
            {meta.glyph}
          </span>
          <span
            className={cn(
              "text-sm",
              meta.muted ? "text-stone-500" : "font-bold text-stone-900",
            )}
          >
            {row.label}
          </span>
        </span>
      </th>
      <td className="py-1.5 pr-2">
        <span className="flex items-center gap-1.5 flex-wrap text-2xs">
          <span className={cn("font-semibold", meta.tone)}>{row.state_label}</span>
          {outcome && (
            <span className={cn("font-semibold", OUTCOME_TONE[outcome])}>
              · {row.outcome_label}
            </span>
          )}
          {row.awaiting_document && (
            <span className="font-semibold text-brand">· Awaiting document</span>
          )}
          {row.preserved && (
            <span
              className="px-1.5 py-0.5 rounded bg-stone-100 text-stone-900 border border-stone-300 text-2xs font-bold flex items-center gap-1"
              title="Cleared before the current submission and carried over — this office will not review again"
            >
              <i className="fas fa-shield-halved text-2xs" aria-hidden />
              Preserved
            </span>
          )}
        </span>
      </td>
      <td className="py-1.5 text-right text-2xs text-stone-500 whitespace-nowrap">
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
        className="text-2xs font-semibold uppercase tracking-[0.14em] text-stone-600 mb-1.5"
      >
        Routing history
      </h3>
      {groups.length === 0 ? (
        <p className="text-xs text-stone-500">No routing recorded yet.</p>
      ) : (
        <ol aria-labelledby="tracker-routing-label" className="space-y-2">
          {groups.map((g) => (
            <li key={g.group_id} className="text-xs text-stone-700">
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
        <p className="text-2xs text-stone-500 mt-2">
          Routing recorded from {formatDate(recordedFrom)}.
        </p>
      )}
    </div>
  );
}
