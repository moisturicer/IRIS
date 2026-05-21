import type { RoleName } from "@/lib/constants";

export interface User {
  id:          number;
  username:    string;
  first_name:  string;
  middle_name: string;
  last_name:   string;
  email:       string;
  contact_no:  string;
  role:        number | null;
  role_name:   RoleName | null;
  is_verified: boolean;
  is_locked:   boolean;
  date_joined: string;
}

export interface LoginPayload {
  username: string;
  password: string;
}

export interface LoginResponse {
  access:  string;
  refresh: string;
  user:    User;
}

export interface RegisterPayload {
  username:         string;
  first_name:       string;
  middle_name?:     string;
  last_name:        string;
  email:            string;
  contact_no?:      string;
  password:         string;
  confirm_password: string;
  /** "Student" or "Faculty Adviser" */
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
  username:   string;
  first_name: string;
  last_name:  string;
  email:      string;
  role_name:  string;
  is_active:  boolean;
  is_locked:  boolean;
  date_joined: string;
}
