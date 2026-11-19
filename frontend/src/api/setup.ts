/**
 * RDCO's Setup: each record type's Requirements, Templates and description
 * (ADR-063, IR-971). Every Setup route is RDCO-only on the server; Template
 * downloads are open to anyone signed in and always arrive as a file.
 *
 *   GET    /documents/setup/record-types/
 *   PATCH  /documents/setup/record-types/<id>/                     {description?, manuscript_description?}
 *   PUT    /documents/setup/record-types/<id>/manuscript-template/ multipart `file`
 *   DELETE /documents/setup/record-types/<id>/manuscript-template/
 *   POST   /documents/setup/record-types/<id>/requirements/        {name, is_required, description}
 *   PUT    /documents/setup/record-types/<id>/requirements/order/  {order: [ids]}
 *   PATCH  /documents/setup/requirements/<id>/                     {name?, is_required?, description?}
 *   DELETE /documents/setup/requirements/<id>/                     -> {outcome: "hidden" | "deleted"}
 *   PUT    /documents/setup/requirements/<id>/template/            multipart `file`
 *   DELETE /documents/setup/requirements/<id>/template/
 *   GET    /documents/slots/<id>/template/                         a download
 *   GET    /documents/record-types/<id>/manuscript-template/       a download
 */
import { apiClient } from "./client";

export interface SetupRequirement {
  id: number;
  name: string;
  /** A label only: it never blocks submitting (ADR-063 decision 3). */
  is_required: boolean;
  description: string;
  position: number;
  /** Empty when there is no Template. */
  template_name: string;
  /** A paper has a file in it, or a request asked for it: removing hides it. */
  in_use: boolean;
}

export interface SetupRecordType {
  id: number;
  name: string;
  description: string;
  /** The fixed first row (decision 4): always Required, never removable. */
  manuscript: { description: string; template_name: string };
  requirements: SetupRequirement[];
}

export type RequirementFields = Pick<SetupRequirement, "name" | "is_required" | "description">;

/** The file types a Template may be (decision 8), for the file picker. */
export const TEMPLATE_ACCEPT = ".pdf,.doc,.docx,.odt,.xls,.xlsx,.ods,.png,.jpg,.jpeg";

function fileForm(file: File): FormData {
  const fd = new FormData();
  fd.append("file", file);
  return fd;
}

const multipart = { headers: { "Content-Type": "multipart/form-data" } };

export const setupApi = {
  recordTypes: (options: { signal?: AbortSignal } = {}) =>
    apiClient.get<SetupRecordType[]>("/documents/setup/record-types/", options),

  describe: (recordTypeId: number, changes: { description?: string; manuscript_description?: string }) =>
    apiClient.patch<SetupRecordType>(`/documents/setup/record-types/${recordTypeId}/`, changes),

  setManuscriptTemplate: (recordTypeId: number, file: File) =>
    apiClient.put<SetupRecordType>(
      `/documents/setup/record-types/${recordTypeId}/manuscript-template/`, fileForm(file), multipart,
    ),

  removeManuscriptTemplate: (recordTypeId: number) =>
    apiClient.delete(`/documents/setup/record-types/${recordTypeId}/manuscript-template/`),

  addRequirement: (recordTypeId: number, fields: RequirementFields) =>
    apiClient.post<SetupRequirement>(`/documents/setup/record-types/${recordTypeId}/requirements/`, fields),

  reorder: (recordTypeId: number, order: number[]) =>
    apiClient.put<SetupRecordType>(`/documents/setup/record-types/${recordTypeId}/requirements/order/`, { order }),

  editRequirement: (id: number, changes: Partial<RequirementFields>) =>
    apiClient.patch<SetupRequirement>(`/documents/setup/requirements/${id}/`, changes),

  removeRequirement: (id: number) =>
    apiClient.delete<{ outcome: "hidden" | "deleted" }>(`/documents/setup/requirements/${id}/`),

  setTemplate: (id: number, file: File) =>
    apiClient.put<SetupRequirement>(`/documents/setup/requirements/${id}/template/`, fileForm(file), multipart),

  removeTemplate: (id: number) => apiClient.delete(`/documents/setup/requirements/${id}/template/`),

  downloadTemplate: (slotId: number) =>
    apiClient.get<Blob>(`/documents/slots/${slotId}/template/`, { responseType: "blob" }),

  downloadManuscriptTemplate: (recordTypeId: number) =>
    apiClient.get<Blob>(`/documents/record-types/${recordTypeId}/manuscript-template/`, { responseType: "blob" }),
};
