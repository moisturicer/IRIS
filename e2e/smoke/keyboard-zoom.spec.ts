// IR-909: keyboard-only paths through the core journeys and their narrow-layout
// equivalent at 400% zoom (1280 CSS px / 4 = 320 CSS px).
import type { Locator, Page, Route } from "@playwright/test";
import { expect, test } from "./support/mock-api";
import { account, mockShell, PAPER, PAPER_DETAIL, paginated, RUNTIME_CONVERSATION, RUNTIME_CONVERSATION_ID, RUNTIME_CONVERSATION_PATH, signedIn, type SmokeRole } from "./support/fixtures";
import { openScreen } from "./support/open-screen";
import { DIALOGS, type DialogCase } from "./support/dialogs";
import { SCREENS } from "./support/screens";
import type { MockApi } from "./support/mock-api";
import { checkReachable, measureOverflow } from "../support/viewport";
import { manuscriptPdf } from "../support/pdf";

const QUESTION = "What soil sensors were tested?";
const COMPOSER = "Ask about the research corpus";
const TAB_STOPS = "a[href], button:not(:disabled), input:not([type=hidden]):not(:disabled), select:not(:disabled), textarea:not(:disabled), [tabindex]:not([tabindex='-1'])";

const screen = (id: string) => {
  const result = SCREENS.find((entry) => entry.id === id);
  if (!result) throw new Error(`Missing smoke screen ${id}`);
  return result;
};

const dialogCase = (id: string): DialogCase => {
  const result = DIALOGS.find((entry) => entry.id === id);
  if (!result) throw new Error(`Missing dialog fixture ${id}`);
  return result;
};

/** Move to a control with physical Tab presses; fail when it cannot be reached. */
async function tabTo(page: Page, target: Locator, limit = 160) {
  for (let i = 0; i < limit; i += 1) {
    if (await target.evaluate((element) => element === document.activeElement).catch(() => false)) return;
    await page.keyboard.press("Tab");
  }
  throw new Error(`Keyboard could not reach ${await target.first().getAttribute("aria-label") ?? await target.first().innerText().catch(() => "the requested control")}`);
}

/** The focused control must show a browser-visible focus indicator. */
async function expectVisibleFocus(target: Locator) {
  await expect(target).toBeFocused();
  const hasIndicator = await target.evaluate((element) => {
    if (!element.matches(":focus-visible")) return false;
    for (let node: Element | null = element; node && node !== document.body; node = node.parentElement) {
      const style = getComputedStyle(node);
      const outline = Number.parseFloat(style.outlineWidth) > 0 && style.outlineStyle !== "none";
      const shadow = style.boxShadow !== "none";
      if (outline || shadow) return true;
    }
    return false;
  });
  expect(hasIndicator, "keyboard focus has a visible outline or ring").toBe(true);
}

async function tabStops(dialog: Locator) {
  const candidates = dialog.locator(TAB_STOPS);
  const visible: Locator[] = [];
  for (const candidate of await candidates.all()) {
    if (await candidate.isVisible() && await candidate.isEnabled()) visible.push(candidate);
  }
  return visible;
}

/** Check both ends of the Tab trap, then Escape and focus restoration. */
async function expectDialogKeyboardContract(page: Page, dialog: Locator, opener: Locator) {
  await expect(dialog).toBeVisible();
  const stops = await tabStops(dialog);
  expect(stops.length, "dialog contains keyboard stops").toBeGreaterThan(1);

  await tabTo(page, stops[stops.length - 1]);
  await page.keyboard.press("Tab");
  await expect(stops[0]).toBeFocused();
  await page.keyboard.press("Shift+Tab");
  await expect(stops[stops.length - 1]).toBeFocused();

  await page.keyboard.press("Escape");
  await expect(dialog).toHaveCount(0);
  await expectVisibleFocus(opener);
}

function draftDetail(overrides: Record<string, unknown> = {}) {
  return {
    ...PAPER_DETAIL,
    id: 42,
    title: "Clearance-aware resubmission in a research office",
    abstract: "An abstract that is comfortably longer than the thirty-character minimum.",
    abstract_file: "/api/v1/records/42/manuscript/",
    year_accomplished: new Date().getFullYear(),
    record_type: "Thesis / Research",
    classification: "Agriculture",
    adviser: 21,
    authors: [{ id: 1, name: "Sam Student", role: null }],
    owners: [{ id: 1, user: 1, email: "student@cit.edu", is_primary: true }],
    keywords: [],
    pipeline_status: "draft",
    workflow_state: "draft",
    workflow_state_label: "Draft",
    stage_label: "Draft",
    details_revision: 1,
    current_holders: [],
    capabilities: ["cite"],
    ...overrides,
  };
}

