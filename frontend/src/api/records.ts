import { apiClient } from "./client";
import type {
  RecordListItem, RecordDetail, RecordFormData,
  Classification, PSCEDClassification, RecordType,
  DownloadRequest, DeleteRequest,
} from "@/types/records";
import type { SemanticSearchResult } from "@/types/ai";

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

  // My records — backend returns a plain array (not paginated)
  mine:           (params?: Record<string, unknown>) =>
    apiClient.get<RecordListItem[]>("/records/mine/", { params }),

  detail:         (id: number) => apiClient.get<RecordDetail>(`/records/${id}/`),
  /**
   * Related institutional works. The backend reuses the Ask IRIS retrieval
   * service, so this returns the retrieval shape (RetrievedSource.as_dict()),
   * not a RecordListItem.
   */
  similar:        (id: number) =>
    apiClient.get<{ results: SemanticSearchResult[] }>(`/records/${id}/similar/`),
  create:         (data: RecordFormData) => apiClient.post<RecordDetail>("/records/", data),
  update:         (id: number, data: Partial<RecordFormData>) => apiClient.patch<RecordDetail>(`/records/${id}/`, data),
  delete:         (id: number) => apiClient.delete(`/records/${id}/`),
  submit:         (id: number) => apiClient.post<{ detail: string }>(`/records/${id}/submit/`),
  incrementAccess:(id: number) => apiClient.post(`/records/${id}/increment_access/`),
  updateTags:     (id: number, tags: { is_ip?: boolean; for_commercialization?: boolean; community_extension?: boolean; ip_type?: string }) =>
    apiClient.patch(`/records/${id}/tags/`, tags),
  completeProposal: (id: number) =>
    apiClient.post<{ detail: string }>(`/records/${id}/complete/`),

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

  // Download requests
  requestDownload:         (recordId: number) =>
    apiClient.post("/records/download-requests/", { record: recordId }),
  listDownloadRequests:    (params?: Record<string, unknown>) =>
    apiClient.get<PaginatedResponse<DownloadRequest>>("/records/download-requests/", { params }),
  approveDownloadRequest:  (id: number) =>
    apiClient.post(`/records/download-requests/${id}/approve/`),
  declineDownloadRequest:  (id: number) =>
    apiClient.post(`/records/download-requests/${id}/decline/`),

  // Delete requests
  requestDelete:           (recordId: number, reason?: string) =>
    apiClient.post("/records/delete-requests/", { record: recordId, reason }),
  listDeleteRequests:      (params?: Record<string, unknown>) =>
    apiClient.get<PaginatedResponse<DeleteRequest>>("/records/delete-requests/", { params }),
  approveDeleteRequest:    (id: number) =>
    apiClient.post(`/records/delete-requests/${id}/approve/`),
  declineDeleteRequest:    (id: number) =>
    apiClient.post(`/records/delete-requests/${id}/decline/`),

  // Combined decide helper (approve or decline in one call)
  decideDownloadRequest:   (id: number, action: "approve" | "decline") =>
    apiClient.post<{ download_url?: string }>(`/records/download-requests/${id}/${action}/`),

  // Redeem a one-time download token
  redeemDownloadToken:     (token: string) =>
    apiClient.get(`/records/download/${token}/`, { responseType: "blob" }),
};
