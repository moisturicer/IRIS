import { apiClient } from "./client";
import type {
  RecordListItem, RecordDetail, RecordFormData,
  Classification, PSCEDClassification, RecordType,
  DownloadRequest, DeleteRequest, RecordTracker,
  DocumentRequest, DocumentRequestItemDecision, DocumentRequestItemInput,
  DocumentRequestSlot, Party,
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

  // My records — backend returns a plain array (not paginated).
  // RecordViewSet.mine() (the actual registered action -- MyRecordsViewSet
  // elsewhere in views.py looks like it should serve this with
  // RecordDetailSerializer already, but isn't wired into urls.py at all) now
  // uses RecordDetailSerializer too, so clearances/ip_type/requested_itso
  // etc. are really in this payload. Was mistyped as RecordListItem[] before
  // the backend fix, matching what the endpoint used to actually return.
  mine:           (params?: Record<string, unknown>) =>
    apiClient.get<RecordDetail[]>("/records/mine/", { params }),

  detail:         (id: number) => apiClient.get<RecordDetail>(`/records/${id}/`),
  /**
   * Related institutional works. The backend reuses the Ask IRIS retrieval
   * service, so this returns the retrieval shape (RetrievedSource.as_dict()),
   * not a RecordListItem.
   */
  tracker:        (id: number) => apiClient.get<RecordTracker>(`/records/${id}/tracker/`),

  /** Document requests on a record, oldest first (ADR-022 §5, IR-262). */
  documentRequests: (id: number) =>
    apiClient.get<DocumentRequest[]>(`/records/${id}/document-requests/`),
  /** A holder asks the owner for documents. `party` only when holding two. */
  createDocumentRequest: (
    id: number,
    body: { message: string; items: DocumentRequestItemInput[]; party?: Party },
  ) => apiClient.post<DocumentRequest>(`/records/${id}/document-requests/`, body),
  /** The requesting party accepts or rejects one upload; answers with the request. */
  decideDocumentRequestItem: (itemId: number, body: DocumentRequestItemDecision) =>
    apiClient.patch<DocumentRequest>(`/document-request-items/${itemId}/`, body),
  /** The requesting party withdraws an open request (IR-263). */
  withdrawDocumentRequest: (requestId: number, reason?: string) =>
    apiClient.patch<DocumentRequest>(`/document-requests/${requestId}/`, {
      action: "withdraw",
      ...(reason ? { reason } : {}),
    }),
  /** The picklist: the record type's upload slots. */
  documentRequestSlots: (id: number) =>
    apiClient.get<DocumentRequestSlot[]>(`/records/${id}/document-requests/slots/`),
  similar:        (id: number) =>
    apiClient.get<{ results: SemanticSearchResult[] }>(`/records/${id}/similar/`),
  create:         (data: RecordFormData) => apiClient.post<RecordDetail>("/records/", data),
  update:         (id: number, data: Partial<RecordFormData>) => apiClient.patch<RecordDetail>(`/records/${id}/`, data),
  /**
   * The manuscript itself. `abstract_file` is a plain FileField on Record,
   * separate from the per-type UploadSlot/RecordUpload system — no seeded
   * slot is named "manuscript" for any record type, so this is the only way
   * to attach it. AddRecordPage never called this before, which is why
   * records could reach the paper view with zero files (see
   * iris-paper-view-design memory).
   */
  uploadManuscript: (id: number, file: File) => {
    const fd = new FormData();
    fd.append("abstract_file", file);
    return apiClient.patch<RecordDetail>(`/records/${id}/`, fd, {
      headers: { "Content-Type": "multipart/form-data" },
    });
  },
  /**
   * The manuscript's own bytes, for the in-app PDF reader (IR-334, IR-335).
   * Through `apiClient` rather than a plain `<a href>`: `/records/<id>/
   * manuscript/` requires `IsAuthenticated`, and a bare anchor navigation
   * carries no `Authorization` header — the bearer token lives in memory, not
   * a cookie. `responseType: "blob"` so the reader can make one object URL
   * do double duty: `Blob.arrayBuffer()` feeds pdf.js, and the same URL
   * backs a "download"/"open in new tab" link with no second request.
   */
  manuscriptBlob: (id: number) =>
    apiClient.get<Blob>(`/records/${id}/manuscript/`, { responseType: "blob" }),
  delete:         (id: number) => apiClient.delete(`/records/${id}/`),
  // `dpaAccepted` is required, not optional (IR-226). The backend refuses a
  // submit without consent, and an optional flag would let a future caller
  // omit it and discover that at runtime instead of at compile time. A record
  // that already carries consent ignores the value, so passing it is always safe.
  submit:         (id: number, dpaAccepted: boolean) =>
    apiClient.post<{ detail: string }>(`/records/${id}/submit/`, { dpa_accepted: dpaAccepted }),
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
