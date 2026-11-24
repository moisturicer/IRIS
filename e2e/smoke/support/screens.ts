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
import type { Locator, Page, Route } from "@playwright/test";
import type { MockApi } from "./mock-api";
import { mockReadingHistory, PAPER, PAPER_DETAIL, SCAN_PNG, RUNTIME_CONVERSATION, RUNTIME_CONVERSATION_ID, RUNTIME_CONVERSATION_PATH, paginated, type SmokeRole } from "./fixtures";

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
  /** A step after the page loads that reaches the view under test, e.g. a tab it does not open on. */
  open?: (page: Page) => Promise<void>;
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
  // Reading history (IR-756): My Library reads it, and the paper view records a visit.
  mockReadingHistory(api);
  if (role === "RDCO") {
    api.on("GET", "/dashboard/queue-counts/", {
      download_requests: 0, delete_requests: 0, role_change_requests: 0, reported_comments: 0,
    });
  }
  // IR-691: the System Admin shares the Reported comments queue, so its sidebar asks for that count alone.
  if (role === "System Admin") api.on("GET", "/dashboard/queue-counts/", { reported_comments: 0 });
}

const wrap = (role: SmokeRole, extra?: (api: MockApi) => void) => (api: MockApi) => {
  shell(api, role);
  extra?.(api);
};

/** An Adviser's Templates (IR-975): a long title, and a description holding a link. */
const MY_TEMPLATES = [
  {
    id: 7, title: "Chapter 1 to 3 proposal format for the Bachelor of Science in Information Technology capstone",
    description: "Use this for every chapter.\nSee https://cit.edu/forms/capstone-proposal-format-guidelines-2026.",
    file_name: "capstone-proposal-format-chapters-1-to-3-bsit-2026-revised-edition.docx", position: 1,
    updated_at: when("11-19"),
  },
  { id: 8, title: "Budget sheet", description: "", file_name: "budget.xlsx", position: 2, updated_at: when("11-19") },
];

/** Guidelines (IR-974): long names, long file names and descriptions holding links, at every width. */
export const GUIDELINES = [
  {
    id: 1, name: "Proposal", description: "Comes before a Thesis / Research. See https://cit.edu/research/proposal-guidelines-2026-revised.",
    manuscript: { description: "The proposal itself, chapters 1 to 3.", template_name: "cit-u-research-proposal-manuscript-format-2026-revised-edition.docx" },
    requirements: [
      { id: 11, name: "Thesis Revision Form", is_required: true, description: "", template_name: "thesis-revision-form.pdf" },
      { id: 12, name: "Patent Search Report", is_required: false, description: "Only when the work may be patentable.", template_name: "" },
    ],
  },
  {
    id: 2, name: "Thesis / Research", description: "Needs an approved Proposal first.",
    manuscript: { description: "", template_name: "" },
    requirements: [
      { id: 21, name: "Publication / Conference Presentation / Both", is_required: true,
        description: "Proof of acceptance. See https://cit.edu/research/forms.", template_name: "publication-proof-of-acceptance-form.pdf" },
    ],
  },
  { id: 3, name: "Project", description: "", manuscript: { description: "", template_name: "" }, requirements: [] },
];

export const ADVISERS_TEMPLATES = MY_TEMPLATES.map((t) => ({
  ...t, shared_by: { id: 40, name: "Maria Concepcion Villanueva-Dela Cruz Santiago" },
}));

/** Setup's record types (IR-971): one requirement with a long name, a Template and a description holding a link. */
const SETUP_RECORD_TYPES = [
  {
    id: 2, name: "Thesis / Research", description: "Needs an approved Proposal first.",
    manuscript: { description: "Use the CIT-U manuscript format.", template_name: "CIT-U manuscript format.docx" },
    requirements: [
      { id: 11, name: "Publication / Conference Presentation / Both", is_required: true,
        description: "Proof of acceptance. See https://cit.edu/research/forms.", position: 1,
        template_name: "publication-proof-of-acceptance-form.pdf", in_use: true },
      { id: 12, name: "Ethics Clearance", is_required: false, description: "", position: 2, template_name: "", in_use: false },
    ],
  },
  { id: 1, name: "Proposal", description: "", manuscript: { description: "", template_name: "" }, requirements: [] },
];

/**
 * The owner's Review with its documents (IR-1203): one slot version, one
 * attachment with a long unbroken name (the Full Text Rule, IR-1218).
 */
