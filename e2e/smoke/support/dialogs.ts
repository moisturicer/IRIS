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
import type { Locator, Page, Route } from "@playwright/test";
import type { MockApi } from "./mock-api";
import { PAPER, PAPER_DETAIL, paginated, type SmokeRole } from "./fixtures";
import { ADVISERS_TEMPLATES, GUIDELINES, OPPORTUNITY } from "./screens";

export interface DialogCase {
  id: string;
  /** The screen in screens.ts it opens from. */
  screen: string;
  /** Opens that address instead of the screen's own. */
  path?: string;
  /** Source files (relative to frontend/src) this case puts on screen. */
  sources: string[];
  /** Override the screen's usual reader when a capability is role-gated. */
  role?: SmokeRole;
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

/**
 * Choose an item from a user row's "⋯" menu (IR-1077). Rows offer different
 * items, so each menu is opened in turn until one has the item.
 */
const fromRowMenu = (name: string | RegExp) => async (page: Page) => {
  const triggers = page.getByRole("button", { name: /^Actions for /, exact: false });
  await triggers.first().waitFor();
  const count = await triggers.count();
  for (let i = 0; i < count; i++) {
    await triggers.nth(i).click();
    const item = page.getByRole("menuitem", { name, exact: typeof name === "string" }).first();
    if (await item.isVisible()) {
      await item.click();
      return;
    }
    await page.keyboard.press("Escape");
  }
  throw new Error(`No row menu offers ${String(name)}`);
};

/** A Record under review that the signed-in reader may act on, with the given actions on offer. */
const reviewing = (...capabilities: string[]) => (api: MockApi) =>
  api.on("GET", `/records/${PAPER.id}/`, {
    ...PAPER_DETAIL, is_participant: true, workflow_state: "under_review", workflow_state_label: "Under review",
    stage_label: "Under review", capabilities: ["cite", ...capabilities], can_request_document: ["itso"],
  });
/** A 1x1 PNG: enough for the photo field to accept a file and open its crop dialog. */
const PNG = Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==", "base64");

/**
 * A Proposal draft resumed with everything filled (IR-973), so Publish opens on
 * Review, and its Edit documents shows step 3. Its Adviser shares Templates,
 * with long names throughout.
 */
const DRAFT_ID = 91;
const publishDraft = (api: MockApi) => {
  api.on("GET", "/records/record-types/", paginated(GUIDELINES.map(({ id, name }) => ({ id, name }))));
  api.on("GET", "/users/advisers/", paginated([{
    id: 40, email: "maria.santiago@cit.edu", first_name: "Maria Concepcion", middle_initial: "", last_name: "Villanueva-Dela Cruz Santiago",
    role_name: "Adviser", department_name: "Computer Science",
  }]));
  api.on("GET", `/records/${DRAFT_ID}/`, {
    ...PAPER_DETAIL, id: DRAFT_ID, title: "Clearance-aware resubmission in a university research office",
    abstract: "An abstract that is comfortably longer than the thirty-character minimum the form asks for.",
    abstract_file: `/api/v1/records/${DRAFT_ID}/manuscript/`, record_type: "Proposal", record_type_name: "Proposal",
    adviser: 40, year_accomplished: 2026, pipeline_status: "draft", workflow_state: "draft", current_holders: [],
    authors: [{ id: 1, name: "Sam Student", role: null }], added_by: 1, embargo: { state: "active", until: null },
  });
  api.on("GET", `/records/${DRAFT_ID}/duplicate-matches/`, { exact: [], likely: [], acknowledged: false });
  api.on("GET", `/records/${DRAFT_ID}/metadata-suggestions/`, { state: "ready", suggestions: { title: null, abstract: null }, source: "pdf_structure" });
  api.on("GET", "/documents/guidelines/", GUIDELINES);
  api.on("GET", "/documents/adviser-templates/", ADVISERS_TEMPLATES.map((t) => ({ ...t, shared_by: { ...t.shared_by, id: 40 } })));
  api.on("GET", `/documents/records/${DRAFT_ID}/slots/`, [
    {
      id: 11, name: "Thesis Revision Form", record_type: 1, is_required: true, description: "", position: 1,
      template_name: "thesis-revision-form.pdf", hidden: false,
      uploads: [{
        id: 600, record: DRAFT_ID, slot: 11, slot_name: "Thesis Revision Form", file: "uploads/revision.pdf", version: 1,
        status: null, status_name: null, uploaded_by: 1, uploaded_by_name: "Samantha Student-Villanueva",
        created_at: "2026-11-19T02:00:00Z", reviews: [], delete_refused: null,
      }],
    },
    {
      id: 12, name: "Patent Search Report", record_type: 1, is_required: false, description: "", position: 2,
      template_name: "", hidden: false, uploads: [],
    },
  ]);
};
const publishDocuments = (id: string, viewport?: { width: number; height: number }): DialogCase => ({
  id, screen: "discover", path: `/?publish=${DRAFT_ID}`, viewport,
  sources: ["features/publish/PublishDialog.tsx"],
  override: publishDraft,
  open: async (page) => {
    await page.getByRole("button", { name: "Edit documents" }).click();
    await page.getByRole("list", { name: "Documents" }).waitFor();
  },
  dialog: (page) => page.getByRole("dialog", { name: "Publish your research" }),
});

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
        authors_line: "Ada Lovelace · v1", clearance_strip: [],
        status: kind === "pool" ? { kind: "unassigned", text: "Unassigned" } : { kind: "due", text: "Due in 2 days" },
        actions: kind === "pool" ? ["assign", "extend"] : ["reassign", "withdraw", "extend"],
        // What the reviewer leaves, so Reassign and Withdraw are scanned with their warning (IR-1226).
        unresolved: kind === "seat" ? { drafts: 1, open_threads: 1, document_requests: 1, revision_requests: 0 } : null,
        withdraw_completes_office: kind === "seat" ? true : null,
      }],
      load: [{ reviewer: 5, name: "Ines Tan", open_count: 1, overdue: 0 }, { reviewer: 6, name: "Rey Cruz", open_count: 0, overdue: 0 }],
    });
    api.on("GET", "/assignments/7/assign/", { assignment: 7, party: "rdco", party_label: "RDCO", members: [{ id: 5, name: "Ines Tan", seated: false }] });
  },
  // Assign is the row's own button; Reassign and Extend sit in its "More actions" menu (IR-1136).
  open: async (page) => {
    if (kind === "pool") {
      await page.getByRole("button", { name: new RegExp(`^${button}`) }).first().click();
      return;
    }
    await page.getByRole("button", { name: /^More actions/ }).first().click();
    await page.getByRole("menuitem", { name: new RegExp(`^${button}`) }).first().click();
  },
  dialog: anyDialog,
});
const reviewAction = (
  id: string, capability: string, label: string, source: string, more?: (api: MockApi) => void,
  /** The reviewer's sidebar is a "Details" tab when the workspace is narrow, so a control that lives there opens it first. */
  inDetails = false,
): DialogCase => ({
  // The bar hosts every review action's dialog. The workspace no longer
  // draws one of its own: the documents drawer became a tab (IR-1203).
  id, screen: "paper-view", path: `/records/${PAPER.id}?section=review`,
  sources: [source, "features/records/paper-view/ReviewActionBar.tsx"],
  viewport: inDetails ? { width: 820, height: 900 } : undefined,
  override: (api) => { reviewing(capability)(api); api.on("GET", `/records/${PAPER.id}/tracker/`, TRACKER); more?.(api); },
  open: async (page) => {
    if (inDetails) await page.getByRole("tab", { name: "Details" }).click();
    // The footer shows one secondary and one primary action; the rest sit in its "More review actions" menu.
    const onBar = page.getByRole("button", { name: label, exact: true });
    if (await onBar.count() === 0) {
      await page.getByRole("button", { name: "More review actions" }).click();
      await page.getByRole("menuitem", { name: label, exact: true }).click();
      return;
    }
    await press(label)(page);
  },
  dialog: anyDialog,
});

