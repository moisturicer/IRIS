/**
 * Static college / department / course options for the signup form.
 * IDs should match rows seeded in PostgreSQL; adjust after running migrations + seed.
 */

export interface CollegeOption {
  id: number;
  name: string;
}

export interface DepartmentOption {
  id: number;
  code: string;
  name: string;
  college_id: number;
}

export interface CourseOption {
  id: number;
  name: string;
  dept_id: number;
}

export const COLLEGES: CollegeOption[] = [
  { id: 1, name: "College of Computer Studies" },
  { id: 2, name: "College of Engineering and Architecture" },
  { id: 3, name: "College of Management and Accountancy" },
];

export const DEPARTMENTS: DepartmentOption[] = [
  { id: 1, code: "CCS", name: "Computer Science",           college_id: 1 },
  { id: 2, code: "IT",  name: "Information Technology",    college_id: 1 },
  { id: 3, code: "CE",  name: "Civil Engineering",         college_id: 2 },
  { id: 4, code: "CBA", name: "Business Administration", college_id: 3 },
];

export const COURSES: CourseOption[] = [
  { id: 1, name: "BS Computer Science",            dept_id: 1 },
  { id: 2, name: "BS Information Technology",      dept_id: 2 },
  { id: 3, name: "BS Civil Engineering",           dept_id: 3 },
  { id: 4, name: "BS Business Administration",     dept_id: 4 },
];

export function deptsForCollege(collegeId: string | number): DepartmentOption[] {
  const id = Number(collegeId);
  return DEPARTMENTS.filter((d) => d.college_id === id);
}