function mockReadyDraft(api: MockApi, initialDraft = draftDetail()) {
  mockShell(api);
  api.on("GET", "/users/role-requests/", paginated([]));
  api.on("GET", "/users/advisers/", paginated([{
    id: 21, first_name: "Maria", middle_initial: "C.", last_name: "Santos", role_name: "Adviser",
  }]));
  let actor: SmokeRole = "Student";
  let state: "draft" | "submitted" | "reviewing" | "revision_requested" | "resubmitted" = "draft";
  api.on("GET", "/users/me/", account(actor));
  api.on("GET", "/records/42/", (route: Route) => {
    if (state === "draft") return route.fulfill({ json: initialDraft });
    const inReview = state === "reviewing";
    const revisionRequested = state === "revision_requested";
    const detail = {
      ...PAPER_DETAIL,
      id: 42,
      pipeline_status: state === "submitted" ? "submitted" : "in_review",
      workflow_state: inReview ? "under_review" : revisionRequested ? "revision_requested" : state,
      workflow_state_label: inReview ? "Under review" : revisionRequested ? "Revision requested" : state,
      stage_label: inReview ? "Under review" : revisionRequested ? "Revision requested" : state,
      is_participant: true,
      owners: [{ id: 1, user: 1, email: "student@cit.edu", full_name: "Sam Student", is_primary: true }],
      capabilities: inReview ? ["cite", "request_revision"] : revisionRequested ? ["cite", "create_version"] : ["cite"],
      revision: inReview
        ? { ...PAPER_DETAIL.revision, party: "itso", label: "ITSO", open: [], new_version: null }
        : revisionRequested
          ? {
              ...PAPER_DETAIL.revision,
              party: "itso",
              label: "ITSO",
              open: [{ id: 1, party: "itso", label: "ITSO", reason: "Please add the ethics clearance.", requested_by: "Ines Tan", version: 1, created_at: "2026-11-04T08:00:00+08:00" }],
              new_version: { number: 2, rereview: ["ITSO"], kept: ["IERC"], blocked: null },
            }
          : PAPER_DETAIL.revision,
    };
    return route.fulfill({ json: detail });
  });
  api.on("GET", "/records/42/tracker/", (route: Route) => route.fulfill({ json: {
    record_id: 42, record_type: "Thesis / Research", workflow_state: state, workflow_state_label: state,
    current_holders: [], parties: [], routing_history: [], routing_recorded_from: null,
    reviews: [], versions: [], review_comments: [], resubmissions: [], document_requests: [], clearances: [],
  } }));
  api.on("GET", "/records/42/document-requests/", []);
  api.on("GET", "/records/42/review-comments/", []);
  api.on("GET", "/records/42/response-letters/", []);
  api.on("GET", "/library/highlights/42/", { results: [] });
  api.on("POST", "/records/42/submit/", (route: Route) => {
    state = "submitted";
    return route.fulfill({ json: { detail: "Submitted." } });
  });
  api.on("POST", "/records/42/request-revision/", (route: Route) => {
    state = "revision_requested";
    return route.fulfill({ json: { record_id: 42 } });
  });
  api.on("POST", "/records/42/new-version/", (route: Route) => {
    state = "resubmitted";
    return route.fulfill({ json: { record_id: 42 } });
  });
  api.on("GET", "/records/42/metadata-suggestions/", {
    state: "ready", suggestions: { title: null, abstract: null }, source: "pdf_structure",
  });
  api.on("GET", "/records/42/manuscript/", (route: Route) => route.fulfill({
    status: 200, headers: { "content-type": "application/pdf" }, body: manuscriptPdf("Zoom fixture"),
  }));
  api.on("GET", "/records/42/duplicate-matches/", { exact: [], likely: [], acknowledged: false });
  api.on("POST", "/records/42/increment_access/", {});
  api.on("GET", "/ai/records/42/overview/", { state: "not_indexed", overview: null });
  api.on("GET", "/records/42/similar/", { results: [] });
  return {
    setActor(role: SmokeRole) {
      actor = role;
      api.on("GET", "/users/me/", account(role));
    },
    setState(next: typeof state) { state = next; },
  };
}

