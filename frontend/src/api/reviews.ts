import { apiClient } from "./client";
import type { Review, ReviewSubmitPayload } from "@/types/reviews";
import type { RecordListItem } from "@/types/records";

export const reviewsApi = {
  pending:    () => apiClient.get<RecordListItem[]>("/reviews/pending/"),
  approved:   () => apiClient.get<RecordListItem[]>("/reviews/approved/"),
  declined:   () => apiClient.get<RecordListItem[]>("/reviews/declined/"),
  submit:     (data: ReviewSubmitPayload) => apiClient.post<Review>("/reviews/submit/", data),
  resubmit:   (recordId: number)         => apiClient.post("/reviews/resubmit/", { record_id: recordId }),
  generatePin:(recordId: number, email: string) => apiClient.post("/reviews/pin/generate/", { record: recordId, email }),
  verifyPin:  (recordId: number, pin: string)   => apiClient.post("/reviews/pin/verify/", { record: recordId, pin }),
};
