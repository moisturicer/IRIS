/**
 * The Review section's actions (IR-412; spec §4.7) -- the slot every ADR-032
 * review act plugs into.
 *
 * **Adding an action is adding an entry to `REVIEW_ACTIONS`**, and nothing
 * else: the bar (`ReviewActionBar`) renders one button per entry whose
 * capability the adapter grants, so an entry the viewer was not granted is
 * never shown. Route (IR-261), clear and finding (IR-269), the Decisions
 * (IR-270, IR-271) and revision against a version (IR-272) each
 * add one here, with their own dialog; their held frontend criteria are met
 * in this bar, not on a separate screen.
 *
 * Two kinds:
 *
 * - **`dialog`** -- the action collects something first (who to route to, a
 *   finding, a revision's reasons, a decision's comment or reason -- the three
 *   Decisions are dialogs, not `ConfirmDialog`s, because each takes text and
 *   must survive a stale record, IR-270). Its `Dialog` is mounted when the
 *   button is pressed and reports back through `onDone` with the outcome to
 *   announce.
 * - **`terminal`** -- the action takes something back with nothing to type
 *   (withdrawing a revision request, IR-272). The bar puts it last and asks
 *   through `ConfirmDialog` first, stating the consequence (ui-ux/16 §4
 *   copy), then calls `run`.
 *
 * `blockedReason` keeps a granted action on the bar but disabled, saying why
 * -- for a condition the server reports but the viewer cannot act past yet.
 */
import type { ComponentType } from "react";

import { recordsApi } from "@/api/records";
import { joinLabels } from "@/lib/utils";
import { RequestDocumentDialog } from "@/features/document-requests/RequestDocumentDialog";
import type { Capability } from "@/features/records/capabilities";
import type { RecordDetail } from "@/types/records";

import { AddReviewerDialog } from "./AddReviewerDialog";
import { DecisionDialog } from "./DecisionDialog";
import { OfficeReviewDialog } from "./OfficeReviewDialog";
import { RequestRevisionDialog } from "./RequestRevisionDialog";
import { RouteDialog } from "./RouteDialog";

export interface ReviewActionDialogProps {
  record: RecordDetail;
  /** Closed with nothing done. */
  onClose: () => void;
  /** Done: `outcome` is announced, and the page re-reads the record. */
  onDone: (outcome: string) => void;
}

interface ReviewActionBase {
  /** Offered exactly when the capabilities adapter grants this. */
  capability: Capability;
  /** The button's words: the act, as a verb. */
  label: string;
  /** A Font Awesome glyph beside the label. */
  icon: string;
  /** Why a granted action cannot be taken yet, or null when it can. */
  blockedReason?: (record: RecordDetail) => string | null;
}

export interface DialogReviewAction extends ReviewActionBase {
  kind: "dialog";
  Dialog: ComponentType<ReviewActionDialogProps>;
}

export interface TerminalReviewAction extends ReviewActionBase {
  kind: "terminal";
  confirm: {
    title: string;
    /** What follows, stated plainly, before anyone commits to it. */
    consequence: string;
    confirmLabel: string;
    /** Destructive (a rejection): the danger glyph and the darker maroon. */
    danger?: boolean;
  };
  /** Takes the action; resolves with the outcome to announce. */
  run: (record: RecordDetail) => Promise<string>;
}

export type ReviewAction = DialogReviewAction | TerminalReviewAction;

/** Ask the owner for documents without sending the record back (ADR-022). */
function RequestDocumentAction({ record, onClose, onDone }: ReviewActionDialogProps) {
  return (
    <RequestDocumentDialog
      recordId={record.id}
      parties={record.can_request_document}
      partyLabels={Object.fromEntries(record.current_holders.map((h) => [h.party, h.label]))}
      onClose={onClose}
      onCreated={() => onDone("Documents requested. The owner has been notified.")}
    />
  );
}

/** The Adviser accepts the work and routes it to offices (ADR-032 §3, IR-261). */
function AcceptAndRouteAction({ record, onClose, onDone }: ReviewActionDialogProps) {
  return (
    <RouteDialog
      recordId={record.id}
      mode="accept"
      onClose={onClose}
      onRouted={(offices) => onDone(`Accepted and sent to ${joinLabels(offices)}.`)}
    />
  );
}

/** An office seat holder routes onward; their own review continues (ADR-032 §4). */
function RouteAction({ record, onClose, onDone }: ReviewActionDialogProps) {
  return (
    <RouteDialog
      recordId={record.id}
      mode="route"
      onClose={onClose}
      onRouted={(offices) => onDone(`Sent to ${joinLabels(offices)}.`)}
    />
  );
}

/** An office seat holder clears: their part of the office's review ends (ADR-032 §4, IR-269). */
function ClearAction({ record, onClose, onDone }: ReviewActionDialogProps) {
  return <OfficeReviewDialog record={record} outcome="cleared" onClose={onClose} onDone={onDone} />;
}

/** An office seat holder records a finding, with its reason. Never a rejection (ADR-032 §3). */
function RecordFindingAction({ record, onClose, onDone }: ReviewActionDialogProps) {
  return <OfficeReviewDialog record={record} outcome="finding" onClose={onClose} onDone={onDone} />;
}

/** A seat holder brings in a colleague from their own office (ADR-032 §4). */
function AddReviewerAction({ record, onClose, onDone }: ReviewActionDialogProps) {
  const assignment = record.office_review.assignment;
  if (assignment == null) return null;
  return (
    <AddReviewerDialog
      assignmentId={assignment}
      onClose={onClose}
      onAdded={(name, office) => onDone(`${name} is now reviewing for ${office}.`)}
    />
  );
}

