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
import type { RoleName } from "@/lib/constants";
import {
  type RecordDetail,
  type ReviewerSeat,
} from "@/types/records";

/**
 * ADR-032 §10's action keys, as spec §4.8 lists them, with the two its
 * 2026-10-06 amendment adds (IR-411): `continue_draft`, reopening one's own
 * draft in Publish, and `attach_file`, an office filing a supplementary file
 * on a record it takes part in. IR-273 adds `replace_manuscript`: the owner
 * uploading a revised manuscript for the next version (ADR-032 §5 Amendment).
 * IR-270 adds the three Decisions: `accept_publish`, `keep_unlisted` (the
 * spec's `final_decide`, renamed to the act it grants) and `reject`. IR-271
 * adds `accept_proposal`, a Proposal's Adviser accepting it (the spec's
 * `decide_proposal`, which also named *Reject*; reject is `reject` on every
 * record).
 */
export type Capability =
  | "open_review"
  | "request_document"
  | "request_revision"
  | "withdraw_revision"
  | "route"
  | "accept_route"
  | "accept_publish"
  | "accept_proposal"
  | "keep_unlisted"
  | "reject"
  | "office_review"
  | "add_reviewer"
  | "create_version"
  | "replace_manuscript"
  | "edit_details"
  | "continue_draft"
  | "continue_as"
  | "set_visibility"
  | "tag_ip"
  | "attach_file"
  | "comment_review"
  | "comment_public"
  | "cite";

/** Paper View's sections, in tab order (spec §4.6). */
export const PAPER_SECTIONS = ["overview", "paper", "review", "files"] as const;
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
 * An owner, or someone taking part in the review. The server's
 * `is_participant` is ADR-032's `is_record_participant`, which also counts
 * anyone who *has* held a seat (IR-415): a reviewer whose part is done keeps
 * the Review and Files sections. The two client-side grounds cover the owner
 * and a pool member who is about to claim.
 */
export function isParticipant(record: CapabilityInputs, viewer: Viewer | null): boolean {
  return viewer != null && (record.is_participant || isOwner(record, viewer) || isReviewing(record, viewer));
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
function hasPaper(record: CapabilityInputs): boolean {
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

/** The sections this viewer may open, in tab order. */
export function sectionsFor(record: CapabilityInputs, viewer: Viewer | null): PaperSection[] {
  const participant = isParticipant(record, viewer);
  return PAPER_SECTIONS.filter((section) => {
    switch (section) {
      case "overview":
        return true;
      case "paper":
        return hasPaper(record);
      case "review":
      case "files":
        return participant;
    }
  });
}
