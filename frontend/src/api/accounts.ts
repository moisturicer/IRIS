import { apiClient } from "./client";
import type { User, UserListItem, RoleRequest } from "@/types/auth";

interface College    { id: number; name: string; code: string; }
interface Department { id: number; name: string; code: string; college: number; college_name: string; }
interface Course     { id: number; name: string; department: number; }
interface PaginatedResponse<T> { count: number; results: T[]; }

export const accountsApi = {
  // Users
  listUsers:  (params?: Record<string, unknown>) =>
    apiClient.get<PaginatedResponse<User>>("/users/", { params }),

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

  /** Lock or unlock a user account */
  setLocked:  (id: number, locked: boolean) =>
    apiClient.patch(`/users/${id}/lock/`, { is_locked: locked }),

  lockedUsers: () => apiClient.get<User[]>("/users/locked/"),
  unlockUser:  (id: number) => apiClient.post(`/users/${id}/unlock/`),

  // Role requests
  roleRequests:  () => apiClient.get<PaginatedResponse<RoleRequest>>("/users/role-requests/"),
  decideRequest: (id: number, action: "approve" | "decline") =>
    apiClient.patch<RoleRequest>(`/users/role-requests/${id}/`, { action }),

  // Reference data
  colleges:    ()                   => apiClient.get<PaginatedResponse<College>>("/colleges/"),
  departments: (collegeId?: number) => apiClient.get<PaginatedResponse<Department>>("/departments/", { params: collegeId ? { college: collegeId } : {} }),
  courses:     (deptId?: number)    => apiClient.get<PaginatedResponse<Course>>("/courses/", { params: deptId ? { department: deptId } : {} }),

  // Settings
  getSetting:    (key: string)             => apiClient.get(`/settings/${key}/`),
  updateSetting: (key: string, value: string) => apiClient.patch(`/settings/${key}/`, { value }),
};
