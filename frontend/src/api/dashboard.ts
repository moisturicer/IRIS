import { apiClient } from "./client";

export interface DashboardStats {
  total_mine:      number;
  pending_mine:    number;
  approved_mine:   number;
  declined_mine:   number;
  /** The user's records waiting on them: a revision or document asked for (IR-534, B2). */
  needs_action_mine: number;
  /** Reviews waiting on the user: My Reviews' To review count, its sidebar badge (IR-1208). */
  reviews_waiting_mine?: number;
  total_published: number;
}

/**
 * What waits in each queue the caller works (IR-1138): RDCO's three request
 * queues, and the Reported comments queue RDCO shares with the System Admin
 * (IR-691), who is told that count alone. Anyone else is refused.
 */
export interface QueueCounts {
  download_requests?:    number;
  delete_requests?:      number;
  role_change_requests?: number;
  reported_comments?:    number;
}

export const dashboardApi = {
  queueCounts: () => apiClient.get<QueueCounts>("/dashboard/queue-counts/"),
  stats: () => apiClient.get<DashboardStats>("/dashboard/stats/"),
};
