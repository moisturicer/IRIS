import { apiClient } from "./client";
import type { StorageListing, StorageFolder, StorageFile } from "@/types/storage";

export const storageApi = {
  /** List folders and files inside a parent folder (or root if no parentId). */
  list: (parentId?: number) =>
    apiClient.get<StorageListing>("/storage/", {
      params: parentId ? { parent: parentId } : {},
    }),

  createFolder: (payload: { name: string; parent: number | null }) =>
    apiClient.post<StorageFolder>("/storage/folders/", payload),

  renameFolder: (id: number, name: string) =>
    apiClient.patch<StorageFolder>(`/storage/folders/${id}/`, { name }),

  deleteFolder: (id: number) =>
    apiClient.delete(`/storage/folders/${id}/`),

  uploadFile: (folderId: number | null, file: File) => {
    const fd = new FormData();
    if (folderId) fd.append("folder", String(folderId));
    fd.append("file", file);
    fd.append("name", file.name);
    return apiClient.post<StorageFile>("/storage/files/", fd, {
      headers: { "Content-Type": "multipart/form-data" },
    });
  },

  deleteFile: (id: number) =>
    apiClient.delete(`/storage/files/${id}/`),

  downloadFile: (id: number) =>
    apiClient.get(`/storage/files/${id}/download/`, { responseType: "blob" }),
};
