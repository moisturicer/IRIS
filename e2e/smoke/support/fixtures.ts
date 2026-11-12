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

export type SmokeRole = "Student" | "RDCO" | "System Admin";

/** What differs between the roles the smoke specs sign in as. */
const PROFILES: Record<SmokeRole, { email: string; office: boolean; admin: boolean }> = {
  Student: { email: "student@cit.edu", office: false, admin: false },
  RDCO: { email: "rdco@cit.edu", office: true, admin: false },
  "System Admin": { email: "admin@cit.edu", office: false, admin: true },
};

export function account(role: SmokeRole = "Student") {
  const { email, office, admin } = PROFILES[role];
  return {
    id: 1,
    email,
    first_name: "Sam",
    middle_initial: "",
    last_name: role,
    role: 1,
    role_name: role,
    is_staff: office,
    is_superuser: admin,
    is_verified: true,
    is_locked: false,
    is_active: true,
    is_office_coordinator: office,
    consent_given: true,
    date_joined: "2026-01-05T00:00:00Z",
    college_name: "",
    department_name: "",
    course_name: "",
    review_access: { my_reviews: office, offices: office ? ["rdco"] : [], is_coordinator: office },
  };
}

/** The signed-in student the auth specs use. */
export const student = () => account("Student");

/** Start the page already signed in, the way a reload does: a stored refresh token the app exchanges. */
export async function signedIn(page: Page, api: MockApi, role: SmokeRole = "Student") {
  const user = account(role);
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

export const paginated = <T,>(results: T[]) => ({ count: results.length, next: null, previous: null, results });

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
  api.on("GET", "/library/feeds/", { results: [], limit: 10 });
}

/**
 * A published Thesis/Research as Paper View's detail endpoint returns it to a
 * reader who is not one of its authors. Shape follows RecordDetail; fields the
 * screen does not read are left out.
 */
export const PAPER_DETAIL = {
  ...PAPER,
  year_completed: null,
  abstract_file: null,
  classification: "Agriculture",
  psced: null,
  record_type: "Thesis / Research",
  adviser: null,
  adviser_name: null,
  added_by: null,
  requires_ethics_review: false,
  requested_itso: false,
  requested_ierc: false,
  requested_ktto: false,
  owners: [],
  is_deleted: false,
  reviews: [],
  clearances: [],
  resubmission: { count: 0, last_resubmitted_at: null, declining_office: null, offices_preserved: [] },
  stage_label: "Published",
  files: [],
  workflow_state: "published",
  workflow_state_label: "Published",
  pipeline_status: "published",
  current_holders: [],
  capabilities: ["cite"],
  can_request_document: [],
  my_seats: [],
  is_participant: false,
  routing: { send_to_rdco: false, route_as: null, targets: [] },
  office_review: { party: null, label: null, blocked: null, assignment: null },
  revision: { party: null, label: null, blocked: null, withdrawable: null, decision_blocked: null, open: [], new_version: null },
  decision: { party: null, outcomes: [], blocked: null, closes: null, token: null, author_hints: [] },
  versions: null,
  manuscript_unsubmitted: false,
  submitter_status: null,
};

/** Ask IRIS on the AI runtime (IR-957): one owned conversation with nothing asked yet. */
export const RUNTIME_CONVERSATION_ID = "00000000-0000-4000-8000-000000000002";
export const RUNTIME_CONVERSATION = { protocol: "runs-reader-1", id: RUNTIME_CONVERSATION_ID, revision: 0, runs: [], turns: [] };
export const RUNTIME_CONVERSATION_PATH = `/ai/runtime/conversations/${RUNTIME_CONVERSATION_ID}`;
