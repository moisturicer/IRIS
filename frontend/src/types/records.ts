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
}

export interface RecordClearance {
  office:           "itso" | "ierc" | "ktto";
  office_label:     string;
  status:           "pending" | "cleared" | "declined" | "rejected" | "not_cleared";
  /** Server-supplied wording, so a status can be renamed without a release. */
  status_label:     string;
  comment:          string;
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
  reviews:         RecordReview[];
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
  | "awaiting";

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
}

export interface TrackerRoutingGroup {
  group_id:   string;
  /** Null when the submitter sent the record in. */
  from:       Party | null;
  from_label: string | null;
  to:         Party[];
  to_labels:  string[];
  actor:      string | null;
  reason:     string;
  at:         string | null;
}

export interface TrackerResubmission {
  id:           number;
  party:        Party;
  label:        string;
  state:        "open" | "resubmitted" | "withdrawn";
  state_label:  string;
  reason:       string;
  requested_by: string | null;
  created_at:   string | null;
  resolved_at:  string | null;
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
  reviews:               TrackerReview[];
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
  classification?:       number;
  psced?:                number;
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
