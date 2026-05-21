import { apiClient } from "./client";
import type { Notification } from "@/types/notifications";

interface PaginatedResponse<T> { count: number; results: T[]; }

export const notificationsApi = {
  list:       (unread?: boolean) =>
    apiClient.get<PaginatedResponse<Notification>>("/notifications/", { params: unread ? { unread: "true" } : {} }),
  markRead:   (id: number)  => apiClient.patch(`/notifications/${id}/read/`),
  markAllRead:()            => apiClient.post("/notifications/mark-all-read/"),
};
