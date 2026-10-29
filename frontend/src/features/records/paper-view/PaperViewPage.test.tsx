/**
 * Two independent concerns on the same screen, merged into one file because
 * `@/api/records` can only be mocked once per module.
 *
 * **Arriving from a citation (IR-284, revised IR-335).** `lib/citedPage` is
 * unit-tested on its own halves — reading the page off the query string, and
 * wrapping a citation for router state — but the two halves being right does
 * not make the *join* right, and the join is what a reader actually walks: a
 * citation carries `?page=N` (and, live, its own regions as router state),
 * and this screen has to turn that into the embedded reader opened at that
 * page with the right thing to highlight. `PaperPdfReader` itself is mocked
 * here — it fetches and renders real PDF bytes through pdf.js, which is its
 * own test file's job (`PaperPdfReader.test.tsx`) — so what this file checks
 * is that this screen hands it the right `scrollToPage` and
 * `highlightRegions`, and that the section switch follows along.
 *
 * **Sections and actions by capability (IR-411).** Paper View has four
 * sections -- Overview, Paper, Review, Files -- kept in the URL as
 * `?section=`. Which ones a viewer sees, and which header actions, come from
 * the capabilities adapter (its own table test is `capabilities.test.ts`);
 * these tests check the page renders exactly what it grants. *Mark as
 * completed* is gone: ADR-032 retires the Proposal completion act.
 *
 * **Who sees the review and resubmit controls (IR-259).** Both read the API,
 * never the stored stage: "Open review" appears exactly when the server offers
 * `open_review` (IR-418), which it does for a seat still to work, and
 * "Resubmit for review" exactly when the
 * record is `awaiting_resubmission` and the viewer owns it. The records below
 * carry a `pipeline_status` that would have said the opposite, so a gate that
 * still read the stage would fail here.
 *
 * Every query goes through the accessible tree, by role and accessible name.
 */
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { Link, Route, Routes, useLocation, useNavigate } from "react-router-dom";

import { expectNoBlockingA11yViolations } from "@/test/axe";
import { act, renderScreen, screen, userEvent, waitFor, within } from "@/test/render";
import { useAuthStore } from "@/store/auth.store";
import { selectSidebarCollapsed, useUIStore } from "@/store/ui.store";
import type { User } from "@/types/auth";
import type { RecordDetail, ReviewerSeat } from "@/types/records";

import { recordsApi } from "@/api/records";
import { seatsApi } from "@/api/reviews";

import { PILL_PRIMARY } from "@/components/ui/pillStyles";
import { PANEL_WIDTH_KEY } from "./PaperChatDock";
import PaperViewPage from "./PaperViewPage";
import { citationNavigationState } from "@/lib/citedPage";

const RECORD_ID = 7;
const PAPER_URL = "https://iris.test/media/manuscripts/thesis.pdf";
const ASSIGNED_ADVISER_ID = 30;

/** A published Thesis/Research, for the citation-arrival tests. */
const record: RecordDetail = {
  id: RECORD_ID,
  title: "Flood Prediction in the Mananga Catchment",
  abstract: "A study of rainfall-driven flood prediction.",
  year_accomplished: 2026,
  year_completed: null,
  abstract_file: PAPER_URL,
  classification_name: "Applied Research",
  classification: "Applied Research",
  psced: null,
  record_type_name: "Thesis/Research",
  record_type: "Thesis/Research",
  pipeline_status: "published",
  is_ip: false,
  ip_type: "",
  for_commercialization: false,
  community_extension: false,
  access_count: 0,
  file_count: 1,
  created_at: "2026-09-01T08:00:00Z",
  authors: [{ id: 1, name: "R. Dela Cruz", role: null }],
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
  resubmission: {
    count: 0,
    last_resubmitted_at: null,
    declining_office: null,
    offices_preserved: [],
  },
  stage_label: "Published",
  files: [],
  workflow_state: "published",
  workflow_state_label: "Published",
  current_holders: [],
  capabilities: ["cite"],
  can_request_document: [],
  my_seats: [],
  is_participant: false,
  routing: { accept_and_route: false, route_as: null },
  office_review: { party: null, label: null, blocked: null, assignment: null },
  revision: { party: null, label: null, blocked: null, withdrawable: null, decision_blocked: null, open: [], new_version: null },
  decision: { party: null, outcomes: [], blocked: null, closes: null, token: null, author_hints: [] },
  versions: null,
  manuscript_unsubmitted: false,
  submitter_status: null,
};

/** An approved Proposal, for the Mark-as-completed tests. */
const approvedProposal: RecordDetail = {
  id: RECORD_ID,
  title: "Low-Cost Soil Moisture Sensing for Upland Farms",
  abstract: "A proposal for a sensor network on smallholder farms.",
  year_accomplished: 2026,
  year_completed: null,
  abstract_file: null,
  classification_name: "Applied Research",
  classification: "Applied Research",
  psced: null,
  record_type_name: "Proposal",
  record_type: "Proposal",
  pipeline_status: "approved",
  is_ip: false,
  ip_type: "",
  for_commercialization: false,
  community_extension: false,
  access_count: 0,
  file_count: 0,
  created_at: "2026-09-01T08:00:00Z",
  authors: [{ id: 1, name: "Andrea Lim", role: null }],
  adviser: ASSIGNED_ADVISER_ID,
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
  resubmission: {
    count: 0,
    last_resubmitted_at: null,
    declining_office: null,
    offices_preserved: [],
  },
  stage_label: "Approved",
  files: [],
  workflow_state: "approved",
  workflow_state_label: "Approved",
  current_holders: [],
  capabilities: ["cite"],
  can_request_document: [],
  my_seats: [],
  is_participant: false,
  routing: { accept_and_route: false, route_as: null },
  office_review: { party: null, label: null, blocked: null, assignment: null },
  revision: { party: null, label: null, blocked: null, withdrawable: null, decision_blocked: null, open: [], new_version: null },
  decision: { party: null, outcomes: [], blocked: null, closes: null, token: null, author_hints: [] },
  versions: null,
  manuscript_unsubmitted: false,
  submitter_status: null,
};

/** Which record `recordsApi.detail` resolves with. Reset per describe block,
 * since the two concerns below need different records shown. */
let shownRecord: RecordDetail = record;

function page<T>(results: T[]) {
  return { data: { count: results.length, next: null, previous: null, results } };
}

const documentRequests = vi.fn(() => Promise.resolve({ data: [] as unknown[] }));

vi.mock("@/api/records", () => ({
  recordsApi: {
    detail:           vi.fn(() => Promise.resolve({ data: shownRecord })),
    incrementAccess:  vi.fn(() => Promise.resolve({ data: {} })),
    similar:          vi.fn(() => Promise.resolve({ data: { results: [] } })),
    // The Novelty check loads itself; its behaviour is
    // `RelatedPublishedResearch.test.tsx`'s. Here only its placement is.
    relatedResearch:  vi.fn(() => Promise.resolve({ data: { checked: true, results: [], threshold: 0.7 } })),
    // The tracker panel loads itself; it has its own test file (IR-258).
    tracker:          vi.fn(() => Promise.reject(new Error("not under test"))),
    // The Action required panel loads itself; its behaviour is tested in
    // features/document-requests (IR-262). Here only its placement is.
    documentRequests: () => documentRequests(),
    // Request documents, from the Review section's action bar (IR-412).
    documentRequestSlots:  vi.fn(() => Promise.resolve({ data: [{ id: 3, name: "Ethics Clearance" }] })),
    createDocumentRequest: vi.fn(() => Promise.resolve({ data: { id: 1 } })),
    updateTags:       vi.fn(),
    // Edit details (IR-411); its own behaviour is `EditDetailsDialog.test.tsx`'s.
    update:           vi.fn(() => Promise.resolve({ data: {} })),
    classifications:  vi.fn(() => Promise.resolve(page([]))),
    pscedList:        vi.fn(() => Promise.resolve(page([]))),
  },
}));

// The Files section loads itself; its behaviour is `FilesSection.test.tsx`'s.
vi.mock("@/api/documents", () => ({
  documentsApi: {
    slotsForRecord: vi.fn(() => Promise.resolve({ data: [] })),
    files:          vi.fn(() => Promise.resolve({ data: [] })),
  },
}));
vi.mock("@/api/accounts", () => ({
  accountsApi: { listAdvisers: vi.fn(() => Promise.resolve(page([]))) },
}));

vi.mock("@/api/reviews", () => ({
  reviewsApi: { resubmit: vi.fn() },
  seatsApi: { open: vi.fn(() => Promise.resolve({ data: {} })) },
}));

// The AI overview reads its own cache; this screen is not what that
// behaviour is tested through (`PaperAiOverview.test.tsx` is).
vi.mock("@/api/ai", () => ({
  aiApi: {
    ask:      vi.fn(() => Promise.reject(new Error("not under test"))),
    overview: vi.fn(() => Promise.reject(new Error("not under test"))),
    // Paper Chat opens its Conversation on mount; its behaviour is
    // `PaperChatDock.test.tsx`'s. Here only where the panel sits is.
    conversations: {
      findForRecord: vi.fn(() => new Promise(() => {})),
      create:        vi.fn(() => Promise.resolve({ data: { id: 50, turns: [] } })),
      // A citation re-resolved from its address after a reload (IR-578).
      get:           vi.fn(() => Promise.reject(new Error("not under test"))),
    },
    // A follow-up asked from Paper Chat (IR-355); nothing else here asks.
    askStream:     vi.fn(),
  },
}));

// `PaperPdfReader` fetches and renders real PDF bytes through pdf.js, which
// jsdom cannot do at all (no canvas 2D context, no worker) and which is this
// component's own test file's job (`PaperPdfReader.test.tsx`). This screen
// only has to hand it the right props -- asserted below by rendering what
// they were.
vi.mock("./PaperPdfReader", () => ({
  PaperPdfReader: ({
    scrollToPage,
    highlightRegions,
    toolbarStart,
    version,
  }: {
    scrollToPage: number | null;
    highlightRegions: unknown[];
    toolbarStart?: ReactNode;
    version?: number | null;
  }) => (
    <div>
      {toolbarStart}
      Paper reader open at page {scrollToPage ?? "none"}, {highlightRegions.length} region(s) to
      highlight{version != null ? `, reading v${version}` : ", reading the current paper"}
    </div>
  ),
}));

function signInAs(id: number, role_name: User["role_name"]) {
  useAuthStore.setState({
    user: {
      id,
      email: `user${id}@cit.edu`,
      first_name: "Test",
      middle_initial: "",
      last_name: "User",
      role: null,
      role_name,
      is_staff: false,
      is_superuser: false,
      is_verified: true,
      is_locked: false,
      consent_given: true,
      date_joined: "2026-01-01T00:00:00Z",
    } as User,
  });
}

/** Mounted on its real path, so `useParams` sees the record id. */
function renderPaper(route: string, state?: unknown) {
  return renderScreen(
    <Routes>
      <Route path="/records/:id" element={<PaperViewPage />} />
    </Routes>,
    { route, state },
  );
}

function renderPaperView() {
  return renderPaper(`/records/${RECORD_ID}`);
}

