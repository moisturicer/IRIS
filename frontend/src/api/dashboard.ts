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

export const dashboardApi = {
  stats: () => apiClient.get<DashboardStats>("/dashboard/stats/"),
};
