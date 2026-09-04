import { apiClient } from "./client";
import type { Opportunity } from "@/types/opportunities";

interface PaginatedResponse<T> { count: number; results: T[]; }

export const opportunitiesApi = {
  list: () => apiClient.get<PaginatedResponse<Opportunity>>("/opportunities/"),

  /**
   * The deadline as a calendar file.
   *
   * Fetched through `apiClient` rather than pointed at by a plain link so the
   * Authorization header goes with it -- a bare <a href> would hit the endpoint
   * unauthenticated and get a 401 instead of a file.
   */
  calendar: (id: number) =>
    apiClient.get<Blob>(`/opportunities/${id}/calendar/`, { responseType: "blob" }),
};