function mockNewSubmission(api: MockApi) {
  mockShell(api);
  api.on("GET", "/users/role-requests/", paginated([]));
  api.on("GET", "/users/advisers/", paginated([{
    id: 21, first_name: "Maria", middle_initial: "C.", last_name: "Santos", role_name: "Adviser",
    email: "maria@cit.edu", department_name: "Computer Science",
  }]));
  api.on("POST", "/records/", { id: 42, details_revision: 1 });
  api.on("POST", "/records/42/manuscript/", { id: 42 });
  api.on("PATCH", "/records/42/", { id: 42, details_revision: 2 });
  api.on("GET", "/records/42/", (route: Route) => route.fulfill({ json: draftDetail() }));
  api.on("GET", "/records/42/metadata-suggestions/", {
    state: "ready", suggestions: { title: null, abstract: null }, source: "pdf_structure",
  });
  api.on("GET", "/records/42/duplicate-matches/", { exact: [], likely: [], acknowledged: false });
  api.on("GET", "/records/42/manuscript/", (route: Route) => route.fulfill({
    status: 200, headers: { "content-type": "application/pdf" }, body: manuscriptPdf("Keyboard fixture"),
  }));
  api.on("POST", "/records/42/submit/", { detail: "Submitted." });
}

async function openRevisionSurface(page: Page, api: Parameters<typeof mockShell>[0], which: "request a revision" | "submit a new version") {
  const dialog = dialogCase(which);
  const paper = screen("paper-view");
  await openScreen(page, api, { ...paper, path: dialog.path ?? paper.path }, { override: dialog.override });
}

test("Discover opens a paper using Tab and Enter, with visible focus", async ({ page, api }) => {
  await openScreen(page, api, screen("discover"));
  const paperLink = page.getByRole("link", { name: new RegExp(PAPER.title) }).first();
  await tabTo(page, paperLink);
  await expectVisibleFocus(paperLink);
  screen("paper-view").mocks?.(api);
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(new RegExp(`/records/${PAPER.id}$`));
  await expect(page.getByRole("heading", { name: PAPER.title })).toBeVisible();
});

test("Ask IRIS accepts and sends a question from the keyboard", async ({ page, api }) => {
  await openScreen(page, api, screen("ask-iris-conversation"));
  const composer = page.getByRole("textbox", { name: COMPOSER });
  await expect(composer).toBeVisible();
  await tabTo(page, composer);
  await expectVisibleFocus(composer);
  await page.keyboard.type(QUESTION);
  const run = {
    protocol: "runs-reader-1",
    id: "00000000-0000-4000-8000-000000000001",
    conversation_id: RUNTIME_CONVERSATION_ID,
    state: "completed",
    question: QUESTION,
    base_revision: 0,
    version: 3,
    turn_id: "00000000-0000-4000-8000-000000000003",
    depth: "ordinary",
    awaiting_reader: false,
    plan: null,
    context: null,
    compaction: null,
    cursor: 2,
    retry_of: null,
    retried_by: null,
    sources_available: true,
    capabilities: { manual_compaction: false },
  };
  api.on("POST", "/ai/runtime/runs", run, 201);
  api.on("GET", RUNTIME_CONVERSATION_PATH, {
    ...RUNTIME_CONVERSATION,
    revision: 1,
    runs: [run],
    turns: [{
      id: run.turn_id,
      run_id: run.id,
      ordinal: 1,
      question: QUESTION,
      answer: "Capacitive probes were tested in upland rice fields.",
      kind: "answer",
      citations: [],
    }],
  });
  await page.keyboard.press("Enter");
  await expect(page.getByText(QUESTION, { exact: true })).toBeVisible();
  await expect(page.getByText("Capacitive probes were tested in upland rice fields.")).toBeVisible();
});

