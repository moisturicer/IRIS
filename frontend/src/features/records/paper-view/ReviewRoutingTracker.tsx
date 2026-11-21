import { useEffect, useState, type ReactNode } from "react";

import { recordsApi } from "@/api/records";
import { isRequestTimeout } from "@/api/requestPolicy";
import { FOCUS_RING } from "@/components/ui/interaction";
import { cn } from "@/lib/utils";
import type {
  RecordTracker,
  TrackerPartyRow,
  TrackerOutcome,
  TrackerPartyState,
} from "@/types/records";
import { RailHeading } from "./headings";

interface ReviewRoutingTrackerProps {
  recordId: number;
  /** Where the record stands, drawn first (IR-1264): the header no longer carries it. */
  status?: ReactNode;
  /** Opens the Review section, which holds the routing and resubmission history. */
  onOpenHistory?: () => void;
}

/**
 * Presentation only: glyph and colour per state (workflow_routing_architecture.md
 * §9.1). Every *word* on this panel -- party names, states, outcomes -- comes
 * from the server, so an institution can rename one without a release. The one
 * decision made here is that the retired Intake is never a step (`RETIRED_PARTY`).
 */
const STATE_META: Record<TrackerPartyState, { glyph: string; tone: string; muted: boolean }> = {
  completed:     { glyph: "✓", tone: "text-stone-900", muted: false },
  active:        { glyph: "●", tone: "text-brand",       muted: false },
  withdrawn:     { glyph: "–", tone: "text-stone-500",   muted: true },
  awaiting:      { glyph: "○", tone: "text-stone-500",   muted: true },
  not_requested: { glyph: "○", tone: "text-stone-500",   muted: true },
  // RDCO on a record no office has held: nothing waits on it (IR-269).
  not_required:  { glyph: "—", tone: "text-stone-500",   muted: true },
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
 * The Review & Routing summary in Record details (IR-258, ADR-021 §14, made a
 * summary by IR-1264).
 *
 * Where the record stands, then one line per party: how far it has got, its
 * outcome, and whether its clearance was kept from an earlier version -- read
 * from `GET /records/<id>/tracker/`, nothing derived here. Who reviewed, when,
 * where the record was routed and what revisions were asked for are the Review
 * section's (its Details tab and Conversation), which `onOpenHistory` opens;
 * the rail repeated them in full before IR-1264.
 *
 * The **Preserved** badge is carried over from `ClearanceTrack` verbatim: it is
 * the one place on the Overview where the thesis contribution -- a clearance
 * surviving another office's resubmission request -- is visible.
 */
export function ReviewRoutingTracker({ recordId, status, onOpenHistory }: ReviewRoutingTrackerProps) {
  const [data, setData] = useState<RecordTracker | null>(null);
  /** Why the read failed (IR-906): a timeout is worded as one, and both offer a retry. */
  const [failed, setFailed] = useState<"failed" | "interrupted" | null>(null);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setData(null);
    setFailed(null);
    recordsApi
      .tracker(recordId)
      .then(({ data: payload }) => {
        if (!cancelled) setData(payload);
      })
      .catch((error: unknown) => {
        if (!cancelled) setFailed(isRequestTimeout(error) ? "interrupted" : "failed");
      });
    return () => {
      cancelled = true;
    };
  }, [recordId, attempt]);

  return (
    <section
      aria-labelledby={HEADING_ID}
      className="bg-white ring-1 ring-stone-200 rounded-card p-5 shadow-card"
    >
      <RailHeading id={HEADING_ID} className="mb-3">Review &amp; Routing</RailHeading>
      {/* Where the record stands, once on the page (IR-525, moved here by IR-1264). */}
      {status && (
        <div className="mb-3 flex items-center justify-between gap-3">
          <span className="text-xs text-stone-500">Status</span>
          {status}
        </div>
      )}

      {failed ? (
        <div role="alert" className="space-y-2 text-xs text-stone-600">
          <p>
            {failed === "interrupted"
              ? "The review tracker took too long to load."
              : "Could not load the review tracker."}
          </p>
          <button
            type="button"
            onClick={() => setAttempt((n) => n + 1)}
            className={cn("font-semibold text-brand hover:underline min-h-11", FOCUS_RING)}
          >
            {failed === "interrupted" ? "Retry" : "Try again"}
          </button>
        </div>
      ) : !data ? (
        <div role="status">
          <span className="sr-only">Loading the review tracker…</span>
          <div aria-hidden className="space-y-2">
            {[0, 1, 2, 3].map((i) => (
              <div key={i} className="h-4 rounded-control bg-stone-100 animate-pulse" />
            ))}
          </div>
        </div>
      ) : (
        <TrackerBody data={data} onOpenHistory={onOpenHistory} />
      )}
    </section>
  );
}

