import type { RoleName } from "@/lib/constants";

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
  date_joined:    string;
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
  date_joined: string;
}
