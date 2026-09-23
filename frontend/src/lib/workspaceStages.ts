/**
 * My Workspace — deriving a case's stage and office status from real data.
 *
 * Grilled with the user before building this (see iris-my-workspace-design
 * memory): the mockup's "stage N of 7" bar doesn't hold up once a record's
 * office involvement is conditional (ADR-018) — a record can legitimately
 * skip stages, so there is no fixed N. IP Assessment (ITSO/IERC) and
 * Commercialization (KTTO) are also genuinely *parallel*, not sequential
 * positions on one bar; a case can be in both at once. This derives a
 * per-record stage list and office-pill row instead of pretending otherwise.
 */
import type { Party, RecordDetail, RecordClearance } from "@/types/records";

export type WorkspaceStage =
  | "validation"
  | "review_routing"
  | "office_review"
  | "final_review"
  | "ongoing"
  | "completed"
  | "revision_requested"
  | "rejected";

const STAGE_LABELS: Record<WorkspaceStage, string> = {
  validation: "Validation",
  review_routing: "Review & Routing",
  office_review: "Office Review",
  final_review: "Final Review",
  ongoing: "Research Ongoing",
  completed: "Completed",
  revision_requested: "Declined",
  rejected: "Rejected",
};

/**
 * The tab a record belongs to, from where the API says it stands (IR-259).
 *
 * `workflow_state` plus the parties holding the record, never the stored
 * stage values IR-260 retires. One row needs the holders: a Proposal enters
 * at its Adviser, who also decides it, so once the Adviser has acted the API
 * says `final_review` -- but the student is still waiting on their Adviser,
 * which this page has always called Review & Routing, not RDCO's Final Review.
 */
export function currentStage(record: RecordDetail): WorkspaceStage {
  switch (record.workflow_state) {
    case "draft":
      return "validation";
    case "submitted":
      return "review_routing";
    case "final_review":
      return heldOnlyBy(record, "adviser") ? "review_routing" : "final_review";
    case "in_review":
    case "awaiting_document":
      return "office_review";
    case "awaiting_resubmission":
      return "revision_requested";
    // `approved` is NOT finished: the adviser signed off and the research is
    // now actually being done. Only a manual /complete/ call -- by RDCO or the
    // assigned Adviser (ADR-021 §3, IR-267) -- ends a Proposal. Collapsing the two
    // told a student their proposal was "Completed" while they were still
    // working on it.
    case "approved":
      return "ongoing";
    case "completed":
    case "published":
      return "completed";
    case "rejected":
    case "pending_delete":
      return "rejected";
    default:
      return "validation";
  }
}

function heldOnlyBy(record: RecordDetail, party: Party): boolean {
  const holders = record.current_holders ?? [];
  return holders.length > 0 && holders.every((h) => h.party === party);
}

/** The ordered stage list a *this specific record* actually passes through. */
export function stageSequence(record: RecordDetail): WorkspaceStage[] {
  if (record.record_type_name === "Proposal") {
    // Four stages, not three: adviser approval lands on `ongoing`, and only
    // RDCO or the assigned Adviser marking it complete reaches `completed`. Only Proposals ever have
    // an `ongoing` stage -- approve_record() sends every other type straight
    // to `published` from its final review.
    return ["validation", "review_routing", "ongoing", "completed"];
  }
  const officeStages: WorkspaceStage[] =
    record.clearances && record.clearances.length > 0 ? ["office_review"] : [];
  return ["validation", "review_routing", ...officeStages, "final_review", "completed"];
}

export function stageLabel(stage: WorkspaceStage): string {
  return STAGE_LABELS[stage];
}

/** Clearances still pending -- what a case card's office pills show. */
export function pendingClearances(record: RecordDetail): RecordClearance[] {
  return (record.clearances ?? []).filter((c) => c.status === "pending");
}

/** IP Assessment = ITSO or IERC has a pending clearance. */
export function inIpAssessment(record: RecordDetail): boolean {
  return pendingClearances(record).some((c) => c.office === "itso" || c.office === "ierc");
}

/** Commercialization = KTTO has a pending clearance. */
export function inCommercialization(record: RecordDetail): boolean {
  return pendingClearances(record).some((c) => c.office === "ktto");
}

/**
 * Who is holding a case up right now, for the card's "Office" line, in the
 * party labels the API serves (`current_holders`, IR-259).
 *
 * While the author owes a revision, a holder that asked for it is waiting on
 * the author, not working -- the card has always shown only who is still
 * reviewing. That is an office whose clearance is still pending: the party
 * that sent the record back holds a declined clearance, or none at all when a
 * sequential party (Intake, Adviser, RDCO) did. The open resubmission requests
 * would say this directly, but only `/records/<id>/tracker/` carries them, and
 * this page lists every case from one `/records/mine/` call.
 */
export function currentOfficeLabel(record: RecordDetail): string {
  let holders = record.current_holders ?? [];
  if (record.workflow_state === "awaiting_resubmission") {
    const reviewing = new Set(pendingClearances(record).map((c) => c.office as string));
    holders = holders.filter((h) => reviewing.has(h.party));
  }
  return holders.length > 0 ? holders.map((h) => h.label).join(" + ") : "—";
}

/**
 * Formatted case id -- pure display, invents nothing. Record.id and its
 * creation year both already exist; this is the same number, formatted.
 */
export function formatCaseId(record: RecordDetail): string {
  const year = new Date(record.created_at).getFullYear();
  return `DISC-${year}-${String(record.id).padStart(4, "0")}`;
}

/** A record the owner must act on -- the sole real match for "Actions Required". */
export function needsAuthorAction(record: RecordDetail): boolean {
  return record.workflow_state === "awaiting_resubmission";
}
