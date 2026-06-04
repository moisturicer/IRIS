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
