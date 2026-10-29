import { apiClient } from "./client";
import type { AuditEvent, AuditEventType } from "@/types/audit";

interface PaginatedResponse<T> { count: number; results: T[]; }

export interface AuditListParams {
  event_type?: AuditEventType;
  record?:     number;
  user?:       number;
  from?:       string;
  to?:         string;
  page?:       number;
  page_size?:  number;
}

export const auditApi = {
  list:     (params?: AuditListParams) =>
    apiClient.get<PaginatedResponse<AuditEvent>>("/audit/", { params }),
  exportCsv: (params?: AuditListParams) =>
    apiClient.get<Blob>("/audit/export/", { params, responseType: "blob" }),
  sessions: () => apiClient.get<AuditEvent[]>("/audit/sessions/"),
};
