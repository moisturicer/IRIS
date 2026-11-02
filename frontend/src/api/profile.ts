/**
 * The profile fields a person edits in Settings (IR-699).
 *
 * This is the only module that speaks IR-695's API contract (the comment on
 * IR-695 in Jira), so if a field or path changes there, it changes here and
 * nowhere else.
 */
import { apiClient } from "./client";
import type { User } from "@/types/auth";
import type { CropRect } from "@/lib/photoCrop";

export interface ProfileFields {
  bio:                string;
  research_interests: string[];
  orcid:              string | null;
}

export const BIO_MAX_LENGTH = 500;
export const MAX_INTERESTS = 10;
export const INTEREST_MAX_LENGTH = 40;

export const profileApi = {
  /** `PATCH /users/me/` with any subset; answers with the whole own payload. */
  updateFields: (fields: Partial<ProfileFields>) =>
    apiClient.patch<User>("/users/me/", fields),

  /** `PUT /users/me/photo/`: the original file and the square the person framed. */
  uploadPhoto: (photo: File, crop: CropRect) => {
    const body = new FormData();
    body.append("photo", photo);
    body.append("crop_x", String(crop.x));
    body.append("crop_y", String(crop.y));
    body.append("crop_size", String(crop.size));
    return apiClient.put<{ photo_url: string }>("/users/me/photo/", body);
  },

  removePhoto: () => apiClient.delete("/users/me/photo/"),

  /**
   * The photo's bytes. The API authenticates with a Bearer header, which an
   * `<img src>` cannot send, so the photo is fetched like a document is.
   */
  photo: (photoUrl: string) => apiClient.get<Blob>(photoUrl, { responseType: "blob" }),

  /** Existing interests containing `q`, most used first, at most ten. */
  suggestInterests: (q: string) =>
    apiClient.get<string[]>("/users/interests/", { params: { q } }),
};

/** Where a person's Profile lives (IR-700 builds the page). */
export function profilePath(userId: number): string {
  return `/people/${userId}`;
}
