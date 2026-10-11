import { apiClient } from "./client";
import type {
  RecordListItem, RecordDetail, RecordFormData,
  Classification, PSCEDClassification, RecordType,
  DownloadRequest, DeleteRequest, RecordTracker,
  DocumentRequest, DocumentRequestItemDecision, DocumentRequestItemInput,
  DocumentRequestSlot, DecisionOutcome, OfficeReviewOutcome, Party, RouteOptions, RouteRequest,
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
  /** The requesting party withdraws an open request (IR-263). No reason is recorded. */
  withdrawDocumentRequest: (requestId: number) =>
    apiClient.patch<DocumentRequest>(`/document-requests/${requestId}/`, { action: "withdraw" }),
  /** The routing dialog's picklist: offices, their members, the author's hints (IR-261). */
  routeOptions: (id: number) => apiClient.get<RouteOptions>(`/records/${id}/route-options/`),
  /** The Adviser accepts and routes to offices (ADR-032 §3). Answers with the tracker. */
  acceptAndRoute: (id: number, body: RouteRequest) =>
    apiClient.post<RecordTracker>(`/records/${id}/accept-and-route/`, body),
  /** A seat holder routes onward; their own review continues (ADR-032 §4). */
  route: (id: number, body: RouteRequest) =>
    apiClient.post<RecordTracker>(`/records/${id}/route/`, body),
  /**
   * An office seat holder clears the record or records a finding (ADR-032
   * §3-§4, IR-269). A finding needs a comment. Answers with the tracker.
   */
  officeReview: (id: number, body: { outcome: OfficeReviewOutcome; comment: string }) =>
    apiClient.post<RecordTracker>(`/records/${id}/office-review/`, body),
  /**
   * The Adviser or RDCO decides the record (ADR-032 §3, IR-270). A reject
   * needs a comment, its reason. `token` is record detail's `decision.token`;
   * a record that changed since is refused with a 409 carrying the fresh
   * `decision`. Answers with the tracker.
   */
  decide: (id: number, body: { outcome: DecisionOutcome; comment: string; token: string }) =>
    apiClient.post<RecordTracker>(`/records/${id}/decide/`, body),
  /**
   * A holder of an opened seat asks the owners for a revision, with a reason
   * (ADR-032 §5, IR-272). Nothing can be decided until the owner answers it.
   */
  requestRevision: (id: number, body: { reason: string }) =>
    apiClient.post<RecordTracker>(`/records/${id}/request-revision/`, body),
  /** A seat holder of the party that asked withdraws its open revision request (IR-272). */
  withdrawRevisionRequest: (id: number, requestId: number) =>
    apiClient.post<RecordTracker>(`/records/${id}/revision-requests/${requestId}/withdraw/`),
  /**
   * An owner answers every open revision request with the record's next
   * version (ADR-032 §5, IR-273). Only the parties that asked review it again.
   */
  submitNewVersion: (id: number) =>
    apiClient.post<RecordTracker>(`/records/${id}/new-version/`),
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
   * to attach it.
   *
   * `onProgress` gets 0–100 as the bytes go up, and `signal` cancels the
   * upload (IR-408: Publish shows progress and lets the author stop it).
   */
  uploadManuscript: (
    id: number,
    file: File,
    options: { onProgress?: (percent: number) => void; signal?: AbortSignal } = {},
  ) => {
    const fd = new FormData();
    fd.append("abstract_file", file);
    return apiClient.patch<RecordDetail>(`/records/${id}/`, fd, {
      headers: { "Content-Type": "multipart/form-data" },
      signal: options.signal,
      onUploadProgress: (event) => {
        const total = event.total ?? file.size;
        if (options.onProgress && total > 0) options.onProgress((event.loaded / total) * 100);
      },
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
  /**
   * An earlier version's manuscript (IR-416), fetched the same way and for
   * the same reason. Participants only: anyone else gets a 404.
   */
  versionManuscriptBlob: (id: number, version: number) =>
    apiClient.get<Blob>(`/records/${id}/versions/${version}/manuscript/`, { responseType: "blob" }),
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

  // Delete requests: raised by `delete` above (DELETE /records/<id>/), then only
  // read and decided here. The queue has no create or update route (IR-496).
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
