import axios from "axios";
import { apiClient } from "./client";
import { API_BASE } from "@/lib/constants";
import type {
  DownloadRequest,
  RecordListItem,
  RecordDetail,
  RecordFormData,
  Classification,
  PSCEDClassification,
  RecordType,
} from "@/types/records";

interface PaginatedResponse<T> {
  count:    number;
  next:     string | null;
  previous: string | null;
  results:  T[];
}

export const recordsApi = {
  // Published records (paginated, filterable)
  list:           (params?: Record<string, unknown>) =>
    apiClient.get<PaginatedResponse<RecordListItem>>("/records/", { params }),

  // My records
  mine:           (params?: Record<string, unknown>) =>
    apiClient.get<PaginatedResponse<RecordListItem>>("/records/mine/", { params }),

  detail:         (id: number) => apiClient.get<RecordDetail>(`/records/${id}/`),
  create:         (data: RecordFormData) => apiClient.post<RecordDetail>("/records/", data),
  update:         (id: number, data: Partial<RecordFormData>) => apiClient.patch<RecordDetail>(`/records/${id}/`, data),
  delete:         (id: number) => apiClient.delete(`/records/${id}/`),
  incrementAccess:(id: number) => apiClient.post(`/records/${id}/increment_access/`),
  updateTags:     (id: number, tags: { is_ip?: boolean; for_commercialization?: boolean; community_extension?: boolean }) =>
    apiClient.patch(`/records/${id}/tags/`, tags),

  importExcel:    (file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    return apiClient.post("/records/import_excel/", fd, { headers: { "Content-Type": "multipart/form-data" } });
  },
  downloadTemplate: () => apiClient.get("/records/download_template/", { responseType: "blob" }),

  // Reference data
  classifications: () => apiClient.get<PaginatedResponse<Classification>>("/records/classifications/"),
  pscedList:       () => apiClient.get<PaginatedResponse<PSCEDClassification>>("/records/psced-classifications/"),
  recordTypes:     () => apiClient.get<PaginatedResponse<RecordType>>("/records/record-types/"),

  // Download / delete requests
  listDownloadRequests: (params?: { status?: string }) =>
    apiClient.get<PaginatedResponse<DownloadRequest>>("/records/download-requests/", { params }),

  requestDownload: (recordId: number) =>
    apiClient.post<DownloadRequest>("/records/download-requests/", { record: recordId }),

  decideDownloadRequest: (id: number, action: "approve" | "decline") =>
    apiClient.patch<DownloadRequest>(`/records/download-requests/${id}/`, { action }),

  /** Redeem email/download link JWT — no session required. */
  redeemDownloadToken: (token: string) =>
    axios.get(`${API_BASE}/records/download/`, {
      params: { token },
      responseType: "blob",
    }),

  requestDelete:   (recordId: number, reason?: string) => apiClient.post("/records/delete-requests/", { record: recordId, reason }),
  approveRequest:  (type: "download" | "delete", id: number, action: "approve" | "decline") =>
    apiClient.patch(`/records/${type}-requests/${id}/`, { action }),
};
