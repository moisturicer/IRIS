import { apiClient } from "./client";

export interface DashboardStats {
  total_mine:      number;
  pending_mine:    number;
  approved_mine:   number;
  declined_mine:   number;
  /** The user's records waiting on them: a revision or document asked for (IR-534, B2). */
  needs_action_mine: number;
  total_published: number;
}

/** What waits in RDCO's three queues (IR-1138). RDCO only: anyone else is refused. */
export interface QueueCounts {
  download_requests: number;
  delete_requests:   number;
  role_change_requests:     number;
}

export const dashboardApi = {
  queueCounts: () => apiClient.get<QueueCounts>("/dashboard/queue-counts/"),
  stats: () => apiClient.get<DashboardStats>("/dashboard/stats/"),
};
