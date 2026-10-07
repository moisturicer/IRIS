/**
 * The Review section's actions (IR-412; spec §4.7) -- the slot every ADR-032
 * review act plugs into.
 *
 * **Adding an action is adding an entry to `REVIEW_ACTIONS`**, and nothing
 * else: the bar (`ReviewActionBar`) renders one button per entry whose
 * capability the adapter grants, so an entry the viewer was not granted is
 * never shown. Route (IR-261), finding (IR-269), accept & publish (IR-270),
 * the Proposal decision (IR-271) and revision against a version (IR-272) each
 * add one here, with their own dialog; their held frontend criteria are met
 * in this bar, not on a separate screen.
 *
 * Two kinds:
 *
 * - **`dialog`** -- the action collects something first (who to route to, a
 *   finding, a revision's reasons). Its `Dialog` is mounted when the button is
 *   pressed and reports back through `onDone` with the outcome to announce.
 * - **`terminal`** -- the action ends the review (accept & publish, reject).
 *   The bar puts it last and asks through `ConfirmDialog` first, stating the
 *   consequence (ui-ux/16 §4 copy), then calls `run`.
 *
 * `blockedReason` keeps a granted action on the bar but disabled, saying why
 * -- for a condition the server reports but the viewer cannot act past yet.
 *
 * Until IR-260 cuts over, decisions are still recorded on the current review
 * form; the Review section links to it beside the bar rather than porting it.
 */
import type { ComponentType } from "react";

import { RequestDocumentDialog } from "@/features/document-requests/RequestDocumentDialog";
import type { Capability } from "@/features/records/capabilities";
import type { RecordDetail } from "@/types/records";

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

/** "ITSO and IERC", "ITSO, IERC and KTTO". */
function joinLabels(labels: string[]): string {
  return labels.length <= 1 ? labels.join("") : `${labels.slice(0, -1).join(", ")} and ${labels[labels.length - 1]}`;
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

/**
 * Order matters: the bar fills its first granted action. The Adviser's primary
 * is *Accept & route*; an office's stays *Request documents*, with *Route to
 * office* beside it.
 */
export const REVIEW_ACTIONS: readonly ReviewAction[] = [
  {
    kind: "dialog",
    capability: "accept_route",
    label: "Accept & route…",
    icon: "fa-share-from-square",
    Dialog: AcceptAndRouteAction,
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
    capability: "route",
    label: "Route to office…",
    icon: "fa-route",
    Dialog: RouteAction,
  },
];
