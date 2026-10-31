import type { RoleName } from "@/lib/constants";

/**
 * One Adviser in the picker, from `GET /users/advisers/` (IR-587). Narrower
 * than `User` on purpose: every signed-in user can read this list, so the
 * server sends only what the IR-540 data notice names -- no account state.
 */
export type AdviserOption = Pick<
  User,
  "id" | "first_name" | "middle_initial" | "last_name" | "email" | "college_name" | "department_name"
>;

export interface User {
  id:             number;
  email:          string;
  first_name:     string;
  middle_initial: string;
  last_name:      string;
  role:           number | null;
  role_name:      RoleName | null;
  is_staff:       boolean;
  is_superuser:   boolean;
  is_verified:    boolean;
  is_locked:      boolean;
  is_active:      boolean;
  /** Granted by RDCO on the Users page (ADR-032 §4, IR-478). Read-only here. */
  is_office_coordinator: boolean;
  /** RA 10173 consent, recorded at registration (FR-M6-06). Read-only. */
  consent_given:  boolean;
  date_joined:    string;
  /**
   * Affiliation, read-only and derived server-side. A student's college comes
   * through StudentProfile.course -> Department -> College; an adviser carries
   * college and department directly. Empty string when the user has neither
   * profile (staff roles), never null -- so the UI can render it unguarded.
   */
  college_name:    string;
  department_name: string;
  course_name:     string;
  /**
   * What review work the user has (IR-415, spec Appendix D · B3). Sent only
   * on the user's own payload (`/users/me/` and sign-in), never on someone
   * else's, so it is optional here.
   */
  review_access?:  ReviewAccess;
  /**
   * The user's latest role request while they have no role (IR-537): what the
   * pending screen reads to tell waiting from declined. `null` once a role is
   * held, or when nothing was asked for. Own payload only, like
   * `review_access`, and read by nothing but `PendingApprovalPage`.
   */
  role_request?:   OwnRoleRequest | null;
  /**
   * Profile fields the person sets in Settings (IR-695, IR-699). Optional on
   * the type until IR-695 ships them; the contract is the comment on IR-695.
   * Empty is `""`, `[]`, `null` and `null` respectively.
   */
  bio?:                string;
  research_interests?: string[];
  orcid?:              string | null;
  /** Relative to the API base, fetched with auth as a blob. Never an open media URL. */
  photo_url?:          string | null;
}

export interface OwnRoleRequest {
  status:         "pending" | "declined";
  /** The role asked for at registration: Student or Adviser. */
  requested_role: RoleName;
}

export interface ReviewAccess {
  /** The user holds or has held a seat, or is a member of an office. */
  my_reviews:     boolean;
  /** The office parties the user is a member of. */
  offices:        ("itso" | "ierc" | "ktto" | "rdco")[];
  /** A coordinator of their office: may assign its reviewers. */
  is_coordinator: boolean;
}

export interface LoginPayload {
  email:    string;
  password: string;
}

export interface LoginResponse {
  access:  string;
  refresh: string;
  user:    User;
}

export interface RegisterPayload {
  email:            string;
  first_name:       string;
  middle_initial?:  string;
  last_name:        string;
  password:         string;
  confirm_password: string;
  /** Required by the register serializer: the registrant agreed to the data notice (IR-540). */
  consent_given:    true;
  /** "Student" or "Adviser" */
  role_name?:       string;
  /** Student: course FK id */
  course_id?:       number;
  /** Adviser: college FK id */
  college_id?:      number;
  /** Adviser: department FK id */
  department_id?:   number;
}

export interface ChangePasswordPayload {
  old_password: string;
  new_password: string;
}

export interface RoleRequest {
  id:             number;
  user:           number;
  user_name:      string;
  requested_role: number;
  role_name:      string;
  status:         "pending" | "approved" | "declined";
  created_at:     string;
}

/** Lightweight user row used in the admin UserListPage table */
export interface UserListItem {
  id:         number;
  email:      string;
  first_name: string;
  last_name:  string;
  role_name:  string;
  is_active:  boolean;
  is_locked:  boolean;
  /** May assign, reassign and withdraw reviewers in their office (ADR-032 §4). */
  is_office_coordinator: boolean;
  date_joined: string;
}
