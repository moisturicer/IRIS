import { apiClient } from "./client";
import type { RecordUpload, RecordFile, UploadSlot, SlotWithUploads } from "@/types/documents";

export const documentsApi = {
  // Fetch all UploadSlots for a record type
  slots:          (recordTypeId?: number) =>
    apiClient.get<UploadSlot[]>("/documents/slots/", {
      params: recordTypeId ? { record_type: recordTypeId } : {},
    }),

  // Fetch slots with their upload history for a specific record (used in DocumentsPage)
  slotsForRecord: (recordId: number) =>
    apiClient.get<SlotWithUploads[]>(`/documents/records/${recordId}/slots/`),

  uploads:        (recordId: number) =>
    apiClient.get<RecordUpload[]>("/documents/uploads/", { params: { record: recordId } }),

  // Upload a PDF to a slot — triggers Celery extraction task
  upload:         (recordId: number, slotId: number, file: File) => {
    const fd = new FormData();
    fd.append("record", String(recordId));
    fd.append("slot",   String(slotId));
    fd.append("file",   file);
    return apiClient.post<{ upload: RecordUpload; extraction: { id: number; status: string } }>(
      "/documents/submit/", fd,
      { headers: { "Content-Type": "multipart/form-data" } },
    );
  },

  // Legacy alias kept for any existing callers
  uploadFile:     (recordId: number, slotId: number, file: File) =>
    documentsApi.upload(recordId, slotId, file),

  downloadUpload: (uploadId: number) =>
    apiClient.get(`/documents/uploads/${uploadId}/download/`, { responseType: "blob" }),

  files:          (recordId: number) =>
    apiClient.get<RecordFile[]>("/documents/files/", { params: { record: recordId } }),

  uploadRecordFile: (recordId: number, file: File) => {
    const fd = new FormData();
    fd.append("record", String(recordId));
    fd.append("file",   file);
    return apiClient.post<RecordFile>("/documents/files/upload/", fd, {
      headers: { "Content-Type": "multipart/form-data" },
    });
  },

  downloadAll:    (recordId: number) =>
    apiClient.get("/documents/files/download-all/", { params: { record: recordId }, responseType: "blob" }),
};
