/**
 * Another person's public Profile, as the draft IR-696 contract sends it
 * (IR-700; the contract is the Jira comment on IR-696).
 *
 * What the server never sends, and so what no type here carries: an email
 * address, coordinator status, lock state, or anything unpublished.
 */

/** Student, Adviser, or the office a staff member works for. Never "Faculty". */
export type RoleLabel = "Student" | "Adviser" | "ITSO" | "IERC" | "KTTO" | "RDCO";

/** `GET /users/<id>/profile/`: the person, without the lists, which are paged. */
export interface PublicProfile {
  id:                 number;
  first_name:         string;
  middle_initial:     string;
  last_name:          string;
  role_label:         RoleLabel;
  college_name:       string;
  department_name:    string;
  course_name:        string;
  bio:                string;
  research_interests: string[];
  /** Relative to the API base, fetched with auth as a blob; `null` when none. */
  photo_url:          string | null;
}

/** A published paper the person owns or advised, with the one figure a reader may see. */
export interface ProfilePaper {
  id:                  number;
  title:               string;
  /** Byline names, not accounts. */
  authors:             string[];
  classification_name: string;
  record_type_name:    string;
  publication_year:    number | null;
  /**
   * The paper's `access_count`: it rises on every opening, so it is not a count
   * of distinct accounts (that counter is IR-369's, not built). Never summed.
   */
  views:               number;
}

/** Another account that shared a published paper with this person. */
export interface Collaborator {
  id:             number;
  first_name:     string;
  middle_initial: string;
  last_name:      string;
  photo_url:      string | null;
  /** How many published papers they shared. */
  shared_papers:  number;
}

/** A public account returned by Discover people search (IR-697). */
export interface PeopleSearchResult {
  id: number;
  first_name: string;
  middle_initial: string;
  last_name: string;
  role_label: string;
  college_name: string;
  department_name: string;
  course_name: string;
  photo_url: string | null;
  published_paper_count: number;
}

/** The paged response used by Discover's people directory. */
export interface PeopleSearchPage {
  count: number;
  next: string | null;
  results: PeopleSearchResult[];
}

/** One page of a list: `next` is `null` on the last. Totals are not sent. */
export interface ProfilePage<T> {
  next:    string | null;
  results: T[];
}
