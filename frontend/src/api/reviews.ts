import { apiClient } from "./client";
import type { Review, ReviewSubmitPayload, ReviewQueueRow } from "@/types/reviews";

/** The three queue filters. One screen, three server-side views (IR-143). */
export type QueueFilter = "pending" | "approved" | "declined";

export const reviewsApi = {
  /**
   * One queue, three filters. Each is a distinct server-side question -- what
   * awaits me, what I cleared, what I sent back -- so the filter is a request,
   * not a client-side slice of one list. That also keeps the row count honest.
   */
  queue: (filter: QueueFilter) => apiClient.get<ReviewQueueRow[]>(`/reviews/${filter}/`),
  submit:     (data: ReviewSubmitPayload) => apiClient.post<Review>("/reviews/submit/", data),
  resubmit:   (recordId: number)         => apiClient.post("/reviews/resubmit/", { record_id: recordId }),
  /** Request a one-time PIN emailed to the current user's account email. */
  generatePin:(recordId: number) => apiClient.post("/reviews/pin/generate/", { record_id: recordId }),
  /** Verify a PIN and confirm access. Returns { verified: true, record_id }. */
  verifyPin:  (recordId: number, pin: string) => apiClient.post<{ verified: boolean; record_id: number }>("/reviews/pin/verify/", { record_id: recordId, pin }),
};