describe("arriving from a citation", () => {
  beforeEach(() => {
    shownRecord = record;
  });

  it("opens the embedded reader at the cited page, without leaving the app", async () => {
    renderPaper(`/records/${RECORD_ID}?page=12`);

    expect(await screen.findByRole("tab", { name: "Paper", selected: true })).toBeInTheDocument();
    expect(await screen.findByText(/open at page 12, 0 region\(s\)/i)).toBeInTheDocument();
  });

  it("carries a citation's regions to the reader as router state, with no second fetch", async () => {
    const citation = {
      marker: 1,
      chunk_id: 11,
      record_id: RECORD_ID,
      record_title: record.title,
      page: 12,
      text: "the network reduced mean absolute error by twelve per cent",
      context_path: [record.title, "Results"],
      regions: [{ page: 12, left: 0.1, top: 0.2, right: 0.6, bottom: 0.3 }],
    };

    renderPaper(`/records/${RECORD_ID}?page=12`, { citation });

    expect(await screen.findByText(/open at page 12, 1 region\(s\)/i)).toBeInTheDocument();
  });

  it("opens on Overview, with the Paper tab one click away, when no page was named", async () => {
    renderPaper(`/records/${RECORD_ID}`);

    expect(await screen.findByRole("tab", { name: "Overview", selected: true })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Paper", selected: false })).toBeEnabled();
  });

  it("ignores a page that is not a page and stays on Overview", async () => {
    renderPaper(`/records/${RECORD_ID}?page=not-a-page`);

    expect(await screen.findByRole("tab", { name: "Overview", selected: true })).toBeInTheDocument();
  });

  it("switches to the reader when the Paper tab is chosen", async () => {
    renderPaper(`/records/${RECORD_ID}`);

    // The floating switch is the one way into the reader (IR-356): the
    // header's "View Paper" button duplicated it and is now Share.
    await userEvent.click(await screen.findByRole("tab", { name: "Paper" }));

    expect(await screen.findByRole("tab", { name: "Paper", selected: true })).toBeInTheDocument();
    expect(await screen.findByText(/open at page none, 0 region\(s\)/i)).toBeInTheDocument();
  });
});

const MARK_COMPLETED = { name: /mark as completed/i };

// ADR-032 retires the Proposal *complete* act and gives RDCO no Proposal
// role, so nobody is offered it any more (spec §4.6, IR-411). Since IR-271
// the client has no completion call at all, and the server refuses one.
describe("Mark as completed is retired", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    shownRecord = approvedProposal;
  });

  it.each([
    ["the assigned Adviser", ASSIGNED_ADVISER_ID, "Adviser"],
    ["RDCO", 1, "RDCO"],
  ] as const)("is not offered to %s on an approved Proposal", async (_label, id, role) => {
    signInAs(id, role);
    renderPaperView();

    // Wait for the record to render before asserting an absence, or the
    // assertion would pass against the loading skeleton.
    await screen.findByRole("heading", { name: approvedProposal.title });
    expect(screen.queryByRole("button", MARK_COMPLETED)).not.toBeInTheDocument();
  });
});

const OWNER_ID = 40;

describe("Proposal lineage", () => {
  beforeEach(() => {
    shownRecord = { ...approvedProposal, capabilities: ["continue_as"], lineage: {
      derived_from: null, continued_as: { id: 456, title: "Full thesis", record_type_name: "Thesis / Research" },
    } };
  });

  it("renders the supplied child link and continuation actions", async () => {
    signInAs(OWNER_ID, "Student");
    renderPaperView();
    expect(await screen.findByRole("link", { name: "Continued as Thesis / Research #456" })).toHaveAttribute("href", "/records/456");
    expect(screen.getByRole("button", { name: "Continue as Thesis" })).toBeInTheDocument();
  });

  it("links a child back to its Proposal and hides actions when not offered", async () => {
    shownRecord = { ...record, capabilities: [], lineage: {
      derived_from: { id: 123, title: "Proposal", record_type_name: "Proposal" }, continued_as: null,
    } };
    signInAs(OWNER_ID, "Student");
    renderPaperView();
    expect(await screen.findByRole("link", { name: "Developed from Proposal #123 — View proposal" })).toHaveAttribute("href", "/records/123");
    expect(screen.queryByRole("button", { name: "Continue as Thesis" })).not.toBeInTheDocument();
  });
});
const OPEN_REVIEW = { name: "Open review" } as const;
const RESUBMIT = { name: "Resubmit for review" } as const;

/** A Thesis/Research in office review, for the IR-259 gate tests. */
const inReview: RecordDetail = {
  ...record,
  title: "Groundwater Recharge Mapping in Metro Cebu",
  pipeline_status: "in_review",
  owners: [{ id: 1, user: OWNER_ID, email: "owner@cit.edu", full_name: "Rhea Owner", is_primary: true }],
  workflow_state: "in_review",
  workflow_state_label: "In review",
  current_holders: [
    { party: "itso", label: "ITSO", opened_at: "2026-09-02T08:00:00Z", opened_by: null },
  ],
  can_request_document: [],
  my_seats: [],
  is_participant: false,
  routing: { accept_and_route: false, route_as: null },
  office_review: { party: null, label: null, blocked: null, assignment: null },
  revision: { party: null, label: null, blocked: null, withdrawable: null, decision_blocked: null, open: [], new_version: null },
  decision: { party: null, outcomes: [], blocked: null, closes: null, token: null, author_hints: [] },
  versions: null,
  manuscript_unsubmitted: false,
  submitter_status: null,
};

/**
 * jsdom lays nothing out, so the page's workspace is measured as `width`
 * wide: the width the three Paper layouts are chosen by (IR-569).
 */
function workspaceAt(width: number) {
  const watching = new Set<{ target: Element; callback: ResizeObserverCallback; observer: ResizeObserver }>();
  const report = (target: Element, callback: ResizeObserverCallback, observer: ResizeObserver, w: number) =>
    callback([{ target, contentRect: { width: w } } as unknown as ResizeObserverEntry], observer);
  vi.stubGlobal(
    "ResizeObserver",
    class {
      constructor(private readonly callback: ResizeObserverCallback) {}
      observe(target: Element) {
        const entry = { target, callback: this.callback, observer: this as unknown as ResizeObserver };
        watching.add(entry);
        report(target, this.callback, entry.observer, width);
      }
      unobserve() {}
      disconnect() {}
    },
  );
  return {
    resizeTo: (next: number) => watching.forEach((w) => report(w.target, w.callback, w.observer, next)),
  };
}

async function waitForRecord(title: string) {
  // Assert absences only after the record renders, not against the skeleton.
  await screen.findByRole("heading", { name: title });
}

/**
 * A reviewer the API names: an open seat of their own, so a participant
 * (ADR-032 §4, §10). IR-274 replaced `can_act: ["itso"]`, the retired review
 * form's flag, with this in every test below that used it.
 */
const reviewingSeat: ReviewerSeat = {
  id: 78, assignment: 5, record: RECORD_ID, party: "itso", party_label: "ITSO",
  reviewer: 2, reviewer_name: "ITSO Reviewer", state: "in_review", state_label: "In review",
  source: "claimed", assigned_by: 2, assigned_at: "2026-10-01T08:00:00Z",
  opened_at: "2026-10-01T09:00:00Z", done_at: null,
};
const reviewing = { my_seats: [reviewingSeat], is_participant: true };

// Since IR-418 the server sends `capabilities`, and the adapter passes it
// through: each record below carries the list the server computes for that
// viewer alongside the fields it is computed from.
describe("the review control follows the server's capabilities", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("is offered when the API gives this viewer a seat to work", async () => {
    shownRecord = { ...inReview, ...reviewing, capabilities: ["cite", "open_review"] };
    signInAs(2, "ITSO");
    const { container } = renderPaperView();

    expect(await screen.findByRole("button", OPEN_REVIEW)).toBeInTheDocument();
    await expectNoBlockingA11yViolations(container);
  });

  it("opens the Review section without the retired fixed-stage decision form", async () => {
    shownRecord = { ...inReview, ...reviewing, capabilities: ["cite", "open_review"] };
    signInAs(2, "ITSO");
    renderPaperView();

    await userEvent.click(await screen.findByRole("button", OPEN_REVIEW));

    expect(await screen.findByRole("tab", { name: "Review", selected: true })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Record a decision (current form)" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", OPEN_REVIEW)).not.toBeInTheDocument();
  });

  // ADR-032 §4, IR-415: opening the review records when this reviewer started.
  it("records the viewer's unopened seat, then opens the Review section", async () => {
    const assigned: ReviewerSeat = {
      id: 77, assignment: 5, record: RECORD_ID, party: "itso", party_label: "ITSO",
      reviewer: 2, reviewer_name: "ITSO Reviewer", state: "assigned", state_label: "Assigned",
      source: "claimed", assigned_by: 2, assigned_at: "2026-10-01T08:00:00Z",
      opened_at: null, done_at: null,
    };
    shownRecord = { ...inReview, my_seats: [assigned], is_participant: true, capabilities: ["cite", "open_review"] };
    signInAs(2, "ITSO");
    renderPaperView();

    await userEvent.click(await screen.findByRole("button", OPEN_REVIEW));

    expect(vi.mocked(seatsApi.open)).toHaveBeenCalledWith(77);
    expect(await screen.findByRole("tab", { name: "Review", selected: true })).toBeInTheDocument();
  });

  it("only navigates when every seat is already open", async () => {
    shownRecord = { ...inReview, ...reviewing, capabilities: ["cite", "open_review"] };
    signInAs(2, "ITSO");
    renderPaperView();

    await userEvent.click(await screen.findByRole("button", OPEN_REVIEW));

    expect(await screen.findByRole("tab", { name: "Review", selected: true })).toBeInTheDocument();
    expect(vi.mocked(seatsApi.open)).not.toHaveBeenCalled();
  });

  it("is not offered to a same-role viewer the API does not name, whatever the stage", async () => {
    // An ITSO reviewer was once shown the control by role alone, at the
    // retired `parallel_review` stage. The API gives this one no seat.
    shownRecord = { ...inReview };
    signInAs(2, "ITSO");
    renderPaperView();

    await waitForRecord(inReview.title);
    expect(screen.queryByRole("button", OPEN_REVIEW)).not.toBeInTheDocument();
  });

  it("is not offered to the owner", async () => {
    shownRecord = inReview;
    signInAs(OWNER_ID, "Student");
    renderPaperView();

    await waitForRecord(inReview.title);
    expect(screen.queryByRole("button", OPEN_REVIEW)).not.toBeInTheDocument();
  });
});

describe("the new-version control follows revision requests", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("on the adviser-first model, shows the owner what was asked instead of the legacy Resubmit (IR-272)", async () => {
    shownRecord = {
      ...inReview,
      workflow_state: "awaiting_resubmission",
      workflow_state_label: "Awaiting resubmission",
      revision: {
        party: null, label: null, blocked: null, withdrawable: null, decision_blocked: null,
        open: [{
          id: 3, party: "ierc", label: "IERC", reason: "Add the assent form\nfor participants under 18.",
          requested_by: "Ivy Ethics", version: 2, created_at: "2026-10-08T02:00:00Z",
        }],
        new_version: null,
      },
    };
    signInAs(OWNER_ID, "Student");
    renderPaperView();

    const banner = await screen.findByRole("region", { name: "Revision requested" });
    expect(banner).toHaveTextContent("IERC asked for changes · on v2");
    expect(banner).toHaveTextContent("Add the assent form for participants under 18.");
    expect(screen.queryByRole("button", RESUBMIT)).not.toBeInTheDocument();
  });

  /** The adviser-first model's revision, with the server offering a new version (IR-273). */
  const asked = (blocked: string | null): RecordDetail => ({
    ...inReview,
    workflow_state: "awaiting_resubmission",
    workflow_state_label: "Awaiting resubmission",
    revision: {
      party: null, label: null, blocked: null, withdrawable: null,
      decision_blocked: "Waiting on the author: IERC asked for a revision.",
      open: [{
        id: 3, party: "ierc", label: "IERC", reason: "Add the assent form.",
        requested_by: "Ivy Ethics", version: 2, created_at: "2026-10-08T02:00:00Z",
      }],
      new_version: { number: 3, rereview: ["IERC"], kept: ["ITSO"], blocked },
    },
    capabilities: ["cite", "create_version", "replace_manuscript", "edit_details"],
  });

  it("on the adviser-first model, offers the owner a new version that names who reviews it (IR-273)", async () => {
    shownRecord = asked(null);
    signInAs(OWNER_ID, "Student");
    renderPaperView();

    const banner = await screen.findByRole("region", { name: "Revision requested" });
    expect(banner).toHaveTextContent("IERC will review v3. ITSO's clearance is kept.");
    expect(screen.queryByRole("button", RESUBMIT)).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Submit new version" }));

    expect(await screen.findByRole("dialog", { name: "Submit new version" })).toBeInTheDocument();
  });

  it("holds the new version, saying why, until something has changed (IR-273)", async () => {
    shownRecord = asked("Nothing has changed since IERC asked for a revision.");
    signInAs(OWNER_ID, "Student");
    renderPaperView();

    const submit = await screen.findByRole("button", { name: "Submit new version" });
    expect(submit).toBeDisabled();
    expect(submit).toHaveAccessibleDescription("Nothing has changed since IERC asked for a revision.");
  });
});

describe("the status the paper shows", () => {
  it("is the API's workflow_state_label, on the badge and in governance", async () => {
    shownRecord = { ...inReview, pipeline_status: "in_review", workflow_state_label: "Final review", workflow_state: "final_review" };
    signInAs(99, "Student");
    renderPaperView();

    await waitForRecord(inReview.title);
    // Once as the badge, once as the governance ledger's status row.
    expect(screen.getAllByText("Final review")).toHaveLength(2);
    expect(screen.queryByText("RDCO Final Review")).not.toBeInTheDocument();
  });
});

