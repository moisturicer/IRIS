// The screens the viewport matrix visits (IR-910), one entry per routed screen
// in frontend/src/router/index.tsx. `viewport-matrix.spec.ts` checks that this
// list and the router agree, so a new route cannot be added without a row here.
//
// What each entry fixes:
//   - the role it is opened as and the API answers it needs (the smoke tier
//     mocks the network; an unlisted request fails the test),
//   - the heading that proves the screen drew and is not an error screen,
//   - its PRIMARY ACTION: the one control a visitor came to this screen to use.
//     "Reachable" is judged on that control at every width (see checkReachable),
//   - for table-heavy screens, the small-screen behaviour (see TABLE_BEHAVIOUR).
import type { Locator, Page } from "@playwright/test";
import type { MockApi } from "./mock-api";
import { PAPER, PAPER_DETAIL, paginated, type SmokeRole } from "./fixtures";

export interface Screen {
  /** Stable name in the results table. */
  id: string;
  /** The address opened, with any parameters filled in. */
  path: string;
  /** The router's full pattern for it. `router/viewportMatrix.test.ts` (frontend) fails when this list and the route table disagree. */
  route: string;
  /** Signed-out screens have no role. */
  role: SmokeRole | null;
  mocks?: (api: MockApi) => void;
  /** The heading that proves the screen rendered. */
  heading: string | RegExp;
  /** The control this screen exists for. */
  primary: (page: Page) => Locator;
  primaryLabel: string;
  /** A table (or table-like list) that gets wider than a phone. Documented in TABLE_BEHAVIOUR. */
  table?: (page: Page) => Locator;
}

/** The table-heavy screens' small-screen behaviour. The matrix checks it still holds. */
export const TABLE_BEHAVIOUR =
  "A table wider than the window scrolls sideways inside its own container; " +
  "the page itself never does (WCAG 1.4.10 exempts two-dimensional data tables). " +
  "See docs/engineering/RESPONSIVE_LAYOUT.md.";

const when = (iso: string) => `2026-${iso}T08:00:00+08:00`;

/** What the app shell asks for on every signed-in screen. */
function shell(api: MockApi, role: SmokeRole) {
  api.on("GET", "/dashboard/stats/", {
    total_mine: 0, pending_mine: 0, approved_mine: 0, declined_mine: 0, needs_action_mine: 0, total_published: 1,
  });
  api.on("GET", "/notifications/", paginated([]));
  if (role === "RDCO") api.on("GET", "/users/role-requests/", paginated([]));
}

const wrap = (role: SmokeRole, extra?: (api: MockApi) => void) => (api: MockApi) => {
  shell(api, role);
  extra?.(api);
};

const USERS = Array.from({ length: 6 }, (_, i) => ({
  id: 10 + i,
  email: `a.long.address.for.row.${i}@students.cit.edu`,
  first_name: ["Maria Cristina", "Juan", "Ana", "Pedro", "Luz", "Carlos"][i],
  last_name: ["Dela Cruz-Santos", "Reyes", "Villanueva", "Magalang", "Ocampo", "Bautista"][i],
  role_name: ["Student", "Adviser", "ITSO", "IERC", "KTTO", "RDCO"][i],
  is_active: true,
  is_locked: i === 3,
  is_office_coordinator: i === 2,
  date_joined: when("01-05"),
}));

/** One open call, so the board draws its filters as it does with data. */
const OPPORTUNITY = {
  id: 1, opportunity_type: "funding_window", type_display: "Funding Window",
  title: "Internal research grant, second cycle", posting_office: "RDCO", audience: "Faculty and graduate students",
  description: "Seed funding for projects that start in the next term.", funding_ceiling: "50000.00",
  external_url: "https://example.edu/grants", due_date: "2026-12-15", is_featured: false, tags: ["funding"],
  source: "internal", posted_by: 2, posted_by_name: "RDCO", created_at: when("11-01"), updated_at: when("11-01"),
  days_left: 39, is_closed: false, can_edit: false,
};

const LONG_TITLE = "A comparative study of low-cost capacitive soil moisture sensing for upland rice in Cebu";

const DOWNLOAD_REQUEST = {
  id: 1, record: 101, record_title: LONG_TITLE, requested_by: 11,
  requested_by_name: "Maria Cristina Dela Cruz-Santos", requested_by_email: "maria.cristina@students.cit.edu",
  note: "For my literature review chapter.", status: "pending", rdco_note: "",
  reviewed_by: null, reviewed_at: null, grant_expires_at: null, grant_live: false,
  revoked_at: null, cancelled_at: null, created_at: when("11-04"),
};

