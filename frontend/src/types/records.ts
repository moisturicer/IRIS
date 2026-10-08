import type { PipelineStatus } from "@/lib/constants";

export type IpType = "patent" | "copyright" | "trade_secret" | "utility_model" | "";

export const IP_TYPE_LABELS: Record<Exclude<IpType, "">, string> = {
  patent:        "Patent",
  copyright:     "Copyright",
  trade_secret:  "Trade Secret",
  utility_model: "Utility Model",
};

export interface RecordOwner {
  id:         number;
  user:       number;
  email:      string;
  full_name:  string;
  is_primary: boolean;
}

export interface Author {
  id:   number;
  name: string;
  role: number | null;
}

export interface RecordListItem {
  id:                    number;
  title:                 string;
  abstract:              string;
  year_accomplished:     number | null;
  classification_name:   string | null;
  record_type_name:      string | null;
  pipeline_status:       PipelineStatus;
  is_ip:                 boolean;
  ip_type:               IpType;
  for_commercialization: boolean;
  community_extension:   boolean;
  access_count:          number;
  /** Attachments on the record (documents.RecordUpload). */
  file_count:            number;
  created_at:            string;
  authors:               Author[];
}

export interface RecordReview {
  id:               number;
  stage:            string;
  status:           "approved" | "declined" | "rejected";
  comment:          string;
  reviewed_by_name: string | null;
  created_at:       string;
  /** The version it was made against; null for reviews written before IR-416. */
  version:          number | null;
}

export interface RecordClearance {
  office:           "itso" | "ierc" | "ktto";
  office_label:     string;
  status:           "pending" | "cleared" | "declined" | "rejected" | "not_cleared";
  /** Server-supplied wording, so a status can be renamed without a release. */
  status_label:     string;
  /**
   * The comment and who signed are review content: null to a viewer who may
   * not read the review (IR-479). The status is not.
   */
  comment:          string | null;
  reviewed_by_name: string | null;
  updated_at:       string;
  /**
   * True when this clearance survived a resubmission rather than being granted
   * again. Derived by the server (IR-139) -- the client used to compute it from
   * the last decline, which is a different rule than `resubmit_record` applies.
   */
  preserved:        boolean;
}

/** What happened across resubmissions, and which offices survived them. */
export interface RecordResubmission {
  count:               number;
  last_resubmitted_at: string | null;
  /** Null when a sequential stage declined -- that path preserves nothing. */
  declining_office:    "itso" | "ierc" | "ktto" | null;
  offices_preserved:   Array<"itso" | "ierc" | "ktto">;
}

export interface RecordFileItem {
  id:         number;
  filename:   string;
  url:        string | null;
  size_bytes: number;
  created_at: string;
  /** The viewer may remove it: their office filed it and takes part (IR-476). */
  can_remove: boolean;
}