describe("the byline credits the adviser (IR-472)", () => {
  beforeEach(() => {
    signInAs(99, "Student");
  });

  it("names the adviser on a record that has one", async () => {
    shownRecord = { ...record, adviser: ASSIGNED_ADVISER_ID, adviser_name: "Maria Santos" };
    renderPaperView();

    await waitForRecord(record.title);
    expect(screen.getByText("Adviser: Maria Santos")).toBeInTheDocument();
  });

  it("shows no adviser line on a record without one", async () => {
    shownRecord = { ...record, adviser: null, adviser_name: null };
    renderPaperView();

    await waitForRecord(record.title);
    expect(screen.queryByText(/^Adviser:/)).not.toBeInTheDocument();
  });
});

describe("document requests (IR-262)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  const openRequest = {
    id: 1, party: "ierc", label: "IERC", state: "open", state_label: "Open",
    message: "The signed consent forms are missing.", requested_by: null,
    created_at: "2026-09-20T02:00:00Z", closed_at: null, can_manage: false,
    items: [{
      id: 11, slot: 3, label: "Ethics Clearance", state: "missing",
      state_label: "Missing", upload: null, uploaded_at: null, rejection_reason: null, decided_at: null,
    }],
  };

  it("shows the owner an Action required panel for an open request", async () => {
    documentRequests.mockResolvedValueOnce({ data: [openRequest] });
    shownRecord = { ...inReview, workflow_state: "awaiting_document", workflow_state_label: "Awaiting document" };
    signInAs(OWNER_ID, "Student");
    renderPaperView();

    const panel = await screen.findByRole("region", { name: "Action required" });
    expect(panel).toHaveTextContent("The signed consent forms are missing.");
  });

  it("does not load requests for a viewer who does not own the record", async () => {
    shownRecord = inReview;
    signInAs(99, "Student");
    renderPaperView();

    await waitForRecord(inReview.title);
    expect(documentRequests).not.toHaveBeenCalled();
  });

  // In the Files section now, which replaced the Documents page (IR-411).
  it("offers Request documents exactly when the API names a party", async () => {
    shownRecord = { ...inReview, can_request_document: ["ierc"] };
    signInAs(2, "IERC");
    renderPaper(`/records/${RECORD_ID}?section=files`);

    expect(await screen.findByRole("button", { name: "Request documents" })).toBeInTheDocument();
  });

  it("does not offer Request documents otherwise", async () => {
    shownRecord = inReview;
    signInAs(2, "IERC");
    renderPaper(`/records/${RECORD_ID}?section=files`);

    await waitForRecord(inReview.title);
    expect(screen.queryByRole("button", { name: "Request documents" })).not.toBeInTheDocument();
  });
});

describe("related published research (IR-312)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  const ownProposal: RecordDetail = {
    ...inReview, record_type_name: "Proposal", record_type: "Proposal",
  };
  const heading = { name: "Related published research" };

  it("is shown to the owner of a Proposal", async () => {
    shownRecord = ownProposal;
    signInAs(OWNER_ID, "Student");
    renderPaperView();

    expect(await screen.findByRole("heading", heading)).toBeInTheDocument();
    expect(vi.mocked(recordsApi.relatedResearch)).toHaveBeenCalledWith(RECORD_ID);
  });

  it("is not shown, or asked for, by anyone who does not own the Proposal", async () => {
    shownRecord = ownProposal;
    signInAs(99, "Adviser");
    renderPaperView();

    await waitForRecord(ownProposal.title);
    expect(screen.queryByRole("heading", heading)).not.toBeInTheDocument();
    expect(vi.mocked(recordsApi.relatedResearch)).not.toHaveBeenCalled();
  });

  it("is not shown on a record that is not a Proposal, even to its owner", async () => {
    shownRecord = inReview;
    signInAs(OWNER_ID, "Student");
    renderPaperView();

    await waitForRecord(inReview.title);
    expect(screen.queryByRole("heading", heading)).not.toBeInTheDocument();
    expect(vi.mocked(recordsApi.relatedResearch)).not.toHaveBeenCalled();
  });
});

describe("the submitter's own status (IR-625)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  const openRequest = {
    id: 1, party: "adviser", label: "Adviser", state: "open", state_label: "Open",
    message: "The signed form, please.", requested_by: null,
    created_at: "2026-09-20T02:00:00Z", closed_at: null, can_manage: false,
    items: [],
  };

  const waitingOwner: RecordDetail = {
    ...inReview,
    workflow_state: "awaiting_resubmission",
    workflow_state_label: "Awaiting resubmission",
    submitter_status: {
      line: "Revision requested by IERC: action needed",
      waiting_on_you: [
        { kind: "revision", party: "ierc", label: "Revision requested by IERC", action_label: "Submit a new version" },
        { kind: "document", party: "adviser", label: "Documents requested by Adviser", action_label: "Upload the documents" },
      ],
      history: [
        {
          number: 1, cause_label: "Submission", submitted_at: "2026-09-01T02:00:00Z",
          decisions: [
            { party: "adviser", label: "Adviser", verdict: "approved", verdict_label: "Approved" },
            { party: "ierc", label: "IERC", verdict: "declined", verdict_label: "Revision requested" },
          ],
        },
        { number: 2, cause_label: "Revision", submitted_at: "2026-09-15T02:00:00Z", decisions: [] },
      ],
    },
  };

  it("tells the owner where the record is, what waits on them, and each version's history", async () => {
    shownRecord = waitingOwner;
    signInAs(OWNER_ID, "Student");
    const { container } = renderPaperView();

    const panel = await screen.findByRole("region", { name: "Your submission" });
    expect(panel).toHaveTextContent("Revision requested by IERC: action needed");

    const waiting = within(panel).getByRole("region", { name: "Waiting on you" });
    expect(within(waiting).getByRole("link", { name: "Submit a new version (Revision requested by IERC)" }))
      .toHaveAttribute("href", "#revision-requested");
    expect(within(waiting).getByRole("link", { name: "Upload the documents (Documents requested by Adviser)" }))
      .toHaveAttribute("href", "#documents-requested");

    const versions = within(within(panel).getByRole("list", { name: "Version history" })).getAllByRole("listitem");
    expect(versions).toHaveLength(2);
    expect(versions[0]).toHaveTextContent("v1 · Submission");
    expect(versions[0]).toHaveTextContent("Adviser: Approved · IERC: Revision requested");
    expect(versions[1]).toHaveTextContent("No decision yet");
    await expectNoBlockingA11yViolations(container);
  });

  it("shows nothing of the kind to anyone the server sends none", async () => {
    shownRecord = { ...waitingOwner, submitter_status: null };
    signInAs(99, "Student");
    renderPaperView();

    await waitForRecord(inReview.title);
    expect(screen.queryByRole("region", { name: "Your submission" })).not.toBeInTheDocument();
  });

  it("lands on the request a My Library link named, once it has loaded", async () => {
    documentRequests.mockResolvedValueOnce({ data: [openRequest] });
    shownRecord = waitingOwner;
    signInAs(OWNER_ID, "Student");
    renderPaper(`/records/${RECORD_ID}?section=overview#documents-requested`);

    const panel = await screen.findByRole("region", { name: "Action required" });
    await waitFor(() => expect(panel).toHaveFocus());
  });
});

// Ask IRIS on the Overview is the Paper workspace's panel, as a column the
// page makes room for (IR-569): the same heading, composer and width, beside
// a page that narrows to fit rather than sitting under it.
describe("Ask IRIS on Overview (IR-569)", () => {
  const RAIL = { name: "Institutional Governance" };

  beforeEach(() => {
    shownRecord = record;
    signInAs(99, "Student");
  });

  it("opens from the round icon at the bottom right", async () => {
    workspaceAt(1400);
    renderPaperView();
    await waitForRecord(record.title);

    await userEvent.click(screen.getByRole("button", { name: "Ask IRIS" }));

    expect(await screen.findByRole("complementary", { name: "Ask IRIS" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Panel position" })).not.toBeInTheDocument();
  });

  it("folds Record details away while it is open, and brings them back when it closes (IR-569)", async () => {
    workspaceAt(1400);
    renderPaperView();
    await waitForRecord(record.title);
    expect(screen.getByRole("heading", RAIL)).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Ask IRIS" }));
    await screen.findByRole("complementary", { name: "Ask IRIS" });

    expect(screen.queryByRole("complementary", { name: "Record details" })).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", RAIL)).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Close Ask IRIS" }));

    expect(await screen.findByRole("complementary", { name: "Record details" })).toBeInTheDocument();
    expect(screen.getByRole("heading", RAIL)).toBeInTheDocument();
  });

  it("is a column beside the page, 450px wide, not a layer over it", async () => {
    workspaceAt(1400);
    renderPaperView();
    await waitForRecord(record.title);

    await userEvent.click(screen.getByRole("button", { name: "Ask IRIS" }));

    const panel = await screen.findByRole("complementary", { name: "Ask IRIS" });
    expect(panel.style.width).toBe("450px");
    expect(panel).toHaveClass("reading-split:sticky");
    expect(panel).not.toHaveClass("reading-split:fixed");
    // The page it sits beside is its own container, so it reads what is left.
    expect(screen.getByRole("heading", { level: 1 }).closest("[class*=container-name]")).not.toBeNull();
    expect(panel.closest("[inert]")).toBeNull();
    expect(screen.getByRole("tablist").closest("[inert]")).toBeNull();
  });

  it("is never more than half the workspace, whatever width was chosen", async () => {
    localStorage.setItem(PANEL_WIDTH_KEY, "900");
    workspaceAt(1400);
    renderPaperView();
    await waitForRecord(record.title);

    await userEvent.click(screen.getByRole("button", { name: "Ask IRIS" }));

    expect((await screen.findByRole("complementary", { name: "Ask IRIS" })).style.width).toBe("700px");
    localStorage.removeItem(PANEL_WIDTH_KEY);
  });

  it("steps aside when the sidebar narrows the page to a phone's width, leaving the page", async () => {
    const workspace = workspaceAt(900);
    renderPaperView();
    await waitForRecord(record.title);
    await userEvent.click(screen.getByRole("button", { name: "Ask IRIS" }));
    await screen.findByRole("complementary", { name: "Ask IRIS" });

    act(() => workspace.resizeTo(700));
    expect(screen.getByRole("complementary", { name: "Ask IRIS" })).toBeInTheDocument();

    act(() => workspace.resizeTo(613));
    expect(screen.queryByRole("heading", { name: "Ask IRIS" })).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 1 })).toBeInTheDocument();
  });

  it("closes back to the icon", async () => {
    renderPaperView();
    await waitForRecord(record.title);
    await userEvent.click(screen.getByRole("button", { name: "Ask IRIS" }));

    await userEvent.click(await screen.findByRole("button", { name: "Close Ask IRIS" }));

    expect(screen.queryByRole("complementary", { name: "Ask IRIS" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Ask IRIS" })).toBeInTheDocument();
  });

  it("is one dialog over the whole page on a phone, which waits behind it", async () => {
    workspaceAt(360);
    renderPaperView();
    await waitForRecord(record.title);

    await userEvent.click(screen.getByRole("button", { name: "Ask IRIS" }));

    const panel = await screen.findByRole("dialog", { name: "Ask IRIS" });
    expect(panel.closest("[inert]")).toBeNull();
    expect(screen.getByRole("tablist").closest("[inert]")).not.toBeNull();
    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("dialog", { name: "Ask IRIS" })).not.toBeInTheDocument();
  });
});