/**
 * Intake is retired (ADR-032 §1, §13): stored rows that hold it are history,
 * never a step, so it is neither a party row nor someone the record is "with"
 * (frontend_redesign_spec §0, invariant 1). The routing history below still
 * names it, in the server's words, as the record's past.
 */
const RETIRED_PARTY = "intake";

function TrackerBody({ data, onOpenHistory }: { data: RecordTracker; onOpenHistory?: () => void }) {
  const parties = data.parties.filter((p) => p.party !== RETIRED_PARTY);
  return (
    <div className="space-y-3">
      {parties.length === 0 ? (
        <p className="text-small text-stone-600">No routing recorded yet.</p>
      ) : (
      <table className="w-full text-left border-collapse">
        <caption className="sr-only">Parties</caption>
        <thead className="sr-only">
          <tr>
            <th scope="col">Party</th>
            <th scope="col">Status</th>
          </tr>
        </thead>
        <tbody>
          {parties.map((row) => (
            <PartyRow key={row.party} row={row} />
          ))}
        </tbody>
      </table>
      )}

      {onOpenHistory && (
        <button
          type="button"
          onClick={onOpenHistory}
          className={cn(
            "inline-flex min-h-11 reading-split:min-h-9 items-center gap-1.5 rounded-control text-xs font-semibold text-brand underline decoration-stone-300 underline-offset-[3px] hover:decoration-brand",
            FOCUS_RING,
          )}
        >
          See review history
          <i className="fas fa-arrow-right text-3xs" aria-hidden />
        </button>
      )}
    </div>
  );
}

/**
 * §9.1's ◐: the party asked the owner for a document and is waiting on it
 * (ADR-022). Overrides the state's glyph, not its words.
 */
const AWAITING_DOCUMENT_META = { glyph: "◐", tone: "text-brand", muted: false };

/**
 * ui-ux/16's ◌: an active office whose pool nobody has claimed yet (ADR-032
 * §4). Overrides the glyph only.
 */
const IN_POOL_META = { glyph: "◌", tone: "text-brand", muted: false };

function PartyRow({ row }: { row: TrackerPartyRow }) {
  const meta = row.awaiting_document
    ? AWAITING_DOCUMENT_META
    : row.in_pool
      ? IN_POOL_META
      : STATE_META[row.state];
  // An outcome is shown once there is one. "Pending" is not a conclusion, and
  // an open revision request reads as *Changes requested* below rather than
  // as the review that made it (IR-272).
  const outcome =
    row.outcome && row.outcome !== "pending" && !(row.changes_requested && row.outcome === "declined")
      ? row.outcome
      : null;

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
      <td className="py-1.5">
        <span className="flex items-center justify-end gap-1.5 flex-wrap text-2xs text-right">
          <span className={cn("font-semibold", meta.tone)}>{row.state_label}</span>
          {outcome && (
            <span className={cn("font-semibold", OUTCOME_TONE[outcome])}>
              · {row.outcome_label}
            </span>
          )}
          {row.in_pool && <span className="font-semibold text-brand">· Unassigned</span>}
          {row.changes_requested && (
            <span className="font-semibold text-brand">· Changes requested</span>
          )}
          {row.awaiting_document && (
            <span className="font-semibold text-brand">· Awaiting document</span>
          )}
          {row.withdrawn_by_decision && (
            <span className="text-stone-600">· {row.withdrawn_by_decision}</span>
          )}
          {row.preserved && (
            <span
              className="px-1.5 py-0.5 rounded-control bg-stone-100 text-stone-900 border border-stone-300 text-2xs font-bold flex items-center gap-1"
              title="Cleared before the current submission and carried over — this office will not review again"
            >
              <i className="fas fa-shield-halved text-2xs" aria-hidden />
              Preserved
            </span>
          )}
        </span>
      </td>
    </tr>
  );
}
