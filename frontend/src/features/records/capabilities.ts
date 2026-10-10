/**
 * The capabilities adapter (IR-411; spec §4.8, ADR-032 §10).
 *
 * **The one place the frontend decides what a viewer may do with a record.**
 * Paper View, My Library, My Reviews and Publish ask this module; none of them
 * reads a role name itself. `test/roleGuard.test.ts` fails the
 * build if one does.
 *
 * **Phase 1 (now).** The Record detail payload carries no `capabilities` list
 * yet, so this derives one from the server fields that exist:
 *
 * - a seat still to work → `open_review`;
 * - the server's per-act flags (`routing`, `decision`, `office_review`,
 *   `revision`) → the review actions;
 * - `can_request_document` non-empty → `request_document`;
 * - ownership plus the server's `workflow_state` → the author actions.
 *
 * `tag_ip` and `attach_file` are the two capabilities still read from the
 * viewer's role, here and nowhere else, until the server says them (phase 2).
 *
 * **Phase 2 (IR-418, "Capabilities payload").** The serializer adds
 * `capabilities: string[]` from `core.permissions`; this module becomes a
 * pass-through and every caller is untouched.
 *
 * Nothing here is a permission. The server re-checks every action, so a
 * capability is only a decision about what to *offer*.
 */
import { STAFF_ROLES, type RoleName } from "@/lib/constants";
import {
  OPEN_SEAT_STATES,
  type DecisionOutcome,
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

/** Which capability offers each Decision outcome (IR-270). */
const DECISION_CAPABILITY: Record<DecisionOutcome, Capability> = {
  accept: "accept_proposal",
  publish: "accept_publish",
  keep_unlisted: "keep_unlisted",
  reject: "reject",
};

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
  | "my_seats"
  | "is_participant"
  | "routing"
  | "office_review"
  | "revision"
  | "decision"
  | "workflow_state"
  | "pipeline_status"
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

/** Whether the viewer holds a seat still to work: assigned, or in review. */
function holdsOpenSeat(record: Pick<RecordDetail, "my_seats">): boolean {
  return record.my_seats.some((seat) => OPEN_SEAT_STATES.includes(seat.state));
}

/** Whether there is a paper to read: the manuscript, else any attached file. */
function hasPaper(record: CapabilityInputs): boolean {
  return Boolean(record.abstract_file) || record.files.length > 0;
}

export function capabilitiesFor(record: CapabilityInputs, viewer: Viewer | null): ReadonlySet<Capability> {
  const granted = new Set<Capability>(["cite"]);
  if (viewer == null) return granted;

  // A seat to work is a review to open.
  if (holdsOpenSeat(record)) granted.add("open_review");
  // Routing (ADR-032 §4, IR-261): the server's own flags, never derived here.
  if (record.routing.accept_and_route) granted.add("accept_route");
  if (record.routing.route_as != null) granted.add("route");
  // Decisions (ADR-032 §3, IR-270): the outcomes the server offers this
  // viewer, each its own action. Read defensively: a payload from before
  // IR-270 carries no `decision`, and offers no Decision.
  for (const outcome of record.decision?.outcomes ?? []) granted.add(DECISION_CAPABILITY[outcome]);
  // An office reviewer (ADR-032 §3-§4, IR-269), from the server's flag: one
  // capability for *Clear* and *Record finding*, which share every rule
  // (ADR-032 §10 Amendment, 2026-10-08), and *Add reviewer* from the same seat.
  if (record.office_review.party != null) {
    granted.add("office_review");
    granted.add("add_reviewer");
  }
  if (record.can_request_document.length > 0) granted.add("request_document");
  // Revision requests (ADR-032 §5, IR-272), from the server's flag. A party
  // asks once: while its request is open, its reviewers are offered the
  // withdrawal instead of a second request.
  if (record.revision.withdrawable != null) granted.add("withdraw_revision");
  else if (record.revision.party != null) granted.add("request_revision");

  if (isOwner(record, viewer)) {
    // Every author action keys off the server's derived state, never the
    // stored stage, so a rejected record (terminal) offers none of them.
    if (record.workflow_state === "draft") {
      granted.add("continue_draft");
      granted.add("edit_details");
    }
    if (record.workflow_state === "awaiting_resubmission") {
      // The owner answers a revision request with a new version, which the
      // server offers through `revision.new_version` (IR-273).
      if (record.revision.new_version != null) granted.add("create_version");
      // A new version may carry a revised manuscript (IR-273). The server
      // opens the manuscript lock to an owner only while a revision is asked
      // for on the new model, which is what its offer says.
      if (record.revision.new_version != null) granted.add("replace_manuscript");
      // The edit becomes part of the next version (IR-273, invariant 4).
      granted.add("edit_details");
    }
  }

  // Phase 1 only: the two role-derived capabilities, mirroring the server's
  // `IsStaff` (KTTO, RDCO, ITSO, IERC). Phase 2 reads them from the server.
  const officeStaff = viewer.role_name != null && STAFF_ROLES.includes(viewer.role_name);
  if (officeStaff && record.pipeline_status === "published") granted.add("tag_ip");
  // Only where the office takes part, which is where the Files section is.
  if (officeStaff && isReviewing(record, viewer)) granted.add("attach_file");

  return granted;
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
