import { apiClient } from "./client";
import type { ReviewerSeat } from "@/types/records";
import type { Review, ReviewSubmitPayload, ReviewQueueRow } from "@/types/reviews";

/**
 * Reviewer seats (ADR-032 §4, IR-415). The server re-checks every act: a
 * 404 is a record the caller cannot see, a 403 an act they may not do, and
 * a 400 one that is not possible now. Each answers with the seat it touched.
 *
 * My Reviews (IR-268) puts *Claim* and *Assign* on its rows; Paper View
 * records *Open review*.
 */
export const seatsApi = {
  /** An office member takes an unclaimed record from their office's pool. */
  claim: (assignmentId: number) =>
    apiClient.post<ReviewerSeat>(`/assignments/${assignmentId}/claim/`),
  /** A coordinator seats a member of their own office. */
  assign: (assignmentId: number, reviewerId: number) =>
    apiClient.post<ReviewerSeat>(`/assignments/${assignmentId}/assign/`, { reviewer: reviewerId }),
  /** A seat holder brings in a colleague from their own office. Never another office: that is routing. */
  addReviewer: (assignmentId: number, reviewerId: number) =>
    apiClient.post<ReviewerSeat>(`/assignments/${assignmentId}/add-reviewer/`, { reviewer: reviewerId }),
  /** *Open review*: the holder's seat moves to `in_review` and records when. Idempotent. */
  open: (seatId: number) => apiClient.post<ReviewerSeat>(`/seats/${seatId}/open/`),
  /** A coordinator moves an unfinished seat to another member; answers with the new seat. */
  reassign: (seatId: number, reviewerId: number) =>
    apiClient.post<ReviewerSeat>(`/seats/${seatId}/reassign/`, { reviewer: reviewerId }),
  /** A coordinator takes an unfinished seat away. */
  withdraw: (seatId: number) => apiClient.post<ReviewerSeat>(`/seats/${seatId}/withdraw/`),
};

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