const reviewDocumentsMocks = (api: MockApi) => {
      api.on("GET", `/records/${PAPER.id}/`, {
        ...PAPER_DETAIL, pipeline_status: "in_review", workflow_state: "in_review", workflow_state_label: "In review",
        stage_label: "In review", is_participant: true, capabilities: ["cite", "edit_details"],
        owners: [{ id: 1, user: 1, email: "student@cit.edu", full_name: "Sam Student", is_primary: true }],
      });
      api.on("POST", `/records/${PAPER.id}/increment_access/`, {});
      api.on("GET", `/records/${PAPER.id}/tracker/`, {
        record_id: PAPER.id, record_type: "Thesis / Research", workflow_state: "in_review", workflow_state_label: "In review",
        current_holders: [], parties: [], routing_history: [], routing_recorded_from: null,
        reviews: [], versions: [], review_comments: [], resubmissions: [],
      });
      api.on("GET", `/documents/records/${PAPER.id}/slots/`, [{
        id: 2, name: "Ethics clearance", record_type: 1, is_required: true, uploads: [{
          id: 9, record: PAPER.id, slot: 2, slot_name: "Ethics clearance", file: "ethics.pdf", version: 1, status: null,
          status_name: null, uploaded_by: 1, uploaded_by_name: "Sam Student", created_at: "2026-11-04T08:00:00+08:00",
          reviews: [], delete_refused: null,
        }],
      }]);
      // One long, unbroken file name: it must wrap in its row, never run off it (the Full Text Rule, IR-1218).
      api.on("GET", "/documents/files/", [{
        id: 31, record: PAPER.id, file: "x.pdf", filename: "Final_Thesis_Manuscript_Revised_Signed_Adviser_Copy_v3.pdf",
        uploaded_by: 1, uploaded_by_name: "Sam Student", created_at: "2026-11-04T08:00:00+08:00", can_remove: true,
      }]);
      api.on("GET", "/documents/guidelines/", GUIDELINES);
      api.on("GET", `/records/${PAPER.id}/document-requests/`, []);
      api.on("GET", "/library/saves/", { results: [] });
      api.on("GET", "/library/folders/", { results: [], limit: 10 });
      api.on("GET", `/library/highlights/${PAPER.id}/`, { results: [] });
      api.on("GET", `/records/${PAPER.id}/review-comments/`, []);
      api.on("GET", `/records/${PAPER.id}/response-letters/`, []);
};

/** A one-page PDF pdf.js opens: enough for the reader to draw a page. */
const ONE_PAGE_PDF = Buffer.from(
  "%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n" +
  "3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF\n",
);
const pdfReply = (route: Route) =>
  route.fulfill({ status: 200, headers: { "content-type": "application/pdf" }, body: ONE_PAGE_PDF });

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

/** One reported comment with two reports, so the queue draws its reasons and a reader's note. */
const REPORTED_COMMENT = {
  id: 41, record: { id: 7, title: "Solar dryers for rural farms in the Visayas region" },
  author_name: "Maria Cristina Dela Cruz-Santos",
  reported_texts: ["Buy cheap followers at example.test"], current_text: "Buy cheap followers at example.test",
  deletion_kind: null, report_count: 2,
  reasons: [{ reason: "spam", count: 1 }, { reason: "other", count: 1 }],
  notes: ["It names a student."], first_reported_at: when("11-14"),
};

/** One open call, so the board draws its filters as it does with data. */
export const OPPORTUNITY = {
  id: 1, opportunity_type: "conference", type_display: "Conference",
  title: "International Conference on Applied Computing", description: "Full papers on applied computing.",
  external_url: "https://example.edu/icac", due_date: "2026-12-15", location: "Cebu City, Philippines",
  areas: [1], area_names: ["Agriculture"], start_date: "2027-02-10", end_date: "2027-02-12",
  registration_fee: "PHP 5,000", is_featured: false,
  posted_by: 2, posted_by_name: "RDCO", created_at: when("11-01"), updated_at: when("11-01"),
  days_left: 39, is_closed: false,
  papers_state: "accepting", papers_label: "Accepting papers",
  event_state: "upcoming", event_label: "Upcoming",
  status: "confirmed", status_label: "Confirmed", review_reason: "", reviewed_at: null,
  can_edit: false, can_delete: false, can_remove: false, can_confirm: false,
  can_reject: false, can_feature: false, edit_returns_to_pending: false,
};

