/**
 * The capabilities adapter (IR-411; spec §4.8, ADR-032 §10).
 *
 * **The one place the frontend decides what a viewer may do with a record.**
 * Paper View, My Library, My Reviews and Publish ask this module; none of them
 * reads a role name or `can_act` itself. `test/roleGuard.test.ts` fails the
 * build if one does.
 *
 * **Phase 1 (now).** The Record detail payload carries no `capabilities` list
 * yet, so this derives one from the server fields that exist:
 *
 * - `can_act` non-empty → the review actions (`open_review`, and `decide`
 *   through the current decision form until ADR-032's actions land);
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
import type { RecordDetail } from "@/types/records";

/**
 * ADR-032 §10's action keys, as spec §4.8 lists them, with the two its
 * 2026-10-06 amendment adds (IR-411): `continue_draft`, reopening one's own
 * draft in Publish, and `attach_file`, an office filing a supplementary file
 * on a record it takes part in.
 */
export type Capability =
  | "open_review"
  | "request_document"
  | "request_revision"
  | "route"
  | "decide"
  | "create_version"
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
  "owners" | "can_act" | "can_request_document" | "workflow_state" | "pipeline_status" | "abstract_file" | "files"
>;

/** Whether the viewer owns the record: the adapter's one client-side input. */
export function isOwner(record: Pick<RecordDetail, "owners">, viewer: Viewer | null): boolean {
  return viewer != null && record.owners.some((o) => o.user === viewer.id);
}

/**
 * Whether the viewer takes part in the review: the server lets them act on the
 * record, or ask its owner for documents.
 */
export function isReviewing(record: CapabilityInputs, viewer: Viewer | null): boolean {
  return viewer != null && (record.can_act.length > 0 || record.can_request_document.length > 0);
}

/**
 * An owner, or someone taking part in the review. ADR-032's
 * `is_record_participant` also counts anyone who *has* held a seat; until
 * seats exist (IR-415) a reviewer whose part is finished is not counted here.
 */
export function isParticipant(record: CapabilityInputs, viewer: Viewer | null): boolean {
  return isOwner(record, viewer) || isReviewing(record, viewer);
}

/** Whether there is a paper to read: the manuscript, else any attached file. */
function hasPaper(record: CapabilityInputs): boolean {
  return Boolean(record.abstract_file) || record.files.length > 0;
}

export function capabilitiesFor(record: CapabilityInputs, viewer: Viewer | null): ReadonlySet<Capability> {
  const granted = new Set<Capability>(["cite"]);
  if (viewer == null) return granted;

  // Reading `can_act` belongs here alone; see the module comment.
  if (record.can_act.length > 0) {
    granted.add("open_review");
    // Through the current decision form, until IR-260 retires it.
    granted.add("decide");
  }
  if (record.can_request_document.length > 0) granted.add("request_document");

  if (isOwner(record, viewer)) {
    // Every author action keys off the server's derived state, never the
    // stored stage, so a rejected record (terminal) offers none of them.
    if (record.workflow_state === "draft") {
      granted.add("continue_draft");
      granted.add("edit_details");
    }
    if (record.workflow_state === "awaiting_resubmission") {
      // Today's act is "Resubmit for review"; versions (IR-416) replace it.
      granted.add("create_version");
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
