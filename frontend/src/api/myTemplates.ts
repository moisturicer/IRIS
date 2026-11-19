/**
 * My Templates: an Adviser's own proposal Templates (ADR-063 decision 8, IR-975).
 * The `my-templates/` routes are the Adviser's alone on the server; the shown
 * list and its downloads are open to anyone signed in, and list only Templates
 * whose Adviser is still an active Adviser.
 *
 *   GET    /documents/my-templates/                  the Adviser's own, in order
 *   POST   /documents/my-templates/                  multipart `title`, `description`, `file`
 *   PUT    /documents/my-templates/order/            {order: [ids]}
 *   PATCH  /documents/my-templates/<id>/             {title?, description?} or multipart `file`
 *   DELETE /documents/my-templates/<id>/
 *   GET    /documents/adviser-templates/[?shared_by=<user id>]   the shown ones
 *   GET    /documents/adviser-templates/<id>/file/   a download
 */
import { apiClient } from "./client";

export interface MyTemplate {
  id: number;
  title: string;
  /** Plain text; line breaks kept, links made clickable (decision 10). */
  description: string;
  file_name: string;
  position: number;
  updated_at: string;
}

export interface ShownTemplate extends MyTemplate {
  shared_by: { id: number; name: string };
}

export type TemplateFields = Pick<MyTemplate, "title" | "description">;

const multipart = { headers: { "Content-Type": "multipart/form-data" } };

export const myTemplatesApi = {
  list: (options: { signal?: AbortSignal } = {}) =>
    apiClient.get<MyTemplate[]>("/documents/my-templates/", options),

  add: (fields: TemplateFields, file: File) => {
    const fd = new FormData();
    fd.append("title", fields.title);
    fd.append("description", fields.description);
    fd.append("file", file);
    return apiClient.post<MyTemplate>("/documents/my-templates/", fd, multipart);
  },

  edit: (id: number, fields: TemplateFields) =>
    apiClient.patch<MyTemplate>(`/documents/my-templates/${id}/`, fields),

  replaceFile: (id: number, file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    return apiClient.patch<MyTemplate>(`/documents/my-templates/${id}/`, fd, multipart);
  },

  reorder: (order: number[]) =>
    apiClient.put<{ order: number[] }>("/documents/my-templates/order/", { order }),

  remove: (id: number) => apiClient.delete(`/documents/my-templates/${id}/`),

  shown: (sharedBy?: number, options: { signal?: AbortSignal } = {}) =>
    apiClient.get<ShownTemplate[]>("/documents/adviser-templates/", {
      ...options, params: sharedBy === undefined ? undefined : { shared_by: sharedBy },
    }),

  download: (id: number) =>
    apiClient.get<Blob>(`/documents/adviser-templates/${id}/file/`, { responseType: "blob" }),
};
