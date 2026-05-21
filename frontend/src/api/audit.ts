import { apiClient } from "./client";
import type { AuditEvent, AuditEventType } from "@/types/audit";

interface PaginatedResponse<T> { count: number; results: T[]; }

interface AuditListParams {
  event_type?: AuditEventType;
  record?:     number;
  user?:       number;
  search?:     string;
  page?:       number;
  page_size?:  number;
}

export const auditApi = {
  list:     (params?: AuditListParams) =>
    apiClient.get<PaginatedResponse<AuditEvent>>("/audit/", { params }),
  sessions: () => apiClient.get<AuditEvent[]>("/audit/sessions/"),
};