export interface RecordDetail extends RecordListItem {
  year_completed:  number | null;
  abstract:        string;
  abstract_file:   string | null;
  /**
   * These three are serialized with StringRelatedField, so the detail payload
   * carries the related object's display name — not its id. Use
   * `classification_name` / `record_type_name` for display.
   */
  classification:  string | null;
  psced:           string | null;
  record_type:     string | null;
  adviser:         number | null;
  added_by:        number | null;
  /** ADR-018: what the submitter requested; RDCO confirms at intake. */
  requires_ethics_review: boolean;
  requested_itso:  boolean;
  requested_ierc:  boolean;
  requested_ktto:  boolean;
  owners:          RecordOwner[];
  keywords?:       string[];
  is_deleted:      boolean;
  /** Null to a viewer who may not read the review: not disclosed, which is not none (IR-479). */
  reviews:         RecordReview[] | null;
  /** Per-office clearance state — makes clearance-aware resubmission visible. */
  clearances:      RecordClearance[];
  resubmission:    RecordResubmission;
  /** Server-worded stage. Never map a pipeline key to English on the client. */
  stage_label:     string;
  /**
   * The office whose clearance the *requesting user* would be recording, or
   * null for Adviser and RDCO, who decide the record at a sequential stage.
   * Server-derived so the client needs no role->office table of its own.
   */
  your_office:       "itso" | "ierc" | "ktto" | null;
  your_office_label: string | null;
  files:           RecordFileItem[];
  /**
   * Derived by the server from the routing tables, never stored (ADR-021 §4,
   * IR-258). A terminal record reports its stored status here instead.
   */
  workflow_state:       WorkflowState;
  workflow_state_label: string;
  current_holders:      TrackerHolder[];
  /** The parties this viewer may act as. Empty for almost everyone. */
  can_act:              Party[];
  /**
   * The parties this viewer may ask the owner for documents as (ADR-022,
   * IR-262): a party they hold. Wider than `can_act`, which the legacy
   * pipeline still narrows.
   */
  can_request_document: Party[];
  /**
   * The viewer's own reviewer seats on this record, withdrawn ones left out
   * (ADR-032 §4, IR-415). Never anyone else's.
   */
  my_seats:             ReviewerSeat[];
  /**
   * ADR-032's `is_record_participant`: an owner, or anyone who has ever held
   * a seat here -- so a reviewer whose part is done keeps Review and Files.
   */
  is_participant:       boolean;
  /**
   * What the action bar may offer for routing (ADR-032 §4, IR-261): *Accept &
   * route…* for the record's Adviser, and the office party *Route to office…*
   * acts as for a seat holder. A rendering hint; the endpoints re-check it.
   */
  routing:              RoutingFlags;
  /**
   * What the action bar may offer an office reviewer (IR-269): the office the
   * viewer may *Clear* or *Record finding* as, why not yet, and the office's
   * assignment for *Add reviewer*. A rendering hint; the endpoints re-check it.
   */
  office_review:        OfficeReviewFlags;
  /**
   * Revision requests (IR-272): whether the viewer may ask for one or
   * withdraw their party's, why nothing can be decided now, and every open
   * request for the owner's *Action required*. A rendering hint; the
   * endpoints re-check it.
   */
  revision:             RevisionFlags;
  /**
   * The record's versions, oldest first (ADR-032 §5, IR-416). Review
   * material: null to a viewer who may not read the review (IR-479), and
   * empty before the record is first submitted.
   */
  versions:             RecordVersion[] | null;
  /**
   * The manuscript is the owner's upload for a version not yet submitted
   * (IR-273). True for an owner only: everyone else is still served the
   * latest version's manuscript.
   */
  manuscript_unsubmitted: boolean;
}

/** One numbered snapshot of what the record put in front of its reviewers. */
export interface RecordVersion {
  number:          number;
  cause:           "submission" | "revision";
  cause_label:     string;
  created_at:      string;
  created_by_name: string | null;
  /** Null when this version was submitted with no manuscript. */
  manuscript_url:  string | null;
}

export interface OfficeReviewFlags {
  /** The specialist office the viewer holds an open seat for, or null. */
  party:      Party | null;
  label:      string | null;
  /** Why the act cannot be taken yet (an unopened seat, an open document request). */
  blocked:    string | null;
  assignment: number | null;
}

export interface RevisionFlags {
  /** The party the viewer holds an open seat for, and may ask as; null otherwise. */
  party:            Party | null;
  label:            string | null;
  /** Why the viewer cannot ask yet: their seat is not opened. */
  blocked:          string | null;
  /** Their party's open request, which they may withdraw instead: a party asks once. */
  withdrawable:     number | null;
  /** Why nobody may decide the record now: a revision request is open (ADR-032 §11). */
  decision_blocked: string | null;
  /** Every open request, oldest first. */
  open:             OpenRevisionRequest[];
  /**
   * For an owner, the version that would answer the open requests (IR-273);
   * null for anyone else, or with none open.
   */
  new_version:      NewVersionHint | null;
}