test("an author submits, a reviewer requests revisions, and the author resubmits by keyboard", async ({ page, api }) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  await signedIn(page, api);
  const workflow = mockReadyDraft(api);
  await page.goto("/?publish=42");
  const submit = page.getByRole("button", { name: "Submit for review" });
  await expect(submit).toBeVisible();
  await tabTo(page, submit);
  await expectVisibleFocus(submit);
  await page.keyboard.press("Enter");
  await expect(page.getByRole("heading", { name: "Submitted for review" })).toBeVisible();

  const openPaper = page.getByRole("link", { name: "Open paper" });
  await expectVisibleFocus(openPaper);
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/\/records\/42$/);

  // Role changes are test setup; the workflow controls themselves stay keyboard-driven.
  workflow.setActor("RDCO");
  workflow.setState("reviewing");
  await page.reload();
  await page.goto("/records/42?section=review");
  const requestRevision = page.getByRole("button", { name: "Request Revision…" });
  await tabTo(page, requestRevision);
  await expectVisibleFocus(requestRevision);
  await page.keyboard.press("Enter");
  const requestDialog = page.getByRole("dialog", { name: "Request Revision" });
  await expectDialogKeyboardContract(page, requestDialog, requestRevision);
  await page.keyboard.press("Enter");
  const reason = requestDialog.getByRole("textbox", { name: "What needs revising?" });
  await tabTo(page, reason);
  await page.keyboard.type("Please add the ethics clearance.");
  const request = requestDialog.getByRole("button", { name: "Request Revision", exact: true });
  await tabTo(page, request);
  await expectVisibleFocus(request);
  await page.keyboard.press("Enter");
  await expect(page.getByText(/Revision requested/).first()).toBeVisible();

  workflow.setActor("Student");
  await page.reload();
  await page.goto("/records/42");
  const newVersion = page.getByRole("button", { name: "Submit new version" });
  await tabTo(page, newVersion);
  await expectVisibleFocus(newVersion);
  await page.keyboard.press("Enter");
  const versionDialog = page.getByRole("dialog", { name: "Submit new version" });
  await expectDialogKeyboardContract(page, versionDialog, newVersion);
  await page.keyboard.press("Enter");
  const resubmit = versionDialog.getByRole("button", { name: "Submit v2" });
  await tabTo(page, resubmit);
  await expectVisibleFocus(resubmit);
  await page.keyboard.press("Enter");
  await expect(page.getByRole("status").filter({ hasText: "v2 submitted. The reviewers who asked for changes have been notified." })).toBeVisible();
});

test("a new submission can be created and sent for review using only the keyboard", async ({ page, api }) => {
  await signedIn(page, api);
  mockNewSubmission(api);
  await page.goto("/?publish=new");

  const dialog = page.getByRole("dialog", { name: "Publish your research" });
  const thesis = page.getByRole("radio", { name: /Thesis \/ Research/ });
  await tabTo(page, thesis);
  await expectVisibleFocus(thesis);
  await page.keyboard.press("Space");

  const upload = page.getByRole("button", { name: /^Upload manuscript/ });
  await tabTo(page, upload);
  await expectVisibleFocus(upload);
  const chooser = page.waitForEvent("filechooser");
  await page.keyboard.press("Enter");
  await (await chooser).setFiles({
    name: "Keyboard_journey_study.pdf",
    mimeType: "application/pdf",
    buffer: manuscriptPdf("Keyboard journey"),
  });
  await expect(dialog.getByRole("status").filter({ hasText: "Keyboard_journey_study.pdf uploaded" })).toBeVisible();

  const continueButton = dialog.getByRole("button", { name: "Continue" });
  await tabTo(page, continueButton);
  await expectVisibleFocus(continueButton);
  await page.keyboard.press("Enter");

  const title = dialog.getByRole("textbox", { name: /^Title/ });
  await tabTo(page, title);
  await page.keyboard.press("Control+A");
  await page.keyboard.type("Keyboard-driven research submission");
  const abstract = dialog.getByRole("textbox", { name: /^Abstract/ });
  await tabTo(page, abstract);
  await page.keyboard.type("A complete research abstract entered using keyboard controls only.");
  const adviser = dialog.getByRole("combobox", { name: /Adviser/ });
  await tabTo(page, adviser);
  await page.keyboard.type("Maria");
  await expect(dialog.getByRole("option", { name: /Maria C\. Santos/ })).toBeVisible();
  await page.keyboard.press("ArrowDown");
  await page.keyboard.press("Enter");
  const detailsContinue = dialog.getByRole("button", { name: "Continue" });
  await tabTo(page, detailsContinue);
  await expectVisibleFocus(detailsContinue);
  await page.keyboard.press("Enter");

  const submit = dialog.getByRole("button", { name: "Submit for review" });
  await tabTo(page, submit);
  await expectVisibleFocus(submit);
  await page.keyboard.press("Enter");
  await expect(page.getByRole("heading", { name: "Submitted for review" })).toBeVisible();
});

test("the Publish dialog traps focus and Escape returns it to its keyboard opener", async ({ page, api }) => {
  await signedIn(page, api);
  mockShell(api);
  api.on("GET", "/users/advisers/", paginated([]));
  await page.goto("/");

  const trigger = page.getByRole("button", { name: "Publish" });
  await tabTo(page, trigger);
  await expectVisibleFocus(trigger);
  await page.keyboard.press("Enter");
  const dialog = page.getByRole("dialog", { name: "Publish your research" });
  await expect(dialog.getByRole("radio", { name: /Thesis \/ Research/ })).toBeVisible();
  await expectDialogKeyboardContract(page, dialog, trigger);
});

