/**
 * Another person's public Profile (IR-700). The only module that speaks the
 * draft IR-696 contract, so if a path or field changes there, it changes here
 * and nowhere else. Every call is signed-in only; a person the server hides
 * (suspended, inactive, unapproved, a System Admin) answers 404, like a person
 * who does not exist.
 */
import { apiClient } from "./client";
import type { Collaborator, PeopleSearchPage, ProfilePage, ProfilePaper, PublicProfile } from "@/types/people";

/** How many a page holds: the numbers settled for the Profile's lists. */
export const PROFILE_PAGE_SIZE = { papers: 10, collaborators: 12 } as const;

export interface PeopleSearchParams {
  q?: string;
  page?: number;
  page_size?: number;
  college?: number;
  department?: number;
  role?: string;
}

export const peopleApi = {
  /** `GET /users/search/` (IR-697): public, paged people matching Discover's query. */
  search: (params: PeopleSearchParams) =>
    apiClient.get<PeopleSearchPage>("/users/search/", { params }),

  /** `GET /users/<id>/profile/` */
  get: (id: number) => apiClient.get<PublicProfile>(`/users/${id}/profile/`),

  /** Published papers they own, newest first. */
  research: (id: number, page: number) =>
    apiClient.get<ProfilePage<ProfilePaper>>(`/users/${id}/profile/research/`, {
      params: { page, page_size: PROFILE_PAGE_SIZE.papers },
    }),

  /** Published papers they advised, newest first. */
  advised: (id: number, page: number) =>
    apiClient.get<ProfilePage<ProfilePaper>>(`/users/${id}/profile/advised/`, {
      params: { page, page_size: PROFILE_PAGE_SIZE.papers },
    }),

  /** Accounts that shared a published paper with them, most papers shared first. */
  collaborators: (id: number, page: number) =>
    apiClient.get<ProfilePage<Collaborator>>(`/users/${id}/profile/collaborators/`, {
      params: { page, page_size: PROFILE_PAGE_SIZE.collaborators },
    }),
};