/** The Adviser, or RDCO, accepts and publishes the record (ADR-032 §3, IR-270). */
function AcceptAndPublishAction({ record, onClose, onDone }: ReviewActionDialogProps) {
  return <DecisionDialog record={record} outcome="publish" onClose={onClose} onDone={onDone} />;
}

/** A Proposal's Adviser accepts it: its resting state (ADR-032 §2, IR-271). */
function AcceptProposalAction({ record, onClose, onDone }: ReviewActionDialogProps) {
  return <DecisionDialog record={record} outcome="accept" onClose={onClose} onDone={onDone} />;
}

/** RDCO accepts the record without publishing it (ADR-032 §3, IR-270). */
function KeepUnlistedAction({ record, onClose, onDone }: ReviewActionDialogProps) {
  return <DecisionDialog record={record} outcome="keep_unlisted" onClose={onClose} onDone={onDone} />;
}

/** The Adviser, or RDCO, rejects and archives the record, with a reason (IR-270). */
function RejectAction({ record, onClose, onDone }: ReviewActionDialogProps) {
  return <DecisionDialog record={record} outcome="reject" onClose={onClose} onDone={onDone} />;
}

/** Why nobody may decide yet: an unopened seat, or an open revision request (IR-270). */
const decisionBlocked = (record: RecordDetail) => record.decision?.blocked ?? null;

/** A seat holder asks the owner to revise the record (ADR-032 §5, IR-272). */
function RequestRevisionAction({ record, onClose, onDone }: ReviewActionDialogProps) {
  return <RequestRevisionDialog record={record} onClose={onClose} onDone={onDone} />;
}

/** The viewer's party has asked already: its reviewers may withdraw the request (IR-272). */
async function withdrawRevision(record: RecordDetail): Promise<string> {
  const requestId = record.revision.withdrawable;
  if (requestId == null) throw new Error("There is no revision request to withdraw.");
  await recordsApi.withdrawRevisionRequest(record.id, requestId);
  return "Revision request withdrawn. The owner has been told.";
}

/** Why the office reviewer cannot clear or record a finding yet, from the server. */
const officeReviewBlocked = (record: RecordDetail) => record.office_review.blocked;

/**
 * Order matters: the bar fills its first granted action. A Proposal's Adviser
 * has *Accept* as primary (IR-271). The Adviser's and RDCO's primary on a
 * Thesis or Project is *Accept & publish* (IR-270: most theses need no office),
 * then RDCO's *Keep unlisted* and the Adviser's *Accept & route*. An office
 * reviewer's is *Clear*, with *Record finding* beside it (ui-ux/16's order),
 * then *Request Revision*, *Request documents*, *Add reviewer* and *Route to
 * office*. *Reject* is the last of the dialogs. A reviewer whose party has
 * already asked for a revision is offered *Withdraw revision request* instead,
 * last of all. *Clear* and *Record finding* share one capability,
 * `office_review` (ADR-032 §10 Amendment, 2026-10-08).
 */
export const REVIEW_ACTIONS: readonly ReviewAction[] = [
  {
    kind: "dialog",
    capability: "accept_proposal",
    label: "Accept…",
    icon: "fa-circle-check",
    blockedReason: decisionBlocked,
    Dialog: AcceptProposalAction,
  },
  {
    kind: "dialog",
    capability: "accept_publish",
    label: "Accept & publish…",
    icon: "fa-circle-check",
    blockedReason: decisionBlocked,
    Dialog: AcceptAndPublishAction,
  },
  {
    kind: "dialog",
    capability: "keep_unlisted",
    label: "Keep unlisted…",
    icon: "fa-eye-slash",
    blockedReason: decisionBlocked,
    Dialog: KeepUnlistedAction,
  },
  {
    kind: "dialog",
    capability: "accept_route",
    label: "Accept & route…",
    icon: "fa-share-from-square",
    // Accepting is a decision: refused while a revision request is open (IR-272).
    blockedReason: (record) => record.revision.decision_blocked,
    Dialog: AcceptAndRouteAction,
  },
  {
    kind: "dialog",
    capability: "office_review",
    label: "Clear…",
    icon: "fa-circle-check",
    blockedReason: officeReviewBlocked,
    Dialog: ClearAction,
  },
  {
    kind: "dialog",
    capability: "office_review",
    label: "Record finding…",
    icon: "fa-flag",
    blockedReason: officeReviewBlocked,
    Dialog: RecordFindingAction,
  },
  {
    kind: "dialog",
    capability: "request_revision",
    // The retired review form's words, kept verbatim (ui-ux/16 §4).
    label: "Request Revision…",
    icon: "fa-arrow-rotate-left",
    blockedReason: (record) => record.revision.blocked,
    Dialog: RequestRevisionAction,
  },
  {
    kind: "dialog",
    capability: "request_document",
    label: "Request documents",
    icon: "fa-file-circle-plus",
    Dialog: RequestDocumentAction,
  },
  {
    kind: "dialog",
    capability: "add_reviewer",
    label: "Add reviewer…",
    icon: "fa-user-plus",
    Dialog: AddReviewerAction,
  },
  {
    kind: "dialog",
    capability: "route",
    label: "Route to office…",
    icon: "fa-route",
    Dialog: RouteAction,
  },
  {
    kind: "dialog",
    capability: "reject",
    label: "Reject…",
    icon: "fa-ban",
    blockedReason: decisionBlocked,
    Dialog: RejectAction,
  },
  {
    kind: "terminal",
    capability: "withdraw_revision",
    label: "Withdraw revision request",
    icon: "fa-rotate-left",
    confirm: {
      title: "Withdraw the revision request?",
      consequence:
        "The owner is told that your request for changes is withdrawn. The record can be decided again once no other revision request is open.",
      confirmLabel: "Withdraw request",
    },
    run: withdrawRevision,
  },
];
