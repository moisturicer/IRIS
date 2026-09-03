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
  comment:          string;
  reviewed_by_name: string | null;
  updated_at:       string;
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
  owners:          RecordOwner[];
  keywords?:       string[];
  is_deleted:      boolean;
  reviews:         RecordReview[];
  /** Per-office clearance state — makes clearance-aware resubmission visible. */
  clearances:      RecordClearance[];
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