/** An Adviser's Call waiting for RDCO (IR-765), with what RDCO may do with it. */
const CALL_REQUEST = {
  ...OPPORTUNITY, id: 2, title: "Visayas Symposium on Island Energy Grids", posted_by: 7, posted_by_name: "Ana Reyes",
  status: "pending", status_label: "Waiting for RDCO",
  can_confirm: true, can_reject: true, can_feature: true,
};

/** One of the viewer's own Calls, rejected, with RDCO's reason (IR-765). */
const MY_CALL = {
  ...OPPORTUNITY, id: 3, title: "Workshop on Edge AI for Agriculture",
  status: "rejected", status_label: "Rejected", review_reason: "The link goes to last year's call.",
  can_edit: true, can_delete: true, edit_returns_to_pending: true,
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
  reason: "Submitted by mistake.", status: "pending", rdco_note: "", reviewed_by: null, reviewed_at: null, created_at: when("11-04"),
};

const DELETION_REQUEST = {
  id: 1, status: "pending", created_at: when("11-04"), decided_at: null, reason: "",
  user: { id: 11, name: "Maria Cristina Dela Cruz-Santos", email: "maria.cristina@students.cit.edu", role: "Student" },
  blockers: [], capabilities: { can_confirm: true, can_reject: true },
};

const RETENTION_RUN = {
  id: 2, event_type: "RETENTION_CLEANUP_RUN", user: null, user_name: null, record: null, record_title: null,
  metadata: { counts: { download_notes: 3 } }, created_at: when("11-05"),
};

const AUDIT_EVENT = {
  id: 1, event_type: "LOGIN", user: 11, user_name: "Maria Cristina Dela Cruz-Santos",
  record: 101, record_title: LONG_TITLE, metadata: {}, created_at: when("11-05"),
};