// The Paper tab is the paper and Ask IRIS, nothing else (IR-372). Since IR-569
// entering it opens Ask IRIS, collapses the sidebar for the visit, and a
// one-line record bar replaces the editorial header; the workspace's width
// picks the layout, and the reader sizes the panel.
describe("the Paper tab (IR-372, IR-569)", () => {
  const RAIL = { name: "Institutional Governance" };
  const ASK = { name: "Ask IRIS" };

  beforeEach(() => {
    shownRecord = record;
    signInAs(99, "Student");
    useUIStore.setState({ sidebarCollapsed: false, sidebarOpen: false, readingRail: null });
  });

  afterEach(() => {
    localStorage.removeItem(PANEL_WIDTH_KEY);
    vi.unstubAllGlobals();
  });

  async function openPaperTab() {
    const view = renderPaperView();
    await waitForRecord(record.title);
    await userEvent.click(screen.getByRole("tab", { name: "Paper" }));
    await screen.findByText(/paper reader open/i);
    // A side panel or, over the paper, a dialog: named by its heading either way.
    await screen.findByRole("heading", { name: "Ask IRIS" });
    return view;
  }

  it("opens Ask IRIS on entry, with the icon only once it is closed, creating nothing", async () => {
    const { aiApi } = await import("@/api/ai");
    vi.mocked(aiApi.conversations.create).mockClear();

    await openPaperTab();

    expect(screen.queryByRole("button", ASK)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Ask about this paper" })).not.toBeInTheDocument();
    expect(aiApi.conversations.create).not.toHaveBeenCalled();
    expect(aiApi.askStream).not.toHaveBeenCalled();
  });

  it("opens Ask IRIS on a direct Paper link too", async () => {
    renderPaper(`/records/${RECORD_ID}?section=paper`);

    expect(await screen.findByRole("complementary", { name: "Ask IRIS" })).toBeInTheDocument();
  });

  it("puts the paper in one line: title, version and Back, not the editorial header", async () => {
    shownRecord = {
      ...record,
      versions: [{
        number: 1, cause: "submission", cause_label: "Submission", created_at: "2026-09-01T08:00:00Z",
        created_by_name: "Rhea Owner", manuscript_url: `/api/v1/records/${RECORD_ID}/versions/1/manuscript/`,
      }],
    };
    await openPaperTab();

    expect(screen.getByRole("heading", { level: 1, name: record.title })).toHaveAttribute("title", record.title);
    expect(screen.getByText("v1")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Back" })).toBeInTheDocument();
    expect(screen.queryByText("Cebu Institute of Technology – University")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Share" })).not.toBeInTheDocument();
  });

  it("has Ask IRIS as an icon, not a button in the record bar", async () => {
    await openPaperTab();
    await userEvent.click(screen.getByRole("button", { name: "Close Ask IRIS" }));

    const icon = screen.getByRole("button", ASK);
    expect(icon.closest("header, [role=tablist]")).toBeNull();
    expect(icon).toHaveClass("fixed", "bottom-5");
  });

  it("collapses the sidebar to its rail while reading, and gives the saved choice back after", async () => {
    await openPaperTab();
    expect(selectSidebarCollapsed(useUIStore.getState())).toBe(true);
    expect(useUIStore.getState().sidebarCollapsed).toBe(false);

    await userEvent.click(screen.getByRole("tab", { name: "Overview" }));

    expect(selectSidebarCollapsed(useUIStore.getState())).toBe(false);
  });

  it("shows no rail", async () => {
    await openPaperTab();
    expect(screen.queryByRole("heading", RAIL)).not.toBeInTheDocument();
  });

  it("closes to the paper, and the icon reopens it with the draft kept", async () => {
    await openPaperTab();
    await userEvent.type(screen.getByRole("textbox", { name: "Ask about this paper" }), "What was measured?");

    await userEvent.click(screen.getByRole("button", { name: "Close Ask IRIS" }));
    expect(screen.queryByRole("complementary", { name: "Ask IRIS" })).not.toBeInTheDocument();
    expect(screen.getByText(/paper reader open/i)).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", ASK));
    expect(await screen.findByRole("textbox", { name: "Ask about this paper" })).toHaveValue("What was measured?");
  });

  it("keeps an open chat's conversation when the reader switches sections", async () => {
    const { aiApi } = await import("@/api/ai");
    const find = vi.mocked(aiApi.conversations.findForRecord);
    find.mockClear();

    renderPaperView();
    await waitForRecord(record.title);
    await userEvent.click(screen.getByRole("button", ASK));
    await screen.findByRole("complementary", { name: "Ask IRIS" });

    await userEvent.click(screen.getByRole("tab", { name: "Paper" }));
    await userEvent.click(screen.getByRole("tab", { name: "Overview" }));

    expect(screen.getByRole("complementary", { name: "Ask IRIS" })).toBeInTheDocument();
    expect(find).toHaveBeenCalledTimes(1);
  });

  it("has no serious or critical accessibility violations with the chat open", async () => {
    const { container } = await openPaperTab();
    await expectNoBlockingA11yViolations(container);
  });

  describe("by the workspace's width", () => {
    const inert = (el: HTMLElement) => el.closest("[inert]") !== null;

    it("sets the chat beside the paper at 1000px and up, with nothing held back", async () => {
      workspaceAt(1200);
      await openPaperTab();

      expect(inert(screen.getByRole("tabpanel"))).toBe(false);
      expect(screen.queryByRole("button", { name: "Back to paper" })).not.toBeInTheDocument();
    });

    it("slides the chat over the paper at 640-999px: focus moves in, the rest waits, Escape closes", async () => {
      workspaceAt(924);
      await openPaperTab();

      const panel = screen.getByRole("dialog", { name: "Ask IRIS" });
      expect(panel).toHaveAttribute("aria-modal", "true");
      await waitFor(() => expect(panel).toHaveFocus());
      expect(inert(screen.getByRole("tabpanel"))).toBe(true);
      expect(inert(screen.getByRole("tablist"))).toBe(true);
      // Focus that escapes (to the app's sidebar, say) is brought back.
      act(() => screen.getByRole("tab", { name: "Overview" }).focus());
      expect(panel).toHaveFocus();

      await userEvent.keyboard("{Escape}");

      expect(screen.queryByRole("dialog", { name: "Ask IRIS" })).not.toBeInTheDocument();
      expect(inert(screen.getByRole("tabpanel"))).toBe(false);
      await waitFor(() => expect(screen.getByRole("button", ASK)).toHaveFocus());
    });

    it("gives the chat the whole view below 640px, with Back to paper keeping the conversation", async () => {
      workspaceAt(360);
      await openPaperTab();

      await userEvent.click(screen.getByRole("button", { name: "Back to paper" }));

      const bar = screen.getByRole("button", { name: "Ask IRIS: back to the answer" });
      expect(inert(screen.getByRole("tabpanel"))).toBe(false);
      await waitFor(() => expect(bar).toHaveFocus());

      await userEvent.click(bar);
      expect(screen.getByRole("textbox", { name: "Ask about this paper" })).toBeInTheDocument();
    });

    it("on a phone, closes the navigation drawer on entry and keeps an unsent draft across Back to paper (IR-570)", async () => {
      const { aiApi } = await import("@/api/ai");
      workspaceAt(360);
      useUIStore.setState({ sidebarOpen: true });
      await openPaperTab();
      vi.mocked(aiApi.conversations.create).mockClear();

      expect(useUIStore.getState().sidebarOpen).toBe(false);
      const box = screen.getByRole("textbox", { name: "Ask about this paper" });
      await userEvent.type(box, "What does the method assume?");

      const paper = screen.getByRole("tabpanel");
      await userEvent.click(screen.getByRole("button", { name: "Back to paper" }));
      expect(inert(paper)).toBe(false);
      await userEvent.click(screen.getByRole("button", { name: "Ask IRIS: back to the answer" }));

      // The reader is the same element throughout, so its page and scroll
      // position are kept rather than rebuilt (jsdom cannot scroll to show it).
      expect(screen.getByRole("tabpanel")).toBe(paper);
      expect(screen.getByRole("textbox", { name: "Ask about this paper" })).toHaveValue("What does the method assume?");
      expect(aiApi.conversations.create).not.toHaveBeenCalled();
    });

    it("steps aside when the sidebar opens and narrows the workspace, leaving the paper in view", async () => {
      const workspace = workspaceAt(1200);
      await openPaperTab();
      expect(screen.getByRole("complementary", { name: "Ask IRIS" })).toBeInTheDocument();

      act(() => workspace.resizeTo(613));

      expect(screen.queryByRole("heading", { name: "Ask IRIS" })).not.toBeInTheDocument();
      expect(screen.getByText(/paper reader open/i)).toBeInTheDocument();
      expect(screen.getByRole("button", ASK)).toBeInTheDocument();
    });

    it("leaves the chat open when the workspace widens", async () => {
      const workspace = workspaceAt(613);
      await openPaperTab();

      act(() => workspace.resizeTo(1200));

      expect(screen.getByRole("complementary", { name: "Ask IRIS" })).toBeInTheDocument();
    });
  });

  describe("the panel's width", () => {
    const panelWidth = () => screen.getByRole("complementary", { name: "Ask IRIS" }).style.width;
    const edge = () => screen.getByRole("separator", { name: "Resize Ask IRIS" });

    it("starts at 450px, a quarter wider than the 360px it was", async () => {
      workspaceAt(1400);
      await openPaperTab();

      expect(panelWidth()).toBe("450px");
    });

    it("is never more than half the workspace, the half the reader asked for included", async () => {
      localStorage.setItem(PANEL_WIDTH_KEY, "900");
      workspaceAt(1400);
      await openPaperTab();

      expect(panelWidth()).toBe("700px");
    });

    it("is held to leave the paper 640px, never under 320px", async () => {
      workspaceAt(1000);
      await openPaperTab();

      expect(panelWidth()).toBe("344px");
    });

    it("is resized from its edge with the arrow keys, and remembered", async () => {
      workspaceAt(1400);
      await openPaperTab();

      edge().focus();
      await userEvent.keyboard("{ArrowLeft}{ArrowLeft}");

      expect(panelWidth()).toBe("498px");
      expect(edge()).toHaveAttribute("aria-valuenow", "498");
      expect(localStorage.getItem(PANEL_WIDTH_KEY)).toBe("498");
    });

    it("keeps what the reader chose, and goes back to 450px on a double click", async () => {
      localStorage.setItem(PANEL_WIDTH_KEY, "600");
      workspaceAt(1500);
      await openPaperTab();
      expect(panelWidth()).toBe("600px");

      await userEvent.dblClick(edge());

      expect(panelWidth()).toBe("450px");
    });
  });
});

describe("sharing the paper (IR-356)", () => {
  const original = Object.getOwnPropertyDescriptor(navigator, "clipboard");
  const stubClipboard = (writeText: () => Promise<void>) =>
    Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });

  beforeEach(() => {
    shownRecord = record;
    signInAs(99, "Student");
  });

  afterEach(() => {
    if (original) Object.defineProperty(navigator, "clipboard", original);
    else delete (navigator as { clipboard?: unknown }).clipboard;
  });

  it("copies the paper's link and says so", async () => {
    const writeText = vi.fn(() => Promise.resolve());
    stubClipboard(writeText);
    renderPaperView();
    await waitForRecord(record.title);

    await userEvent.click(screen.getByRole("button", { name: "Share" }));

    expect(writeText).toHaveBeenCalledWith(`${window.location.origin}/records/${RECORD_ID}`);
    expect(await screen.findByRole("button", { name: "Link copied" })).toBeInTheDocument();
  });

  it("says so when the link cannot be copied, rather than failing silently", async () => {
    stubClipboard(vi.fn(() => Promise.reject(new Error("no permission"))));
    renderPaperView();
    await waitForRecord(record.title);

    await userEvent.click(screen.getByRole("button", { name: "Share" }));

    expect(await screen.findByRole("button", { name: /couldn.t copy/i })).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent(/copy it from the address bar/i);
  });
});

/**
 * Following a citation from Paper Chat (IR-354). Below `lg` the docked chat
 * is a bottom sheet over the paper, so following a citation minimizes it,
 * and the passage lands where the reader can see it. At `lg` it is a column
 * beside the paper and covers nothing, so it stays as it is.
 */
describe("following a citation from Paper Chat (IR-354)", () => {
  const citation = {
    marker: 1,
    chunk_id: 11,
    record_id: RECORD_ID,
    record_title: record.title,
    page: 12,
    text: "the network reduced mean absolute error by twelve per cent",
    context_path: [record.title, "Results"],
    regions: [{ page: 12, left: 0.1, top: 0.85, right: 0.6, bottom: 0.9 }],
  };
  const CITED = { name: `Open ${record.title} at page 12` };

  beforeEach(async () => {
    shownRecord = record;
    signInAs(99, "Student");
    const { aiApi } = await import("@/api/ai");
    vi.mocked(aiApi.conversations.findForRecord).mockImplementation(() =>
      Promise.resolve({
        id: 42, title: "", record: RECORD_ID, record_title: record.title, turn_count: 1,
        created_at: "2026-09-20T00:00:00.000Z", updated_at: "2026-09-20T00:00:00.000Z",
        turns: [
          {
            id: 1, question: "How much did the error fall?", resolved_question: null,
            answer: "By twelve per cent [1].", message: null, state: "generative",
            degraded: false, widened: false, created_at: "2026-09-20T00:00:00.000Z",
            citations: [citation],
          },
        ],
      } as never),
    );
  });

  afterEach(async () => {
    const { aiApi } = await import("@/api/ai");
    vi.mocked(aiApi.conversations.findForRecord).mockImplementation(() => new Promise(() => {}));
    vi.unstubAllGlobals();
  });

  async function followCitationFromChat() {
    renderPaperView();
    await waitForRecord(record.title);
    await userEvent.click(screen.getByRole("tab", { name: "Paper" }));
    await userEvent.click(await screen.findByRole("link", CITED));
    await screen.findByText(/open at page 12, 1 region\(s\)/i);
  }

  it("minimizes the sheet below lg, and restores it with the answer still there", async () => {
    await followCitationFromChat();

    const bar = await screen.findByRole("button", { name: "Ask IRIS: back to the answer" });
    expect(screen.queryByRole("textbox", { name: "Ask about this paper" })).not.toBeInTheDocument();

    await userEvent.click(bar);

    expect(screen.getByRole("link", CITED)).toBeVisible();
    expect(screen.getByRole("textbox", { name: "Ask about this paper" })).toBeInTheDocument();
  });

  it("leaves the docked column as it is in a wide workspace, where it covers nothing", async () => {
    workspaceAt(1200);

    await followCitationFromChat();

    expect(screen.queryByRole("button", { name: "Ask IRIS: back to the answer" })).not.toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "Ask about this paper" })).toBeInTheDocument();
  });

  it("keeps the passage highlighted when the chat is closed and opened again", async () => {
    workspaceAt(1200);
    await followCitationFromChat();

    await userEvent.click(screen.getByRole("button", { name: "Close Ask IRIS" }));
    expect(screen.getByText(/open at page 12, 1 region\(s\)/i)).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Ask IRIS" }));
    await screen.findByRole("complementary", { name: "Ask IRIS" });
    expect(screen.getByText(/open at page 12, 1 region\(s\)/i)).toBeInTheDocument();
  });
});

