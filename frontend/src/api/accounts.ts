import { apiClient } from "./client";
import type { AdviserOption, User, UserListItem, RoleRequest } from "@/types/auth";
import type { NoticeAnswer } from "@/types/notice";

interface College    { id: number; name: string; code: string; }
interface Department { id: number; name: string; code: string; college: number; college_name: string; }
interface Course     { id: number; name: string; department: number; }
interface PaginatedResponse<T> { count: number; results: T[]; }

export interface ActiveSession {
  jti:        string;
  user_id:    number;
  user_email: string | null;
  user_name:  string | null;
  created_at: string;
  expires_at: string;
}

/** What stops an account deletion being confirmed, in plain words (ADR-051 §9, IR-785). */
export interface DeletionBlocker {
  kind:    "sole_owner_in_review" | "open_review";
  record:  number;
  title:   string;
  message: string;
}

/** A pending account deletion request, as the System Admin sees it (IR-788). */
export interface AccountDeletionRequest {
  id:         number;
  status:     "pending" | "approved" | "declined" | "cancelled";
  created_at: string;
  decided_at: string | null;
  reason:     string;
  user:       { id: number; name: string; email: string; role: string };
  blockers:   DeletionBlocker[];
  capabilities: { can_confirm: boolean; can_reject: boolean };
}

/** The person's own latest deletion request (ADR-051 §8, IR-787). */
export interface MyDeletionRequest {
  id:         number;
  status:     "pending" | "approved" | "declined" | "cancelled";
  created_at: string;
  decided_at: string | null;
  /** A rejection's reason, theirs to read. */
  reason:     string;
  can_cancel: boolean;
  /** What stops a pending request being confirmed; empty once it isn't pending. */
  blockers:   DeletionBlocker[];
}

/** One system setting (IR-667). The System Admin alone reads or changes it. */
export interface SystemSetting {
  key:        string;
  value:      string;
  updated_by: number | null;
  updated_at: string;
}

/** What a retention period would erase if saved now (ADR-051 §19, IR-795). */
export interface RetentionPreview {
  key:   string;
  /** Null when the period is blank, which erases nothing. */
  days:  number | null;
  count: number;
}

export const accountsApi = {
  // Users
  listUsers:  (params?: Record<string, unknown>) =>
    apiClient.get<PaginatedResponse<User>>("/users/", { params }),

  /** List all active Adviser-role users — usable by any authenticated user. */
  listAdvisers: () =>
    apiClient.get<PaginatedResponse<AdviserOption>>("/users/advisers/"),

  /** Alias used by UserListPage -- same endpoint, narrower return type */
  userList:   (params?: Record<string, unknown>) =>
    apiClient.get<PaginatedResponse<UserListItem>>("/users/", { params }),

  getUser:    (id: number) =>
    apiClient.get<User>(`/users/${id}/`),

  /** Set role by role name string (e.g. "Adviser") */
  setRole:    (id: number, roleName: string) =>
    apiClient.patch(`/users/${id}/role/`, { role_name: roleName }),

  /** Legacy alias -- role by numeric ID */
  changeRole: (id: number, role: number) =>
    apiClient.patch(`/users/${id}/role/`, { role }),

  /** Grant or remove office-coordinator status (ADR-032 §4). RDCO only; refused for anyone without an office role. */
  setCoordinator: (id: number, isCoordinator: boolean) =>
    apiClient.patch<User>(`/users/${id}/coordinator/`, { is_office_coordinator: isCoordinator }),

  /** Lock or unlock a user account */
  setLocked:  (id: number, locked: boolean) =>
    apiClient.patch(`/users/${id}/lock/`, { is_locked: locked }),

  lockedUsers: () => apiClient.get<User[]>("/users/locked/"),
  unlockUser:  (id: number) => apiClient.post(`/users/${id}/unlock/`),

  // Account deletion (ADR-051 §8-§9). The System Admin alone.
  deletionRequests: (opts?: { signal?: AbortSignal }) =>
    apiClient.get<PaginatedResponse<AccountDeletionRequest>>("/users/deletion-requests/", { signal: opts?.signal }),
  confirmDeletion: (id: number) =>
    apiClient.post<AccountDeletionRequest>(`/users/deletion-requests/${id}/confirm/`, {}),
  rejectDeletion: (id: number, reason: string) =>
    apiClient.post<AccountDeletionRequest>(`/users/deletion-requests/${id}/reject/`, { reason }),
  // The caller's own request (ADR-051 §8, IR-785). Open even while the data
  // notice is unanswered (ADR-054 decision 3, IR-790).
  requestMyDeletion: () =>
    apiClient.post<{ request: MyDeletionRequest }>("/users/me/deletion-request/", {}),
  /** The caller's latest request, or `null` if they never made one (IR-787). */
  myDeletionRequest: (opts?: { signal?: AbortSignal }) =>
    apiClient.get<{ request: MyDeletionRequest | null }>("/users/me/deletion-request/", { signal: opts?.signal }),
  cancelMyDeletion: () =>
    apiClient.delete<{ request: MyDeletionRequest }>("/users/me/deletion-request/"),

  /**
   * Change the caller's own AI answer (ADR-054 decisions 11-13, IR-791). A No
   * becoming a Yes needs `papers`; the server refuses it otherwise.
   */
  changeAiAnswer: (data: { ai_consent: boolean; papers?: "all" | "from_now" }) =>
    apiClient.post<{ answer: NoticeAnswer; changed: boolean; papers_updated: number }>("/users/me/ai-answer/", data),

  /** One JSON file of the caller's own data (ADR-051 decision 13, IR-786). */
  downloadMyData: () => apiClient.get<Blob>("/users/me/data/", { responseType: "blob" }),

  // Role requests
  roleRequests:  () => apiClient.get<PaginatedResponse<RoleRequest>>("/users/role-requests/"),
  decideRequest: (id: number, action: "approve" | "decline") =>
    apiClient.patch<RoleRequest>(`/users/role-requests/${id}/`, { action }),

  // Reference data
  colleges:    ()                   => apiClient.get<PaginatedResponse<College>>("/colleges/"),
  departments: (collegeId?: number) => apiClient.get<PaginatedResponse<Department>>("/departments/", { params: collegeId ? { college: collegeId } : {} }),
  courses:     (deptId?: number)    => apiClient.get<PaginatedResponse<Course>>("/courses/", { params: deptId ? { department: deptId } : {} }),

  // Settings
  getSetting:    (key: string, opts?: { signal?: AbortSignal }) =>
    apiClient.get<SystemSetting>(`/settings/${key}/`, { signal: opts?.signal }),
  updateSetting: (key: string, value: string) => apiClient.patch<SystemSetting>(`/settings/${key}/`, { value }),
  /** How many items the daily cleanup would erase now under `days` (IR-795). Reads only. */
  retentionPreview: (key: string, days: string) =>
    apiClient.get<RetentionPreview>(`/settings/${key}/erasure-preview/`, { params: { days } }),

  // Active sessions (admin)
  sessions:      () => apiClient.get<ActiveSession[]>("/users/sessions/"),
  revokeSession: (jti: string) => apiClient.delete(`/users/sessions/${jti}/`),
};
