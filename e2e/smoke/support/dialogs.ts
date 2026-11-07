// The dialogs axe scans (IR-908), one entry per dialog a smoke screen can open.
//
// Each starts from a screen in screens.ts (its address, its role, its mocked
// API), optionally changes a mock so the control that opens the dialog is there,
// and opens it with `open`. The scan runs with the dialog on screen, which is
// where a missing name, an unlabelled field or a contrast failure inside it can
// be seen; the page behind a modal is inert and not scanned (axe skips it).
//
// A dialog source file that is neither here nor in UNSCANNED fails
// dialog-coverage.spec.ts, so a new dialog cannot ship without a decision.
import type { Locator, Page } from "@playwright/test";
import type { MockApi } from "./mock-api";
import { PAPER, PAPER_DETAIL, paginated } from "./fixtures";

export interface DialogCase {
  id: string;
  /** The screen in screens.ts it opens from. */
  screen: string;
  /** Opens that address instead of the screen's own. */
  path?: string;
  /** Source files (relative to frontend/src) this case puts on screen. */
  sources: string[];
  override?: (api: MockApi) => void;
  /** Narrower than the desktop default, for a dialog that exists only there. */
  viewport?: { width: number; height: number };
  open: (page: Page) => Promise<void>;
  /** The dialog itself. */
  dialog: (page: Page) => Locator;
}

const anyDialog = (page: Page) => page.locator('[role="dialog"], [role="alertdialog"]').last();
const press = (name: string | RegExp) => async (page: Page) => {
  // A string is an exact name: "Decline" must not match the "Declined" filter.
  await page.getByRole("button", { name, exact: typeof name === "string" }).first().click();
};

/** A Record under review that the signed-in reader may act on, with the given actions on offer. */
const reviewing = (...capabilities: string[]) => (api: MockApi) =>
  api.on("GET", `/records/${PAPER.id}/`, {
    ...PAPER_DETAIL, is_participant: true, workflow_state: "under_review", workflow_state_label: "Under review",
    stage_label: "Under review", capabilities: ["cite", ...capabilities], can_request_document: ["itso"],
  });
/** A 1x1 PNG: enough for the photo field to accept a file and open its crop dialog. */
const PNG = Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==", "base64");

/** One office the reviewer may ask, with one person to nominate there. */
const ROUTE_TARGETS = [{ party: "itso", label: "ITSO", members: [{ id: 5, name: "Ines Tan" }], already_holds: false, author_hint: null }];

/** The record's tracker with nothing on it yet: valid, and enough for the review panels to draw. */
const TRACKER = {
  record_id: PAPER.id, record_type: "Thesis / Research", workflow_state: "under_review", workflow_state_label: "Under review",
  current_holders: [], parties: [], routing_history: [], routing_recorded_from: null,
  reviews: [], versions: [], review_comments: [], resubmissions: [], document_requests: [], clearances: [],
  resubmission: { count: 0, last_resubmitted_at: null, declining_office: null, offices_preserved: [] },
};
/** The coordinator's console with one open row, drawn as an unseated pool row or a seated one. */
const consoleAction = (id: string, button: string, kind: "pool" | "seat", source: string): DialogCase => ({
  id, screen: "office-console", sources: [source],
  override: (api) => {
    api.on("GET", "/reviews/office/", {
      office: "rdco", office_label: "RDCO",
      rows: [{
        key: `${kind}-1`, kind, record: PAPER.id, title: PAPER.title, assignment: 7,
        seat: kind === "seat" ? 3 : null, reviewer: kind === "seat" ? 5 : null, reviewer_name: kind === "seat" ? "Ines Tan" : null,
        seat_state: kind === "seat" ? "in_review" : null, seat_state_label: kind === "seat" ? "In review" : null,
        opened_at: "2026-11-01T08:00:00+08:00", due_at: "2026-11-12T08:00:00+08:00", original_due_at: "2026-11-12T08:00:00+08:00",
        is_overdue: false, clock_paused: false, can_extend: true,
      }],
      load: [{ reviewer: 5, name: "Ines Tan", open_count: 1, overdue: 0 }, { reviewer: 6, name: "Rey Cruz", open_count: 0, overdue: 0 }],
    });
    api.on("GET", "/assignments/7/assign/", { assignment: 7, party: "rdco", party_label: "RDCO", members: [{ id: 5, name: "Ines Tan", seated: false }] });
  },
  open: async (page) => { await page.getByRole("button", { name: new RegExp(`^${button}`) }).first().click(); },
  dialog: anyDialog,
});
const reviewAction = (
  id: string, capability: string, label: string, source: string, more?: (api: MockApi) => void,
  /** The reviewer's sidebar is a "Details" tab when the workspace is narrow, so a control that lives there opens it first. */
  inDetails = false,
): DialogCase => ({
  // The bar and the workspace host every review action's dialog.
  id, screen: "paper-view", path: `/records/${PAPER.id}?section=review`,
  sources: [source, "features/records/paper-view/ReviewActionBar.tsx", "features/records/paper-view/ReviewWorkspace.tsx"],
  viewport: inDetails ? { width: 820, height: 900 } : undefined,
  override: (api) => { reviewing(capability)(api); api.on("GET", `/records/${PAPER.id}/tracker/`, TRACKER); more?.(api); },
  open: async (page) => {
    if (inDetails) await page.getByRole("tab", { name: "Details" }).click();
    await press(label)(page);
  },
  dialog: anyDialog,
});