/**
 * Following a citation to a different paper keeps the conversation it came
 * from (IR-355, decided with the project lead 2026-09-24). With "All papers"
 * on, an answer about X can cite Y. Following it shows Y's paper, but the
 * panel stays on X's conversation, the answer the reader clicked included,
 * until the reader says otherwise or reaches Y some other way.
 */
describe("following a citation to another paper (IR-355)", () => {
  const OTHER_ID = 8;
  const other: RecordDetail = {
    ...record,
    id: OTHER_ID,
    title: "Rainfall Gauge Density and Flood Warning Lead Time",
  };
  const crossCitation = {
    marker: 1,
    chunk_id: 21,
    record_id: OTHER_ID,
    record_title: other.title,
    page: 3,
    text: "denser gauge networks lengthened warning lead time",
    context_path: [other.title, "Results"],
    regions: [{ page: 3, left: 0.1, top: 0.4, right: 0.6, bottom: 0.45 }],
  };
  const samePaperCitation = {
    ...crossCitation,
    marker: 2,
    chunk_id: 11,
    record_id: RECORD_ID,
    record_title: record.title,
    page: 12,
  };
  const ANSWER_ON_X = "Gauge density matters [1], as this paper also finds [2].";
  const QUESTION_ON_Y = "What lead time did the denser network give?";
  const TO_OTHER = { name: `Open ${other.title} at page 3` };
  const TO_SAME = { name: `Open ${record.title} at page 12` };
  const INSTEAD = { name: "Chat about this paper instead" };
  const PINNED_HEADER = /^Chatting about/;

  function turn(id: number, question: string, answer: string, citations: unknown[] = []) {
    return {
      id, question, resolved_question: null, answer, message: null, state: "generative",
      degraded: false, widened: false, created_at: "2026-09-20T00:00:00.000Z", citations,
    };
  }

  const conversations: Record<number, unknown> = {
    [RECORD_ID]: {
      id: 42, title: "", record: RECORD_ID, record_title: record.title, turn_count: 1,
      created_at: "2026-09-20T00:00:00.000Z", updated_at: "2026-09-20T00:00:00.000Z",
      turns: [turn(1, "Does gauge density matter?", ANSWER_ON_X, [crossCitation, samePaperCitation])],
    },
    [OTHER_ID]: {
      id: 43, title: "", record: OTHER_ID, record_title: other.title, turn_count: 1,
      created_at: "2026-09-20T00:00:00.000Z", updated_at: "2026-09-20T00:00:00.000Z",
      turns: [turn(2, QUESTION_ON_Y, "About forty minutes.")],
    },
  };

  /** A record whose detail is held back, to watch the page while it loads. */
  let heldBack: { id: number; release: () => void } | null = null;

  beforeEach(async () => {
    signInAs(99, "Student");
    // In a wide workspace the chat is a column and never minimizes
    // (IR-354), so the transcript stays readable after a citation is followed.
    workspaceAt(1200);

    const { recordsApi } = await import("@/api/records");
    vi.mocked(recordsApi.detail).mockImplementation(((id: number) => {
      const data = id === OTHER_ID ? other : record;
      const held = heldBack;
      if (held?.id === id) {
        return new Promise((resolve) => {
          held.release = () => resolve({ data });
        });
      }
      return Promise.resolve({ data });
    }) as never);

    const { aiApi } = await import("@/api/ai");
    vi.mocked(aiApi.conversations.findForRecord).mockReset();
    vi.mocked(aiApi.conversations.findForRecord).mockImplementation(
      ((id: number) => Promise.resolve(conversations[id])) as never,
    );
    // The atomic first-send POST returns the same default as the GET (IR-561),
    // including when the panel remains pinned to X on Y's page.
    vi.mocked(aiApi.conversations.create).mockImplementation(
      ((body: { record: number }) => Promise.resolve({ data: conversations[body.record] })) as never,
    );
    vi.mocked(aiApi.askStream).mockReset();
    vi.mocked(aiApi.askStream).mockImplementation((async function* () {
      yield {
        event: "done",
        data: {
          answer: "Roughly forty minutes longer.", citations: [], sources: [], message: null,
          mode: "generative", degraded: false, conversation_id: 42, resolved_question: null,
          widened: true,
        },
      };
    }) as never);
  });

  beforeEach(async () => {
    const { aiApi } = await import("@/api/ai");
    vi.mocked(aiApi.conversations.get).mockImplementation(((id: number) => {
      const found = Object.values(conversations).find((c) => (c as { id: number }).id === id);
      return found ? Promise.resolve({ data: found }) : Promise.reject({ response: { status: 404 } });
    }) as never);
  });

  afterEach(async () => {
    heldBack = null;
    vi.unstubAllGlobals();
    const { recordsApi } = await import("@/api/records");
    vi.mocked(recordsApi.detail).mockImplementation((() => Promise.resolve({ data: shownRecord })) as never);
    const { aiApi } = await import("@/api/ai");
    vi.mocked(aiApi.conversations.findForRecord).mockImplementation(() => new Promise(() => {}));
    vi.mocked(aiApi.conversations.create).mockImplementation(
      (() => Promise.resolve({ data: { id: 50, turns: [] } })) as never,
    );
  });

  async function conversationsOpened(): Promise<number[]> {
    const { aiApi } = await import("@/api/ai");
    return vi.mocked(aiApi.conversations.findForRecord).mock.calls.map(([id]) => id as number);
  }

  /**
   * Mounted on its real path, with a plain link to Y beside it: the way a
   * reader reaches Y other than through a citation (Discover, a typed URL,
   * Related works), carrying no router state at all.
   */
  /** The browser's Back and Forward, which `MemoryRouter` takes as `navigate(-1)` and `navigate(1)`. */
  function HistoryButtons() {
    const navigate = useNavigate();
    return (
      <>
        <button type="button" onClick={() => navigate(-1)}>Browser back</button>
        <button type="button" onClick={() => navigate(1)}>Browser forward</button>
      </>
    );
  }

  function renderWithPlainLink() {
    return renderScreen(
      <>
        <Routes>
          <Route path="/records/:id" element={<PaperViewPage />} />
        </Routes>
        <Link to={`/records/${OTHER_ID}`}>Go to the other paper</Link>
        <HistoryButtons />
      </>,
      { route: `/records/${RECORD_ID}` },
    );
  }

  function panel() {
    return screen.getByRole("complementary", { name: "Ask IRIS" });
  }

  /** On X, chat open, "All papers" on, the answer citing Y on screen. */
  async function openChatOnX() {
    const view = renderWithPlainLink();
    await waitForRecord(record.title);
    await userEvent.click(screen.getByRole("button", { name: "Ask IRIS" }));
    await screen.findByText(/Gauge density matters/);
    await userEvent.click(within(panel()).getByRole("button", { name: "This paper" }));
    return view;
  }

  async function followToOtherPaper() {
    const view = await openChatOnX();
    await userEvent.click(within(panel()).getByRole("link", TO_OTHER));
    await screen.findByText(/open at page 3, 1 region\(s\)/i);
    await screen.findByRole("heading", { level: 1, name: other.title });
    return view;
  }

  // IR-578: the way back rides in the address, as ids.
  it("links each Paper Chat citation to its conversation and answer", async () => {
    await openChatOnX();

    expect(within(panel()).getByRole("link", TO_OTHER)).toHaveAttribute(
      "href",
      `/records/${OTHER_ID}?page=3&conversation=42&turn=1&cite=1&from=paper`,
    );
  });

  it("goes back to the Paper Chat answer from the header, after a reload, on the other paper", async () => {
    // A reload of Y keeps the address and loses the panel that followed it.
    renderPaper(`/records/${OTHER_ID}?page=3&conversation=42&turn=1&cite=1&from=paper`);
    await screen.findByRole("heading", { level: 1, name: other.title });
    const opened = await screen.findByRole("complementary", { name: "Ask IRIS" });
    // Nothing is pinned on arrival (IR-355): Y's own conversation shows.
    expect(await within(opened).findByText(QUESTION_ON_Y)).toBeInTheDocument();
    // The passage is re-read through X's conversation, and still highlighted.
    expect(await screen.findByText(/open at page 3, 1 region\(s\)/i)).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Back to answer" }));

    expect(await within(panel()).findByText(/Gauge density matters/)).toBeInTheDocument();
    expect(within(panel()).getByText(PINNED_HEADER)).toHaveTextContent(`Chatting about ${record.title}`);
    expect(within(panel()).queryByText(QUESTION_ON_Y)).not.toBeInTheDocument();
  });

  it("shows Y's paper at the cited passage while the panel keeps X's conversation", async () => {
    await followToOtherPaper();

    expect(within(panel()).getByText(/Gauge density matters/)).toBeVisible();
    expect(within(panel()).getByText(PINNED_HEADER)).toHaveTextContent(`Chatting about ${record.title}`);
    expect(within(panel()).getByRole("button", { name: "All papers" })).toHaveAttribute("aria-pressed", "true");
    expect(await conversationsOpened()).toEqual([RECORD_ID]);
  });

  it("keeps the panel mounted while Y loads, rather than a skeleton over it", async () => {
    const held = { id: OTHER_ID, release: () => {} };
    heldBack = held;
    await openChatOnX();

    await userEvent.click(within(panel()).getByRole("link", TO_OTHER));

    // Y is still loading: the panel and its answer are there all the same.
    expect(screen.queryByRole("heading", { level: 1 })).not.toBeInTheDocument();
    expect(within(panel()).getByText(/Gauge density matters/)).toBeVisible();
    held.release();
    await screen.findByRole("heading", { level: 1, name: other.title });
    expect(within(panel()).getByText(/Gauge density matters/)).toBeVisible();
    expect(await conversationsOpened()).toEqual([RECORD_ID]);
  });

  it("sends a follow-up into X's conversation, with the widen it had", async () => {
    await followToOtherPaper();

    await userEvent.type(
      // Named for X while pinned, not "this paper" (decided 2026-10-06).
      within(panel()).getByRole("textbox", { name: `Ask about ${record.title}` }),
      "How much longer was the lead time?",
    );
    await userEvent.click(within(panel()).getByRole("button", { name: "Send" }));

    const { aiApi } = await import("@/api/ai");
    await waitFor(() => expect(aiApi.askStream).toHaveBeenCalled());
    const [question, options] = vi.mocked(aiApi.askStream).mock.calls[0];
    expect(question).toBe("How much longer was the lead time?");
    expect(options).toMatchObject({ conversationId: 42, widen: true });
  });

  it("switches to Y's own conversation, named Y, on Chat about this paper instead", async () => {
    await followToOtherPaper();

    await userEvent.click(within(panel()).getByRole("button", INSTEAD));

    expect(await within(panel()).findByText(QUESTION_ON_Y)).toBeInTheDocument();
    expect(within(panel()).queryByText(PINNED_HEADER)).not.toBeInTheDocument();
    expect(within(panel()).queryByRole("button", INSTEAD)).not.toBeInTheDocument();
    expect(within(panel()).getByText(other.title)).toBeInTheDocument();
    // The conversation changed, so its scope starts again at this paper.
    expect(within(panel()).getByRole("button", { name: "This paper" })).toHaveAttribute("aria-pressed", "false");
    expect(await conversationsOpened()).toEqual([RECORD_ID, OTHER_ID]);
  });

  it("releases the pin when the panel is closed and opened again", async () => {
    await followToOtherPaper();

    await userEvent.click(within(panel()).getByRole("button", { name: "Close Ask IRIS" }));
    await userEvent.click(screen.getByRole("button", { name: "Ask IRIS" }));

    expect(await within(panel()).findByText(QUESTION_ON_Y)).toBeInTheDocument();
    expect(within(panel()).queryByText(PINNED_HEADER)).not.toBeInTheDocument();
  });

  it("releases the pin when the reader reaches Y some other way", async () => {
    await followToOtherPaper();

    await userEvent.click(screen.getByRole("link", { name: "Go to the other paper" }));

    expect(await within(panel()).findByText(QUESTION_ON_Y)).toBeInTheDocument();
    expect(within(panel()).queryByText(PINNED_HEADER)).not.toBeInTheDocument();
  });

  it("pins nothing on a page that only remembers a citation, as after a reload", async () => {
    // A reload keeps the history entry's state, the mark included, but the
    // panel that followed it is gone: there is no conversation to keep.
    renderPaper(`/records/${OTHER_ID}?page=3`, { citation: crossCitation, origin: "paper-chat" });
    await screen.findByRole("heading", { level: 1, name: other.title });
    // Ask IRIS opens on entry, a render after the record arrives.
    const opened = await screen.findByRole("complementary", { name: "Ask IRIS" });

    expect(await within(opened).findByText(QUESTION_ON_Y)).toBeInTheDocument();
    expect(within(panel()).queryByText(PINNED_HEADER)).not.toBeInTheDocument();
  });

  it("follows a same-paper citation exactly as before: no pin, no header change", async () => {
    await openChatOnX();

    await userEvent.click(within(panel()).getByRole("link", TO_SAME));
    await screen.findByText(/open at page 12, 1 region\(s\)/i);

    expect(within(panel()).queryByText(PINNED_HEADER)).not.toBeInTheDocument();
    expect(within(panel()).getByText(record.title)).toBeInTheDocument();
    expect(await conversationsOpened()).toEqual([RECORD_ID]);
  });

  it("keeps the pin when the reader moves between sections", async () => {
    await followToOtherPaper();

    await userEvent.click(screen.getByRole("tab", { name: "Overview" }));

    expect(within(panel()).getByText(PINNED_HEADER)).toHaveTextContent(`Chatting about ${record.title}`);
    expect(within(panel()).getByText(/Gauge density matters/)).toBeVisible();
    expect(await conversationsOpened()).toEqual([RECORD_ID]);
  });

  // While pinned, "this paper" would read as Y, the paper on screen. The
  // scope control and the composer name X instead (decided 2026-10-06).
  it("names the pinned paper on the scope control and the composer, not 'this paper'", async () => {
    await followToOtherPaper();

    await userEvent.click(within(panel()).getByRole("button", { name: "All papers" }));

    expect(within(panel()).getByRole("button", { name: record.title })).toHaveAttribute("aria-pressed", "false");
    expect(within(panel()).queryByRole("button", { name: "This paper" })).not.toBeInTheDocument();
    expect(within(panel()).getByRole("textbox", { name: `Ask about ${record.title}` })).toBeInTheDocument();
  });

  // A history entry brings back the chat it was left with (decided
  // 2026-10-06): X's entry carries no mark, Y's does.
  it("re-aligns on Back to X, and keeps the pin on Forward to Y", async () => {
    await followToOtherPaper();

    await userEvent.click(screen.getByRole("button", { name: "Browser back" }));
    await screen.findByRole("heading", { level: 1, name: record.title });
    expect(within(panel()).queryByText(PINNED_HEADER)).not.toBeInTheDocument();
    expect(within(panel()).getByText(/Gauge density matters/)).toBeVisible();

    await userEvent.click(screen.getByRole("button", { name: "Browser forward" }));
    await screen.findByRole("heading", { level: 1, name: other.title });
    expect(within(panel()).getByText(PINNED_HEADER)).toHaveTextContent(`Chatting about ${record.title}`);
    expect(await conversationsOpened()).toEqual([RECORD_ID]);
  });

  it("keeps the pin on Back while hopping between the conversation's citations", async () => {
    await followToOtherPaper();
    // A second citation from the same answer, back to X itself.
    await userEvent.click(within(panel()).getByRole("link", TO_SAME));
    await screen.findByRole("heading", { level: 1, name: record.title });

    await userEvent.click(screen.getByRole("button", { name: "Browser back" }));

    await screen.findByRole("heading", { level: 1, name: other.title });
    expect(within(panel()).getByText(PINNED_HEADER)).toHaveTextContent(`Chatting about ${record.title}`);
    expect(await conversationsOpened()).toEqual([RECORD_ID]);
  });

  it("has no serious or critical accessibility violations while pinned", async () => {
    const { container } = await followToOtherPaper();

    await expectNoBlockingA11yViolations(container);
  });
});