// Ask IRIS runs on the AI runtime (IR-957): its history, and the conversation an address opens.
const askIrisMocks = wrap("Student", (api) => {
  api.on("GET", "/ai/runtime/conversations", { protocol: "runs-reader-1", conversations: [] });
  api.on("GET", RUNTIME_CONVERSATION_PATH, RUNTIME_CONVERSATION);
  // Conversations Django answered before the switch, listed read-only under the history.
  api.on("GET", "/ai/conversations/", []);
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
      // The server's data notice, which registration shows and answers (IR-790),
      // as its `text` (IR-800).
      api.on("GET", "/auth/notice/", {
        version: 1, text: "IRIS data notice\n\nWhat IRIS keeps\nYour name and CIT-U email.",
        published_at: "2026-11-01T00:00:00Z",
      });
    },
    heading: "Create an Account",
    primary: (p) => p.getByRole("button", { name: "Continue to affiliation" }), primaryLabel: "Continue to affiliation",
  },
  // ADR-045 (IR-643). Opening the link verifies nothing, so the screen is drawn
  // before its one POST and needs no mock.
  {
    id: "verify-email", path: "/verify-email#token=abc", route: "/verify-email", role: null,
    heading: "Verify your email",
    primary: (p) => p.getByRole("button", { name: "Verify email" }), primaryLabel: "Verify email",
  },
  {
    id: "verify-email-resend", path: "/verify-email/resend", route: "/verify-email/resend", role: null,
    heading: "Send a new verification email",
    primary: (p) => p.getByRole("button", { name: "Send verification email" }),
    primaryLabel: "Send verification email",
  },
  // Both retired link shapes (IR-643, ADR-045 §8) land on the same guidance,
  // with no request at all.
  {
    id: "activate", path: "/activate#uid=abc&token=def", route: "/activate", role: null,
    heading: "This link can't be used",
    primary: (p) => p.getByRole("link", { name: "Resend verification email" }),
    primaryLabel: "Resend verification email",
  },
  {
    id: "activate-path", path: "/activate/abc/def", route: "/activate/:uidb64/:token", role: null,
    heading: "This link can't be used",
    primary: (p) => p.getByRole("link", { name: "Resend verification email" }),
    primaryLabel: "Resend verification email",
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
      api.on("GET", "/users/search/", { count: 0, next: null, results: [] });
      api.on("GET", "/library/saves/", { results: [] });
      // IR-572: folders are read with the saves.
      api.on("GET", "/library/folders/", { results: [], limit: 10 });
    },
    heading: "Discover",
    primary: (p) => p.getByRole("button", { name: "Publish" }), primaryLabel: "Publish",
  },
  {
    id: "paper-view", path: `/records/${PAPER.id}`, route: "/records/:id", role: "Student",
    mocks: wrap("Student", (api) => {
      api.on("GET", `/records/${PAPER.id}/`, PAPER_DETAIL);
      api.on("POST", `/records/${PAPER.id}/increment_access/`, {});
      api.on("GET", `/records/${PAPER.id}/comments/`, { comments: [], count: 0 });
      api.on("GET", "/library/saves/", { results: [] });
      // IR-572: folders are read with the saves.
      api.on("GET", "/library/folders/", { results: [], limit: 10 });
      api.on("GET", `/library/highlights/${PAPER.id}/`, { results: [] });
      api.on("GET", `/ai/records/${PAPER.id}/overview/`, { state: "not_indexed", overview: null });
      api.on("GET", `/records/${PAPER.id}/similar/`, { results: [] });
      // Review threads (IR-875): the review workspace reads them beside the tracker.
      api.on("GET", `/records/${PAPER.id}/review-comments/`, []);
      // The response to reviewers (IR-876), read beside the threads.
      api.on("GET", `/records/${PAPER.id}/response-letters/`, []);
      // A participant's Review opens on its Documents tab (IR-1203), which reads these.
      api.on("GET", `/documents/records/${PAPER.id}/slots/`, []);
      // Its rows read their labels and Templates from Guidelines (IR-973).
      api.on("GET", "/documents/guidelines/", GUIDELINES);
      api.on("GET", "/documents/files/", []);
      api.on("GET", `/records/${PAPER.id}/document-requests/`, []);
    }),
    heading: PAPER.title,
    primary: (p) => p.getByRole("button", { name: /Cite/ }).first(), primaryLabel: "Cite",
  },
  {
    // IR-1206: the owner's Review is the reviewers' frame -- Back and the title
    // above the reader, the Readiness tab first. Its own row, since the same
    // route draws a different screen for the paper's owner.
    id: "paper-view-author-review", path: `/records/${PAPER.id}?section=review`, route: "/records/:id", role: "Student",
    mocks: wrap("Student", (api) => {
      api.on("GET", `/records/${PAPER.id}/`, {
        ...PAPER_DETAIL, pipeline_status: "in_review", workflow_state: "in_review", workflow_state_label: "In review",
        stage_label: "In review", is_participant: true, capabilities: ["cite", "edit_details"],
        owners: [{ id: 1, user: 1, email: "student@cit.edu", full_name: "Sam Student", is_primary: true }],
      });
      api.on("POST", `/records/${PAPER.id}/increment_access/`, {});
      api.on("GET", `/records/${PAPER.id}/tracker/`, {
        record_id: PAPER.id, record_type: "Thesis / Research", workflow_state: "in_review", workflow_state_label: "In review",
        current_holders: [], parties: [], routing_history: [], routing_recorded_from: null,
        reviews: [], versions: [], review_comments: [], resubmissions: [],
      });
      api.on("GET", "/library/saves/", { results: [] });
      api.on("GET", "/library/folders/", { results: [], limit: 10 });
      api.on("GET", `/library/highlights/${PAPER.id}/`, { results: [] });
      api.on("GET", `/records/${PAPER.id}/review-comments/`, []);
      api.on("GET", `/records/${PAPER.id}/response-letters/`, []);
    }),
    heading: PAPER.title,
    // Wide, the Readiness tab is in reach; narrower, the pane is a drawer and
    // its launcher is what the owner reaches first.
    primary: (p) => p.getByRole("tab", { name: "Readiness" }).or(p.getByRole("button", { name: "Open review pane" }))
      .filter({ visible: true }).first(),
    primaryLabel: "Readiness (tab) or Open review pane",
  },
  {
    // IR-1203: documents are a Review tab, which replaced the "All documents"
    // drawer. An old `?documents=open` link opens the owner's Review on that
    // tab, and a narrow window opens the pane to it.
    id: "paper-view-review-documents", path: `/records/${PAPER.id}?section=review&documents=open`, route: "/records/:id",
    role: "Student",
    mocks: wrap("Student", reviewDocumentsMocks),
    heading: PAPER.title,
    primary: (p) => p.getByRole("tab", { name: "Documents", selected: true }).filter({ visible: true }).first(),
    primaryLabel: "Documents (tab, selected)",
  },
  {
    // IR-1203 part (b): a document opened from Documents is read in the
    // reader in place of the manuscript, named above it with the way back.
    // A narrow window closes the pane so the reader is seen.
    id: "paper-view-review-document-open", path: `/records/${PAPER.id}?section=review&documents=open`, route: "/records/:id",
    role: "Student",
    mocks: wrap("Student", (api) => {
      reviewDocumentsMocks(api);
      api.on("GET", `/records/${PAPER.id}/`, {
        ...PAPER_DETAIL, pipeline_status: "in_review", workflow_state: "in_review", workflow_state_label: "In review",
        stage_label: "In review", is_participant: true, capabilities: ["cite", "edit_details"],
        abstract_file: "/media/manuscript.pdf",
        owners: [{ id: 1, user: 1, email: "student@cit.edu", full_name: "Sam Student", is_primary: true }],
      });
      api.on("GET", `/records/${PAPER.id}/manuscript/`, pdfReply);
      api.on("GET", "/documents/uploads/9/download/", pdfReply);
    }),
    open: async (page) => {
      await page.getByRole("button", { name: "Open Ethics clearance version 1" }).filter({ visible: true }).first().click();
    },
    heading: PAPER.title,
    primary: (p) => p.getByRole("button", { name: "Back to the manuscript" }).filter({ visible: true }).first(),
    primaryLabel: "Back to the manuscript",
  },
  {
    // IR-1203's image half: a scanned PNG opens in the reader as an image,
    // with zoom and the watermark, where a PDF would get pages.
    id: "paper-view-review-image-open", path: `/records/${PAPER.id}?section=review&documents=open`, route: "/records/:id",
    role: "Student",
    mocks: wrap("Student", (api) => {
      reviewDocumentsMocks(api);
      api.on("GET", `/records/${PAPER.id}/`, {
        ...PAPER_DETAIL, pipeline_status: "in_review", workflow_state: "in_review", workflow_state_label: "In review",
        stage_label: "In review", is_participant: true, capabilities: ["cite", "edit_details"],
        abstract_file: "/media/manuscript.pdf",
        owners: [{ id: 1, user: 1, email: "student@cit.edu", full_name: "Sam Student", is_primary: true }],
      });
      api.on("GET", `/records/${PAPER.id}/manuscript/`, pdfReply);
      api.on("GET", "/documents/files/", [{
        id: 32, record: PAPER.id, file: "x.png", filename: "Signed consent form.png",
        uploaded_by: 1, uploaded_by_name: "Sam Student", created_at: "2026-11-04T08:00:00+08:00", can_remove: true,
      }]);
      api.on("GET", "/documents/files/32/download/", (route: Route) =>
        route.fulfill({ status: 200, headers: { "content-type": "image/png" }, body: SCAN_PNG }));
    }),
    open: async (page) => {
      await page.getByRole("button", { name: "Open Signed consent form.png" }).filter({ visible: true }).first().click();
      await page.getByRole("img", { name: "Signed consent form.png" }).waitFor();
    },
    heading: PAPER.title,
    primary: (p) => p.getByRole("button", { name: "Back to the manuscript" }).filter({ visible: true }).first(),
    primaryLabel: "Back to the manuscript",
  },
  {
    // IR-1204: a reviewer's Must fix on a supporting document, as the author
    // reads it in Threads. The document's long name wraps in the card, and its
    // link opens the document in the reader.
    id: "paper-view-review-document-thread", path: `/records/${PAPER.id}?section=review`, route: "/records/:id",
    role: "Student",
    mocks: wrap("Student", (api) => {
      reviewDocumentsMocks(api);
      api.on("GET", `/records/${PAPER.id}/`, {
        ...PAPER_DETAIL, pipeline_status: "in_review", workflow_state: "in_review", workflow_state_label: "In review",
        stage_label: "In review", is_participant: true, capabilities: ["cite", "edit_details"],
        abstract_file: "/media/manuscript.pdf",
        owners: [{ id: 1, user: 1, email: "student@cit.edu", full_name: "Sam Student", is_primary: true }],
      });
      api.on("GET", `/records/${PAPER.id}/manuscript/`, pdfReply);
      api.on("GET", "/documents/uploads/9/download/", pdfReply);
      api.on("GET", `/records/${PAPER.id}/review-comments/`, [{
        id: 70, kind: "thread", author: 2, author_name: "Ina Ercilla", body: "The consent form isn't signed on page 2.",
        version: 1, reply_to: null, created_at: "2026-11-05T08:00:00+08:00", edited_at: null, can_edit: false, mentions: [],
        party: "ierc", party_label: "IERC", severity: "must_fix", is_draft: false, round: null, anchor: null,
        document: {
          upload: 9, slot: "Certificate of Informed Consent and Ethics Clearance", version: 1,
          label: "Certificate of Informed Consent and Ethics Clearance, v1", earlier: true, extension: "pdf",
        },
        suggestion: "", place: null, outdated_since: null, wording_check: null, not_followed: null,
        state: "open", resolved_by: null, resolved_at: null, closed_by_decision: null, closed_reason: null,
        answer: null, events: [], can_delete: false, can_post: false, can_change_severity: false,
        can_resolve: false, can_reopen: false, can_answer: true,
      }]);
    }),
    open: async (page) => {
      // Narrower than the side-by-side workspace, the pane is a drawer: open it first.
      const drawer = page.getByRole("button", { name: "Open review pane" }).filter({ visible: true });
      if (await drawer.count()) await drawer.first().click();
      await page.getByRole("tab", { name: /^Threads/ }).filter({ visible: true }).first().click();
      await page.getByText("From an earlier upload").filter({ visible: true }).first().waitFor();
    },
    heading: PAPER.title,
    primary: (p) => p.getByRole("button", { name: "Open Certificate of Informed Consent and Ethics Clearance, v1" })
      .filter({ visible: true }).first(),
    primaryLabel: "Open Certificate of Informed Consent and Ethics Clearance, v1",
  },
  {
    id: "my-library", path: "/records/mine", route: "/records/mine", role: "Student",
    mocks: wrap("Student", (api) => {
      api.on("GET", "/library/saves/", { results: [] });
      // IR-572: folders are read with the saves.
      api.on("GET", "/library/folders/", { results: [], limit: 10 });
      api.on("GET", "/records/mine/", []);
    }),
    heading: "My Library",
    primary: (p) => p.getByRole("link", { name: "Publish" }), primaryLabel: "Publish",
  },
  {
    id: "opportunities", path: "/opportunities", route: "/opportunities", role: "Student",
    mocks: wrap("Student", (api) => {
      api.on("GET", "/opportunities/", { count: 1, next: null, previous: null, results: [OPPORTUNITY], can_post: false, can_review_requests: false });
      // The reader's saved Calls follow the account (IR-766).
      api.on("GET", "/opportunities/saved/", { results: [] });
    }),
    heading: "Calls & Conferences",
    primary: (p) => p.getByRole("button", { name: /^All\s*\d*$/ }).first(), primaryLabel: "All (filter)",
  },
  {
    // A poster's own Calls (IR-765). RDCO and Advisers reach it; the smoke roles have no Adviser.
    id: "my-calls", path: "/opportunities/mine", route: "/opportunities/mine", role: "RDCO",
    mocks: wrap("RDCO", (api) => {
      api.on("GET", "/opportunities/mine/", paginated([MY_CALL]));
      api.on("GET", "/records/classifications/", paginated([{ id: 1, name: "Agriculture" }]));
    }),
    heading: "My Calls",
    primary: (p) => p.getByRole("button", { name: /^Edit and send again/ }).first(), primaryLabel: "Edit and send again",
  },
  {
    // An Adviser's own proposal Templates (ADR-063 decision 8, IR-975).
    id: "my-templates", path: "/my-templates", route: "/my-templates", role: "Adviser",
    mocks: wrap("Adviser", (api) => api.on("GET", "/documents/my-templates/", MY_TEMPLATES)),
    heading: "My Templates",
    primary: (p) => p.getByRole("button", { name: "Add a Template" }), primaryLabel: "Add a Template",
  },
  {
    id: "guidelines", path: "/guidelines", route: "/guidelines", role: "Student",
    mocks: wrap("Student", (api) => {
      api.on("GET", "/documents/guidelines/", GUIDELINES);
      api.on("GET", "/documents/adviser-templates/", ADVISERS_TEMPLATES);
    }),
    heading: "Guidelines",
    primary: (p) => p.getByRole("button", { name: /^Download the Manuscript Template, cit-u-research-proposal/ }),
    primaryLabel: "Download the Proposal's Manuscript Template",
  },
  {
    id: "notifications", path: "/notifications", route: "/notifications", role: "Student",
    mocks: wrap("Student"),
    heading: "Notifications",
    // The breadcrumb's Discover link until IR-1255 removed the breadcrumb.
    primary: (p) => p.getByRole("button", { name: "Mark all as read" }), primaryLabel: "Mark all as read",
  },
  {
    id: "ask-iris", path: "/ai", route: "/ai", role: "Student",
    mocks: askIrisMocks,
    heading: "Ask IRIS",
    primary: (p) => p.getByRole("button", { name: "Send message" }), primaryLabel: "Send message",
  },
  {
    // The address a bookmark or a chat in the history lands on directly.
    id: "ask-iris-conversation", path: `/ai/conversations/${RUNTIME_CONVERSATION_ID}`, route: "/ai/conversations/:conversationId", role: "Student",
    mocks: askIrisMocks,
    heading: "New conversation",
    primary: (p) => p.getByRole("button", { name: "Send message" }), primaryLabel: "Send message",
  },
  {
    // Help is a Settings section since IR-1245; `/help` redirects here.
    id: "help", path: "/settings?tab=help", route: "/settings", role: "Student",
    mocks: wrap("Student"),
    heading: "Settings",
    primary: (p) => p.getByRole("link", { name: "Finding research" }).first(), primaryLabel: "Finding research (contents)",
  },
  {
    // Only the preview since IR-1304: editing is in Settings, so the page's one
    // control here is the paging of its Research list, which needs a next page.
    id: "profile", path: "/profile", route: "/profile", role: "Student",
    mocks: wrap("Student", (api) => {
      api.on("GET", "/users/1/profile/research/", {
        next: "page-2",
        results: [{
          id: 500, title: "Flood Risk Mapping in Cebu", authors: ["Student, S."],
          classification_name: "Environmental Engineering", record_type_name: "Thesis / Research",
          publication_year: 2025, views: 12,
        }],
      });
      api.on("GET", "/users/1/profile/advised/", { next: null, results: [] });
      api.on("GET", "/users/1/profile/collaborators/", { next: null, results: [] });
    }),
    heading: /Sam Student/,
    primary: (p) => p.getByRole("button", { name: "Show more research papers" }), primaryLabel: "Show more research papers",
  },
  {
    // Edit profile was a page of its own until IR-1304; it is Settings' first section.
    id: "profile-settings", path: "/settings?tab=profile", route: "/settings", role: "Student",
    mocks: wrap("Student"),
    heading: "Settings",
    primary: (p) => p.getByRole("button", { name: "Save" }), primaryLabel: "Save",
  },
  {
    // Another person's Profile (IR-700), read from the draft IR-696 contract.
    id: "person-profile", path: "/people/101", route: "/people/:id", role: "Student",
    mocks: wrap("Student", (api) => {
      api.on("GET", "/users/101/profile/", {
        id: 101, first_name: "Marites", middle_initial: "C", last_name: "Villanueva", role_label: "Adviser",
        college_name: "College of Engineering and Architecture", department_name: "Department of Computer Engineering",
        course_name: "", bio: "I work on how communities in Cebu prepare for flooding.",
        research_interests: ["Flood risk", "GIS"], photo_url: null,
      });
      const papers = (from: number) => ({
        next: "page-2",
        results: Array.from({ length: 10 }, (_, i) => ({
          id: from + i, title: LONG_TITLE, authors: ["Reyes, A.", "Villanueva, M."],
          classification_name: "Environmental Engineering", record_type_name: "Thesis / Research",
          publication_year: 2025, views: 48,
        })),
      });
      api.on("GET", "/users/101/profile/research/", papers(500));
      api.on("GET", "/users/101/profile/advised/", papers(600));
      api.on("GET", "/users/101/profile/collaborators/", {
        next: null,
        results: [{ id: 201, first_name: "Ana", middle_initial: "L", last_name: "Reyes", photo_url: null, shared_papers: 14 }],
      });
    }),
    heading: "Marites C. Villanueva",
    primary: (p) => p.getByRole("button", { name: "Show more research papers" }), primaryLabel: "Show more research papers",
  },
  {
    id: "settings", path: "/settings?tab=security", route: "/settings", role: "Student",
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
    heading: /console$/,
    // The breadcrumb's Discover link until IR-1255 removed the breadcrumb.
    primary: (p) => p.getByRole("link", { name: "Back to My Reviews" }), primaryLabel: "Back to My Reviews",
  },
  {
    id: "workflow-analytics", path: "/rdco/analytics", route: "/rdco/analytics", role: "RDCO",
    mocks: wrap("RDCO", (api) =>
      api.on("GET", "/reviews/analytics/", {
        parties: [{ party: "rdco", label: "RDCO" }], data_since: null, generated_at: when("11-05"),
        range: { from: null, to: null }, thresholds: { median: 5, p90: 5 },
        open_now: [], time_in_stage: [], unmeasured: [], throughput: [], revision_cycles: [], preserved_by_office: [],
      })),
    heading: "Workflow analytics",
    // The breadcrumb's Discover link until IR-1255 removed the breadcrumb.
    primary: (p) => p.getByLabel("From"), primaryLabel: "From (date)",
  },
  {
    id: "import-records", path: "/records/import", route: "/records/import", role: "RDCO",
    mocks: wrap("RDCO"),
    heading: "Import records",
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
    heading: "Role requests",
    primary: (p) => p.getByRole("button", { name: /Approve/ }).first(), primaryLabel: "Approve",
    table: (p) => p.getByRole("table").first(),
  },
  {
    id: "call-requests", path: "/rdco/call-requests", route: "/rdco/call-requests", role: "RDCO",
    mocks: wrap("RDCO", (api) => api.on("GET", "/opportunities/requests/", paginated([CALL_REQUEST]))),
    heading: "Call requests",
    primary: (p) => p.getByRole("button", { name: /^Confirm / }).first(), primaryLabel: "Confirm",
  },
  {
    id: "download-requests", path: "/rdco/download-requests", route: "/rdco/download-requests", role: "RDCO",
    mocks: wrap("RDCO", (api) => api.on("GET", "/records/download-requests/", paginated([DOWNLOAD_REQUEST]))),
    heading: "Download requests",
    primary: (p) => p.getByRole("button", { name: "Refresh" }), primaryLabel: "Refresh",
    table: (p) => p.getByRole("table").first(),
  },
  {
    id: "delete-requests", path: "/rdco/delete-requests", route: "/rdco/delete-requests", role: "RDCO",
    mocks: wrap("RDCO", (api) => {
      api.on("GET", "/records/delete-requests/", paginated([DELETE_REQUEST]));
      api.on("GET", "/records/delete-requests/counts/", { pending: 1, approved: 0, declined: 0, all: 1 });
    }),
    heading: "Delete requests",
    primary: (p) => p.getByRole("button", { name: "Refresh" }), primaryLabel: "Refresh",
    table: (p) => p.getByRole("table").first(),
  },
  {
    id: "rdco-setup", path: "/rdco/setup", route: "/rdco/setup", role: "RDCO",
    mocks: wrap("RDCO", (api) => api.on("GET", "/documents/setup/record-types/", SETUP_RECORD_TYPES)),
    heading: "Setup",
    primary: (p) => p.getByRole("button", { name: "Add a requirement" }), primaryLabel: "Add a requirement",
  },
  // IR-693: RDCO and the System Admin share this queue at one path, as Notices does.
  {
    id: "reported-comments", path: "/moderation/comments", route: "/moderation/comments", role: "RDCO",
    mocks: wrap("RDCO", (api) => api.on("GET", "/moderation/comments/", { comments: [REPORTED_COMMENT] })),
    heading: "Reported comments",
    primary: (p) => p.getByRole("button", { name: /^Remove / }).first(), primaryLabel: "Remove",
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
    id: "account-deletion-requests", path: "/admin/account-deletion-requests",
    route: "/admin/account-deletion-requests", role: "System Admin",
    mocks: wrap("System Admin", (api) => api.on("GET", "/users/deletion-requests/", paginated([DELETION_REQUEST]))),
    heading: "Account Deletion Requests",
    primary: (p) => p.getByRole("button", { name: "Confirm deletion" }), primaryLabel: "Confirm deletion",
  },
  {
    id: "retention", path: "/admin/retention", route: "/admin/retention", role: "System Admin",
    mocks: wrap("System Admin", (api) => {
      api.on("GET", "/settings/retention.download_notes_days/",
        { key: "retention.download_notes_days", value: "", updated_by: null, updated_at: when("11-01") });
      api.on("GET", "/audit/", paginated([RETENTION_RUN]));
    }),
    heading: "Retention",
    primary: (p) => p.getByRole("button", { name: "Save period" }), primaryLabel: "Save period",
  },
  // ADR-051 decisions 16-17 as amended by ADR-063 decision 9 (IR-800, IR-972):
  // RDCO publishes the next version of the data notice in Setup's Notice section.
  {
    id: "rdco-setup-notice", path: "/rdco/setup?section=notice", route: "/rdco/setup", role: "RDCO",
    mocks: wrap("RDCO", (api) => (api.on("GET", "/auth/notice/draft/", null), api.on("GET", "/auth/notice/versions/", [{
      version: 1, text: "IRIS data notice\n\nWhat IRIS keeps\nYour name and CIT-U email.",
      published_at: when("11-01"), published_by: { id: 4, name: "Rita Dela Cruz", email: "rdco@cit.edu" },
    }]))),
    heading: "Version history",
    primary: (p) => p.getByRole("button", { name: "Preview" }), primaryLabel: "Preview",
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