/** Discover with one saved feed, opened from the My feeds menu: its rename and delete dialogs. */
const SAVED_FEED = { id: 5, name: "Flood studies", query: { q: "flood" }, stale: {}, created_at: "2026-11-01T08:00:00+08:00", updated_at: "2026-11-01T08:00:00+08:00" };
const feedAction = (id: string, verb: string, title: string): DialogCase => ({
  id, screen: "discover", sources: ["features/discover/MyFeeds.tsx"],
  override: (api) => api.on("GET", "/library/feeds/", { results: [SAVED_FEED], limit: 10 }),
  open: async (page) => {
    await page.getByRole("button", { name: /^My feeds/ }).click();
    await page.getByRole("button", { name: `${verb} ${SAVED_FEED.name}` }).click();
  },
  dialog: (page) => page.getByRole("dialog", { name: title }),
});

export const DIALOGS: DialogCase[] = [
  {
    id: "cite a paper", screen: "paper-view", sources: ["features/discover/PaperCiteModal.tsx", "features/discover/DiscoverPage.tsx", "components/ui/Modal.tsx"],
    open: press(/Cite/), dialog: anyDialog,
  },
  {
    id: "publish", screen: "discover", sources: ["features/publish/PublishDialog.tsx"],
    override: (api) => api.on("GET", "/users/advisers/", paginated([])),
    open: press("Publish"), dialog: anyDialog,
  },
  {
    id: "discover filters", screen: "discover", sources: ["features/discover/DiscoverFilterBar.tsx"],
    open: press(/^Filters/), dialog: (page) => page.getByRole("dialog", { name: "Filters" }),
  },
  {
    id: "save a custom feed", screen: "discover", sources: ["features/discover/MyFeeds.tsx"],
    open: async (page) => {
      await page.getByRole("button", { name: /^My feeds/ }).click();
      await page.getByRole("button", { name: /^Save these filters as a feed/ }).click();
    },
    dialog: (page) => page.getByRole("dialog", { name: "Save these filters as a feed" }),
  },
  feedAction("rename a custom feed", "Rename", "Rename feed"),
  feedAction("delete a custom feed", "Delete", "Delete this feed?"),
  {
    id: "notifications", screen: "help", sources: ["components/layout/NotificationBell.tsx"],
    open: press(/^Notifications/), dialog: (page) => page.getByRole("dialog", { name: "Notifications" }),
  },
  {
    id: "post a call", screen: "opportunities", sources: ["features/opportunities/OpportunityFormDialog.tsx", "features/opportunities/CallsAndConferencesPage.tsx"],
    override: (api) => api.on("GET", "/opportunities/", { count: 0, next: null, previous: null, results: [], can_post: true }),
    open: press("Post a call"), dialog: anyDialog,
  },
  {
    id: "change a user's role", screen: "rdco-users", sources: ["features/accounts/UserListPage.tsx"],
    open: press("Change role"), dialog: anyDialog,
  },
  {
    id: "make or remove a coordinator", screen: "admin-users", sources: ["features/accounts/UserListPage.tsx", "components/shared/ConfirmDialog.tsx"],
    open: press(/coordinator$/), dialog: anyDialog,
  },
  {
    id: "lock or unlock an account", screen: "rdco-users", sources: ["features/accounts/UserListPage.tsx", "components/shared/ConfirmDialog.tsx"],
    open: press(/^(Lock|Unlock)$/), dialog: anyDialog,
  },
  {
    id: "approve a role request", screen: "role-requests", sources: ["features/accounts/RoleRequestsPage.tsx"],
    open: press(/Approve/), dialog: anyDialog,
  },
  {
    id: "decline a role request", screen: "role-requests", sources: ["features/accounts/RoleRequestsPage.tsx"],
    open: press("Decline"), dialog: anyDialog,
  },
  {
    id: "decline a download request", screen: "download-requests", sources: ["features/admin/DownloadRequestsPage.tsx"],
    open: press("Decline"), dialog: anyDialog,
  },
  {
    id: "account locked after failed sign-ins", screen: "login", sources: ["components/auth/AccountLockedModal.tsx", "components/auth/EntryFrame.tsx"],
    override: (api) => api.on("POST", "/auth/login/", { code: "too_many_attempts", unlock_at: "2099-01-01T00:00:00Z" }, 429),
    open: async (page) => {
      await page.getByLabel("Email Address").fill("student@cit.edu");
      await page.getByLabel("Password", { exact: true }).fill("not-the-password");
      await page.getByRole("button", { name: "Sign In" }).click();
    },
    dialog: (page) => page.getByRole("dialog"),
  },
  {
    id: "ask again for a download", screen: "my-library", path: "/records/mine?section=downloads",
    sources: ["components/records/DownloadRequestModal.tsx"],
    override: (api) => api.on("GET", "/records/download-requests/mine/", [{
      id: 1, record: PAPER.id, record_title: PAPER.title, note: "For my literature review.", created_at: "2026-11-04T08:00:00+08:00",
      state: "declined", grant_expires_at: null, rdco_note: "", actions: ["request_again"],
    }]),
    open: press("Request again"), dialog: anyDialog,
  },
  {
    id: "crop a profile photo", screen: "profile-edit", sources: ["features/profile/PhotoCropDialog.tsx"],
    open: async (page) => {
      await page.locator('input[type="file"]').first().setInputFiles({ name: "me.png", mimeType: "image/png", buffer: PNG });
    },
    dialog: anyDialog,
  },
  {
    id: "edit a paper's details", screen: "paper-view", path: `/records/${PAPER.id}?edit=details`,
    sources: ["features/records/paper-view/EditDetailsDialog.tsx"],
    override: (api) => {
      api.on("GET", `/records/${PAPER.id}/`, { ...PAPER_DETAIL, capabilities: ["cite", "edit_details"] });
      api.on("GET", "/users/advisers/", paginated([]));
      api.on("GET", "/records/classifications/", paginated([{ id: 1, name: "Agriculture" }]));
      api.on("GET", "/records/psced-classifications/", paginated([]));
    },
    open: async () => undefined, // `?edit=details` opens it on load
    dialog: anyDialog,
  },
  {
    // RDCO publishes an Unlisted paper once its embargo is released (IR-878).
    id: "publish an unlisted paper", screen: "paper-view", sources: ["features/records/paper-view/UnlistedCard.tsx"],
    override: (api) => {
      api.on("GET", `/records/${PAPER.id}/`, {
        ...PAPER_DETAIL, pipeline_status: "completed", workflow_state: "completed", workflow_state_label: "Unlisted",
        stage_label: "Unlisted", capabilities: ["cite", "publish_unlisted"], publish_unlisted: { blocked: null },
      });
    },
    open: press("Publish to Discover"), dialog: anyDialog,
  },
  {
    id: "submit a new version", screen: "paper-view", sources: ["features/records/paper-view/NewVersionDialog.tsx"],
    override: (api) => {
      api.on("GET", `/records/${PAPER.id}/tracker/`, { ...TRACKER, workflow_state: "revision_requested", workflow_state_label: "Revision requested" });
      api.on("GET", `/records/${PAPER.id}/document-requests/`, []);
      api.on("GET", `/records/${PAPER.id}/`, {
      ...PAPER_DETAIL, workflow_state: "revision_requested", workflow_state_label: "Revision requested",
      owners: [{ id: 1, user: 1, email: "student@cit.edu", full_name: "Sam Student", is_primary: true }],
      capabilities: ["cite", "create_version"],
      revision: {
        ...PAPER_DETAIL.revision, party: "itso", label: "ITSO",
        open: [{ id: 1, party: "itso", label: "ITSO", reason: "Please add the ethics clearance.", requested_by: "Ines Tan", version: 1, created_at: "2026-11-04T08:00:00+08:00" }],
        new_version: { number: 2, rereview: ["ITSO"], kept: ["IERC"], blocked: null },
      },
      });
    },
    open: press("Submit new version"), dialog: anyDialog,
  },
  {
    id: "ask iris chat history on a narrow screen", screen: "ask-iris-conversation", sources: ["features/ai/components/ChatDrawer.tsx", "features/ai/RAGChatPage.tsx"],
    viewport: { width: 640, height: 900 },
    open: press("Show chat history"), dialog: (page) => page.getByRole("dialog", { name: "Chat history" }),
  },
  consoleAction("assign a reviewer", "Assign reviewer", "pool", "features/review/AssignReviewerDialog.tsx"),
  consoleAction("reassign a reviewer", "Reassign", "seat", "features/review/ReassignDialog.tsx"),
  consoleAction("extend a due date", "Extend due date", "seat", "features/review/ExtendDueDateDialog.tsx"),
  reviewAction("accept and publish a paper", "accept_publish", "Accept & publish…", "features/records/paper-view/DecisionDialog.tsx"),
  reviewAction("reject a paper", "reject", "Reject…", "features/records/paper-view/DecisionDialog.tsx"),
  // Finish review (IR-875): the footer's one way to finish where `finish_review` is granted.
  reviewAction("finish a review", "finish_review", "Finish review…", "features/records/paper-view/threads/FinishReviewDialog.tsx"),
  reviewAction("request a revision", "request_revision", "Request Revision…", "features/records/paper-view/RequestRevisionDialog.tsx"),
  reviewAction("clear a paper at an office", "office_review", "Clear…", "features/records/paper-view/OfficeReviewDialog.tsx"),
  reviewAction("record an office finding", "office_review", "Record finding…", "features/records/paper-view/OfficeReviewDialog.tsx"),
  reviewAction("add a reviewer", "add_reviewer", "Add a colleague…", "features/records/paper-view/AddReviewerDialog.tsx",
    (api) => {
      api.on("GET", `/records/${PAPER.id}/`, {
        ...PAPER_DETAIL, is_participant: true, workflow_state: "under_review", workflow_state_label: "Under review",
        stage_label: "Under review", capabilities: ["cite", "add_reviewer"],
        my_seats: [{
          id: 3, assignment: 7, record: PAPER.id, party: "itso", party_label: "ITSO", reviewer: 1, reviewer_name: "Sam Student",
          state: "in_review", state_label: "In review", source: "routed", assigned_by: null, assigned_at: null,
        }],
      });
      api.on("GET", "/assignments/7/add-reviewer/", {
        assignment: 7, party: "itso", party_label: "ITSO",
        members: [{ id: 5, name: "Ines Tan", seated: false }, { id: 6, name: "Rey Cruz", seated: true }],
      });
    }, true),
  reviewAction("request a review from an office", "route", "Request review", "features/records/paper-view/RouteDialog.tsx",
    (api) => {
      api.on("GET", `/records/${PAPER.id}/`, {
        ...PAPER_DETAIL, is_participant: true, workflow_state: "under_review", workflow_state_label: "Under review",
        stage_label: "Under review", capabilities: ["cite", "route"], routing: { send_to_rdco: false, route_as: null, targets: ROUTE_TARGETS },
      });
      api.on("GET", `/records/${PAPER.id}/route-options/`, { from_party: "adviser", from_label: "Adviser", accept: false, targets: ROUTE_TARGETS });
    }, true),
  reviewAction("request documents", "request_document", "Request documents", "features/document-requests/RequestDocumentDialog.tsx",
    (api) => api.on("GET", `/records/${PAPER.id}/document-requests/slots/`, [{ id: 1, name: "Ethics clearance" }])),
];

