import { apiClient } from "./client";
import type { ReportedComment } from "@/types/records";

/**
 * Comment moderation for RDCO and the System Admin (ADR-032 §7, IR-691):
 * the Reported comments queue, and removing or dismissing. Reporting is a
 * reader's act on the paper (`recordsApi.reportPublicComment`).
 */
export const moderationApi = {
  reportedComments: (options?: { signal?: AbortSignal }) =>
    apiClient.get<{ comments: ReportedComment[] }>("/moderation/comments/", options),
  /** Any comment, reported or not; the writer is told the reason. 409 once handled. */
  removeComment: (commentId: number, reason: string) =>
    apiClient.post<void>(`/moderation/comments/${commentId}/remove/`, { reason }),
  /** Closes the comment's open reports and leaves it standing. 409 once handled. */
  dismissReports: (commentId: number) =>
    apiClient.post<void>(`/moderation/comments/${commentId}/dismiss/`),
};
