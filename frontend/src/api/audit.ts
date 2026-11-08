import { apiClient } from "./client";
import type { AuditEvent } from "@/types/audit";
import type { AuditEventTypeOption } from "@/lib/auditEventGroups";

interface PaginatedResponse<T> { count: number; results: T[]; }

export interface AuditListParams {
  // A string, not the frontend's union: the filter also offers types learned
  // from the server (IR-913), and the log itself validates the value.
  event_type?: string;
  record?:     number;
  user?:       number;
  from?:       string;
  to?:         string;
  page?:       number;
  page_size?:  number;
}

export const auditApi = {
  list:     (params?: AuditListParams, opts?: { signal?: AbortSignal }) =>
    apiClient.get<PaginatedResponse<AuditEvent>>("/audit/", { params, signal: opts?.signal }),
  exportCsv: (params?: AuditListParams) =>
    apiClient.get<Blob>("/audit/export/", { params, responseType: "blob" }),
  /** Every event type the log can hold, with the server's labels (IR-913). */
  eventTypes: () => apiClient.get<AuditEventTypeOption[]>("/audit/event-types/"),
  sessions: () => apiClient.get<AuditEvent[]>("/audit/sessions/"),
};