export const DIALOGS: DialogCase[] = [
  {
    id: "report a paper comment", screen: "paper-view",
    sources: ["features/records/paper-view/CommentsSection.tsx"],
    override: (api) => api.on("GET", `/records/${PAPER.id}/comments/`, {
      comments: [{
        id: 7, author_name: "Sam Student", body: "A public comment.", created_at: "2026-11-04T08:00:00Z",
        edited_at: null, is_author: false, can_edit: false, can_report: true, reply_to: null, deletion_kind: null,
      }],
      count: 1,
    }),
    open: async (page) => {
      await page.getByRole("button", { name: "More actions for Sam Student's comment" }).click();
      await page.getByRole("button", { name: "Report", exact: true }).click();
    },
    dialog: (page) => page.getByRole("dialog", { name: "Report comment" }),
  },
  {
    id: "delete a paper comment", screen: "paper-view",
    sources: ["features/records/paper-view/CommentsSection.tsx"],
    override: (api) => api.on("GET", `/records/${PAPER.id}/comments/`, {
      comments: [{
        id: 7, author_name: "Sam Student", body: "A public comment.", created_at: "2026-11-04T08:00:00Z",
        edited_at: null, is_author: true, can_edit: true, can_report: false, reply_to: null, deletion_kind: null,
      }],
      count: 1,
    }),
    open: async (page) => {
      await page.getByRole("button", { name: "More actions for Sam Student's comment" }).click();
      await page.getByRole("button", { name: "Delete", exact: true }).click();
    },
    dialog: (page) => page.getByRole("dialog", { name: "Delete this comment?" }),
  },
  {
    id: "cite a paper", screen: "paper-view", sources: ["features/discover/PaperCiteModal.tsx", "components/ui/Modal.tsx"],
    open: press(/Cite/), dialog: anyDialog,
  },
  {
    id: "publish", screen: "discover", sources: ["features/publish/PublishDialog.tsx"],
    override: (api) => api.on("GET", "/users/advisers/", paginated([])),
    open: press("Publish"), dialog: anyDialog,
  },
  // IR-973: Publish's Documents step, as wide as a laptop and as narrow as 320 px.
  publishDocuments("publish documents step"),
  publishDocuments("publish documents step at 320 px", { width: 320, height: 800 }),
  {
    id: "discover filters", screen: "discover", sources: ["features/discover/DiscoverFilterBar.tsx"],
    open: press(/^Filters/), dialog: (page) => page.getByRole("dialog", { name: "Filters" }),
  },
  {
    id: "notifications", screen: "help", sources: ["components/layout/NotificationBell.tsx"],
    // The bell is the phone bar's since IR-1288; from md the sidebar has a link instead.
    viewport: { width: 390, height: 844 },
    open: press(/^Notifications/), dialog: (page) => page.getByRole("dialog", { name: "Notifications" }),
  },
  {
    id: "post a call", screen: "opportunities", sources: ["features/opportunities/OpportunityFormDialog.tsx", "features/opportunities/CallsAndConferencesPage.tsx"],
    override: (api) => {
      api.on("GET", "/opportunities/", { count: 0, next: null, previous: null, results: [], can_post: true, can_review_requests: false });
      // The form's Areas (IR-760), so the scan sees the checkboxes, not a load error.
      api.on("GET", "/records/classifications/", paginated([{ id: 1, name: "Agriculture" }]));
    },
    open: press("Post a call"), dialog: anyDialog,
  },
  {
    // RDCO removes an Adviser's Call with a reason (IR-765).
    id: "remove an Adviser's call", screen: "opportunities", role: "RDCO",
    sources: ["features/opportunities/CallsAndConferencesPage.tsx", "features/admin/RdcoNoteDialog.tsx"],
    override: (api) => {
      api.on("GET", "/opportunities/", {
        count: 1, next: null, previous: null, can_post: true, can_review_requests: true,
        results: [{ ...OPPORTUNITY, posted_by_name: "Ana Reyes", can_edit: true, can_remove: true, can_feature: true }],
      });
      // The board's screen signs in a Student; RDCO's sidebar also reads its queues.
      api.on("GET", "/dashboard/queue-counts/", { download_requests: 0, delete_requests: 0, role_change_requests: 0, reported_comments: 0 });
    },
    open: press(/^Remove /), dialog: anyDialog,
  },
  {
    id: "confirm a call request", screen: "call-requests",
    sources: ["features/opportunities/CallRequestsPage.tsx", "components/shared/ConfirmDialog.tsx"],
    open: press(/^Confirm /), dialog: anyDialog,
  },
  {
    id: "reject a call request", screen: "call-requests",
    sources: ["features/opportunities/CallRequestsPage.tsx", "features/admin/RdcoNoteDialog.tsx"],
    open: press(/^Reject /), dialog: anyDialog,
  },
  {
    id: "edit and resend my call", screen: "my-calls",
    sources: ["features/opportunities/MyCallsPage.tsx", "features/opportunities/OpportunityFormDialog.tsx"],
    open: press(/^Edit and send again/), dialog: anyDialog,
  },
  {
    id: "delete my call", screen: "my-calls",
    sources: ["features/opportunities/MyCallsPage.tsx", "components/shared/ConfirmDialog.tsx"],
    open: press(/^Delete /), dialog: anyDialog,
  },
  {
    id: "change a user's role", screen: "rdco-users", sources: ["features/accounts/UserListPage.tsx"],
    open: fromRowMenu("Change role"), dialog: anyDialog,
  },
  {
    id: "make or remove a coordinator", screen: "admin-users", sources: ["features/accounts/UserListPage.tsx", "components/shared/ConfirmDialog.tsx"],
    open: fromRowMenu(/coordinator$/), dialog: anyDialog,
  },
  {
    id: "remove a requirement", screen: "rdco-setup", sources: ["features/setup/SetupPage.tsx", "components/shared/ConfirmDialog.tsx"],
    open: async (page) => { await page.getByRole("button", { name: "Remove Publication / Conference Presentation / Both" }).click(); },
    dialog: anyDialog,
  },
  {
    id: "remove one of my Templates", screen: "my-templates",
    sources: ["features/myTemplates/MyTemplatesPage.tsx", "components/shared/ConfirmDialog.tsx"],
    open: async (page) => { await page.getByRole("button", { name: "Remove Budget sheet" }).click(); },
    dialog: anyDialog,
  },
  {
    id: "lock or unlock an account", screen: "rdco-users", sources: ["features/accounts/UserListPage.tsx", "components/shared/ConfirmDialog.tsx"],
    open: fromRowMenu(/^(Lock|Unlock)/), dialog: anyDialog,
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
    id: "reject an account deletion request", screen: "account-deletion-requests",
    sources: ["features/admin/AccountDeletionRequestsPage.tsx"],
    open: press("Reject"), dialog: anyDialog,
  },
  {
    id: "confirm an account deletion", screen: "account-deletion-requests",
    sources: ["features/admin/AccountDeletionRequestsPage.tsx", "components/shared/ConfirmDialog.tsx"],
    open: press("Confirm deletion"), dialog: anyDialog,
  },
  {
    id: "confirm a retention period that erases data", screen: "retention",
    sources: ["features/admin/RetentionPage.tsx", "components/shared/ConfirmDialog.tsx"],
    override: (api) => api.on("GET", "/settings/retention.download_notes_days/erasure-preview/",
      { key: "retention.download_notes_days", days: 30, count: 12 }),
    open: async (page) => {
      await page.getByRole("textbox", { name: /Period in days/ }).fill("30");
      await press("Save period")(page);
    },
    dialog: (page) => page.getByRole("dialog", { name: "Erase existing data?" }),
  },
  {
    id: "publish a new notice version", screen: "rdco-setup-notice",
    sources: ["features/setup/NoticeSection.tsx", "components/shared/ConfirmDialog.tsx"],
    override: (api) => api.on("GET", "/auth/notice/versions/impact/", { current_version: 1, accounts_to_answer: 41 }),
    open: async (page) => {
      await page.getByRole("textbox", { name: "Notice text" }).fill("IRIS data notice, version two");
      await press("Publish version 2")(page);
    },
    dialog: (page) => page.getByRole("dialog", { name: "Publish version 2?" }),
  },
  {
    id: "decline a download request", screen: "download-requests", sources: ["features/admin/RdcoNoteDialog.tsx"],
    open: press("Decline"), dialog: anyDialog,
  },
  {
    // The same dialog, opened from the other queue (IR-1099); its copy differs.
    id: "decline a delete request", screen: "delete-requests", sources: ["features/admin/RdcoNoteDialog.tsx"],
    open: press("Decline"), dialog: anyDialog,
  },
  {
    // The approvals ask in ConfirmDialog (IR-1028), naming the paper and the person.
    id: "approve a download request", screen: "download-requests",
    sources: ["features/admin/DownloadRequestsPage.tsx", "components/shared/ConfirmDialog.tsx"],
    open: press("Approve"), dialog: anyDialog,
  },
  {
    id: "approve a delete request", screen: "delete-requests",
    sources: ["features/admin/DeleteRequestsPage.tsx", "components/shared/ConfirmDialog.tsx"],
    open: press("Approve Deletion"), dialog: anyDialog,
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
    // A failed sign-in is said in a dialog in front of the form (IR-1303).
    id: "sign-in failed", screen: "login", sources: ["components/auth/EntryErrorDialog.tsx"],
    override: (api) => api.on("POST", "/auth/login/", { detail: "Invalid credentials." }, 401),
    open: async (page) => {
      await page.getByLabel("Email Address").fill("student@cit.edu");
      await page.getByLabel("Password", { exact: true }).fill("not-the-password");
      await page.getByRole("button", { name: "Sign In" }).click();
    },
    dialog: (page) => page.getByRole("alertdialog", { name: "Invalid email or password" }),
  },
  {
    // Why the session ended opens by itself on arrival (IR-1197).
    id: "session ended on arrival at sign-in", screen: "login", path: "/login?reason=session_expired&code=session_idle",
    sources: ["components/auth/SessionNoticeDialog.tsx"],
    open: async () => {},
    dialog: (page) => page.getByRole("dialog", { name: "Session Expired" }),
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
    id: "delete a draft", screen: "my-library", path: "/records/mine?section=research",
    sources: ["features/library/DeleteDraft.tsx"],
    override: (api) => api.on("GET", "/records/mine/", [{
      id: 12, title: "Community Water Monitoring", authors: [{ id: 1, name: "Lee Cruz", role: null }],
      adviser_name: "Dr Santos", record_type_name: "Thesis / Research", pipeline_status: "draft",
      workflow_state: "draft", workflow_state_label: "Draft", holders: [], cleared_offices: [],
      submitter_status: { line: "Draft: not yet submitted", waiting_on_you: [] },
      created_at: "2026-11-01T08:00:00+08:00", updated_at: "2026-11-02T08:00:00+08:00",
    }]),
    open: press(/^Delete draft/), dialog: anyDialog,
  },
  {
    id: "crop a profile photo", screen: "profile-settings", sources: ["features/profile/PhotoCropDialog.tsx"],
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
  // RDCO's three acts on a paper in review (ADR-051 §10, IR-798), one dialog each.
  ...([
    ["replace a paper's adviser", "Replace Adviser"],
    ["add an owner to a paper", "Add owner"],
    ["withdraw a paper in review", "Withdraw paper"],
  ] as const).map(([id, button]): DialogCase => ({
    id, screen: "paper-view", sources: ["features/records/paper-view/RdcoPaperControls.tsx"],
    override: (api) => {
      api.on("GET", `/records/${PAPER.id}/`, {
        ...PAPER_DETAIL, pipeline_status: "in_review", workflow_state: "under_review",
        workflow_state_label: "Under review", stage_label: "Under review",
        capabilities: ["cite", "replace_adviser", "add_owner", "withdraw_paper"],
      });
      api.on("GET", "/users/advisers/", paginated([]));
    },
    open: press(button), dialog: anyDialog,
  })),
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
    // IR-1233: the one pane toggle, "Show conversations", opens this dialog at 640px and below.
    open: press("Show conversations"), dialog: (page) => page.getByRole("dialog", { name: "Conversations" }),
  },
  consoleAction("assign a reviewer", "Assign", "pool", "features/review/AssignReviewerDialog.tsx"),
  consoleAction("reassign a reviewer", "Reassign", "seat", "features/review/ReassignDialog.tsx"),
  consoleAction("withdraw a reviewer", "Withdraw", "seat", "features/review/WithdrawSeatDialog.tsx"),
  consoleAction("extend a due date", "Extend due date", "seat", "features/review/ExtendDueDateDialog.tsx"),
  reviewAction("accept and publish a paper", "accept_publish", "Accept & publish…", "features/records/paper-view/DecisionDialog.tsx"),
  reviewAction("reject a paper", "reject", "Reject…", "features/records/paper-view/DecisionDialog.tsx"),
  // Finish review (IR-875): the footer's one way to finish where `finish_review` is granted.
  reviewAction("finish a review", "finish_review", "Finish review…", "features/records/paper-view/threads/FinishReviewDialog.tsx"),
  // The guided tour (IR-997): a non-modal dialog opened from the pane header's Take a tour.
  reviewAction("take the review workspace tour", "comment_review", "Take a tour", "features/records/paper-view/tour/GuidedTour.tsx"),
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
  {
    // Saved replies (IR-877): managed from the menu under the Conversation tab's comment box.
    id: "manage saved replies", screen: "paper-view", path: `/records/${PAPER.id}?section=review`,
    sources: ["features/records/paper-view/SavedReplies.tsx"],
    override: (api) => {
      reviewing("comment_review")(api);
      api.on("GET", `/records/${PAPER.id}/tracker/`, TRACKER);
      api.on("GET", "/reviews/saved-replies/", {
        results: [{ id: 1, title: "Cite the source", body: "Please cite where this comes from.",
          created_at: "2026-11-01T08:00:00+08:00", updated_at: "2026-11-01T08:00:00+08:00" }],
        limit: 50,
      });
    },
    open: async (page) => {
      // A reviewer's Review opens on Documents (IR-1203): the comment box is the Conversation tab's.
      await page.getByRole("tab", { name: "Conversation" }).click();
      await page.getByRole("button", { name: "Saved replies" }).first().click();
      await page.getByRole("button", { name: "Manage saved replies" }).click();
    },
    dialog: anyDialog,
  },
  {
    // Paper Chat on the AI runtime (IR-957): the modal form opens on the paper with no chat yet.
    id: "paper chat in its modal form", screen: "paper-view", path: `/records/${PAPER.id}`,
    // At tablet width the new icon rail leaves enough workspace for Ask IRIS
    // to sit beside the page. Keep this modal case below the reading split.
    viewport: { width: 600, height: 900 }, sources: ["features/records/paper-view/PaperChatDock.tsx"],
    override: (api) => {
      api.on("GET", "/ai/runtime/conversations", { protocol: "runs-reader-1", conversations: [] });
    },
    open: async (page) => { await page.getByRole("button", { name: "Ask IRIS" }).click(); },
    dialog: (page) => page.getByRole("dialog", { name: "Ask IRIS" }),
  },
  {
    id: "reviewer name card", screen: "paper-view", path: `/records/${PAPER.id}?section=review`,
    sources: ["features/records/paper-view/ReviewDetails.tsx"],
    override: (api) => {
      reviewing()(api);
      api.on("GET", `/records/${PAPER.id}/tracker/`, {
        ...TRACKER,
        parties: [{
          party: "itso", label: "ITSO", state: "active", state_label: "Reviewing", started: true,
          outcome: null, outcome_label: null, at: null, preserved: false, carryover: null, carryover_version: null,
          carryover_label: null, awaiting_document: null, outcome_earlier: false, in_pool: false,
          changes_requested: false, seats: [{ reviewer: 5, reviewer_name: "Ines Tan", state: "in_review", state_label: "In review", verdict: null, verdict_label: null }],
          due_at: null, original_due_at: null, is_overdue: false, clock_paused: false, can_extend: false, extensions: [],
        }],
      });
    },
    open: async (page) => {
      await page.getByRole("tab", { name: "Details" }).click();
      await page.getByRole("button", { name: "Ines Tan" }).click();
    },
    dialog: (page) => page.getByRole("dialog", { name: "Ines Tan" }),
  },
  {
    id: "review workspace details drawer", screen: "paper-view", path: `/records/${PAPER.id}?section=review`,
    viewport: { width: 820, height: 900 }, sources: ["features/records/paper-view/ReviewWorkspaceLayout.tsx"],
    override: (api) => {
      reviewing()(api);
      api.on("GET", `/records/${PAPER.id}/`, { ...PAPER_DETAIL, is_participant: true, abstract_file: "/media/manuscript.pdf" });
      api.on("GET", `/records/${PAPER.id}/tracker/`, TRACKER);
      api.on("GET", `/records/${PAPER.id}/manuscript/`, (route: Route) => route.fulfill({
        status: 200, headers: { "content-type": "application/pdf" }, body: Buffer.from("%PDF-1.4\n%%EOF"),
      }));
    },
    open: async (page) => { await page.getByRole("button", { name: "Open review pane" }).click(); },
    dialog: (page) => page.getByRole("dialog", { name: "Review pane" }),
  },
  ...(["set", "release", "release_ip"] as const).map((action): DialogCase => ({
    id: action === "set" ? "change embargo review date" : action === "release" ? "release embargo" : "release IP mark",
    screen: "paper-view", role: "RDCO", sources: ["features/records/paper-view/EmbargoCard.tsx"],
    override: (api) => {
      api.on("GET", `/records/${PAPER.id}/`, {
        ...PAPER_DETAIL, is_ip: action === "release_ip", embargo: { state: "held", until: "2026-12-01" },
        capabilities: ["cite", "set_embargo", "release_embargo", ...(action === "release_ip" ? ["release_ip"] : [])],
      });
      api.on("GET", "/dashboard/queue-counts/", { download_requests: 0, delete_requests: 0, role_change_requests: 0 });
    },
    open: async (page) => {
      const label = action === "set" ? "Change date" : action === "release" ? "Release embargo" : "Release IP mark";
      await page.getByRole("button", { name: label }).click();
    },
    dialog: anyDialog,
  })),
  {
    id: "remove an attached file", screen: "paper-view", role: "Student",
    path: `/records/${PAPER.id}?section=review&documents=open`,
    sources: ["features/records/paper-view/DocumentsTab.tsx"],
    override: (api) => {
      api.on("GET", `/records/${PAPER.id}/`, {
        ...PAPER_DETAIL, owners: [{ id: 1, user: 1, email: "student@cit.edu", full_name: "Sam Student", is_primary: true }],
        capabilities: ["cite", "edit_details"],
      });
      api.on("GET", `/documents/records/${PAPER.id}/slots/`, [{ id: 2, name: "Ethics clearance", uploads: [] }]);
      api.on("GET", "/documents/files/", [{
        id: 7, record: PAPER.id, file: "ethics.pdf", filename: "Ethics clearance.pdf", uploaded_by: 1,
        uploaded_by_name: "Sam Student", created_at: "2026-11-04T08:00:00+08:00", can_remove: true,
      }]);
      api.on("GET", `/records/${PAPER.id}/document-requests/`, []);
      api.on("GET", `/records/${PAPER.id}/tracker/`, TRACKER);
    },
    open: async (page) => { await page.getByRole("button", { name: "Remove Ethics clearance.pdf" }).click(); },
    dialog: (page) => page.getByRole("dialog", { name: "Remove Ethics clearance.pdf?" }),
  },
];

/**
 * Dialog source files this tier does not open, and why. Each is a decision,
 * not an omission: the reason is what would have to be built to scan it.
 */
export const UNSCANNED: Record<string, string> = {
  "features/admin/SessionsPage.tsx":
    "SessionsPage has no route, so no smoke screen reaches its revoke dialog (IR-1028); the dialog is axe-checked in SessionsPage.test.tsx. It becomes a case here if the page is routed, and goes if the dead-code ticket removes it.",
  "features/records/paper-view/NotesPanel.tsx":
    "Notes is a reader panel that becomes a dialog only after an authenticated reader opens it; its focused editor is covered by NotesPanel tests.",
};

