import { useId } from "react";

import { cn, formatDate } from "@/lib/utils";
import type { Carryover, RecordTracker, TrackerPartyRow, TrackerPartyState } from "@/types/records";

import { RailHeading } from "./headings";

/** Parties never asked are not part of this review: nothing to say of them. */
const UNASKED: ReadonlySet<TrackerPartyState> = new Set(["not_requested", "not_required"]);

/** The submitter holds the record; no party's seats are what it waits on. */
const SUBMITTER_HOLDS: ReadonlySet<RecordTracker["workflow_state"]> = new Set([
  "awaiting_resubmission",
  "awaiting_document",
]);

/** A glyph beside the server's words, never instead of them. */
const CARRYOVER_ICON: Record<Carryover, string> = {
  preserved: "fa-shield-halved",
  reset: "fa-arrow-rotate-left",
};

/**
 * Where the review stands (IR-624), above the Review section's timeline:
 * whose turn it is, each asked party's reviewers, state and due date, and
 * which clearances the latest version kept or reset. This is where clearance-
 * aware resubmission is seen working.
 *
 * Built from the tracker alone. Preserved and reset are the server's
 * `carryover`, worded by it with their version; nothing here works either
 * out. Seats are null to a viewer who may not read the review (IR-479), and
 * then no reviewer is named.
 */
export function ReviewStatus({ data }: { data: RecordTracker }) {
  const headingId = useId();
  const asked = data.parties.filter((p) => !UNASKED.has(p.state));

  return (
    <section aria-labelledby={headingId} className="space-y-3">
      <RailHeading id={headingId}>Where it stands</RailHeading>
      <p className="text-small font-semibold text-stone-900">{turnLine(data)}</p>
      {asked.length > 0 && (
        <ul aria-label="Where each party stands" className="space-y-3">
          {asked.map((row) => (
            <PartyStatus key={row.party} row={row} />
          ))}
        </ul>
      )}
    </section>
  );
}

/**
 * Whose turn it is, in one line: "Waiting on ITSO: 1 of 2 seats done". The
 * submitter's turn is the server's own state label; with nobody holding the
 * record, so is everything else.
 */
export function turnLine(data: RecordTracker): string {
  if (SUBMITTER_HOLDS.has(data.workflow_state)) {
    return `Waiting on the submitter: ${data.workflow_state_label}`;
  }
  const active = data.parties.filter((p) => p.state === "active");
  if (active.length === 0) return data.workflow_state_label;
  return `Waiting on ${active.map(partyTurn).join("; ")}`;
}

function partyTurn(row: TrackerPartyRow): string {
  if (row.in_pool) return `${row.label}: unassigned`;
  const seats = (row.seats ?? []).filter((s) => s.state !== "withdrawn");
  if (seats.length === 0) return row.label;
  const done = seats.filter((s) => s.state === "done").length;
  return `${row.label}: ${done} of ${seats.length} seats done`;
}

/** The due date, in words. Only a party still reviewing has one that matters. */
export function dueText(row: Pick<TrackerPartyRow, "due_at" | "original_due_at" | "is_overdue" | "clock_paused"> & {
  state?: TrackerPartyState;
}): string | null {
  if (row.state !== undefined && row.state !== "active") return null;
  if (row.clock_paused) return "Clock paused while waiting on the submitter";
  if (!row.due_at) return null;
  const due = formatDate(row.due_at);
  if (row.is_overdue) return `Overdue: was due ${due}`;
  const extended = row.original_due_at && row.original_due_at !== row.due_at;
  return extended ? `Due ${due}, extended from ${formatDate(row.original_due_at)}` : `Due ${due}`;
}

function PartyStatus({ row }: { row: TrackerPartyRow }) {
  const due = dueText(row);
  // "Pending" is not a conclusion; an outcome is shown once there is one.
  const outcome = row.outcome && row.outcome !== "pending" ? row.outcome_label : null;
  const facts = [row.state_label, outcome, row.changes_requested ? "Changes requested" : null].filter(
    Boolean,
  ) as string[];

  return (
    <li className="text-2xs text-stone-600">
      <span className="text-small font-bold text-stone-900">{row.label}</span>
      <p className="mt-0.5">
        {facts.join(" · ")}
        {due && (
          <span className={cn(row.is_overdue && "font-semibold text-brand")}>
            {" · "}
            {due}
          </span>
        )}
      </p>
      {row.carryover && row.carryover_label && (
        <p className="mt-1 inline-flex items-center gap-1 px-1.5 py-0.5 rounded border border-stone-300 bg-stone-100 font-bold text-stone-900">
          <i className={cn("fas text-2xs", CARRYOVER_ICON[row.carryover])} aria-hidden />
          {row.carryover_label}
        </p>
      )}
      {row.seats && row.seats.length > 0 && (
        <ul aria-label={`Reviewing for ${row.label}`} className="mt-1 space-y-0.5">
          {row.seats.map((seat, i) => (
            <li key={i}>
              {seat.reviewer_name ?? "A reviewer"} — {seat.state_label.toLowerCase()}
              {seat.verdict_label && (
                <span className="font-semibold text-stone-900"> · {seat.verdict_label}</span>
              )}
            </li>
          ))}
        </ul>
      )}
    </li>
  );
}
