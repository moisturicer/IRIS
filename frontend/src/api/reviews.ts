import { apiClient } from "./client";
import type { AddReviewerOptions, ReviewerSeat } from "@/types/records";
import type {
  OfficeConsole,
  MyReviewsPage,
  MyReviewsQuery,
  WorkflowAnalytics,
  WorkflowAnalyticsQuery,
} from "@/types/reviews";


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
  /** Who a coordinator may assign: their office's members, marked when already seated (IR-268). */
  assignOptions: (assignmentId: number) =>
    apiClient.get<AddReviewerOptions>(`/assignments/${assignmentId}/assign/`),
  /** A coordinator seats a member of their own office. */
  assign: (assignmentId: number, reviewerId: number) =>
    apiClient.post<ReviewerSeat>(`/assignments/${assignmentId}/assign/`, { reviewer: reviewerId }),
  /** Who a seat holder may add: their office's members, marked when already seated (IR-269). */
  addReviewerOptions: (assignmentId: number) =>
    apiClient.get<AddReviewerOptions>(`/assignments/${assignmentId}/add-reviewer/`),
  /** A seat holder brings in a colleague from their own office. Never another office: that is routing. */
  addReviewer: (assignmentId: number, reviewerId: number) =>
    apiClient.post<ReviewerSeat>(`/assignments/${assignmentId}/add-reviewer/`, { reviewer: reviewerId }),
  /** *Open review*: the holder's seat moves to `in_review` and records when. Idempotent. */
  open: (seatId: number) => apiClient.post<ReviewerSeat>(`/seats/${seatId}/open/`),
  /** A coordinator moves an unfinished seat to another member, saying why (IR-623); answers with the new seat. */
  reassign: (seatId: number, reviewerId: number, reason: string) =>
    apiClient.post<ReviewerSeat>(`/seats/${seatId}/reassign/`, { reviewer: reviewerId, reason }),
  /**
   * A coordinator moves an assignment's due date later, saying why (ADR-043 §6).
   * `dueAt` must be 23:59 Asia/Manila on a later day; the server refuses anything else.
   */
  extend: (assignmentId: number, dueAt: string, reason: string) =>
    apiClient.post(`/assignments/${assignmentId}/extend/`, { due_at: dueAt, reason }),
  /** A coordinator takes an unfinished seat away. */
  withdraw: (seatId: number) => apiClient.post<ReviewerSeat>(`/seats/${seatId}/withdraw/`),
};

export const reviewsApi = {
  /**
   * One tab of My Reviews (IR-268), with every tab's count. Each tab is a
   * server-side question, so the counts stay honest and Done can page.
   */
  mine: ({ tab, outcome, office, cursor, sort, overdue }: MyReviewsQuery) =>
    apiClient.get<MyReviewsPage>("/reviews/mine/", {
      params: {
        tab,
        ...(outcome ? { outcome } : {}),
        ...(office ? { office } : {}),
        ...(cursor ? { cursor } : {}),
        ...(sort ? { sort } : {}),
        ...(overdue ? { overdue: "1" } : {}),
      },
    }),
  /**
   * Workflow analytics (IR-626): an office's own figures, every party's for
   * RDCO. Empty filters are left off, so the server applies none.
   */
  analytics: ({ office, from, to }: WorkflowAnalyticsQuery) =>
    apiClient.get<WorkflowAnalytics>("/reviews/analytics/", {
      params: {
        ...(office ? { office } : {}),
        ...(from ? { from } : {}),
        ...(to ? { to } : {}),
      },
    }),
  /** A coordinator's console of their office's open work (IR-623). Refused (403) to anyone else. */
  office: (office: string | null) =>
    apiClient.get<OfficeConsole>("/reviews/office/", { params: office ? { office } : {} }),
};