/** What submitting a new version would do, for its confirmation (IR-273). */
export interface NewVersionHint {
  /** The version it would be. */
  number:   number;
  /** The parties that asked, who review it. */
  rereview: string[];
  /** The offices whose clearance it keeps; empty under the restart-all policy. */
  kept:     string[];
  /** Why it cannot be submitted yet: nothing has changed since the newest request. */
  blocked:  string | null;
}

export interface OpenRevisionRequest {
  id:           number;
  party:        Party;
  label:        string;
  /** Plain text. Null, as `requested_by` is, to a viewer who may not read the review (IR-479). */
  reason:       string | null;
  requested_by: string | null;
  /** The version it was made against; null for one made before versions were recorded. */
  version:      number | null;
  created_at:   string;
}

/** An office reviewer's two outcomes (ADR-032 §3): offices never reject or publish. */
export type OfficeReviewOutcome = "cleared" | "finding";

/** `GET /assignments/<id>/add-reviewer/`: the office's members, marked when already seated. */
export interface AddReviewerOptions {
  assignment:  number;
  party:       Party;
  party_label: string;
  members:     { id: number; name: string; seated: boolean }[];
}

export interface RoutingFlags {
  accept_and_route: boolean;
  route_as:         Party | null;
}

/** One office the routing dialog offers (`GET /records/<id>/route-options/`). */
export interface RouteTarget {
  party:         Party;
  label:         string;
  /** Who may be nominated there: the office's members. */
  members:       { id: number; name: string }[];
  /** The office already reviews this record: routing there only adds a nominee. */
  already_holds: boolean;
  /** The author's ADR-018 flag for this office, worded; routes nothing by itself. */
  author_hint:   string | null;
}

export interface RouteOptions {
  from_party: Party;
  from_label: string;
  /** True for the Adviser's *Accept & route*, false for onward routing. */
  accept:     boolean;
  targets:    RouteTarget[];
}

/** A routing request: one reason for the decision, at most one nominee per office. */
export interface RouteRequest {
  to:     { party: Party; nominee?: number }[];
  reason: string;
}

// ---------------------------------------------------------------------------
// Reviewer seats (ADR-032 §4, IR-415)
// ---------------------------------------------------------------------------

export type SeatState = "assigned" | "in_review" | "done" | "withdrawn";
export type SeatSource = "entry" | "claimed" | "assigned" | "nominated" | "added";

/** The states in which a seat is still held: not finished, not taken away. The server's `OPEN_SEAT_STATES`. */
export const OPEN_SEAT_STATES: readonly SeatState[] = ["assigned", "in_review"];

/** One person reviewing a record for a party. Every seat endpoint answers with this. */
export interface ReviewerSeat {
  id:            number;
  assignment:    number;
  record:        number;
  party:         Party;
  party_label:   string;
  reviewer:      number | null;
  reviewer_name: string | null;
  state:         SeatState;
  state_label:   string;
  source:        SeatSource;
  assigned_by:   number | null;
  assigned_at:   string | null;
  /** Stamped by *Open review*: when this reviewer started. */
  opened_at:     string | null;
  done_at:       string | null;
}

// ---------------------------------------------------------------------------
// Review & Routing Tracker (IR-258, ADR-021 §14)
// ---------------------------------------------------------------------------

/** ADR-021 §1. `intake` is its own party, even though RDCO staffs it. */
export type Party = "intake" | "adviser" | "itso" | "ierc" | "ktto" | "rdco";

export type WorkflowState =
  | "awaiting_resubmission"
  | "awaiting_document"
  | "submitted"
  | "final_review"
  | "in_review"
  | PipelineStatus;

export type TrackerPartyState =
  | "active"
  | "completed"
  | "withdrawn"
  | "not_requested"
  | "awaiting"
  /** RDCO on a new-model record no specialist office has held (ADR-032 §10, IR-269). */
  | "not_required";

