/**
 * The capabilities adapter (IR-411; spec §4.8, ADR-032 §10).
 *
 * Paper View, My Library, My Reviews and Publish ask this module for the
 * server's action offers; none compares a role name to decide an action.
 * `test/roleGuard.test.ts` guards that boundary.
 *
 * Nothing here is a permission. The server re-checks every action, so a
 * capability is only a decision about what to *offer*.
 */
import { PIPELINE_STATUS, type RoleName } from "@/lib/constants";
import type { Capability, RecordDetail, ReviewerSeat } from "@/types/records";

/** ADR-032 §10's action keys; the union lives with the payload that carries it. */
export type { Capability } from "@/types/records";

/**
 * Paper View's sections, in tab order (spec §4.6). Participants see Overview ·
 * Review; everyone else Overview · Paper (ADR-032 §10, 2026-11-04; IR-879).
 * On a published paper a participant reads it like anyone else, unless the
 * address opens its review: then Overview · Paper · Review (IR-1339). Files
 * lives in Review's Documents tab now (IR-1203; a drawer from IR-879),
 * so it is no section: an old `?section=files` link is a participant's Review
 * on that tab.
 */
export const PAPER_SECTIONS = ["overview", "paper", "review"] as const;
export type PaperSection = (typeof PAPER_SECTIONS)[number];


/** Who is looking: the signed-in user, or nobody. */
export type Viewer = { id: number; role_name: RoleName | null };

/** The Record detail fields the adapter reads. */
type CapabilityInputs = Pick<
  RecordDetail,
  | "owners"
  | "can_request_document"
  | "is_participant"
  | "abstract_file"
  | "files"
  | "review_claim"
  | "pipeline_status"
>;

/** Whether the viewer owns the record: the adapter's one client-side input. */
export function isOwner(record: Pick<RecordDetail, "owners">, viewer: Viewer | null): boolean {
  return viewer != null && record.owners.some((o) => o.user === viewer.id);
}

/**
 * Whether the viewer takes part in the review now: they hold a party's active
 * assignment, which is what lets them ask the owner for documents.
 */
export function isReviewing(record: CapabilityInputs, viewer: Viewer | null): boolean {
  return viewer != null && record.can_request_document.length > 0;
}

/**
 * Someone who may read the review. The server's `is_participant` is
 * ADR-032's `is_record_participant`: an owner, or anyone who *has* held an
 * office seat, withdrawn included, so a reviewer whose part is done or who was
 * taken off keeps the Review and Files sections, read-only (IR-415, IR-1226).
 * An Adviser seat counts only while its holder is the record's Adviser. Reading
 * is not acting: what this viewer may do comes from `capabilities`. The
 * client-side grounds cover the owner and a pool member about to claim.
 */
export function isParticipant(record: CapabilityInputs, viewer: Viewer | null): boolean {
  return viewer != null && (record.is_participant || isOwner(record, viewer) || isReviewing(record, viewer) || record.review_claim != null);
}

/**
 * The viewer's seat that *Open review* records (ADR-032 §4): one not yet
 * opened. Null when every seat is already open, finished, or there is none,
 * so the button then only navigates.
 */
export function seatToOpen(record: Pick<RecordDetail, "my_seats">): ReviewerSeat | null {
  return record.my_seats.find((seat) => seat.state === "assigned") ?? null;
}

/** Whether there is a paper to read: the manuscript, else any attached file. */
export function hasPaper(record: Pick<RecordDetail, "abstract_file" | "files">): boolean {
  return Boolean(record.abstract_file) || record.files.length > 0;
}

/** The server's action offers for this viewer, as a set (IR-418: a pass-through). */
export function capabilitiesFor(record: Pick<RecordDetail, "capabilities">): ReadonlySet<Capability> {
  return new Set(record.capabilities);
}

/** A `?section=` value Paper View knows, else null. */
export function asSection(value: string | null): PaperSection | null {
  return (PAPER_SECTIONS as readonly string[]).includes(value ?? "") ? (value as PaperSection) : null;
}

/** The parameter that keeps a published paper open for its review (IR-1339). */
export const REVIEW_PARAM = "review";

/**
 * Whether the address opens the paper for its review (IR-1339): My Library,
 * My Reviews and the office console link a published paper this way, and any
 * address that asks for Review or its Documents (`?section=review`,
 * `?section=files`, `?documents=open`) does too, so older links keep working.
 * `?review=open` is what keeps it while the reader moves between tabs.
 */
export function asksForReview(search: URLSearchParams): boolean {
  const section = search.get("section");
  return search.get(REVIEW_PARAM) === "open" || section === "review" || section === "files" || search.get("documents") === "open";
}

/** Where My Library and My Reviews open a published paper: its review (IR-1339). */
export const reviewHref = (recordId: number, section: PaperSection = "review") =>
  `/records/${recordId}?section=${section}&${REVIEW_PARAM}=open`;

/**
 * Whether the page shows this viewer the review: a participant's paper before
 * it is published, and after only when the address opens its review
 * (IR-1339). Anywhere else a published paper reads as it does to anyone, so
 * an author who finds their paper in Discover sees what its readers see.
 */
export function showsReview(record: CapabilityInputs, viewer: Viewer | null, reviewAsked: boolean): boolean {
  return isParticipant(record, viewer) && (reviewAsked || record.pipeline_status !== PIPELINE_STATUS.PUBLISHED);
}

/**
 * The sections this viewer may open, in tab order. A participant reads the
 * paper in Review, beside the review, so has no Paper section (IR-879) --
 * except on a published paper, which keeps the reader's Paper tab beside
 * Review when its review is open (IR-1339).
 */
export function sectionsFor(record: CapabilityInputs, viewer: Viewer | null, reviewAsked = false): PaperSection[] {
  const review = showsReview(record, viewer, reviewAsked);
  const published = record.pipeline_status === PIPELINE_STATUS.PUBLISHED;
  return PAPER_SECTIONS.filter((section) => {
    switch (section) {
      case "overview":
        return true;
      case "paper":
        return (!review || published) && hasPaper(record);
      case "review":
        return review;
    }
  });
}

/**
 * Where a `?section=` value lands for this viewer (IR-879): a participant's
 * old Paper or Files link opens Review, and Files also opens the Documents
 * drawer. Null for a value Paper View doesn't know.
 */
export function landingSection(
  value: string | null,
  sections: readonly PaperSection[],
): { section: PaperSection; documents: boolean } | null {
  if (value === "files") return { section: sections.includes("review") ? "review" : "overview", documents: sections.includes("review") };
  const section = asSection(value);
  if (section == null) return null;
  if (section === "paper" && !sections.includes("paper") && sections.includes("review")) {
    return { section: "review", documents: false };
  }
  return { section: sections.includes(section) ? section : "overview", documents: false };
}