const DELETE_REQUEST = {
  id: 1, record: 101, record_title: LONG_TITLE, requested_by: 11,
  requested_by_name: "Maria Cristina Dela Cruz-Santos", requested_by_email: "maria.cristina@students.cit.edu",
  reason: "Submitted by mistake.", status: "pending", reviewed_by: null, reviewed_at: null, created_at: when("11-04"),
};

const AUDIT_EVENT = {
  id: 1, event_type: "LOGIN", user: 11, user_name: "Maria Cristina Dela Cruz-Santos",
  record: 101, record_title: LONG_TITLE, metadata: {}, created_at: when("11-05"),
};

const askIrisMocks = wrap("Student", (api) => {
  api.on("GET", "/ai/reader/", { path: "django" });
  api.on("GET", "/ai/conversations/", []);
  api.on("GET", "/ai/status/", { embedding_space: null, generative: false, indexed_records: 0 });
  api.on("GET", "/records/classifications/", paginated([]));
  // Opening a blank chat makes its conversation, then reads it back.
  const conversation = {
    id: 1, title: "", record: null, record_title: null, turn_count: 0,
    created_at: when("11-05"), updated_at: when("11-05"), turns: [],
  };
  api.on("POST", "/ai/conversations/", conversation, 201);
  api.on("GET", "/ai/conversations/1/", conversation);
});

