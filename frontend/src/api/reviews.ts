import { apiClient } from "./client";
import type { Review, ReviewSubmitPayload } from "@/types/reviews";
import type { RecordListItem } from "@/types/records";

export const reviewsApi = {
  pending:    () => apiClient.get<RecordListItem[]>("/reviews/pending/"),
  approved:   () => apiClient.get<RecordListItem[]>("/reviews/approved/"),
  declined:   () => apiClient.get<RecordListItem[]>("/reviews/declined/"),
  submit:     (data: ReviewSubmitPayload) => apiClient.post<Review>("/reviews/submit/", data),
  resubmit:   (recordId: number)         => apiClient.post("/reviews/resubmit/", { record_id: recordId }),
  /** Request a one-time PIN emailed to the current user's account email. */
  generatePin:(recordId: number) => apiClient.post("/reviews/pin/generate/", { record_id: recordId }),
  /** Verify a PIN and confirm access. Returns { verified: true, record_id }. */
  verifyPin:  (recordId: number, pin: string) => apiClient.post<{ verified: boolean; record_id: number }>("/reviews/pin/verify/", { record_id: recordId, pin }),
};
