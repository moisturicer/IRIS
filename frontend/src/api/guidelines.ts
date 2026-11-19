/**
 * Guidelines (ADR-063 decision 7, IR-974): what each record type needs, and the
 * Templates to follow. Everything here is open to anyone signed in, only reads,
 * and every Template arrives as a download.
 *
 *   GET /documents/guidelines/                                every record type, in order
 *   GET /documents/record-types/<id>/manuscript-template/     a download
 *   GET /documents/slots/<id>/template/                       a download
 *   GET /documents/adviser-templates/                         Advisers' shown Templates
 *   GET /documents/adviser-templates/<id>/file/               a download
 *
 * The server lists only requirements RDCO shows, and only Templates whose
 * Adviser is still an active Adviser, so nothing hidden reaches this page.
 */
import { apiClient } from "./client";

export interface GuidelineRequirement {
  id: number;
  name: string;
  /** A label only: it never blocks submitting (decision 3). */
  is_required: boolean;
  /** Plain text; line breaks kept, links made clickable (decision 10). */
  description: string;
  /** Empty when the requirement has no Template. */
  template_name: string;
}

export interface GuidelineRecordType {
  id: number;
  name: string;
  description: string;
  /** The fixed first requirement, always Required (decision 4). */
  manuscript: { description: string; template_name: string };
  requirements: GuidelineRequirement[];
}

export interface SharedTemplate {
  id: number;
  title: string;
  description: string;
  file_name: string;
  position: number;
  updated_at: string;
  shared_by: { id: number; name: string };
}

const blob = { responseType: "blob" as const };

export const guidelinesApi = {
  list: (options: { signal?: AbortSignal } = {}) =>
    apiClient.get<GuidelineRecordType[]>("/documents/guidelines/", options),

  advisersTemplates: (options: { signal?: AbortSignal } = {}) =>
    apiClient.get<SharedTemplate[]>("/documents/adviser-templates/", options),

  downloadManuscriptTemplate: (recordTypeId: number) =>
    apiClient.get<Blob>(`/documents/record-types/${recordTypeId}/manuscript-template/`, blob),

  downloadRequirementTemplate: (slotId: number) =>
    apiClient.get<Blob>(`/documents/slots/${slotId}/template/`, blob),

  downloadAdviserTemplate: (templateId: number) =>
    apiClient.get<Blob>(`/documents/adviser-templates/${templateId}/file/`, blob),
};