// ---------------------------------------------------------------------------
// IR-411: sections, header actions and Edit details, by capability
// ---------------------------------------------------------------------------

/** Where the router is, so a test can read what the page put in the URL. */
function LocationProbe() {
  const location = useLocation();
  return <output aria-label="Location">{`${location.pathname}${location.search}`}</output>;
}

function renderWithProbe(route: string) {
  return renderScreen(
    <>
      <Routes>
        <Route path="/records/:id" element={<PaperViewPage />} />
      </Routes>
      <LocationProbe />
    </>,
    { route },
  );
}

const tabNames = () => screen.getAllByRole("tab").map((tab) => tab.textContent);

describe("the sections follow the capabilities (IR-411)", () => {
  beforeEach(() => vi.clearAllMocks());

  it("gives a reader Overview and Paper only", async () => {
    shownRecord = record;
    signInAs(99, "Student");
    renderPaperView();

    await waitForRecord(record.title);
    expect(tabNames()).toEqual(["Overview", "Paper"]);
  });

  it("gives the owner Review and Files as well", async () => {
    shownRecord = inReview;
    signInAs(OWNER_ID, "Student");
    renderPaperView();

    await waitForRecord(inReview.title);
    expect(tabNames()).toEqual(["Overview", "Paper", "Review", "Files"]);
  });

  it("gives a reviewer the API names Review and Files", async () => {
    shownRecord = { ...inReview, ...reviewing };
    signInAs(2, "ITSO");
    renderPaperView();

    await waitForRecord(inReview.title);
    expect(tabNames()).toEqual(["Overview", "Paper", "Review", "Files"]);
  });

  it("has no Paper section on a record with no paper to read", async () => {
    shownRecord = { ...record, abstract_file: null, files: [] };
    signInAs(99, "Student");
    renderPaperView();

    await waitForRecord(record.title);
    expect(tabNames()).toEqual(["Overview"]);
  });

  it("opens the section the URL names", async () => {
    shownRecord = inReview;
    signInAs(OWNER_ID, "Student");
    renderPaper(`/records/${RECORD_ID}?section=files`);

    expect(await screen.findByRole("tab", { name: "Files", selected: true })).toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: "Supporting documents" })).toBeInTheDocument();
  });

  it("shows Overview, not the section, to a viewer who may not open it", async () => {
    shownRecord = inReview;
    signInAs(99, "Student");
    renderPaper(`/records/${RECORD_ID}?section=files`);

    expect(await screen.findByRole("tab", { name: "Overview", selected: true })).toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: "Files" })).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Supporting documents" })).not.toBeInTheDocument();
  });

  it("keeps the chosen section in the URL, with the rest of the address", async () => {
    shownRecord = inReview;
    signInAs(OWNER_ID, "Student");
    renderWithProbe(`/records/${RECORD_ID}?page=4`);

    await userEvent.click(await screen.findByRole("tab", { name: "Review" }));

    expect(screen.getByRole("tab", { name: "Review", selected: true })).toBeInTheDocument();
    expect(screen.getByRole("status", { name: "Location" })).toHaveTextContent(
      `/records/${RECORD_ID}?page=4&section=review`,
    );
  });

  it("moves between sections with the arrow keys", async () => {
    shownRecord = inReview;
    signInAs(OWNER_ID, "Student");
    renderPaperView();

    const overview = await screen.findByRole("tab", { name: "Overview", selected: true });
    overview.focus();
    await userEvent.keyboard("{ArrowRight}");

    expect(await screen.findByRole("tab", { name: "Paper", selected: true })).toHaveFocus();
  });
});

describe("the header's actions follow the capabilities (IR-411)", () => {
  beforeEach(() => vi.clearAllMocks());

  const draft: RecordDetail = {
    ...inReview,
    pipeline_status: "draft",
    workflow_state: "draft",
    workflow_state_label: "Draft",
    adviser: ASSIGNED_ADVISER_ID,
    // What the server offers the owner; another viewer gets `cite` alone.
    capabilities: ["cite", "continue_draft", "edit_details"],
  };

  it("offers the owner of a draft Continue, into Publish, as the one primary action", async () => {
    shownRecord = draft;
    signInAs(OWNER_ID, "Student");
    renderPaperView();

    const resume = await screen.findByRole("link", { name: "Continue" });
    expect(resume).toHaveAttribute("href", `/?publish=${RECORD_ID}`);
    expect(screen.getByRole("button", { name: "Edit details" })).toBeInTheDocument();
  });

  it("offers no author action on a rejected record (invariant 5)", async () => {
    shownRecord = { ...inReview, pipeline_status: "rejected", workflow_state: "rejected", workflow_state_label: "Rejected" };
    signInAs(OWNER_ID, "Student");
    renderPaperView();

    await waitForRecord(inReview.title);
    expect(screen.getByText("This record was rejected")).toBeInTheDocument();
    for (const name of [/^Continue/, /Edit details/, /New version/, /Resubmit/]) {
      expect(screen.queryByRole("button", { name })).not.toBeInTheDocument();
      expect(screen.queryByRole("link", { name })).not.toBeInTheDocument();
    }
  });

  it.each([
    ["in review", { workflow_state: "in_review" as const }],
    ["published", { pipeline_status: "published" as const, workflow_state: "published" as const }],
    ["approved", { pipeline_status: "approved" as const, workflow_state: "approved" as const }],
  ])("offers no Edit details on a record that is %s", async (_label, overrides) => {
    shownRecord = { ...inReview, ...overrides };
    signInAs(OWNER_ID, "Student");
    renderPaper(`/records/${RECORD_ID}?edit=details`);

    await waitForRecord(inReview.title);
    expect(screen.queryByRole("button", { name: "Edit details" })).not.toBeInTheDocument();
    expect(screen.queryByRole("dialog", { name: "Edit details" })).not.toBeInTheDocument();
  });

  it("offers Edit details to the owner while a revision is requested", async () => {
    shownRecord = {
      ...inReview, workflow_state: "awaiting_resubmission", workflow_state_label: "Revision requested",
      capabilities: ["cite", "edit_details"],
    };
    signInAs(OWNER_ID, "Student");
    renderPaperView();

    expect(await screen.findByRole("button", { name: "Edit details" })).toBeInTheDocument();
  });

  it("offers nobody but the owner Edit details on a draft", async () => {
    shownRecord = { ...draft, capabilities: ["cite"] };
    signInAs(99, "Student");
    renderPaperView();

    await waitForRecord(inReview.title);
    expect(screen.queryByRole("button", { name: "Edit details" })).not.toBeInTheDocument();
  });

  it("edits the details in a dialog, and the page shows the change at once", async () => {
    shownRecord = draft;
    signInAs(OWNER_ID, "Student");
    renderWithProbe(`/records/${RECORD_ID}`);

    await userEvent.click(await screen.findByRole("button", { name: "Edit details" }));
    const dialog = await screen.findByRole("dialog", { name: "Edit details" });
    const title = await within(dialog).findByRole("textbox", { name: /Title/ });
    await userEvent.clear(title);
    await userEvent.type(title, "Groundwater Recharge Mapping, Revised");
    shownRecord = { ...draft, title: "Groundwater Recharge Mapping, Revised" };
    await userEvent.click(within(dialog).getByRole("button", { name: "Save details" }));

    expect(await screen.findByRole("heading", { level: 1, name: "Groundwater Recharge Mapping, Revised" })).toBeInTheDocument();
    expect(screen.queryByRole("dialog", { name: "Edit details" })).not.toBeInTheDocument();
    expect(recordsApi.update).toHaveBeenCalledWith(
      RECORD_ID,
      expect.objectContaining({ title: "Groundwater Recharge Mapping, Revised" }),
    );
    expect(screen.getByRole("status", { name: "Location" })).toHaveTextContent(`/records/${RECORD_ID}`);
    expect(screen.getByRole("status", { name: "Location" })).not.toHaveTextContent("edit=");
  });

  it("opens Edit details from the old edit page's address", async () => {
    shownRecord = draft;
    signInAs(OWNER_ID, "Student");
    renderPaper(`/records/${RECORD_ID}?edit=details`);

    expect(await screen.findByRole("dialog", { name: "Edit details" })).toBeInTheDocument();
  });
});

