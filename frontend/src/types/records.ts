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
  status:           "pending" | "cleared" | "declined" | "rejected";
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
  /** ADR-018 (Proposed): what the submitter requested; RDCO confirms at intake. */
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
  /** ADR-018 (Proposed): conditional parallel-office routing. */
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
