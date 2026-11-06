// Data the smoke specs answer with. Shapes follow frontend/src/types; a field
// the interface does not read is left out rather than invented.
import type { Page } from "@playwright/test";
import type { MockApi } from "./mock-api";

function b64url(value: unknown): string {
  return Buffer.from(JSON.stringify(value)).toString("base64url");
}

/** A JWT the interface will accept on `exp` alone; nothing in the browser verifies a signature. */
export function token(): string {
  const exp = Math.floor(Date.now() / 1000) + 3600;
  return `${b64url({ alg: "HS256", typ: "JWT" })}.${b64url({ user_id: 1, role_id: 1, exp })}.signature`;
}

export function student() {
  return {
    id: 1,
    email: "student@cit.edu",
    first_name: "Sam",
    middle_initial: "",
    last_name: "Student",
    role: 1,
    role_name: "Student",
    is_staff: false,
    is_superuser: false,
    is_verified: true,
    is_locked: false,
    is_active: true,
    is_office_coordinator: false,
    consent_given: true,
    date_joined: "2026-01-05T00:00:00Z",
    college_name: "",
    department_name: "",
    course_name: "",
    review_access: { my_reviews: false },
  };
}

/** Start the page already signed in, the way a reload does: a stored refresh token the app exchanges. */
export async function signedIn(page: Page, api: MockApi) {
  const user = student();
  api.on("POST", "/auth/token/refresh/", { access: token(), refresh: "refresh-2" });
  api.on("GET", "/users/me/", user);
  await page.addInitScript(() => sessionStorage.setItem("iris_refresh_token", "refresh-1"));
  return user;
}

export const PAPER = {
  id: 101,
  title: "Low-cost soil moisture sensing for upland rice",
  abstract: "A field study of capacitive sensors on upland rice plots in Cebu.",
  year_accomplished: 2025,
  classification_name: "Agriculture",
  record_type_name: "Thesis / Research",
  pipeline_status: "published",
  is_ip: false,
  ip_type: null,
  for_commercialization: false,
  community_extension: false,
  access_count: 3,
  ai_hook: null,
  file_count: 0,
  has_manuscript: false,
  created_at: "2026-01-05T00:00:00Z",
  authors: [{ id: 1, name: "Sam Student", role: 1 }],
};

const paginated = <T,>(results: T[]) => ({ count: results.length, next: null, previous: null, results });

/** Everything the app shell and the Discover page ask for on load. */
export function mockShell(
  api: MockApi,
  papers: unknown[] = [PAPER],
) {
  api.on("GET", "/dashboard/stats/", {
    total_mine: 0, pending_mine: 0, approved_mine: 0, declined_mine: 0,
    needs_action_mine: 0, total_published: papers.length,
  });
  api.on("GET", "/records/classifications/", paginated([{ id: 1, name: "Agriculture" }]));
  api.on("GET", "/records/psced-classifications/", paginated([]));
  api.on("GET", "/records/record-types/", paginated([{ id: 1, name: "Thesis / Research" }]));
  api.on("GET", "/colleges/", paginated([]));
  api.on("GET", "/records/facets/", { years: [2025] });
  api.on("GET", "/records/interests/", { classifications: [], psced: [] });
  api.on("GET", "/records/", paginated(papers));
  api.on("GET", "/notifications/", paginated([]));
  api.on("GET", "/library/saves/", { results: [] });
}