export const SCREENS: Screen[] = [
  // --- signed out -----------------------------------------------------------
  {
    id: "login", path: "/login", route: "/login", role: null,
    heading: "Welcome back",
    primary: (p) => p.getByRole("button", { name: "Sign In" }), primaryLabel: "Sign In",
  },
  {
    id: "signup", path: "/signup", route: "/signup", role: null,
    mocks: (api) => {
      api.on("GET", "/colleges/", paginated([]));
      api.on("GET", "/departments/", paginated([]));
      api.on("GET", "/courses/", paginated([]));
    },
    heading: "Create an Account",
    primary: (p) => p.getByRole("button", { name: "Continue to affiliation" }), primaryLabel: "Continue to affiliation",
  },
  // IR-928: the secret is in the fragment and the page POSTs it in a body. The
  // link is one the server refuses, so the screen is drawn in its failed state.
  {
    id: "activate", path: "/activate#uid=abc&token=def", route: "/activate", role: null,
    mocks: (api) => api.on("POST", "/auth/activate/", { detail: "Invalid link" }, 400),
    heading: "Verification Failed",
    primary: (p) => p.getByRole("link", { name: "Register again" }), primaryLabel: "Register again",
  },
  // The deprecated path shape of links emailed before IR-928 is still routed
  // (until those tokens expire), so it keeps a row; it now POSTs too.
  {
    id: "activate-path", path: "/activate/abc/def", route: "/activate/:uidb64/:token", role: null,
    mocks: (api) => api.on("POST", "/auth/activate/", { detail: "Invalid link" }, 400),
    heading: "Verification Failed",
    primary: (p) => p.getByRole("link", { name: "Register again" }), primaryLabel: "Register again",
  },
  {
    id: "password-forgot", path: "/password/forgot", route: "/password/forgot", role: null,
    heading: "Reset your password",
    primary: (p) => p.getByRole("button", { name: "Send reset email" }), primaryLabel: "Send reset email",
  },
  {
    id: "password-reset", path: "/password/reset", route: "/password/reset", role: null,
    heading: "This link can't be used",
    primary: (p) => p.getByRole("link", { name: "Request a new email" }), primaryLabel: "Request a new email",
  },

  // --- every signed-in role -------------------------------------------------
  {
    id: "discover", path: "/", route: "/", role: "Student",
    mocks: (api) => {
      shell(api, "Student");
      api.on("GET", "/records/classifications/", paginated([{ id: 1, name: "Agriculture" }]));
      api.on("GET", "/records/psced-classifications/", paginated([]));
      api.on("GET", "/records/record-types/", paginated([{ id: 1, name: "Thesis / Research" }]));
      api.on("GET", "/colleges/", paginated([]));
      api.on("GET", "/records/facets/", { years: [2025] });
      api.on("GET", "/records/interests/", { classifications: [], psced: [] });
      api.on("GET", "/records/", paginated([PAPER]));
      api.on("GET", "/library/saves/", { results: [] });
    },
    heading: "Discover",
    primary: (p) => p.getByRole("button", { name: "Publish" }), primaryLabel: "Publish",
  },
  {
    id: "paper-view", path: `/records/${PAPER.id}`, route: "/records/:id", role: "Student",
    mocks: wrap("Student", (api) => {
      api.on("GET", `/records/${PAPER.id}/`, PAPER_DETAIL);
      api.on("POST", `/records/${PAPER.id}/increment_access/`, {});
      api.on("GET", "/library/saves/", { results: [] });
      api.on("GET", `/ai/records/${PAPER.id}/overview/`, { state: "not_indexed", overview: null });
      api.on("GET", `/records/${PAPER.id}/similar/`, { results: [] });
    }),
    heading: PAPER.title,
    primary: (p) => p.getByRole("button", { name: /Cite/ }).first(), primaryLabel: "Cite",
  },
  {
    id: "my-library", path: "/records/mine", route: "/records/mine", role: "Student",
    mocks: wrap("Student", (api) => {
      api.on("GET", "/library/saves/", { results: [] });
      api.on("GET", "/records/mine/", []);
    }),
    heading: "My Library",
    primary: (p) => p.getByRole("link", { name: "Publish" }), primaryLabel: "Publish",
  },
  {
    id: "opportunities", path: "/opportunities", route: "/opportunities", role: "Student",
    mocks: wrap("Student", (api) => api.on("GET", "/opportunities/", { count: 1, next: null, previous: null, results: [OPPORTUNITY], can_post: false })),
    heading: "Calls & Conferences",
    primary: (p) => p.getByRole("button", { name: /^All\s*\d*$/ }).first(), primaryLabel: "All (filter)",
  },
  {
    id: "notifications", path: "/notifications", route: "/notifications", role: "Student",
    mocks: wrap("Student"),
    heading: "Notifications",
    primary: (p) => p.getByRole("link", { name: "Home" }).first(), primaryLabel: "Home (breadcrumb)",
  },
  {
    id: "ask-iris", path: "/ai", route: "/ai", role: "Student",
    mocks: askIrisMocks,
    heading: /What do you want to ask/,
    primary: (p) => p.getByRole("button", { name: "Send message" }), primaryLabel: "Send message",
  },
  {
    // `/ai` opens a conversation and replaces itself with this address; this is
    // the address a bookmark or "recent chats" link lands on directly.
    id: "ask-iris-conversation", path: "/ai/conversations/1", route: "/ai/conversations/:conversationId", role: "Student",
    mocks: askIrisMocks,
    heading: /What do you want to ask/,
    primary: (p) => p.getByRole("button", { name: "Send message" }), primaryLabel: "Send message",
  },
  {
    id: "help", path: "/help", route: "/help", role: "Student",
    mocks: wrap("Student"),
    heading: "Help",
    primary: (p) => p.getByRole("link", { name: "Finding research" }).first(), primaryLabel: "Finding research (contents)",
  },
  {
    id: "profile", path: "/profile", route: "/profile", role: "Student",
    mocks: wrap("Student"),
    heading: /Sam Student/,
    primary: (p) => p.getByRole("link", { name: "Edit profile" }).first(), primaryLabel: "Edit profile",
  },
  {
    id: "profile-edit", path: "/profile/edit", route: "/profile/edit", role: "Student",
    mocks: wrap("Student"),
    heading: "Edit profile",
    primary: (p) => p.getByRole("button", { name: "Save" }), primaryLabel: "Save",
  },
  {
    id: "settings", path: "/settings", route: "/settings", role: "Student",
    mocks: wrap("Student"),
    heading: "Settings",
    primary: (p) => p.getByRole("button", { name: "Change password" }), primaryLabel: "Change password",
  },
  {
    id: "not-found", path: "/there-is-no-such-page", route: "*", role: "Student",
    mocks: wrap("Student"),
    heading: "Page not found",
    primary: (p) => p.getByRole("link", { name: "Go to Discover" }), primaryLabel: "Go to Discover",
  },

  // --- RDCO ----------------------------------------------------------------
  {
    id: "my-reviews", path: "/review", route: "/review", role: "RDCO",
    mocks: wrap("RDCO", (api) =>
      api.on("GET", "/reviews/mine/", { rows: [], counts: { to_review: 0, in_review: 0, done: 0 }, next: null })),
    heading: "My Reviews",
    primary: (p) => p.getByRole("tab", { name: /^To review/ }), primaryLabel: "To review (tab)",
  },
  {
    id: "office-console", path: "/review/office", route: "/review/office", role: "RDCO",
    mocks: wrap("RDCO", (api) =>
      api.on("GET", "/reviews/office/", { office: "rdco", office_label: "RDCO", rows: [], load: [] })),
    heading: "Office console",
    primary: (p) => p.getByRole("link", { name: "Home" }).first(), primaryLabel: "Home (breadcrumb)",
  },
  {
    id: "workflow-analytics", path: "/review/analytics", route: "/review/analytics", role: "RDCO",
    mocks: wrap("RDCO", (api) =>
      api.on("GET", "/reviews/analytics/", {
        parties: [{ party: "rdco", label: "RDCO" }], data_since: null, generated_at: when("11-05"),
        range: { from: null, to: null }, thresholds: { median: 5, p90: 5 },
        open_now: [], time_in_stage: [], unmeasured: [], throughput: [], revision_cycles: [], preserved_by_office: [],
      })),
    heading: "Workflow Analytics",
    primary: (p) => p.getByRole("link", { name: "Home" }).first(), primaryLabel: "Home (breadcrumb)",
  },
  {
    id: "import-records", path: "/records/import", route: "/records/import", role: "RDCO",
    mocks: wrap("RDCO"),
    heading: "Import Records",
    primary: (p) => p.getByRole("button", { name: "Generate" }), primaryLabel: "Generate",
  },
  {
    id: "rdco-users", path: "/rdco/users", route: "/rdco/users", role: "RDCO",
    mocks: wrap("RDCO", (api) => api.on("GET", "/users/", paginated(USERS))),
    heading: "Users",
    primary: (p) => p.getByRole("button", { name: "Filter" }), primaryLabel: "Filter",
    table: (p) => p.getByRole("table").first(),
  },
  {
    id: "role-requests", path: "/rdco/role-requests", route: "/rdco/role-requests", role: "RDCO",
    mocks: wrap("RDCO", (api) =>
      api.on("GET", "/users/role-requests/", paginated([
        { id: 1, user: 11, user_name: "Maria Cristina Dela Cruz-Santos", requested_role: 2, role_name: "Adviser", status: "pending", created_at: when("11-04") },
      ]))),
    heading: "Role Requests",
    primary: (p) => p.getByRole("button", { name: /Approve/ }).first(), primaryLabel: "Approve",
    table: (p) => p.getByRole("table").first(),
  },
  {
    id: "download-requests", path: "/rdco/download-requests", route: "/rdco/download-requests", role: "RDCO",
    mocks: wrap("RDCO", (api) => api.on("GET", "/records/download-requests/", paginated([DOWNLOAD_REQUEST]))),
    heading: "Download Requests",
    primary: (p) => p.getByRole("button", { name: "Refresh" }), primaryLabel: "Refresh",
    table: (p) => p.getByRole("table").first(),
  },
  {
    id: "delete-requests", path: "/rdco/delete-requests", route: "/rdco/delete-requests", role: "RDCO",
    mocks: wrap("RDCO", (api) => api.on("GET", "/records/delete-requests/", paginated([DELETE_REQUEST]))),
    heading: "Delete Requests",
    primary: (p) => p.getByRole("button", { name: "Refresh" }), primaryLabel: "Refresh",
    table: (p) => p.getByRole("table").first(),
  },

  // --- System Admin --------------------------------------------------------
  {
    id: "admin-users", path: "/admin/users", route: "/admin/users", role: "System Admin",
    mocks: wrap("System Admin", (api) => api.on("GET", "/users/", paginated(USERS))),
    heading: "Users",
    primary: (p) => p.getByRole("button", { name: "Filter" }), primaryLabel: "Filter",
    table: (p) => p.getByRole("table").first(),
  },
  {
    id: "audit-log", path: "/admin/audit", route: "/admin/audit", role: "System Admin",
    mocks: wrap("System Admin", (api) => {
      api.on("GET", "/audit/event-types/", []);
      api.on("GET", "/audit/", paginated([AUDIT_EVENT]));
    }),
    heading: "Audit Log",
    primary: (p) => p.getByRole("button", { name: "Export CSV" }), primaryLabel: "Export CSV",
    table: (p) => p.getByRole("table").first(),
  },
];
