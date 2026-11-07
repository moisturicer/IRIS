import type { User } from "@/types/auth";

type Named = Pick<User, "first_name" | "middle_initial" | "last_name">;
type Placed = Pick<User, "college_name" | "department_name" | "course_name">;

/** "Ana L. Reyes": the middle initial only when there is one. */
export function displayName(u: Named): string {
  const mi = u.middle_initial?.trim();
  return [u.first_name, mi ? `${mi.replace(/\.$/, "")}.` : "", u.last_name].filter(Boolean).join(" ");
}

export function initialsOf(u: Pick<User, "first_name" | "last_name">): string {
  return `${u.first_name.charAt(0)}${u.last_name.charAt(0)}`.toUpperCase();
}

/**
 * College, department and course as the university recorded them. A student
 * and an adviser reach their affiliation by different routes, so any may be
 * empty.
 */
export function affiliationOf(u: Placed): string {
  return [u.college_name, u.department_name, u.course_name].filter(Boolean).join(" · ");
}
