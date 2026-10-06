import { apiClient } from "./client";
import type { RecordUpload, RecordFile, UploadSlot, SlotWithUploads } from "@/types/documents";

/** Upload progress as a percentage, for `UploadDropzone`'s bar. */
type ProgressOptions = { onProgress?: (percent: number) => void };

function progressConfig(file: File, { onProgress }: ProgressOptions) {
  return {
    headers: { "Content-Type": "multipart/form-data" },
    onUploadProgress: (event: { loaded: number; total?: number }) => {
      const total = event.total ?? file.size;
      if (onProgress && total > 0) onProgress((event.loaded / total) * 100);
    },
  };
}

export const documentsApi = {
  // Fetch all UploadSlots for a record type.
  // The global paginator wraps this in { count, next, previous, results }.
  slots:          (recordTypeId?: number) =>
    apiClient.get<{ count: number; results: UploadSlot[] }>("/documents/slots/", {
      params: recordTypeId ? { record_type: recordTypeId } : {},
    }),

  // Fetch slots with their upload history for a specific record (Paper View's Files section)
  slotsForRecord: (recordId: number) =>
    apiClient.get<SlotWithUploads[]>(`/documents/records/${recordId}/slots/`),

  uploads:        (recordId: number) =>
    apiClient.get<RecordUpload[]>("/documents/uploads/", { params: { record: recordId } }),

  /**
   * Upload a PDF answering one item of a document request (ADR-022 §3.2,
   * IR-262). Same endpoint as `upload`; the server takes the slot from the item.
   */
  uploadForRequestItem: (recordId: number, itemId: number, file: File, options: ProgressOptions = {}) => {
    const fd = new FormData();
    fd.append("record",       String(recordId));
    fd.append("request_item", String(itemId));
    fd.append("file",         file);
    return apiClient.post<{ upload: RecordUpload; extraction: { id: number; status: string } }>(
      "/documents/submit/", fd, progressConfig(file, options),
    );
  },

  // Upload a PDF to a slot — triggers Celery extraction task
  upload:         (recordId: number, slotId: number, file: File, options: ProgressOptions = {}) => {
    const fd = new FormData();
    fd.append("record", String(recordId));
    fd.append("slot",   String(slotId));
    fd.append("file",   file);
    return apiClient.post<{ upload: RecordUpload; extraction: { id: number; status: string } }>(
      "/documents/submit/", fd, progressConfig(file, options),
    );
  },

  // Legacy alias kept for any existing callers
  uploadFile:     (recordId: number, slotId: number, file: File) =>
    documentsApi.upload(recordId, slotId, file),

  downloadUpload: (uploadId: number) =>
    apiClient.get(`/documents/uploads/${uploadId}/download/`, { responseType: "blob" }),

  viewUpload: (uploadId: number) =>
    apiClient.get(`/documents/uploads/${uploadId}/download/?inline=true`, { responseType: "blob" }),

  downloadFile: (fileId: number) =>
    apiClient.get(`/documents/files/${fileId}/download/`, { responseType: "blob" }),

  viewFile: (fileId: number) =>
    apiClient.get(`/documents/files/${fileId}/download/?inline=true`, { responseType: "blob" }),

  files:          (recordId: number) =>
    apiClient.get<RecordFile[]>("/documents/files/", { params: { record: recordId } }),

  uploadRecordFile: (recordId: number, file: File, options: ProgressOptions = {}) => {
    const fd = new FormData();
    fd.append("record", String(recordId));
    fd.append("file",   file);
    return apiClient.post<RecordFile>("/documents/files/upload/", fd, progressConfig(file, options));
  },

  downloadAll:    (recordId: number) =>
    apiClient.get("/documents/files/download-all/", { params: { record: recordId }, responseType: "blob" }),

  /** Delete a specific upload version. Staff may delete v1; owners may only delete v2+. */
  deleteUpload:   (uploadId: number) =>
    apiClient.delete(`/documents/uploads/${uploadId}/`),

  /** Delete a miscellaneous RecordFile attachment. */
  deleteFile:     (fileId: number) =>
    apiClient.delete(`/documents/files/${fileId}/`),
};
