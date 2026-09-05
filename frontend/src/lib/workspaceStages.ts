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
import type { RecordDetail, RecordClearance } from "@/types/records";

export type WorkspaceStage =
  | "validation"
  | "review_routing"
  | "office_review"
  | "final_review"
  | "ongoing"
  | "completed"
  | "declined"
  | "rejected";

const STAGE_LABELS: Record<WorkspaceStage, string> = {
  validation: "Validation",
  review_routing: "Review & Routing",
  office_review: "Office Review",
  final_review: "Final Review",
  ongoing: "Research Ongoing",
  completed: "Completed",
  declined: "Declined",
  rejected: "Rejected",
};

/** The tab a record's *current* pipeline_status belongs to, if any. */
export function currentStage(record: RecordDetail): WorkspaceStage {
  switch (record.pipeline_status) {
    case "draft":
      return "validation";
    case "adviser_review":
    case "rdco_intake":
      return "review_routing";
    case "itso_review":
    case "parallel_review":
      return "office_review";
    case "rdco_review":
      return "final_review";
    // `approved` is NOT finished: SRS describes it as "visible as ongoing" --
    // the adviser signed off and the research is now actually being done.
    // Only RDCO's manual /complete/ call ends a Proposal. Collapsing the two
    // told a student their proposal was "Completed" while they were still
    // working on it.
    case "approved":
      return "ongoing";
    case "completed":
    case "published":
      return "completed";
    case "declined":
      return "declined";
    case "rejected":
    case "pending_delete":
      return "rejected";
    default:
      return "validation";
  }
}

/** The ordered stage list a *this specific record* actually passes through. */
export function stageSequence(record: RecordDetail): WorkspaceStage[] {
  if (record.record_type_name === "Proposal") {
    // Four stages, not three: adviser approval lands on `ongoing`, and only
    // RDCO marking it complete reaches `completed`. Only Proposals ever have
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
 * The office(s) actually holding a case up right now, for the card's "Office"
 * line. Not the ADR-018 request -- what's genuinely pending. Falls back to
 * who owns the *current sequential* stage when there's no clearance yet.
 */
export function currentOfficeLabel(record: RecordDetail): string {
  const pending = pendingClearances(record);
  if (pending.length > 0) return pending.map((c) => c.office_label).join(" + ");
  switch (record.pipeline_status) {
    case "adviser_review":
      return "Adviser";
    case "rdco_intake":
    case "rdco_review":
      return "RDCO";
    default:
      return "—";
  }
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
  return record.pipeline_status === "declined";
}
