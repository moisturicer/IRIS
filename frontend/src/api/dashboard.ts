import { apiClient } from "./client";

export interface DashboardStats {
  total_mine:      number;
  pending_mine:    number;
  approved_mine:   number;
  declined_mine:   number;
  total_published: number;
}

export interface ClassificationChartRow {
  classification__name: string | null;
  count:                number;
}

export const dashboardApi = {
  stats:           () => apiClient.get<DashboardStats>("/dashboard/stats/"),
  classifications: () => apiClient.get<ClassificationChartRow[]>("/dashboard/charts/classifications/"),
};