const ZOOM_WIDTH = 320;

async function expect400PercentEquivalentReflow(page: Page, primary: Locator) {
  expect(await page.evaluate(() => window.innerWidth)).toBe(ZOOM_WIDTH);
  const report = await measureOverflow(page);
  expect(report.overflow, `document overflow at 320 CSS px: ${report.culprits.join(", ")}`).toBeLessThanOrEqual(0);
  const reachable = await checkReachable(primary);
  expect(reachable.reachable, reachable.reason).toBe(true);
}

test.describe("400% equivalent reflow at 320 CSS pixels", () => {
  test("Discover keeps its paper link visible and reachable", async ({ page, api }) => {
    await page.setViewportSize({ width: ZOOM_WIDTH, height: 900 });
    await openScreen(page, api, screen("discover"));
    const paperLink = page.getByRole("link", { name: new RegExp(PAPER.title) }).first();
    await expect(paperLink).toBeVisible();
    await expect400PercentEquivalentReflow(page, paperLink);
  });

  test("Ask IRIS keeps its composer visible and reachable", async ({ page, api }) => {
    await page.setViewportSize({ width: ZOOM_WIDTH, height: 900 });
    await openScreen(page, api, screen("ask-iris-conversation"));
    const composer = page.getByRole("textbox", { name: COMPOSER });
    await expect(composer).toBeVisible();
    await expect400PercentEquivalentReflow(page, composer);
  });

  test("Submit keeps its final action visible and reachable", async ({ page, api }) => {
    await page.setViewportSize({ width: ZOOM_WIDTH, height: 900 });
    await signedIn(page, api);
    mockReadyDraft(api);
    await page.goto("/?publish=42");
    const submit = page.getByRole("button", { name: "Submit for review" });
    await expect(submit).toBeVisible();
    await expect400PercentEquivalentReflow(page, submit);
  });

  test("Publish keeps its manuscript step visible and reachable", async ({ page, api }) => {
    await page.setViewportSize({ width: ZOOM_WIDTH, height: 900 });
    await signedIn(page, api);
    mockNewSubmission(api);
    await page.goto("/?publish=new");
    const dialog = page.getByRole("dialog", { name: "Publish your research" });
    const thesis = dialog.getByRole("radio", { name: /Thesis \/ Research/ });
    await expect(thesis).toBeVisible();
    await expect400PercentEquivalentReflow(page, thesis);
    await tabTo(page, thesis);
    await page.keyboard.press("Space");
    const upload = dialog.getByRole("button", { name: /^Upload manuscript/ });
    await expect(upload).toBeVisible();
    await expect400PercentEquivalentReflow(page, upload);
  });

  test("Publish keeps its Details step visible and reachable", async ({ page, api }) => {
    await page.setViewportSize({ width: ZOOM_WIDTH, height: 900 });
    await signedIn(page, api);
    mockReadyDraft(api, draftDetail({
      title: "", abstract: "", year_accomplished: null, adviser: null, authors: [],
    }));
    await page.goto("/?publish=42");
    const dialog = page.getByRole("dialog", { name: "Publish your research" });
    const title = dialog.getByRole("textbox", { name: /^Title/ });
    await expect(title).toBeVisible();
    await expect400PercentEquivalentReflow(page, title);
    const detailsContinue = dialog.getByRole("button", { name: "Continue" });
    await expect400PercentEquivalentReflow(page, detailsContinue);
  });

  test("Decide and Resubmit keep their required review actions reachable", async ({ page, api }) => {
    await page.setViewportSize({ width: ZOOM_WIDTH, height: 900 });
    const revision = dialogCase("request a revision");
    const paper = screen("paper-view");
    await openScreen(page, api, { ...paper, path: revision.path ?? paper.path }, { override: revision.override });
    const requestRevision = page.getByRole("button", { name: "Request Revision…" });
    await expect(requestRevision).toBeVisible();
    await expect400PercentEquivalentReflow(page, requestRevision);
  });

  test("Resubmit keeps its new-version action visible and reachable", async ({ page, api }) => {
    await page.setViewportSize({ width: ZOOM_WIDTH, height: 900 });
    const version = dialogCase("submit a new version");
    const paper = screen("paper-view");
    await openScreen(page, api, { ...paper, path: version.path ?? paper.path }, { override: version.override });
    const submitNewVersion = page.getByRole("button", { name: "Submit new version" });
    await expect(submitNewVersion).toBeVisible();
    await expect400PercentEquivalentReflow(page, submitNewVersion);
  });
});