/**
 * Dialog source files this tier does not open, and why. Each is a decision,
 * not an omission: the reason is what would have to be built to scan it.
 */
export const UNSCANNED: Record<string, string> = {
  "features/ai/components/ComparisonPicker.tsx":
    "Opens from the Ask IRIS composer and searches Records as you type; it needs the search mock and a draft question first.",
  "features/records/paper-view/EmbargoCard.tsx":
    "Its dialogs set and release an embargo, which only the Adviser or RDCO may do on a submitted Record: a fixture with the embargo capabilities and an embargo state.",
  "features/records/paper-view/FilesSection.tsx":
    "Its dialogs replace a manuscript and remove a file: a Record the reader owns with files attached and the upload slots mocked.",
  "components/compliance/DpaConsentModal.tsx":
    "Not rendered by any screen: only `components/compliance/index.ts` imports it. There is nothing to open; when a screen mounts it, give it a case here.",
  "features/records/paper-view/PaperChatDock.tsx":
    "Paper Chat's modal form needs the dock opened on a Record with an indexed paper and a mocked conversation stream (SSE), which the smoke tier's JSON mock cannot answer yet.",
  "features/records/paper-view/ReviewDetails.tsx":
    "A name card that opens over a reviewer or party in the review sidebar; it needs a tracker with parties and reviews, a fixture of its own.",
  "features/records/paper-view/ReviewWorkspaceLayout.tsx":
    "The review workspace's details drawer, which opens only when the workspace is too narrow for its three columns and a tracker is drawn; the Details tab is covered by the add-a-colleague and request-a-review cases, the drawer itself is not.",
};