// The Review section (IR-412; spec §4.7): the paper, the timeline beside it,
// and an action bar whose buttons are the capabilities adapter's, nothing
// else. Ask IRIS is not part of it (spec §4.6, decided 2026-09-26).
describe("the Review section (IR-412)", () => {
  const trackerPayload = {
    record_id: RECORD_ID,
    record_type: "Thesis / Research",
    workflow_state: "in_review",
    workflow_state_label: "In review",
    current_holders: [],
    parties: [],
    routing_history: [
      {
        group_id: "g1", from: null, from_label: null, to: ["itso"], to_labels: ["ITSO"],
        actor: "Rhea Owner", reason: "", at: "2026-09-01T08:00:00Z",
      },
    ],
    routing_recorded_from: null,
    reviews: [],
    versions: [],
    resubmissions: [],
    document_requests: [],
    clearances: [],
    resubmission: { count: 0, last_resubmitted_at: null, declining_office: null, offices_preserved: [] },
  };

  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(recordsApi.tracker).mockResolvedValue({ data: trackerPayload } as never);
  });

  afterEach(() => {
    vi.mocked(recordsApi.tracker).mockImplementation(() => Promise.reject(new Error("not under test")));
  });

  const bar = () => screen.getByRole("toolbar", { name: "Review actions" });

  it("puts the paper beside the timeline, from the tracker", async () => {
    shownRecord = { ...inReview, ...reviewing };
    signInAs(2, "ITSO");
    const { container } = renderPaper(`/records/${RECORD_ID}?section=review`);

    expect(await screen.findByText(/paper reader open at page none/i)).toBeInTheDocument();
    const timeline = await screen.findByRole("list", { name: "Review timeline" });
    expect(within(timeline).getByText("Submitted to ITSO")).toBeInTheDocument();
    expect(recordsApi.tracker).toHaveBeenCalledWith(RECORD_ID);
    await expectNoBlockingA11yViolations(container);
  });

  it("offers a reviewer who may request documents exactly that action", async () => {
    shownRecord = { ...inReview, can_request_document: ["ierc"], capabilities: ["cite", "request_document"] };
    signInAs(2, "IERC");
    renderPaper(`/records/${RECORD_ID}?section=review`);

    await screen.findByRole("tab", { name: "Review", selected: true });
    expect(within(bar()).getAllByRole("button").map((b) => b.textContent?.trim())).toEqual([
      "Request documents",
    ]);
    expect(within(bar()).queryByRole("link", { name: "Record a decision (current form)" })).not.toBeInTheDocument();
  });

  it("offers Request documents alone to a party that may ask but not decide", async () => {
    shownRecord = { ...inReview, can_request_document: ["ierc"], capabilities: ["cite", "request_document"] };
    signInAs(2, "IERC");
    renderPaper(`/records/${RECORD_ID}?section=review`);

    await screen.findByRole("tab", { name: "Review", selected: true });
    expect(within(bar()).getByRole("button", { name: "Request documents" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Record a decision (current form)" })).not.toBeInTheDocument();
  });

  it("gives an owner the timeline and no action bar: nothing was granted", async () => {
    shownRecord = inReview;
    signInAs(OWNER_ID, "Student");
    renderPaper(`/records/${RECORD_ID}?section=review`);

    await screen.findByRole("list", { name: "Review timeline" });
    expect(screen.queryByRole("toolbar", { name: "Review actions" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Request documents" })).not.toBeInTheDocument();
  });

  it("requests documents from the bar and re-reads the timeline after", async () => {
    shownRecord = { ...inReview, can_request_document: ["ierc"], capabilities: ["cite", "request_document"] };
    signInAs(2, "IERC");
    renderPaper(`/records/${RECORD_ID}?section=review`);

    await userEvent.click(await screen.findByRole("button", { name: "Request documents" }));
    const dialog = screen.getByRole("dialog", { name: "Request documents" });
    await userEvent.click(await within(dialog).findByRole("checkbox", { name: "Ethics Clearance" }));
    await userEvent.type(within(dialog).getByRole("textbox", { name: /Message to the owner/ }), "Please.");
    await userEvent.click(within(dialog).getByRole("button", { name: "Send request" }));

    expect(await screen.findByText("Documents requested. The owner has been notified.")).toBeInTheDocument();
    await waitFor(() => expect(recordsApi.tracker).toHaveBeenCalledTimes(2));
  });

  it("has no Ask IRIS, and Ask about this paper takes the reader to the Paper tab with the chat open", async () => {
    shownRecord = { ...inReview, ...reviewing };
    signInAs(2, "ITSO");
    renderWithProbe(`/records/${RECORD_ID}?section=review`);

    await screen.findByRole("list", { name: "Review timeline" });
    expect(screen.queryByRole("complementary", { name: "Ask IRIS" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Ask IRIS" })).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Ask about this paper" }));

    expect(await screen.findByRole("tab", { name: "Paper", selected: true })).toBeInTheDocument();
    expect(await screen.findByRole("complementary", { name: "Ask IRIS" })).toBeInTheDocument();
    expect(screen.getByRole("status", { name: "Location" })).toHaveTextContent(
      `/records/${RECORD_ID}?section=paper`,
    );
  });

  it("offers no Ask about this paper when there is no paper to ask about", async () => {
    shownRecord = { ...inReview, abstract_file: null, files: [], ...reviewing };
    signInAs(2, "ITSO");
    renderPaper(`/records/${RECORD_ID}?section=review`);

    await screen.findByRole("list", { name: "Review timeline" });
    expect(screen.queryByText(/paper reader open/i)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Ask about this paper" })).not.toBeInTheDocument();
  });

  it("lands a citation on its passage in the Review section's reader too", async () => {
    shownRecord = { ...inReview, ...reviewing };
    signInAs(2, "ITSO");
    const citation = {
      marker: 1, chunk_id: 11, record_id: RECORD_ID, record_title: inReview.title, page: 3,
      text: "recharge rates fell", context_path: [inReview.title],
      regions: [{ page: 3, left: 0.1, top: 0.4, right: 0.6, bottom: 0.45 }],
    };
    renderPaper(`/records/${RECORD_ID}?section=review&page=3`, { citation });

    expect(await screen.findByRole("tab", { name: "Review", selected: true })).toBeInTheDocument();
    expect(await screen.findByText(/open at page 3, 1 region\(s\)/i)).toBeInTheDocument();
  });
});

describe("a record the viewer cannot read (IR-411)", () => {
  it("shows the same not-found state as a missing record", async () => {
    vi.mocked(recordsApi.detail).mockRejectedValueOnce({ response: { status: 404, data: { detail: "Not found." } } });
    signInAs(99, "Student");
    renderPaperView();

    expect(await screen.findByRole("heading", { name: "Record not available" })).toBeInTheDocument();
    expect(screen.queryByRole("tablist")).not.toBeInTheDocument();
  });

  it("says a failed load failed, rather than calling the record missing, and tries again", async () => {
    shownRecord = record;
    vi.mocked(recordsApi.detail).mockRejectedValueOnce(new Error("Network Error"));
    signInAs(99, "Student");
    renderPaperView();

    expect(await screen.findByRole("heading", { name: "We couldn't load this record" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Record not available" })).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    await waitForRecord(record.title);
  });
});

// Record versions (IR-416; ADR-032 §5 Amendment). The server sends
// `versions` only to a participant, so what is under test here is what the
// page does with the list it was given.
describe("record versions (IR-416)", () => {
  const version = (number: number, cause: "submission" | "revision", manuscript = true) => ({
    number,
    cause,
    cause_label: cause === "submission" ? "Submission" : "Revision",
    created_at: `2026-09-0${number}T08:00:00Z`,
    created_by_name: "Rhea Owner",
    manuscript_url: manuscript ? `/api/v1/records/${RECORD_ID}/versions/${number}/manuscript/` : null,
  });
  const twoVersions = [version(1, "submission"), version(2, "revision")];
  const PICKER = { name: "Version" };

  beforeEach(() => {
    signInAs(99, "Student");
  });

  it("offers no picker with one version, or with none disclosed", async () => {
    for (const versions of [[version(1, "submission")], null]) {
      shownRecord = { ...record, versions };
      const { unmount } = renderPaperView();
      await waitForRecord(record.title);

      expect(screen.queryByRole("combobox", PICKER)).not.toBeInTheDocument();
      expect(screen.queryByText(/^v1\b/)).not.toBeInTheDocument();
      unmount();
    }
  });

  it("lists every version, the newest marked current and chosen", async () => {
    shownRecord = { ...record, versions: twoVersions };
    const { container } = renderPaperView();
    await waitForRecord(record.title);

    const picker = screen.getByRole("combobox", PICKER);
    expect(picker).toHaveValue("2");
    expect(within(picker).getByRole("option", { name: /^v2 · Revision · .* \(current\)$/ })).toBeInTheDocument();
    expect(within(picker).getByRole("option", { name: /^v1 · Submission/ })).toBeInTheDocument();
    await expectNoBlockingA11yViolations(container);
  });

  it("opens an earlier version on the Paper tab, says so, and drops a citation's page and highlight", async () => {
    shownRecord = { ...record, versions: twoVersions };
    const citation = {
      marker: 1, chunk_id: 11, record_id: RECORD_ID, record_title: record.title,
      page: 4, text: "a passage", context_path: [record.title],
      regions: [{ page: 4, left: 0.1, top: 0.2, right: 0.6, bottom: 0.3 }],
    };
    renderPaper(`/records/${RECORD_ID}?page=4`, { citation });
    expect(await screen.findByText(/open at page 4, 1 region\(s\) to highlight, reading the current paper/i))
      .toBeInTheDocument();

    await userEvent.selectOptions(screen.getByRole("combobox", PICKER), "1");

    expect(await screen.findByText(/open at page none, 0 region\(s\) to highlight, reading v1/i))
      .toBeInTheDocument();
    expect(screen.getByText("You are viewing v1 of 2")).toBeInTheDocument();
    expect(screen.getByText("Citation highlights and Ask IRIS use the current version.")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Back to current" }));

    expect(await screen.findByText(/reading the current paper/i)).toBeInTheDocument();
    expect(screen.queryByText("You are viewing v1 of 2")).not.toBeInTheDocument();
    expect(screen.getByRole("combobox", PICKER)).toHaveValue("2");
  });

  it("moves from Overview to the Paper tab when a version is chosen", async () => {
    shownRecord = { ...record, versions: twoVersions };
    renderPaperView();
    await waitForRecord(record.title);
    expect(screen.getByRole("tab", { name: "Overview", selected: true })).toBeInTheDocument();

    await userEvent.selectOptions(screen.getByRole("combobox", PICKER), "1");

    expect(await screen.findByRole("tab", { name: "Paper", selected: true })).toBeInTheDocument();
    expect(await screen.findByText(/reading v1/i)).toBeInTheDocument();
  });

  it("lets an owner with an unsubmitted revision still read the submitted latest version (IR-273)", async () => {
    shownRecord = { ...record, versions: twoVersions, manuscript_unsubmitted: true };
    signInAs(OWNER_ID, "Student");
    renderPaper(`/records/${RECORD_ID}?section=paper`);
    expect(await screen.findByText("Your revised manuscript, not yet submitted")).toBeInTheDocument();
    expect(screen.getByText("Ask IRIS answers about the submitted version (v2) until you submit."))
      .toBeInTheDocument();

    const picker = screen.getByRole("combobox", PICKER);
    expect(picker).toHaveValue("");
    expect(within(picker).getByRole("option", { name: "Your revision · not yet submitted (current)" }))
      .toBeInTheDocument();
    expect(within(picker).queryByRole("option", { name: /^v2 .*\(current\)$/ })).not.toBeInTheDocument();

    await userEvent.selectOptions(picker, "2");

    expect(await screen.findByText(/reading v2/i)).toBeInTheDocument();
  });

  it("tells Paper Chat's reader that answers are about the current version", async () => {
    shownRecord = { ...record, versions: twoVersions };
    renderPaper(`/records/${RECORD_ID}?section=paper&version=1`);
    await screen.findByText(/reading v1/i);

    const panel = await screen.findByRole("complementary", { name: "Ask IRIS" });
    expect(within(panel).getByText("Answers are about the current version, not v1.")).toBeInTheDocument();
  });

  it("reads the current paper for a version that is current, missing or has no manuscript", async () => {
    shownRecord = {
      ...record,
      versions: [version(1, "submission", false), version(2, "revision"), version(3, "revision")],
    };
    for (const asked of ["3", "1", "9"]) {
      const { unmount } = renderPaper(`/records/${RECORD_ID}?section=paper&version=${asked}`);

      expect(await screen.findByText(/reading the current paper/i)).toBeInTheDocument();
      expect(screen.queryByText(/You are viewing/)).not.toBeInTheDocument();
      unmount();
    }
    const { unmount } = renderPaperView();
    await waitForRecord(record.title);
    expect(
      within(screen.getByRole("combobox", PICKER)).getByRole("option", { name: /^v1 .*\(no manuscript\)$/ }),
    ).toBeDisabled();
    unmount();
  });
});

// ---------------------------------------------------------------------------
// IR-569: the Overview is one reading column, and View is its filled action
// ---------------------------------------------------------------------------

describe("the Overview's header (IR-569)", () => {
  beforeEach(() => {
    shownRecord = record;
    signInAs(99, "Student");
  });

  it("fills View, which opens the paper, and leaves Save outlined", async () => {
    renderWithProbe(`/records/${RECORD_ID}`);
    await waitForRecord(record.title);

    const view = screen.getByRole("button", { name: "View" });
    expect(view).toHaveClass(...PILL_PRIMARY.split(" "));
    expect(screen.getByRole("button", { name: "Save to collection" })).not.toHaveClass("bg-brand");

    await userEvent.click(view);

    expect(await screen.findByRole("tab", { name: "Paper", selected: true })).toBeInTheDocument();
    expect(screen.getByRole("status", { name: "Location" })).toHaveTextContent("section=paper");
  });

  it("fills Save instead where there is no paper to view", async () => {
    shownRecord = { ...record, abstract_file: null, files: [] };
    renderPaperView();
    await waitForRecord(record.title);

    expect(screen.queryByRole("button", { name: "View" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save to collection" })).toHaveClass("bg-brand");
  });

  it("lists the authors as chips, and says what the record is", async () => {
    renderPaperView();
    await waitForRecord(record.title);

    const authors = screen.getByRole("list", { name: "Authors" });
    expect(within(authors).getByText("R. Dela Cruz")).toBeInTheDocument();
    expect(screen.getAllByText("Thesis/Research").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Applied Research").length).toBeGreaterThan(0);
  });

  it("holds governance and documents in Record details, beside the page", async () => {
    renderPaperView();
    await waitForRecord(record.title);

    const details = screen.getByRole("complementary", { name: "Record details" });
    expect(within(details).getByRole("heading", { name: "Institutional Governance" })).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Record details" })).not.toBeInTheDocument();
  });

  it("sets the reading sections apart with hairlines, and draws Comments last (IR-569)", async () => {
    renderPaperView();
    await waitForRecord(record.title);

    const abstract = screen.getByRole("heading", { level: 2, name: "Abstract" }).closest("section");
    const group = abstract?.parentElement;
    expect(group).toHaveClass("divide-y", "divide-stone-200");
    const sections = within(group as HTMLElement).getAllByRole("heading", { level: 2 });
    expect(sections[sections.length - 1]).toHaveTextContent("Comments");
  });
});

describe("the section tabs (IR-569)", () => {
  beforeEach(() => {
    shownRecord = record;
    signInAs(99, "Student");
  });

  it("slides one thumb to the chosen tab", async () => {
    renderPaperView();
    await waitForRecord(record.title);
    const thumb = screen.getByRole("tablist").firstElementChild as HTMLElement;
    expect(thumb).toHaveAttribute("aria-hidden", "true");
    expect(thumb.style.transform).toBe("translateX(0%)");

    await userEvent.click(screen.getByRole("tab", { name: "Paper" }));

    expect(thumb.style.transform).toBe("translateX(100%)");
    // Half the track less its padding, as the browser normalises it.
    expect(thumb.style.width).toMatch(/^calc\((0\.5 \* \(100% - 4px\)|\(100% - 4px\) \/ 2)\)$/);
  });
});

describe("back to the answer after following a citation (IR-578)", () => {
  const CONVERSATION = 12;
  const TURN = 88;
  /** The passage as it reads now: page 14, running onto 15. */
  const current = {
    marker: 1,
    chunk_id: 31,
    record_id: RECORD_ID,
    record_title: record.title,
    page: 14,
    text: "the network reduced mean absolute error by twelve per cent",
    context_path: [record.title, "Results"],
    regions: [
      { page: 14, left: 0.1, top: 0.8, right: 0.9, bottom: 0.95 },
      { page: 15, left: 0.1, top: 0.05, right: 0.9, bottom: 0.1 },
    ],
  };
  const ADDRESS = `/records/${RECORD_ID}?page=12&conversation=${CONVERSATION}&turn=${TURN}&cite=1`;

  function answeredWith(citations: unknown[]) {
    return {
      data: {
        id: CONVERSATION, title: "Flood prediction", record: null, record_title: null, turn_count: 1,
        created_at: "2026-10-20T00:00:00.000Z", updated_at: "2026-10-20T00:00:00.000Z",
        turns: [{
          id: TURN, question: "How accurate is it?", resolved_question: null,
          answer: "Twelve per cent better [1].", message: null, state: "generative",
          degraded: false, widened: false, created_at: "2026-10-20T00:00:00.000Z", citations,
        }],
      },
    };
  }

  async function conversationReads(result: () => Promise<unknown>) {
    const { aiApi } = await import("@/api/ai");
    vi.mocked(aiApi.conversations.get).mockReset();
    vi.mocked(aiApi.conversations.get).mockImplementation(result as never);
    return vi.mocked(aiApi.conversations.get);
  }

  function renderWithAskIris(route: string) {
    function Where() {
      const location = useLocation();
      return <p>Ask IRIS at {location.pathname + location.search}</p>;
    }
    return renderScreen(
      <Routes>
        <Route path="/records/:id" element={<PaperViewPage />} />
        <Route path="/ai/conversations/:conversationId" element={<Where />} />
      </Routes>,
      { route },
    );
  }

  beforeEach(() => {
    shownRecord = record;
    signInAs(99, "Student");
  });

  it("re-reads the citation through the reader's own conversation after a reload", async () => {
    const get = await conversationReads(() => Promise.resolve(answeredWith([current])));

    renderPaper(ADDRESS);

    // The page it reads now wins over the one the address was written with,
    // and a passage over two pages keeps both.
    expect(await screen.findByText(/open at page 14, 2 region\(s\)/i)).toBeInTheDocument();
    expect(get).toHaveBeenCalledWith(CONVERSATION);
  });

  it("lands only once the citation is re-read, on the page it reads now", async () => {
    let answer: (value: unknown) => void = () => {};
    await conversationReads(() => new Promise((resolve) => { answer = resolve; }));

    renderPaper(ADDRESS);

    // The Paper section opens at once; the reader waits rather than landing
    // on page 12 and staying there when the re-read says 14.
    expect(await screen.findByRole("tab", { name: "Paper", selected: true })).toBeInTheDocument();
    expect(await screen.findByText(/open at page none, 0 region\(s\)/i)).toBeInTheDocument();
    await act(async () => answer(answeredWith([current])));
    expect(await screen.findByText(/open at page 14, 2 region\(s\)/i)).toBeInTheDocument();
  });

  it("does not trust the router state a reload kept", async () => {
    await conversationReads(() => Promise.resolve(answeredWith([current])));
    const stale = {
      citation: { ...current, page: 12, regions: [{ page: 12, left: 0, top: 0, right: 1, bottom: 1 }] },
      answer: { conversationId: CONVERSATION, turnId: TURN, load: "an earlier page load" },
    };

    renderPaper(ADDRESS, stale);

    expect(await screen.findByText(/open at page 14, 2 region\(s\)/i)).toBeInTheDocument();
  });

  it("needs no fetch for a citation followed in this page load", async () => {
    const get = await conversationReads(() => Promise.resolve(answeredWith([current])));

    renderPaper(
      `/records/${RECORD_ID}?page=14&conversation=${CONVERSATION}&turn=${TURN}&cite=1`,
      citationNavigationState(current, null, { conversationId: CONVERSATION, turnId: TURN }),
    );

    expect(await screen.findByText(/open at page 14, 2 region\(s\)/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Back to answer" })).toBeInTheDocument();
    expect(get).not.toHaveBeenCalled();
  });

  it("lands a re-chunked passage on its page, highlights nothing, and says so", async () => {
    await conversationReads(() =>
      Promise.resolve(answeredWith([{ marker: 1, record_id: RECORD_ID, chunk_id: 31, page: 9 }])),
    );

    renderPaper(ADDRESS);

    expect(await screen.findByText(/open at page 9, 0 region\(s\)/i)).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent(
      "The passage this answer quoted has changed since, so nothing is highlighted. Page 9 is where it was when the answer was written.",
    );
  });

  it("highlights nothing from a citation into another paper", async () => {
    await conversationReads(() => Promise.resolve(answeredWith([{ ...current, record_id: 8 }])));

    renderPaper(ADDRESS);

    expect(await screen.findByRole("status")).toHaveTextContent("That citation points at another paper, so nothing is highlighted here.");
    expect(screen.getByText(/open at page 12, 0 region\(s\)/i)).toBeInTheDocument();
  });

  it("highlights nothing from a citation the answer no longer has", async () => {
    await conversationReads(() => Promise.resolve(answeredWith([])));

    renderPaper(ADDRESS);

    expect(await screen.findByRole("status")).toHaveTextContent(/no longer part of the answer/);
    expect(screen.getByText(/open at page 12, 0 region\(s\)/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Back to answer" })).toBeInTheDocument();
  });

  it("offers no way back into a conversation that is not the reader's", async () => {
    // Someone else's reads exactly like a missing one (IR-548).
    await conversationReads(() => Promise.reject({ response: { status: 404 } }));

    renderPaper(ADDRESS);

    expect(await screen.findByRole("status")).toHaveTextContent(/answer this citation came from is no longer available/);
    expect(screen.getByText(/open at page 12, 0 region\(s\)/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Back to answer" })).not.toBeInTheDocument();
  });

  it("goes back to the Ask IRIS answer from the reading header", async () => {
    await conversationReads(() => Promise.resolve(answeredWith([current])));
    renderWithAskIris(ADDRESS);
    await screen.findByText(/open at page 14/i);

    await userEvent.click(screen.getByRole("button", { name: "Back to answer" }));

    expect(await screen.findByText(`Ask IRIS at /ai/conversations/${CONVERSATION}?turn=${TURN}`)).toBeInTheDocument();
  });

  it("offers no way back on a paper reached without an answer", async () => {
    renderPaper(`/records/${RECORD_ID}?page=12`);

    await screen.findByText(/open at page 12/i);
    expect(screen.queryByRole("button", { name: "Back to answer" })).not.toBeInTheDocument();
  });

  it("marks only the stated page of an Overview citation, and calls it page context", async () => {
    // A page citation gathers every chunk on the page, one of which runs over.
    renderPaper(`/records/${RECORD_ID}?page=14&context=page`, citationNavigationState(current, "overview"));

    expect(await screen.findByText(/open at page 14, 1 region\(s\)/i)).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent(
      "Page context: the Overview drew on page 14 as a whole, so only page 14 is marked.",
    );
  });

  it("still lands an Overview page as page context after a reload, marking nothing it cannot recheck", async () => {
    // A reload keeps router state; an Overview page cannot be re-read from
    // its address, so the kept highlight is dropped, and the note says only
    // what is true.
    const kept = { citation: current, origin: "overview", load: "an earlier page load" };

    renderPaper(`/records/${RECORD_ID}?page=14&context=page`, kept);

    expect(await screen.findByText(/open at page 14, 0 region\(s\)/i)).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("Page context: the Overview drew on page 14 as a whole.");
  });
});