/**
 * What a finished (or reviewing) party concluded: its clearance status for an
 * office, else its latest review decision. Named so an outcome the UI has not
 * styled fails `tsc` rather than falling through.
 */
export type TrackerOutcome =
  | RecordClearance["status"]
  | "approved"
  | "rejected"
  | "negative_finding";

export interface TrackerReview {
  id:               number;
  party:            Party | null;
  label:            string | null;
  status:           string;
  status_label:     string;
  comment:          string;
  reviewed_by_name: string | null;
  created_at:       string | null;
  /** The version it was made against; null for reviews written before IR-416. */
  version:          number | null;
}

export interface TrackerHolder {
  party:     Party;
  label:     string;
  opened_at: string | null;
  opened_by: string | null;
}

export interface TrackerPartyRow {
  party:         Party;
  /** Server-worded; Intake reads differently to staff and to students. */
  label:         string;
  state:         TrackerPartyState;
  state_label:   string;
  /**
   * Only for an active party: true once it has recorded a review, false while
   * it is requested but not yet started. Always false in any other state.
   */
  started:       boolean;
  /** Null for a party that was never assigned. */
  outcome:       TrackerOutcome | null;
  outcome_label: string | null;
  at:            string | null;
  preserved:     boolean;
  /**
   * This party has an open document request and is waiting on it (◐). Null
   * when the viewer may not read the record's document requests (IR-349):
   * not disclosed, which is not the same as false.
   */
  awaiting_document: boolean | null;
  /**
   * The outcome is an earlier review round's, standing while the office
   * reviews again; `outcome_label` already says so (IR-269).
   */
  outcome_earlier: boolean;
  /** Active, with nobody there reviewing it yet: the office's pool (◌). */
  in_pool:         boolean;
  /** This party has an open revision request: *Changes requested* (IR-272). */
  changes_requested: boolean;
  /**
   * Who is reviewing for this party, per seat. Null when the viewer does not
   * take part in the review: not disclosed, which is not the same as none.
   */
  seats:           TrackerSeat[] | null;
}

export interface TrackerSeat {
  reviewer_name: string | null;
  state:         SeatState;
  state_label:   string;
  /** A finished seat's own verdict: `approved` (cleared) or `negative_finding`. */
  verdict:       string | null;
  verdict_label: string | null;
}

export interface TrackerRoutingGroup {
  group_id:   string;
  /** Null when the submitter sent the record in. */
  from:       Party | null;
  from_label: string | null;
  to:         Party[];
  to_labels:  string[];
  /** Who routed it, and why: null to a viewer who may not read the review (IR-479). */
  actor:      string | null;
  reason:     string | null;
  at:         string | null;
}

export interface TrackerResubmission {
  id:           number;
  party:        Party;
  label:        string;
  state:        "open" | "resubmitted" | "withdrawn";
  state_label:  string;
  /** Null, as `requested_by` and `resolved_by` are, to a viewer who may not read the review (IR-479). */
  reason:       string | null;
  /** The `declined` review that made this request, one of `reviews` (IR-412). */
  review:       number;
  /** The version it was made against; null for one made before versions were recorded (IR-272). */
  version:      number | null;
  requested_by: string | null;
  created_at:   string | null;
  resolved_at:  string | null;
  /** Who resubmitted, or withdrew, and so closed it (IR-412). */
  resolved_by:  string | null;
}

export interface RecordTracker {
  record_id:             number;
  record_type:           string | null;
  workflow_state:        WorkflowState;
  workflow_state_label:  string;
  current_holders:       TrackerHolder[];
  can_act:               Party[];
  parties:               TrackerPartyRow[];
  routing_history:       TrackerRoutingGroup[];
  /** Routing was not recorded before this date (IR-257's backfill wrote none). */
  routing_recorded_from: string | null;
  /**
   * Null to a viewer who may not read the review (IR-479): who reviewed and
   * what they wrote is internal workflow data, as document requests are.
   */
  reviews:               TrackerReview[] | null;
  /** Each a timeline entry of its own (IR-416). Null as `reviews` is. */
  versions:              RecordVersion[] | null;
  resubmissions:         TrackerResubmission[];
  /** Null when the viewer may not read them (IR-349) -- not "there are none". */
  document_requests:     DocumentRequest[] | null;
  clearances:            RecordClearance[];
  resubmission:          RecordResubmission;
}

