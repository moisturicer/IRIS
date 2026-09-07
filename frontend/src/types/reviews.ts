import type { RecordListItem } from "@/types/records";
import type { PipelineStatus } from "@/lib/constants";
export type ReviewStage  = "adviser" | "rdco_intake" | "itso" | "ktto" | "rdco";
export type ReviewStatus = "approved" | "declined" | "rejected";

export interface Review {
  id:               number;
  record:           number;
  reviewed_by:      number;
  reviewed_by_name: string;
  stage:            ReviewStage;
  status:           ReviewStatus;
  comment:          string;
  created_at:       string;
}

export interface ReviewSubmitPayload {
  record_id: number;
  status:    ReviewStatus;
  comment?:  string;
}

/** One office's decision on a record, as shown to a *peer* reviewer. */
export interface PeerClearance {
  office:       "itso" | "ierc" | "ktto";
  office_label: string;
  status:       "pending" | "cleared" | "declined" | "rejected";
  status_label: string;
}

/**
 * A review-queue row (IR-139).
 *
 * A `RecordListItem` plus the context that makes the row mean something to the
 * office looking at it. Before this, every reviewer saw title/type/date and had
 * no way to tell which clearance was theirs or whether anyone else had acted.
 */
export interface ReviewQueueRow extends RecordListItem {
  stage:              PipelineStatus;
  /** Server-worded. Never map a stage key to English on the client. */
  stage_label:        string;
  /** The office *this viewer* would be recording a clearance for; null for
   *  sequential reviewers (Adviser, RDCO), who decide the record itself. */
  your_office:        "itso" | "ierc" | "ktto" | null;
  your_office_label:  string | null;
  /** The other offices' decisions. Status only — never their comments. */
  peers:              PeerClearance[];
  waiting_since:      string;
  waiting_days:       number;
  resubmitted:        boolean;
  resubmission_count: number;
}