export interface RecordFormData {
  title:                 string;
  year_accomplished?:    number;
  year_completed?:       number;
  abstract?:             string;
  classification?:       number | null;
  psced?:                number | null;
  record_type?:          number;
  adviser?:              number;
  is_ip?:                boolean;
  for_commercialization?: boolean;
  community_extension?:  boolean;
  /** ADR-018: conditional parallel-office routing. */
  requires_ethics_review?: boolean;
  requested_itso?:        boolean;
  requested_ierc?:        boolean;
  requested_ktto?:        boolean;
  /** Flat list of author name strings — backend creates Author rows. */
  authors?:              string[];
}

export interface Classification {
  id:   number;
  name: string;
}

export interface PSCEDClassification {
  id:   number;
  name: string;
}

export interface RecordType {
  id:   number;
  name: string;
}

export interface DownloadRequest {
  id:                  number;
  record:              number;
  record_title:        string;
  requested_by:        number;
  requested_by_name:   string | null;
  requested_by_email:  string | null;
  status:              "pending" | "approved" | "declined";
  reviewed_by:         number | null;
  reviewed_at:         string | null;
  created_at:          string;
}

export interface DeleteRequest {
  id:                  number;
  record:              number;
  record_title:        string;
  requested_by:        number;
  requested_by_name:   string | null;
  requested_by_email:  string | null;
  reason:              string;
  status:              "pending" | "approved" | "declined";
  reviewed_by:         number | null;
  reviewed_at:         string | null;
  created_at:          string;
}

// ---------------------------------------------------------------------------
// Document requests (ADR-022, IR-262)
// ---------------------------------------------------------------------------

export type DocumentRequestState = "open" | "fulfilled" | "withdrawn";
export type DocumentRequestItemState = "missing" | "uploaded" | "accepted" | "rejected";

export interface DocumentRequestItem {
  id:          number;
  /** Null for a free-text "Other" item. */
  slot:        number | null;
  label:       string;
  state:       DocumentRequestItemState;
  state_label: string;
  upload:      number | null;
  uploaded_at: string | null;
  /**
   * The requesting party's reason, the last time it rejected an upload
   * (IR-263). A rejected item is back to `missing`; this says why. Plain
   * text. Null when it was never rejected.
   */
  rejection_reason: string | null;
  /** When the requesting party last accepted or rejected an upload. */
  decided_at:  string | null;
}

export interface DocumentRequest {
  id:           number;
  party:        Party;
  /** Server-worded; Intake reads "Intake" to the owner. */
  label:        string;
  state:        DocumentRequestState;
  state_label:  string;
  /** Plain text, as the reviewer wrote it. Never render as markup. */
  message:      string;
  requested_by: string | null;
  created_at:   string;
  closed_at:    string | null;
  /**
   * The viewer can staff the party that asked, so may accept, reject or
   * withdraw (ADR-022 §3.4, §4). Server-decided; the controls follow it.
   */
  can_manage:   boolean;
  items:        DocumentRequestItem[];
}

/** `PATCH /document-request-items/<id>/` (IR-263). A rejection needs a reason. */
export type DocumentRequestItemDecision =
  | { action: "accept" }
  | { action: "reject"; reason: string };

/** One entry of a new request: a picklist slot, or free text for "Other". */
export type DocumentRequestItemInput = { slot: number } | { label: string };

export interface DocumentRequestSlot {
  id:   number;
  name: string;
}
