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
import { afterEach, beforeEach, describe, expect, it, onTestFinished, vi } from "vitest";
import { importedReference } from "@/test/fixtures/importedReference";
import { Route, Routes, useLocation } from "react-router-dom";

import { expectNoBlockingA11yViolations } from "@/test/axe";
import { act, fireEvent, renderScreen, screen, userEvent, waitFor, within } from "@/test/render";
import { useAuthStore } from "@/store/auth.store";
import { selectSidebarCollapsed, useUIStore } from "@/store/ui.store";
import type { User } from "@/types/auth";
import type { PaperDetails, PaperPerson, Readiness, ReadinessItem, RecordDetail, ReviewerSeat } from "@/types/records";

import { documentsApi } from "@/api/documents";
import { recordsApi } from "@/api/records";
import { libraryApi } from "@/api/library";
import { RequestTimeoutError } from "@/api/requestPolicy";
import { seatsApi } from "@/api/reviews";

import { PILL_PRIMARY } from "@/components/ui/pillStyles";
import { CORNER_CLEARANCE_CLASS } from "./AskIrisFab";
import { PANEL_WIDTH_KEY } from "./PaperChatDock";
import PaperViewPage from "./PaperViewPage";
import { citationNavigationState } from "@/lib/citedPage";
import { formatDate } from "@/lib/utils";

vi.mock("@/config/institution", () => ({
  INSTITUTION: { name: "Example Research University", shortName: "ERU", logo: "example.png", seal: "example-seal.png", emailDomain: "example.edu" },
}));

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
  routing: { send_to_rdco: false, route_as: null, targets: [] },
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
  routing: { send_to_rdco: false, route_as: null, targets: [] },
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
    manuscriptBlob: vi.fn(() => Promise.resolve({ data: new Blob(["pdf"]) })),
    versionManuscriptBlob: vi.fn(() => Promise.resolve({ data: new Blob(["pdf"]) })),
    detail:           vi.fn(() => Promise.resolve({ data: shownRecord })),
    publicComments:   vi.fn(() => Promise.resolve({ data: { comments: [], count: 0 } })),
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
    // Request review, from the sidebar's Reviewers (IR-685); the dialog's own
    // behaviour is `RouteDialog.test.tsx`'s.
    routeOptions:     vi.fn(() => Promise.resolve({ data: {
      from_party: "itso", from_label: "ITSO", accept: false,
      targets: [{ party: "ierc", label: "IERC", members: [], already_holds: false, author_hint: null }],
    } })),
    route:            vi.fn(() => Promise.resolve({ data: {} })),
    updateTags:       vi.fn(),
    // The embargo card's acts (IR-817); its own behaviour is `EmbargoCard.test.tsx`'s.
    setEmbargo:       vi.fn(),
    releaseEmbargo:   vi.fn(() => Promise.resolve({ data: { state: "released", until: "2099-01-01" } })),
    publishUnlisted:  vi.fn(() => Promise.resolve({ data: { pipeline_status: "published" } })),
    releaseIp:        vi.fn(),
    // RDCO's acts on a paper in review (IR-798); their own behaviour is `RdcoPaperControls.test.tsx`'s.
    rdcoWithdraw:     vi.fn(() => Promise.resolve({ data: { id: 7, withdrawn: true } })),
    // The Contact person card (IR-803); its own behaviour is `ContactPersonCard.test.tsx`'s.
    changeContactPerson: vi.fn(() => Promise.resolve({ data: { owners: [] } })),
    // Edit details (IR-411); its own behaviour is `EditDetailsDialog.test.tsx`'s.
    update:           vi.fn(() => Promise.resolve({ data: {} })),
    classifications:  vi.fn(() => Promise.resolve(page([]))),
    pscedList:        vi.fn(() => Promise.resolve(page([]))),
  },
}));

// The Documents tab loads itself; its behaviour is `DocumentsTab.test.tsx`'s.
vi.mock("@/api/documents", () => ({
  documentsApi: {
    downloadFile: vi.fn(() => Promise.resolve({ data: new Blob(["attachment"]) })),
    // An image in the reader reads its bytes itself (IR-1203); a PDF's go to the reader stand-in.
    viewFile: vi.fn(),
    slotsForRecord: vi.fn(() => Promise.resolve({ data: [] })),
    files:          vi.fn(() => Promise.resolve({ data: [] })),
  },
}));
// The Save menu reads the account library (IR-566); this page's tests start empty.
vi.mock("@/api/library", () => ({
  libraryApi: {
    saves: vi.fn(() => Promise.resolve({ data: { results: [] } })),
    save: vi.fn(),
    unsave: vi.fn(),
    // The reader's own folders (IR-572): read with the saves by the Save menu.
    folders: vi.fn(() => Promise.resolve({ data: { results: [], limit: 10 } })),
    createFolder: vi.fn(),
    renameFolder: vi.fn(),
    deleteFolder: vi.fn(),
    fileInFolder: vi.fn(),
    removeFromFolder: vi.fn(),
    // Private notes (IR-580): read only once Notes is first opened.
    note: vi.fn(() => Promise.resolve({ data: { body: "", revision: 0, updated_at: null } })),
    saveNote: vi.fn(),
    // Highlights (IR-583): read whenever the paper is shown, so the reader can draw them.
    highlights: vi.fn(() => Promise.resolve({ data: { results: [] } })),
    saveHighlight: vi.fn(),
    deleteHighlight: vi.fn(),
    // Reading history (IR-756): the page tells the account a paper was opened.
    preferences: vi.fn(() => Promise.resolve({ data: { keep_history: true } })),
    visit: vi.fn(() => Promise.resolve({})),
  },
}));

vi.mock("@/api/accounts", () => ({
  accountsApi: { listAdvisers: vi.fn(() => Promise.resolve(page([]))) },
}));

vi.mock("@/api/reviews", () => ({
  reviewsApi: { resubmit: vi.fn() },
  seatsApi: { open: vi.fn(() => Promise.resolve({ data: {} })), claim: vi.fn(() => Promise.resolve({ data: {} })) },
}));

// The AI overview reads its own cache; this screen is not what that
// behaviour is tested through (`PaperAiOverview.test.tsx` is).
vi.mock("@/api/ai", () => ({
  aiApi: {
    overview: vi.fn(() => Promise.reject(new Error("not under test"))),
    conversations: {
      // A citation re-resolved from its address after a reload (IR-578).
      get:           vi.fn(() => Promise.reject(new Error("not under test"))),
    },
  },
}));

// `PaperPdfReader` fetches and renders real PDF bytes through pdf.js, which
// jsdom cannot do at all (no canvas 2D context, no worker) and which is this
// component's own test file's job (`PaperPdfReader.test.tsx`). This screen
// only has to hand it the right props -- asserted below by rendering what
// they were.
/** The passage the mocked reader says the reader selected (IR-583). */
const SELECTED = {
  page: 3, quote: "robot arm", prefix: "A ", suffix: ", and another",
  regions: [{ page: 3, left: 0.1, top: 0.5, right: 0.4, bottom: 0.52 }],
};

vi.mock("./PaperPdfReader", () => ({
  PaperPdfReader: ({
    scrollToPage,
    highlightRegions,
    toolbarStart,
    version,
    highlights,
    selectionActions,
    clearCorner,
    downloadControl,
    keepPlace,
    document: shownDocument,
  }: {
    document?: { kind: string; id: number } | null;
    clearCorner?: boolean;
    downloadControl?: ReactNode;
    keepPlace?: boolean;
    scrollToPage: number | null;
    highlightRegions: unknown[];
    toolbarStart?: ReactNode;
    version?: number | null;
    highlights?: { key: string | number }[];
    selectionActions?: { id: string; label: string; run: (passage: unknown, revision: string | null) => void }[];
  }) => (
    <>
      <div>
        {toolbarStart}
        Paper reader open at page {scrollToPage ?? "none"}, {highlightRegions.length} region(s) to
        highlight{shownDocument ? `, reading ${shownDocument.kind} ${shownDocument.id}`
          : version != null ? `, reading v${version}` : ", reading the current paper"}
      </div>
      {/* The reader's own toolbar holds the download control it is handed. */}
      <div role="toolbar" aria-label="Reader toolbar">{downloadControl}</div>
      {/* IR-583: what the page hands the reader to draw and to offer on a selection. */}
      <p>{highlights?.length ?? 0} saved highlight(s) drawn</p>
      {/* IR-1079: whether the page asked the reader to scroll clear of the corner buttons. */}
      {clearCorner && <p>Reader keeps its last page clear of the corner buttons</p>}
      {/* IR-573: whether the page asked the reader to keep the reader's place on their account. */}
      {keepPlace && <p>Reader keeps the reader&apos;s place</p>}
      {(selectionActions ?? []).map((a) => (
        <button key={a.id} type="button" onClick={() => a.run(SELECTED, "rev-1")}>
          Selection: {a.label}
        </button>
      ))}
    </>
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

it("names the configured institution on an institutional paper", async () => {
  shownRecord = { ...record, origin: "institutional" };
  signInAs(99, "Student");
  renderPaperView();
  expect(await screen.findByText("Example Research University")).toBeVisible();
});

describe("loading the record (IR-939)", () => {
  beforeEach(() => {
    shownRecord = record;
  });

  it("announces the load once, by role and name, and says nothing more when the record draws", async () => {
    signInAs(99, "Student");
    vi.mocked(recordsApi.detail).mockReturnValueOnce(new Promise(() => {}) as never);
    renderPaperView();

    expect(screen.getByRole("status")).toHaveTextContent("Loading this record…");
    expect(screen.getAllByRole("status")).toHaveLength(1);
  });

  it("removes the status when the page replaces the skeleton", async () => {
    signInAs(99, "Student");
    renderPaperView();

    await screen.findByRole("heading", { name: record.title });
    expect(screen.queryByText("Loading this record…")).not.toBeInTheDocument();
  });
});

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

const researcherCard: PaperPerson = {
  id: OWNER_ID, name: "Rhea Owner", role: "Researcher", office: null,
  college: null, department: null, program: null, email: "owner@cit.edu",
};
const adviserCard: PaperPerson = {
  id: ASSIGNED_ADVISER_ID, name: "Ada Adviser", role: "Adviser", office: null,
  college: "College of Computer Studies", department: "Computer Science",
  program: null, email: "ada@cit.edu",
};
const sidebarDetails: PaperDetails = {
  colleges: null, programs: null, author_flags: [], researchers: [researcherCard],
  adviser: null, participants: [researcherCard], due_dates: [],
};

/** A Thesis/Research in office review, for the IR-259 gate tests. */
const inReview: RecordDetail = {
  ...record,
  paper_details: sidebarDetails,
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
  routing: { send_to_rdco: false, route_as: null, targets: [] },
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
    // The server still offers `open_review` for the opened seat, but the
    // footer asks it only of a seat not yet opened (IR-875): this one is open.
    // Changed deliberately: IR-681 expected the footer to keep offering it,
    // which hid Finish review from every opened seat.
    expect(within(screen.getByRole("contentinfo", { name: "Your part" })).queryByRole("button", OPEN_REVIEW)).not.toBeInTheDocument();
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

  it("lets the owner upload the revised manuscript from the card, and says when one is waiting (IR-1046)", async () => {
    shownRecord = { ...asked(null), manuscript_unsubmitted: true };
    signInAs(OWNER_ID, "Student");
    renderPaperView();

    const banner = await screen.findByRole("region", { name: "Revision requested" });
    expect(within(banner).getByLabelText("Replace revised manuscript")).toBeInTheDocument();
    expect(banner).toHaveTextContent("Revised manuscript ready, not yet submitted");
  });

  it("offers no manuscript upload in the card without the replace_manuscript capability (IR-1046)", async () => {
    shownRecord = { ...asked(null), capabilities: ["cite", "create_version"] };
    signInAs(OWNER_ID, "Student");
    renderPaperView();

    const banner = await screen.findByRole("region", { name: "Revision requested" });
    expect(within(banner).queryByLabelText(/revised manuscript/i)).not.toBeInTheDocument();
  });

  it("holds the new version, saying why, until something has changed (IR-273)", async () => {
    shownRecord = asked("Nothing has changed since IERC asked for a revision.");
    signInAs(OWNER_ID, "Student");
    renderPaperView();

    const open = await screen.findByRole("button", { name: "Submit new version" });
    expect(open).toHaveAccessibleDescription("Nothing has changed since IERC asked for a revision.");
    // The dialog opens anyway, so the owner can read the response to
    // reviewers it would carry, and holds Submit there (IR-876).
    await userEvent.click(open);
    const dialog = await screen.findByRole("dialog", { name: "Submit new version" });
    const submit = within(dialog).getByRole("button", { name: /^Submit v\d+$/ });
    expect(submit).toBeDisabled();
    expect(submit).toHaveAccessibleDescription("Nothing has changed since IERC asked for a revision.");
  });
});

describe("the status the paper shows", () => {
  it("is the API's workflow_state_label, stated once on the badge and not again in governance (IR-525)", async () => {
    shownRecord = { ...inReview, pipeline_status: "in_review", workflow_state_label: "Final review", workflow_state: "final_review" };
    signInAs(99, "Student");
    renderPaperView();

    await waitForRecord(inReview.title);
    // Once, as the badge. Governance has no "Pipeline Status" row repeating it.
    expect(screen.getAllByText("Final review")).toHaveLength(1);
    expect(screen.queryByText("Pipeline Status")).not.toBeInTheDocument();
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
    const adviser = screen.getByRole("list", { name: "Adviser" });
    expect(within(adviser).getByText("Maria Santos")).toBeInTheDocument();
    expect(within(adviser).getByText("Adviser")).toBeInTheDocument();
  });

  it("shows no adviser line on a record without one", async () => {
    shownRecord = { ...record, adviser: null, adviser_name: null };
    renderPaperView();

    await waitForRecord(record.title);
    expect(screen.queryByRole("list", { name: "Adviser" })).not.toBeInTheDocument();
  });
});

describe("names that open a Profile (IR-700)", () => {
  beforeEach(() => {
    signInAs(99, "Student");
  });

  it("links the adviser only when the server says their Profile can be opened", async () => {
    shownRecord = { ...record, adviser: ASSIGNED_ADVISER_ID, adviser_name: "Maria Santos", adviser_has_profile: true };
    renderPaperView();

    await waitForRecord(record.title);
    expect(screen.getByRole("link", { name: "Maria Santos, Adviser" })).toHaveAttribute("href", `/people/${ASSIGNED_ADVISER_ID}`);
  });

  it("leaves the adviser as plain text when the flag is false or absent", async () => {
    shownRecord = { ...record, adviser: ASSIGNED_ADVISER_ID, adviser_name: "Maria Santos", adviser_has_profile: false };
    renderPaperView();

    await waitForRecord(record.title);
    const adviser = screen.getByRole("list", { name: "Adviser" });
    expect(within(adviser).getByText("Maria Santos")).toBeInTheDocument();
    expect(within(adviser).getByText("Adviser")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Maria Santos, Adviser" })).not.toBeInTheDocument();
  });

  it("links an author chip to the matching owner's Profile when available", async () => {
    shownRecord = {
      ...record,
      authors: [{ id: 1, name: "Ana Reyes", role: null }],
      owners: [
        { id: 1, user: 41, email: "a@x.edu", full_name: "Ana Reyes", is_primary: true, has_profile: true },
        { id: 2, user: 42, email: "j@x.edu", full_name: "Jomar Ybanez", is_primary: false, has_profile: false },
      ],
    };
    renderPaperView();

    await waitForRecord(record.title);
    expect(screen.getByRole("link", { name: "Ana Reyes, Author" })).toHaveAttribute("href", "/people/41");
    expect(screen.queryByText("Jomar Ybanez")).not.toBeInTheDocument();
    expect(screen.queryByText(/Owners:/)).not.toBeInTheDocument();
  });

  it("says why a chip is not a link, and adds nothing to one that is (IR-1025)", async () => {
    shownRecord = {
      ...record,
      authors: [
        { id: 1, name: "Ana Reyes", role: null },
        { id: 2, name: "Jomar Ybanez", role: null },
      ],
      adviser: ASSIGNED_ADVISER_ID,
      adviser_name: "Maria Santos",
      adviser_has_profile: false,
      owners: [
        { id: 1, user: 41, email: "a@x.edu", full_name: "Ana Reyes", is_primary: true, has_profile: true },
        { id: 2, user: 42, email: "j@x.edu", full_name: "Jomar Ybanez", is_primary: false, has_profile: false },
      ],
    };
    renderPaperView();

    await waitForRecord(record.title);
    const hint = "No public profile available";
    const authors = screen.getByRole("list", { name: "Authors" });
    expect(within(authors).getAllByText(hint)).toHaveLength(1);
    const linked = screen.getByRole("link", { name: "Ana Reyes, Author" });
    expect(linked).toHaveAttribute("href", "/people/41");
    expect(within(linked).queryByText(hint)).not.toBeInTheDocument();
    expect(within(screen.getByRole("list", { name: "Adviser" })).getByText(hint)).toBeInTheDocument();
  });

  it("does not expose owner metadata when an author has no Profile", async () => {
    shownRecord = {
      ...record,
      owners: [{ id: 1, user: 41, email: "a@x.edu", full_name: "Ana Reyes", is_primary: true }],
    };
    renderPaperView();

    await waitForRecord(record.title);
    expect(screen.queryByText(/Owners:/)).not.toBeInTheDocument();
    expect(screen.queryByText("a@x.edu")).not.toBeInTheDocument();
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

  it("opens Ask IRIS on entry, with the icon only once it is closed", async () => {
    await openPaperTab();

    expect(screen.queryByRole("button", ASK)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Ask about this paper" })).not.toBeInTheDocument();
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
    // The version menu, even with v1 alone (IR-1214).
    expect(screen.getByRole("combobox", { name: "Version" })).toHaveValue("1");
    expect(screen.getByRole("button", { name: "Back" })).toBeInTheDocument();
    expect(screen.queryByText("Example Research University")).not.toBeInTheDocument();
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

  it("keeps an open chat when the reader switches sections", async () => {
    renderPaperView();
    await waitForRecord(record.title);
    await userEvent.click(screen.getByRole("button", ASK));
    await screen.findByRole("complementary", { name: "Ask IRIS" });

    await userEvent.click(screen.getByRole("tab", { name: "Paper" }));
    await userEvent.click(screen.getByRole("tab", { name: "Overview" }));

    expect(screen.getByRole("complementary", { name: "Ask IRIS" })).toBeInTheDocument();
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
      workspaceAt(360);
      useUIStore.setState({ sidebarOpen: true });
      await openPaperTab();

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

// The Notes and Ask IRIS icons float over the bottom-right corner (IR-1079,
// audit CMP-02). jsdom has no layout, so what is checked is that the reading
// surface reserves the room the pair needs; the scrolled-to-the-bottom look at
// 1440, 768 and 390 px is the by-hand check recorded on the PR.
describe("the corner buttons never cover reading text (IR-1079)", () => {
  beforeEach(() => {
    shownRecord = record;
    signInAs(99, "Student");
    useUIStore.setState({ sidebarCollapsed: false, sidebarOpen: false, readingRail: null });
  });

  it("offers Notes and Ask IRIS together on Overview, which reserves room beneath its last line", async () => {
    workspaceAt(1400);
    renderPaperView();
    await waitForRecord(record.title);

    expect(screen.getByRole("button", { name: "Notes" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Ask IRIS" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 1 }).closest(`.${CORNER_CLEARANCE_CLASS}`)).not.toBeNull();
  });

  it("asks the Paper reader to keep its last page clear of them", async () => {
    renderPaperView();
    await waitForRecord(record.title);

    await userEvent.click(screen.getByRole("tab", { name: "Paper" }));

    expect(await screen.findByText(/keeps its last page clear of the corner buttons/i)).toBeInTheDocument();
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
    expect(await screen.findByRole("heading", { name: "Comments (0)" })).toBeInTheDocument();
    expect(vi.mocked(recordsApi.publicComments)).toHaveBeenCalledWith(RECORD_ID);
  });

  it("does not request or show public comments on an unpublished Proposal", async () => {
    shownRecord = approvedProposal;
    signInAs(99, "Student");
    renderPaperView();

    await waitForRecord(approvedProposal.title);
    expect(screen.queryByRole("heading", { name: /Comments/ })).not.toBeInTheDocument();
    expect(vi.mocked(recordsApi.publicComments)).not.toHaveBeenCalled();
  });

  // Changed on purpose by IR-879 (ADR-032 §10, 2026-11-04): a participant
  // reads the paper in Review, and Files moved into Review's Documents drawer.
  it("gives the owner Overview and Review, where the paper is", async () => {
    shownRecord = inReview;
    signInAs(OWNER_ID, "Student");
    renderPaperView();

    await waitForRecord(inReview.title);
    expect(tabNames()).toEqual(["Overview", "Review"]);
  });

  it("gives a reviewer the API names Overview and Review", async () => {
    shownRecord = { ...inReview, ...reviewing };
    signInAs(2, "ITSO");
    renderPaperView();

    await waitForRecord(inReview.title);
    expect(tabNames()).toEqual(["Overview", "Review"]);
  });

  it("lands a participant's old Paper link in Review", async () => {
    shownRecord = { ...inReview, ...reviewing };
    signInAs(2, "ITSO");
    renderPaper(`/records/${RECORD_ID}?section=paper`);
    expect(await screen.findByRole("tab", { name: "Review", selected: true })).toBeInTheDocument();
  });

  it("opens a participant's cited page in Review", async () => {
    shownRecord = { ...inReview, ...reviewing };
    signInAs(2, "ITSO");
    renderPaper(`/records/${RECORD_ID}?page=3`);
    expect(await screen.findByRole("tab", { name: "Review", selected: true })).toBeInTheDocument();
    expect(await screen.findByText(/paper reader open at page 3/i)).toBeInTheDocument();
  });

  it("has no Paper section on a record with no paper to read", async () => {
    shownRecord = { ...record, abstract_file: null, files: [] };
    signInAs(99, "Student");
    renderPaperView();

    await waitForRecord(record.title);
    expect(tabNames()).toEqual(["Overview"]);
  });

  // Changed on purpose by IR-1203: the drawer is gone, so an old Files link
  // opens Review on its Documents tab ("the Documents tab (IR-1203)").
  it("opens an old Files link as Review on its Documents tab (IR-879, IR-1203)", async () => {
    shownRecord = inReview;
    signInAs(OWNER_ID, "Student");
    renderPaper(`/records/${RECORD_ID}?section=files`);

    expect(await screen.findByRole("tab", { name: "Review", selected: true })).toBeInTheDocument();
    expect(await screen.findByRole("tab", { name: "Documents", selected: true })).toBeInTheDocument();
    expect(screen.queryByRole("dialog", { name: "All documents" })).not.toBeInTheDocument();
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

    // Changed on purpose by IR-879: an owner's next section is Review.
    expect(await screen.findByRole("tab", { name: "Review", selected: true })).toHaveFocus();
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
    review_comments: [],
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
    localStorage.removeItem("iris-review-cols");
    vi.unstubAllGlobals();
  });

  const bar = () => screen.getByRole("toolbar", { name: "Review actions" });
  /** A reviewer opens on Documents (IR-1203): open Conversation, where the timeline and comment box are. */
  const openConversation = async () => userEvent.click(await screen.findByRole("tab", { name: "Conversation" }));
  /** Details is a tab at every width now (IR-1094): open it and return its panel. */
  const openDetails = async () => {
    await userEvent.click(await screen.findByRole("tab", { name: "Details" }));
    return screen.getByRole("tabpanel", { name: "Details" });
  };

  // IR-1206: the paper's owners get the frame reviewers have. Nothing above
  // the reader but Back and the title; what the header held moved to tabs.
  describe("the author's Review uses the reviewers' frame (IR-1206)", () => {
    const authorReview: RecordDetail = {
      ...inReview,
      adviser_name: "Ada Adviser",
      capabilities: ["cite", "edit_details", "continue_as"],
      lineage: { derived_from: { id: 123, title: "Proposal", record_type_name: "Proposal" }, continued_as: null },
    };
    const paneTabs = () => within(screen.getByRole("tablist", { name: "Review pane sections" }))
      .getAllByRole("tab").map((t) => t.textContent?.replace(/\s*\d+$/, "").trim());

    it("puts only Back and the title above the reader", async () => {
      workspaceAt(1600);
      shownRecord = authorReview;
      signInAs(OWNER_ID, "Student");
      renderPaper(`/records/${RECORD_ID}?section=review`);

      expect(await screen.findByRole("region", { name: "Review pane content" })).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Back" })).toBeInTheDocument();
      // The title is the bar's, once; the editorial header's is gone.
      expect(screen.getAllByRole("heading", { level: 1 }).map((h) => h.textContent)).toEqual([inReview.title]);
      expect(screen.queryByRole("list", { name: "Authors" })).not.toBeInTheDocument();
      expect(screen.queryByRole("list", { name: "Adviser" })).not.toBeInTheDocument();
      expect(screen.queryByText("Completed 2026")).not.toBeInTheDocument();
      for (const name of ["View", "Cite", "Share", /^Save/]) {
        expect(screen.queryByRole("button", { name })).not.toBeInTheDocument();
      }
    });

    // Changed on purpose by IR-1203: Documents is the author's second tab, and
    // Readiness no longer carries a Documents button.
    it("opens on Readiness, with the status at its top, then Documents, Conversation, Threads and Details", async () => {
      workspaceAt(1600);
      shownRecord = authorReview;
      signInAs(OWNER_ID, "Student");
      renderPaper(`/records/${RECORD_ID}?section=review`);

      const readiness = await screen.findByRole("tabpanel", { name: "Readiness" });
      expect(paneTabs()).toEqual(["Readiness", "Documents", "Conversation", "Threads", "Details"]);
      expect(screen.getByRole("tab", { name: "Readiness" })).toHaveAttribute("aria-selected", "true");
      expect(within(readiness).getByText("In review")).toBeInTheDocument();
      expect(within(readiness).queryByRole("button", { name: "Documents" })).not.toBeInTheDocument();
    });

    it("moves Edit details, the lineage and Continue as into Details", async () => {
      workspaceAt(1600);
      shownRecord = authorReview;
      signInAs(OWNER_ID, "Student");
      renderPaper(`/records/${RECORD_ID}?section=review`);

      const details = await openDetails();
      expect(within(details).getByRole("button", { name: "Edit details" })).toBeInTheDocument();
      expect(within(details).getByRole("link", { name: "Developed from Proposal #123 — View proposal" }))
        .toHaveAttribute("href", "/records/123");
      expect(within(details).getByRole("button", { name: "Continue as Thesis" })).toBeInTheDocument();
      expect(await within(details).findByRole("heading", { name: "Reviewers" })).toBeInTheDocument();
      // Readiness is a tab of its own for the author, not repeated here.
      expect(within(details).queryByRole("heading", { name: "Readiness" })).not.toBeInTheDocument();
    });

    it("offers no Edit details in Details when the server does not grant it", async () => {
      workspaceAt(1600);
      shownRecord = { ...authorReview, capabilities: ["cite"] };
      signInAs(OWNER_ID, "Student");
      renderPaper(`/records/${RECORD_ID}?section=review`);

      const details = await openDetails();
      expect(within(details).queryByRole("button", { name: "Edit details" })).not.toBeInTheDocument();
      expect(within(details).queryByRole("button", { name: "Continue as Thesis" })).not.toBeInTheDocument();
    });

    it("keeps the reviewers' own tabs and nothing of the author's", async () => {
      workspaceAt(1600);
      shownRecord = { ...inReview, ...reviewing, capabilities: ["cite", "edit_details"] };
      signInAs(2, "ITSO");
      renderPaper(`/records/${RECORD_ID}?section=review`);

      await screen.findByRole("region", { name: "Review pane content" });
      // Changed on purpose by IR-1203: Documents is the reviewers' first tab.
      expect(paneTabs()).toEqual(["Documents", "Conversation", "Threads", "Changes", "Details"]);
      const details = await openDetails();
      expect(within(details).queryByRole("button", { name: "Edit details" })).not.toBeInTheDocument();
    });

    it("moves between the author's tabs with the arrow keys, Home and End", async () => {
      workspaceAt(1600);
      shownRecord = authorReview;
      signInAs(OWNER_ID, "Student");
      renderPaper(`/records/${RECORD_ID}?section=review`);

      const readiness = await screen.findByRole("tab", { name: "Readiness" });
      readiness.focus();
      await userEvent.keyboard("{ArrowRight}");
      // Changed on purpose by IR-1203: Documents follows Readiness.
      expect(screen.getByRole("tab", { name: "Documents" })).toHaveFocus();
      await userEvent.keyboard("{End}");
      expect(screen.getByRole("tab", { name: "Details", selected: true })).toHaveFocus();
      await userEvent.keyboard("{Home}");
      expect(screen.getByRole("tab", { name: "Readiness", selected: true })).toHaveFocus();
    });

    it("keeps the paper first at 320px, its pane one tap away and free of serious axe violations", async () => {
      workspaceAt(320);
      shownRecord = authorReview;
      signInAs(OWNER_ID, "Student");
      const { container } = renderPaper(`/records/${RECORD_ID}?section=review`);

      await userEvent.click(await screen.findByRole("button", { name: "Open review pane" }));
      const pane = screen.getByRole("dialog", { name: "Review pane" });
      expect(within(pane).getByRole("tab", { name: "Readiness", selected: true })).toBeInTheDocument();
      await expectNoBlockingA11yViolations(container);
    });

    it("leaves Overview's header as it was", async () => {
      shownRecord = authorReview;
      signInAs(OWNER_ID, "Student");
      renderPaperView();

      expect(await screen.findByRole("heading", { level: 1, name: inReview.title })).toBeInTheDocument();
      expect(screen.getByRole("list", { name: "Authors" })).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Edit details" })).toBeInTheDocument();
    });
  });

  it("makes the office review body a named keyboard-scrollable region (IR-774)", async () => {
    workspaceAt(800);
    shownRecord = { ...inReview, ...reviewing };
    signInAs(2, "ITSO");
    renderPaper(`/records/${RECORD_ID}?section=review`);

    const region = await screen.findByRole("region", { name: "Review pane content" });
    expect(region).toHaveAttribute("tabindex", "0");
    expect(region).toHaveClass("focus-visible:ring-2", "focus-visible:ring-brand");
  });

  it("resizes the pane by 24px with arrow keys and restores it on double click (IR-681, IR-1094)", async () => {
    workspaceAt(1600);
    shownRecord = { ...inReview, ...reviewing };
    signInAs(2, "ITSO");
    renderPaper(`/records/${RECORD_ID}?section=review`);
    const mid = await screen.findByRole("separator", { name: "Resize the review pane" });
    // Two columns, the pane getting 520px; no details column to resize.
    expect(screen.queryByRole("separator", { name: "Resize the details sidebar" })).not.toBeInTheDocument();
    expect(mid).toHaveAttribute("aria-valuenow", "520");
    mid.focus();
    await userEvent.keyboard("{ArrowLeft}");
    expect(mid).toHaveAttribute("aria-valuenow", "544");
    await userEvent.keyboard("{ArrowRight}");
    expect(mid).toHaveAttribute("aria-valuenow", "520");
    await userEvent.keyboard("{ArrowLeft}");
    await userEvent.dblClick(mid);
    expect(mid).toHaveAttribute("aria-valuenow", "520");
  });

  it("keeps one filled footer action and words for an unopened review (IR-681)", async () => {
    workspaceAt(1600);
    shownRecord = { ...inReview, ...reviewing, capabilities: ["open_review", "office_review", "request_revision"],
      my_seats: [{ ...reviewingSeat, state: "assigned", state_label: "Assigned", opened_at: null }] };
    signInAs(2, "ITSO");
    renderPaper(`/records/${RECORD_ID}?section=review`);
    const foot = await screen.findByRole("contentinfo", { name: "Your part" });
    expect(within(foot).getByText("Your review: Assigned")).toBeInTheDocument();
    const primary = within(foot).getAllByRole("button").filter((b) => b.classList.contains("bg-brand"));
    expect(primary).toHaveLength(1);
    expect(primary[0]).toHaveAccessibleName("Open review");
    await userEvent.click(primary[0]);
    expect(seatsApi.open).toHaveBeenCalledWith(78);
  });

  it("offers a pool member Claim review and refreshes after claiming (IR-681)", async () => {
    workspaceAt(1600);
    shownRecord = { ...inReview, capabilities: ["cite"], review_claim: { assignment: 55, label: "Claim review", party_label: "ITSO" } };
    signInAs(2, "ITSO");
    renderPaper(`/records/${RECORD_ID}?section=review`);
    const foot = await screen.findByRole("contentinfo", { name: "Your part" });
    const claim = within(foot).getByRole("button", { name: "Claim review" });
    expect(within(foot).getAllByRole("button").filter((b) => b.classList.contains("bg-brand"))).toEqual([claim]);
    // Claimed, not yet opened, as the server leaves it (changed for IR-875:
    // the footer offers Open review only to a seat still to open).
    shownRecord = { ...inReview, ...reviewing, capabilities: ["open_review"],
      my_seats: [{ ...reviewingSeat, state: "assigned", state_label: "Assigned", opened_at: null }] };
    await userEvent.click(claim);
    expect(seatsApi.claim).toHaveBeenCalledWith(55);
    expect(await within(foot).findByRole("button", { name: "Open review" })).toBeInTheDocument();
  });

  it.each([
    { role: "Adviser", party: "adviser", capabilities: ["send_to_rdco", "reject"], primary: "Accept & send to RDCO…" },
    { role: "ITSO", party: "itso", capabilities: ["office_review", "request_revision", "route"], primary: "Clear…" },
    { role: "RDCO", party: "rdco", capabilities: ["accept_publish", "keep_unlisted", "reject"], primary: "Accept & publish…" },
  ] as const)("keeps one filled footer action for $role from its granted actions (IR-681)", async ({ role, party, capabilities, primary }) => {
    workspaceAt(1600);
    shownRecord = { ...inReview, ...reviewing, capabilities: [...capabilities], my_seats: [{ ...reviewingSeat, party }] };
    signInAs(2, role);
    renderPaper(`/records/${RECORD_ID}?section=review`);
    const foot = await screen.findByRole("contentinfo", { name: "Your part" });
    expect(within(foot).getByText(/Your review: In review/)).toBeInTheDocument();
    expect(within(foot).getAllByRole("button").filter((b) => b.classList.contains("bg-brand")))
      .toEqual([within(foot).getByRole("button", { name: primary })]);
  });

  it("shows the viewer's recorded verdict and offers no new authority on a finished seat (IR-681)", async () => {
    workspaceAt(1600);
    shownRecord = { ...inReview, ...reviewing, capabilities: ["cite"],
      my_seats: [{ ...reviewingSeat, state: "done", state_label: "Done", verdict_label: "Cleared" }] };
    signInAs(2, "ITSO");
    renderPaper(`/records/${RECORD_ID}?section=review`);
    const foot = await screen.findByRole("contentinfo", { name: "Your part" });
    expect(within(foot).getByText(/Your review: Cleared/)).toBeInTheDocument();
    expect(within(foot).queryByRole("button")).not.toBeInTheDocument();
  });

  it("clamps dragging to leave the paper 480px and the pane 320px (IR-681, IR-1094)", async () => {
    workspaceAt(1100);
    shownRecord = { ...inReview, ...reviewing };
    signInAs(2, "ITSO");
    renderPaper(`/records/${RECORD_ID}?section=review`);
    const mid = await screen.findByRole("separator", { name: "Resize the review pane" });
    // The separator renders before the container is measured; until then the
    // layout uses its 1600px fallback, and a drag would capture those sizes.
    await waitFor(() => expect(mid).toHaveAttribute("aria-valuenow", "520"));
    fireEvent.pointerDown(mid, { button: 0, pointerId: 1, clientX: 600 });
    fireEvent.pointerMove(mid, { pointerId: 1, clientX: -1000 });
    fireEvent.pointerUp(mid, { pointerId: 1 });
    // The paper keeps 480px of 1100, and the pane no more than half.
    expect(mid).toHaveAttribute("aria-valuenow", "550");
    fireEvent.pointerDown(mid, { button: 0, pointerId: 2, clientX: 600 });
    fireEvent.pointerMove(mid, { pointerId: 2, clientX: 5000 });
    fireEvent.pointerUp(mid, { pointerId: 2 });
    expect(mid).toHaveAttribute("aria-valuenow", "320");
    mid.focus();
    await userEvent.keyboard("{ArrowRight>30/}");
    expect(mid).toHaveAttribute("aria-valuenow", "320");
  });

  it("remembers widths across a remount and safely ignores broken storage (IR-681)", async () => {
    workspaceAt(1600);
    shownRecord = { ...inReview, ...reviewing };
    signInAs(2, "ITSO");
    const first = renderPaper(`/records/${RECORD_ID}?section=review`);
    const mid = await screen.findByRole("separator", { name: "Resize the review pane" });
    mid.focus();
    await userEvent.keyboard("{ArrowLeft}");
    first.unmount();
    const second = renderPaper(`/records/${RECORD_ID}?section=review`);
    expect(await screen.findByRole("separator", { name: "Resize the review pane" })).toHaveAttribute("aria-valuenow", "544");
    second.unmount();
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => { throw new Error("storage blocked"); });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw new Error("storage blocked"); });
    renderPaper(`/records/${RECORD_ID}?section=review`);
    const fallback = await screen.findByRole("separator", { name: "Resize the review pane" });
    expect(fallback).toHaveAttribute("aria-valuenow", "520");
    fallback.focus();
    await userEvent.keyboard("{ArrowLeft}");
    expect(fallback).toHaveAttribute("aria-valuenow", "544");
  });

  it("folds Details at the container breakpoint, then gives the paper a dismissible drawer (IR-681)", async () => {
    const workspace = workspaceAt(1199);
    shownRecord = { ...inReview, ...reviewing, capabilities: ["comment_review"] };
    signInAs(2, "ITSO");
    renderPaper(`/records/${RECORD_ID}?section=review`);
    // Changed on purpose by IR-1203: a reviewer opens on Documents, so Conversation is a click away.
    await openConversation();
    await userEvent.type(await screen.findByRole("textbox", { name: "Comment" }), "Keep this draft");
    await userEvent.click(screen.getByRole("tab", { name: "Details" }));
    expect(screen.getByRole("heading", { name: "Reviewers" })).toBeInTheDocument();
    expect(screen.queryByRole("complementary")).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("tab", { name: "Conversation" }));
    expect(screen.getByRole("textbox", { name: "Comment" })).toHaveValue("Keep this draft");
    act(() => workspace.resizeTo(899));
    // Narrow, it starts on the paper (IR-875); the launcher opens the drawer.
    // Changed deliberately: IR-681 opened the drawer over the paper at once.
    expect(screen.queryByRole("dialog", { name: "Review pane" })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Open review pane" }));
    const drawer = screen.getByRole("dialog", { name: "Review pane" });
    expect(drawer).toHaveAttribute("aria-modal", "true");
    await waitFor(() => expect(drawer).toHaveFocus());
    expect(screen.queryByRole("separator")).not.toBeInTheDocument();
    await userEvent.click(within(drawer).getByRole("button", { name: "Back to paper" }));
    await userEvent.click(screen.getByRole("button", { name: "Open review pane" }));
    expect(screen.getByRole("textbox", { name: "Comment" })).toHaveValue("Keep this draft");
    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("dialog", { name: "Review pane" })).not.toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole("button", { name: "Open review pane" })).toHaveFocus());
  });

  it("opens two columns, the pane getting 520px, with no People & details column (IR-1094)", async () => {
    workspaceAt(1600);
    shownRecord = { ...inReview, ...reviewing };
    signInAs(2, "ITSO");
    renderPaper(`/records/${RECORD_ID}?section=review`);

    expect(await screen.findByRole("separator", { name: "Resize the review pane" }))
      .toHaveAttribute("aria-valuenow", "520");
    expect(screen.queryByRole("complementary")).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "People & details" })).not.toBeInTheDocument();
    // Changed on purpose by IR-1203: a reviewer opens on Documents.
    expect(screen.getByRole("tab", { name: "Documents", selected: true })).toBeInTheDocument();
    // What the column held is the Details tab, whatever the width.
    const details = await openDetails();
    expect(await within(details).findByRole("heading", { name: "Reviewers" })).toBeInTheDocument();
    expect(recordsApi.tracker).toHaveBeenCalledTimes(1);
    vi.unstubAllGlobals();
  });

  describe("a tab opened on the right (IR-1094)", () => {
    const columns = () => screen.getByRole("button", { name: "Open a tab beside this one" });
    // The first render has no width until the observer reports, so wait for the button.
    const findColumns = () => screen.findByRole("button", { name: "Open a tab beside this one" });

    afterEach(() => localStorage.removeItem("iris-review-side-tab"));

    it("is offered from 1180px, and not below it", async () => {
      shownRecord = { ...inReview, ...reviewing };
      signInAs(2, "ITSO");
      const workspace = workspaceAt(1180);
      renderPaper(`/records/${RECORD_ID}?section=review`);
      expect(await findColumns()).toBeInTheDocument();

      act(() => workspace.resizeTo(1179));
      expect(screen.queryByRole("button", { name: "Open a tab beside this one" })).not.toBeInTheDocument();
    });

    it("moves Threads to a right column, leaves the row without it, and puts it back on close", async () => {
      workspaceAt(1600);
      shownRecord = { ...inReview, ...reviewing };
      signInAs(2, "ITSO");
      renderPaper(`/records/${RECORD_ID}?section=review`);
      await screen.findByRole("tab", { name: "Threads" });

      await userEvent.click(await findColumns());
      await userEvent.click(screen.getByRole("menuitem", { name: "Threads on the right" }));

      const side = screen.getByRole("complementary", { name: "Threads on the right" });
      expect(within(side).getByRole("heading", { level: 2, name: "Threads" })).toBeInTheDocument();
      expect(screen.queryByRole("tab", { name: /Threads/ })).not.toBeInTheDocument();
      // Changed on purpose by IR-1203: a reviewer opens on Documents, and stays there.
      expect(screen.getByRole("tab", { name: "Documents", selected: true })).toBeInTheDocument();
      expect(screen.getByRole("separator", { name: "Resize the right column" })).toHaveAttribute("aria-valuenow", "320");

      // Focus follows the tab to its new place, and back to it on close.
      await waitFor(() => expect(within(side).getByRole("button", { name: "Close Threads on the right" })).toHaveFocus());
      await userEvent.click(within(side).getByRole("button", { name: "Close Threads on the right" }));
      expect(screen.queryByRole("complementary")).not.toBeInTheDocument();
      expect(screen.getByRole("tab", { name: /Threads/ })).toBeInTheDocument();
      await waitFor(() => expect(screen.getByRole("tab", { name: /Threads/ })).toHaveFocus());
    });

    it("does not bring back as selected a tab that was moved out while it was shown", async () => {
      workspaceAt(1600);
      shownRecord = { ...inReview, ...reviewing };
      signInAs(2, "ITSO");
      renderPaper(`/records/${RECORD_ID}?section=review`);
      await userEvent.click(await screen.findByRole("tab", { name: /Threads/ }));

      await userEvent.click(await findColumns());
      await userEvent.click(screen.getByRole("menuitem", { name: "Threads on the right" }));
      await userEvent.click(screen.getByRole("button", { name: "Close Threads on the right" }));

      // Changed on purpose by IR-1203: the tab a reviewer opens on, Documents, takes its place.
      expect(screen.getByRole("tab", { name: "Documents", selected: true })).toBeInTheDocument();
      expect(screen.getByRole("tab", { name: /Threads/, selected: false })).toBeInTheDocument();
    });

    it("can open Conversation on the right too, leaving the other tabs in the row", async () => {
      workspaceAt(1600);
      shownRecord = { ...inReview, ...reviewing };
      signInAs(2, "ITSO");
      renderPaper(`/records/${RECORD_ID}?section=review`);
      await screen.findByRole("tab", { name: "Conversation" });

      await userEvent.click(await findColumns());
      expect(screen.getAllByRole("menuitem").map((m) => m.textContent)).toEqual([
        // Changes is a tab on the first version too (IR-1139). Changed on
        // purpose by IR-1203: Documents leads the row, so it leads the menu.
        "Documents on the right", "Conversation on the right", "Threads on the right", "Changes on the right",
        "Details on the right",
      ]);
      await userEvent.click(screen.getByRole("menuitem", { name: "Conversation on the right" }));

      expect(screen.getByRole("complementary", { name: "Conversation on the right" })).toBeInTheDocument();
      expect(screen.queryByRole("tab", { name: "Conversation" })).not.toBeInTheDocument();
      // Changed on purpose by IR-1203: the first tab left in the row is Documents.
      expect(screen.getByRole("tab", { name: "Documents", selected: true })).toBeInTheDocument();
    });

    it("closes the menu with Escape, returning focus to the columns button, and with Tab", async () => {
      workspaceAt(1600);
      shownRecord = { ...inReview, ...reviewing };
      signInAs(2, "ITSO");
      renderPaper(`/records/${RECORD_ID}?section=review`);
      await screen.findByRole("tab", { name: "Conversation" });

      await userEvent.click(await findColumns());
      await userEvent.keyboard("{Escape}");
      expect(screen.queryByRole("menu")).not.toBeInTheDocument();
      expect(columns()).toHaveFocus();

      await userEvent.click(await findColumns());
      await userEvent.keyboard("{Tab}");
      expect(screen.queryByRole("menu")).not.toBeInTheDocument();
    });

    it("is remembered across a visit, and goes back to the row where the workspace is too narrow", async () => {
      shownRecord = { ...inReview, ...reviewing };
      signInAs(2, "ITSO");
      workspaceAt(1600);
      const visit = renderPaper(`/records/${RECORD_ID}?section=review`);
      await screen.findByRole("tab", { name: "Threads" });
      await userEvent.click(await findColumns());
      await userEvent.click(screen.getByRole("menuitem", { name: "Details on the right" }));
      visit.unmount();

      const narrow = workspaceAt(1600);
      renderPaper(`/records/${RECORD_ID}?section=review`);
      expect(await screen.findByRole("complementary", { name: "Details on the right" })).toBeInTheDocument();
      expect(screen.queryByRole("tab", { name: "Details" })).not.toBeInTheDocument();

      act(() => narrow.resizeTo(1100));
      expect(screen.queryByRole("complementary")).not.toBeInTheDocument();
      expect(screen.getByRole("tab", { name: "Details" })).toBeInTheDocument();
    });

    it("resizes by 24px with arrow keys, and keeps the paper 480px", async () => {
      workspaceAt(1200);
      shownRecord = { ...inReview, ...reviewing };
      signInAs(2, "ITSO");
      localStorage.setItem("iris-review-side-tab", "threads");
      renderPaper(`/records/${RECORD_ID}?section=review`);
      const side = await screen.findByRole("separator", { name: "Resize the right column" });
      const mid = screen.getByRole("separator", { name: "Resize the review pane" });
      // 1200 less the paper's 480 leaves 720 for the pane and the column.
      await waitFor(() => expect(side).toHaveAttribute("aria-valuenow", "320"));
      expect(mid).toHaveAttribute("aria-valuenow", "400");
      side.focus();
      await userEvent.keyboard("{ArrowLeft}");
      expect(side).toHaveAttribute("aria-valuenow", "344");
      await userEvent.dblClick(side);
      expect(side).toHaveAttribute("aria-valuenow", "320");
    });

    it("keeps a draft typed in Conversation when another tab is opened beside it", async () => {
      workspaceAt(1600);
      shownRecord = { ...inReview, ...reviewing, capabilities: ["comment_review"] };
      signInAs(2, "ITSO");
      renderPaper(`/records/${RECORD_ID}?section=review`);
      // Changed on purpose by IR-1203: a reviewer opens on Documents, so Conversation is a click away.
      await openConversation();
      await userEvent.type(await screen.findByRole("textbox", { name: "Comment" }), "Keep this draft");

      await userEvent.click(await findColumns());
      await userEvent.click(screen.getByRole("menuitem", { name: "Threads on the right" }));

      expect(screen.getByRole("textbox", { name: "Comment" })).toHaveValue("Keep this draft");
    });
  });

  const partyRow = (party: string, label: string, extra: object = {}) => ({
    party, label, state: "active", state_label: "Active", started: true, outcome: null, outcome_label: null,
    at: "2026-09-02T08:00:00Z", preserved: false, carryover: null, carryover_version: null, carryover_label: null,
    awaiting_document: false, outcome_earlier: false, changes_requested: false, in_pool: false, seats: [],
    due_at: null, original_due_at: null, is_overdue: false, clock_paused: false, extensions: [], can_extend: false,
    withdrawn_by_decision: null, ...extra,
  });
  const readinessFor = (items: Partial<ReadinessItem>[]): Readiness => ({
    verdict: "blocked", headline: "You can't decide yet.",
    items: items.map((i) => ({ party: null, actor_name: null, since: null, paused: null, action: null, ...i }) as ReadinessItem),
  });

  it("says Your part in the server's words, and keeps the facts behind it in Details (IR-1094)", async () => {
    workspaceAt(1600);
    shownRecord = { ...inReview, ...reviewing, capabilities: ["comment_review", "open_review"],
      my_seats: [{ ...reviewingSeat, state: "assigned", state_label: "Assigned", opened_at: null }], readiness: readinessFor([
      { kind: "open_review", severity: "blocker", label: "Open the review first.", action: { kind: "open_review", target: "78" } },
      { kind: "party_reviewing", severity: "info", label: "IERC is reviewing.", actor_name: "Ina Ierc", since: "2026-09-03T08:00:00Z" },
    ]) };
    signInAs(2, "ITSO");
    renderPaper(`/records/${RECORD_ID}?section=review`);
    const foot = await screen.findByRole("contentinfo", { name: "Your part" });
    // One heading, one line, one filled action.
    expect(within(foot).getByText("You can't decide yet.")).toBeInTheDocument();
    expect(within(foot).getByText("Open the review first.")).toBeInTheDocument();
    expect(within(foot).getAllByRole("button").filter((b) => b.classList.contains("bg-brand")))
      .toEqual([within(foot).getByRole("button", { name: "Open review" })]);
    // The card is gone from Conversation, which is the timeline and the comment box.
    // Changed on purpose by IR-1203: a reviewer opens on Documents, so Conversation is a click away.
    await openConversation();
    expect(screen.getByRole("textbox", { name: "Comment" })).toBeInTheDocument();

    // The facts are in Details; "IERC is reviewing." is Reviewers' to say, once.
    await userEvent.click(within(foot).getByRole("button", { name: "See what it depends on" }));
    expect(screen.getByRole("tab", { name: "Details", selected: true })).toBeInTheDocument();
    const section = screen.getByRole("heading", { name: "Readiness" }).closest("section")!;
    const facts = within(section).getAllByRole("listitem");
    expect(facts).toHaveLength(1);
    expect(facts[0]).toHaveTextContent("Blocker: Open the review first.");
    expect(screen.queryByText("IERC is reviewing.")).not.toBeInTheDocument();
    await waitFor(() => expect(section).toHaveFocus());
    await userEvent.click(within(section).getByRole("button", { name: "Open review" }));
    expect(seatsApi.open).toHaveBeenCalledWith(78);
  });

  it("offers Withdraw request only on the Revision request whose action allows it (IR-682)", async () => {
    workspaceAt(1600);
    shownRecord = { ...inReview, ...reviewing, capabilities: ["withdraw_revision"], readiness: readinessFor([
      { kind: "revision_request", severity: "blocker", label: "IERC asked the author for a revision.", party: "ierc",
        actor_name: "Ina Ierc", since: "2026-09-03T08:00:00Z", action: { kind: "withdraw_revision", target: "3" } },
      { kind: "revision_request", severity: "info", label: "ITSO asked the author for a revision.", party: "itso",
        actor_name: "Ito Itso", since: "2026-09-04T08:00:00Z" },
    ]) };
    signInAs(2, "IERC");
    renderPaper(`/records/${RECORD_ID}?section=review`);
    const foot = await screen.findByRole("contentinfo", { name: "Your part" });
    expect(within(foot).getByText("You can't decide yet.")).toBeInTheDocument();
    // The blocker, the server having sorted it first, is the one line.
    expect(within(foot).getByText("IERC asked the author for a revision.")).toBeInTheDocument();
    await openDetails();
    const section = screen.getByRole("heading", { name: "Readiness" }).closest("section")!;
    const [ierc, itso] = within(section).getAllByRole("listitem");
    expect(ierc).toHaveTextContent("Blocker: IERC asked the author for a revision.");
    expect(ierc).toHaveTextContent("Ina Ierc");
    expect(ierc).toHaveTextContent(`since ${formatDate("2026-09-03T08:00:00Z")}`);
    expect(itso).toHaveTextContent("ITSO asked the author for a revision.");
    expect(itso).not.toHaveTextContent("Blocker");
    expect(within(itso).queryByRole("button")).not.toBeInTheDocument();
    expect(within(section).getAllByRole("button", { name: "Withdraw request" })).toHaveLength(1);

    // It hands over to the footer's own Withdraw, which still asks first.
    await userEvent.click(within(ierc).getByRole("button", { name: "Withdraw request" }));
    expect(within(foot).getByRole("button", { name: "Withdraw revision request" })).toHaveFocus();
  });

  it("says a party still reviewing and an unclaimed Pool once, in Reviewers, with the footer's Claim (IR-683, IR-1094)", async () => {
    workspaceAt(1600);
    vi.mocked(recordsApi.tracker).mockResolvedValue({
      data: { ...trackerPayload, parties: [partyRow("itso", "ITSO"), partyRow("ierc", "IERC", { in_pool: true })] },
    } as never);
    // What the server sends an IERC member while ITSO reviews and IERC's Pool
    // waits: nobody here decides, so no item speaks of closing.
    shownRecord = { ...inReview, ...reviewing, review_claim: { assignment: 55, label: "Claim review", party_label: "IERC" },
      readiness: { ...readinessFor([
        { kind: "party_reviewing", severity: "info", label: "ITSO is reviewing.",
          party: "itso", actor_name: "Ito Itso", since: "2026-09-03T08:00:00Z", action: { kind: "show_party", target: "itso" } },
        { kind: "pool_unclaimed", severity: "info", label: "Nobody at IERC has claimed this review yet.",
          party: "ierc", since: "2026-09-04T08:00:00Z", action: { kind: "claim", target: "55" } },
      ]), verdict: "waiting_on_you", headline: "IERC has not claimed this review yet." } };
    signInAs(2, "IERC");
    renderPaper(`/records/${RECORD_ID}?section=review`);
    const foot = await screen.findByRole("contentinfo", { name: "Your part" });
    expect(within(foot).getByText("IERC has not claimed this review yet.")).toBeInTheDocument();
    // Neither fact restates a party's status, so there is no line and nothing more to see.
    expect(within(foot).queryByRole("button", { name: "See what it depends on" })).not.toBeInTheDocument();

    const details = await openDetails();
    expect(within(details).queryByRole("heading", { name: "Readiness" })).not.toBeInTheDocument();
    expect(screen.queryByText("ITSO is reviewing.")).not.toBeInTheDocument();
    const itso = await within(details).findByText("ITSO");
    expect(itso.closest("li")).toHaveTextContent("Active");
    expect(within(details).getByText("Nobody has claimed this yet").closest("li")).toHaveTextContent(/^IERC/);

    // The footer's one filled action is the page's own claim.
    await userEvent.click(within(foot).getByRole("button", { name: "Claim review" }));
    expect(seatsApi.claim).toHaveBeenCalledWith(55);
  });

  it("shows no Readiness when the server does not disclose it (IR-681)", async () => {
    workspaceAt(1600);
    shownRecord = { ...inReview, ...reviewing, readiness: null };
    signInAs(2, "ITSO");
    renderPaper(`/records/${RECORD_ID}?section=review`);
    // Changed on purpose by IR-1203: a reviewer opens on Documents, so Conversation is a click away.
    await openConversation();
    await screen.findByRole("list", { name: "Review timeline" });
    expect(screen.queryByRole("heading", { name: "Readiness" })).not.toBeInTheDocument();
  });

  // IR-685 supersedes IR-681's version of this test on purpose: every party is
  // listed now, uninvolved ones in the tracker's words, and the Pool and
  // Request review read as the ticket words them.
  it("lists every party with its people, an unclaimed Pool as the office (IR-685)", async () => {
    workspaceAt(1600);
    vi.mocked(recordsApi.tracker).mockResolvedValue({ data: { ...trackerPayload, parties: [
      partyRow("itso", "ITSO", { seats: [
        { reviewer_name: "ITSO Reviewer", state: "in_review", state_label: "In review", verdict: null, verdict_label: null },
        { reviewer_name: "Cleared Colleague", state: "done", state_label: "Done", verdict: "approved", verdict_label: "Cleared" },
      ] }),
      partyRow("ierc", "IERC", { in_pool: true, due_at: "2026-11-04T08:00:00Z" }),
      partyRow("ktto", "KTTO", { state: "not_requested", state_label: "Not requested" }),
      partyRow("rdco", "RDCO", { state: "awaiting", state_label: "Waiting" }),
    ] } } as never);
    // IR-686: person cards now come from the server projection, not adviser_name.
    // No route or add_reviewer capability: this test asserts neither control shows.
    shownRecord = { ...inReview, ...reviewing, adviser_name: "Ada Adviser", keywords: ["groundwater"],
      paper_details: { ...sidebarDetails, adviser: adviserCard } };
    signInAs(2, "ITSO");
    renderPaper(`/records/${RECORD_ID}?section=review`);
    const side = await openDetails();
    expect(await within(side).findByRole("heading", { name: "Reviewers" })).toBeInTheDocument();

    const itso = within(side).getByRole("list", { name: "Reviewing for ITSO" });
    expect(within(itso).getAllByRole("listitem").map((li) => li.textContent)).toEqual([
      expect.stringMatching(/ITSO Reviewer.*In review/), expect.stringMatching(/Cleared Colleague.*Cleared/),
    ]);

    // The Pool is the office, not a person: no person card to open.
    const pool = within(side).getByText("Nobody has claimed this yet").closest("li")!;
    expect(pool).toHaveTextContent(/^IERC/);
    expect(within(pool).queryByRole("button")).not.toBeInTheDocument();

    expect(within(side).getByText("KTTO").closest("li")).toHaveTextContent("Not requested");
    expect(within(side).getByText("RDCO").closest("li")).toHaveTextContent("Waiting");
    expect(screen.queryByRole("button", { name: "Request review" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Add a colleague/ })).not.toBeInTheDocument();
    expect(within(side).getAllByRole("heading", { level: 3 }).map((h) => h.textContent)).toEqual([
      // IR-1193: keywords are pills under Classification; due dates sit on each reviewer's line.
      // Changed deliberately by IR-1202: Version and Documents are one Version history; Participants is gone.
      "Reviewers", "Researchers", "Adviser", "Classification", "Flagged by the authors", "Version history",
    ]);

    const adviser = within(side).getAllByRole("button", { name: /Ada Adviser/ })[0];
    await userEvent.click(adviser);
    expect(screen.getByRole("dialog", { name: "Ada Adviser" })).toHaveTextContent("Adviser on this record");
    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("dialog", { name: "Ada Adviser" })).not.toBeInTheDocument();
    expect(adviser).toHaveFocus();
  });

  it("says each party's status once: through its people when it has them, else on its own row (IR-1094)", async () => {
    workspaceAt(1600);
    vi.mocked(recordsApi.tracker).mockResolvedValue({ data: { ...trackerPayload, parties: [
      // The party says "Active"; its person says "In review". Only the person's is shown.
      partyRow("itso", "ITSO", { changes_requested: true, seats: [
        { reviewer_name: "ITSO Reviewer", state: "in_review", state_label: "In review", verdict: null, verdict_label: null },
      ] }),
      partyRow("ierc", "IERC", { state_label: "Waiting for a reviewer", in_pool: true }),
      partyRow("ktto", "KTTO", { state: "not_requested", state_label: "Not requested" }),
    ] } } as never);
    shownRecord = { ...inReview, ...reviewing };
    signInAs(2, "ITSO");
    renderPaper(`/records/${RECORD_ID}?section=review`);
    const details = await openDetails();
    await within(details).findByText("ITSO Reviewer");

    const itso = within(details).getByRole("list", { name: "Reviewing for ITSO" }).closest("li")!;
    expect(itso).toHaveTextContent("In review");
    expect(itso).not.toHaveTextContent("Active");
    expect(itso).not.toHaveTextContent("Changes requested");
    // An unclaimed Pool is the office with one line, not that line and a state beside it.
    const ierc = within(details).getByText("Nobody has claimed this yet").closest("li")!;
    expect(ierc).not.toHaveTextContent("Waiting for a reviewer");
    // A party with nobody to show says where it stands on its own row.
    expect(within(details).getByText("KTTO").closest("li")).toHaveTextContent("Not requested");
    expect(within(details).getAllByText(/In review/)).toHaveLength(1);
  });

  it("offers Request review with exactly the routing flags' targets, and refreshes once routed (IR-685)", async () => {
    workspaceAt(1600);
    vi.mocked(recordsApi.tracker).mockResolvedValue({ data: { ...trackerPayload, parties: [partyRow("itso", "ITSO")] } } as never);
    shownRecord = { ...inReview, ...reviewing, capabilities: ["route"],
      routing: { send_to_rdco: false, route_as: "itso", targets: [{ party: "ierc", label: "IERC" }, { party: "ktto", label: "KTTO" }] } };
    signInAs(2, "ITSO");
    renderPaper(`/records/${RECORD_ID}?section=review`);
    const side = await openDetails();
    const request = await within(side).findByRole("button", { name: "Request review" });
    expect(request).toHaveAccessibleDescription("Can be sent to IERC and KTTO");
    expect(within(screen.getByRole("contentinfo", { name: "Your part" })).queryByRole("button", { name: "Request review…" }))
      .not.toBeInTheDocument();

    const reads = vi.mocked(recordsApi.tracker).mock.calls.length;
    await userEvent.click(request);
    await userEvent.click(await screen.findByRole("checkbox", { name: "IERC" }));
    await userEvent.type(screen.getByRole("textbox", { name: "Why? (required)" }), "Human participants.");
    await userEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Send request" }));
    expect(recordsApi.route).toHaveBeenCalledWith(RECORD_ID, expect.objectContaining({ to: [{ party: "ierc" }] }));
    await waitFor(() => expect(vi.mocked(recordsApi.tracker).mock.calls.length).toBeGreaterThan(reads));
  });

  it("offers no Request review without targets, and Add a colleague only with add_reviewer (IR-685)", async () => {
    workspaceAt(1600);
    vi.mocked(recordsApi.tracker).mockResolvedValue({ data: { ...trackerPayload, parties: [partyRow("itso", "ITSO")] } } as never);
    shownRecord = { ...inReview, ...reviewing, capabilities: ["route", "add_reviewer"],
      routing: { send_to_rdco: false, route_as: "itso", targets: [] } };
    signInAs(2, "ITSO");
    renderPaper(`/records/${RECORD_ID}?section=review`);
    const side = await openDetails();
    await within(side).findByRole("heading", { name: "Reviewers" });
    expect(within(side).queryByRole("button", { name: "Request review" })).not.toBeInTheDocument();
    // A separate control from Request review, under the parties.
    expect(within(side).getByRole("button", { name: /Add a colleague/ })).toBeInTheDocument();
  });

  // Changed deliberately by IR-1202: Compare (the Changes tab's) and Copy link left Details,
  // and the Version line is Version history's, tested in "Version history (IR-1202)".
  it("draws one row per reviewer with Kept and a revision request (IR-1193)", async () => {
    workspaceAt(1600);
    vi.mocked(recordsApi.tracker).mockResolvedValue({ data: { ...trackerPayload,
      resubmissions: [{ id: 5, party: "ierc", label: "IERC", state: "open", state_label: "Open", reason: "Assent form", review: 1,
        version: 1, requested_by: "Marco Lim", created_at: "2026-09-30T08:00:00Z", resolved_at: null }],
      parties: [
        partyRow("itso", "ITSO", { state: "completed", state_label: "Completed", carryover: "preserved",
          carryover_label: "Cleared on v1, preserved", seats: [
            { reviewer_name: "Irene Villanueva", state: "done", state_label: "Done", verdict: "approved", verdict_label: "Cleared" },
          ] }),
        partyRow("ierc", "IERC", { seats: [
          { reviewer_name: "Marco Lim", state: "in_review", state_label: "Reviewing", verdict: null, verdict_label: null },
        ] }),
      ] } } as never);
    shownRecord = { ...inReview, ...reviewing, versions: [
      { number: 1, cause: "submission", cause_label: "Submission", created_at: "2026-09-05T08:00:00Z", created_by_name: "Rhea Owner", manuscript_url: PAPER_URL },
      { number: 2, cause: "revision", cause_label: "Revision", created_at: "2026-10-07T08:00:00Z", created_by_name: "Rhea Owner", manuscript_url: PAPER_URL },
    ] };
    signInAs(2, "ITSO");
    renderPaper(`/records/${RECORD_ID}?section=review`);
    const side = await openDetails();
    const itso = within(await within(side).findByRole("list", { name: "Reviewing for ITSO" })).getByRole("listitem");
    // A clearance kept through the resubmission says so, with the server's words on hover.
    expect(within(itso).getByText("Kept")).toHaveAttribute("title", "Cleared on v1, preserved");
    expect(itso).toHaveTextContent(/Irene VillanuevaITSO · Sep 2, 2026Kept$/);
    const ierc = within(within(side).getByRole("list", { name: "Reviewing for IERC" })).getByRole("listitem");
    expect(ierc).toHaveTextContent(/IERC · Since /);
    expect(ierc).toHaveTextContent("Requested revision on v1");
    expect(ierc).toHaveTextContent("Reviewing");
  });

  // IR-1202: Details keeps only who and what. Version and Documents become one
  // plain-text Version history; files, requests and downloads are the Documents
  // tab's (IR-1203), and comparing versions is the Changes tab's.
  describe("Version history (IR-1202)", () => {
    const v = (number: number, created_at: string, extra: Partial<NonNullable<RecordDetail["versions"]>[number]> = {}) => ({
      number, cause: number === 1 ? "submission" as const : "revision" as const, cause_label: number === 1 ? "Submission" : "Revision",
      created_at, created_by_name: "Rhea Owner", manuscript_url: PAPER_URL, ...extra,
    });
    const doc = (upload_id: number, slot: string, version: number, uploaded_at: string, rejections: unknown = []) => ({
      upload_id, slot, version, uploaded_at, download_url: `/api/v1/documents/uploads/${upload_id}/download/`, rejections,
    }) as NonNullable<NonNullable<RecordDetail["versions"]>[number]["documents"]>[number];
    const ethics = doc(10, "Ethics Clearance", 1, "2026-10-06T08:00:00Z");
    const consent1 = doc(11, "Consent Paper", 1, "2026-10-08T08:00:00Z");
    const consent2 = doc(12, "Consent Paper", 2, "2026-11-03T08:00:00Z");
    const history = async () => {
      const side = await openDetails();
      return within(await within(side).findByRole("list", { name: "Manuscript versions, oldest first" }));
    };
    const lines = (list: HTMLElement) => within(list).getAllByRole("listitem").map((li) => li.textContent);

    it("keeps only who and what in Details", async () => {
      workspaceAt(1600);
      shownRecord = { ...inReview, ...reviewing, versions: [v(1, "2026-10-07T08:00:00Z"), v(2, "2026-11-01T08:00:00Z")],
        files: [{ id: 88, filename: "consent.pdf", url: "/api/v1/files/88/download/" } as RecordDetail["files"][number]] };
      signInAs(2, "ITSO");
      renderPaper(`/records/${RECORD_ID}?section=review`);
      const side = await openDetails();
      await within(side).findByRole("heading", { name: "Researchers" });

      expect(within(side).getAllByRole("heading", { level: 3 }).map((h) => h.textContent)).toEqual([
        "Reviewers", "Researchers", "Adviser", "Classification", "Flagged by the authors", "Version history",
      ]);
      for (const gone of ["Copy link to this review", "All documents", "Compare 2 versions", "consent.pdf", "Manuscript · v2"]) {
        expect(within(side).queryByRole("button", { name: gone })).not.toBeInTheDocument();
      }
    });

    it("lists each Version oldest first, with what was submitted under it, as text", async () => {
      workspaceAt(1600);
      shownRecord = { ...inReview, ...reviewing, versions: [
        // v2's documents repeat v1's unchanged uploads: each is listed once, under the first Version that has it.
        v(1, "2026-10-07T08:00:00Z", { documents: [ethics], documents_added: [consent1] }),
        v(2, "2026-11-01T08:00:00Z", { documents: [ethics, consent1], documents_added: [consent2] }),
      ] };
      signInAs(2, "ITSO");
      renderPaper(`/records/${RECORD_ID}?section=review`);
      const list = await history();

      const versionLine = (_: string, el: Element | null) => el?.tagName === "P" && /^Manuscript v/.test(el.textContent ?? "");
      expect(list.getAllByText(versionLine).map((el) => el.textContent))
        .toEqual(["Manuscript v1 · submitted October 7, 2026", "Manuscript v2 · submitted November 1, 2026"]);
      expect(lines(list.getByRole("list", { name: "Documents with v1" }))).toEqual([
        "Ethics Clearance v1 · submitted October 6, 2026", "Consent Paper v1 · submitted October 8, 2026",
      ]);
      expect(lines(list.getByRole("list", { name: "Documents with v2" }))).toEqual(["Consent Paper v2 · submitted November 3, 2026"]);
      expect(list.queryAllByRole("button")).toEqual([]);
      expect(list.queryAllByRole("link")).toEqual([]);
    });

    it("gives a replaced document its rejection reason, and none where requests are not disclosed", async () => {
      workspaceAt(1600);
      const rejected = doc(11, "Consent Paper", 1, "2026-10-08T08:00:00Z", [{
        party: "ierc", reason: "The signature page is missing.", rejected_by_name: "Marco Lim", rejected_at: "2026-10-09T08:00:00Z",
      }]);
      shownRecord = { ...inReview, ...reviewing, versions: [
        v(1, "2026-10-07T08:00:00Z", { documents: [rejected], documents_added: [consent2] }),
      ] };
      signInAs(2, "ITSO");
      const { unmount } = renderPaper(`/records/${RECORD_ID}?section=review`);
      const [first, second] = (await history()).getByRole("list", { name: "Documents with v1" }).children;
      expect(first).toHaveTextContent("Consent Paper v1 · submitted October 8, 2026");
      expect(first).toHaveTextContent("Replacement asked by IERC: The signature page is missing.");
      expect(second).not.toHaveTextContent("Replacement asked");
      unmount();

      // Reject reasons are document-request data (ADR-022 §Amendment 5): `null` to a reader who may not read requests.
      shownRecord = { ...inReview, ...reviewing, versions: [v(1, "2026-10-07T08:00:00Z", { documents: [{ ...rejected, rejections: null }] })] };
      renderPaper(`/records/${RECORD_ID}?section=review`);
      expect((await history()).getByRole("list", { name: "Documents with v1" })).not.toHaveTextContent("Replacement asked");
    });

    it("shows a Version from before IR-872 its reconstructed list with no note", async () => {
      workspaceAt(1600);
      shownRecord = { ...inReview, ...reviewing, versions: [
        v(1, "2026-10-07T08:00:00Z", { documents: [ethics], documents_reconstructed: true }),
      ] };
      signInAs(2, "ITSO");
      renderPaper(`/records/${RECORD_ID}?section=review`);
      const list = await history();
      expect(lines(list.getByRole("list", { name: "Documents with v1" }))).toEqual(["Ethics Clearance v1 · submitted October 6, 2026"]);
      expect(screen.queryByText(/best guess/)).not.toBeInTheDocument();
    });

    it("gives the owner the same history at 320px, reached by keyboard, with no serious axe violations", async () => {
      workspaceAt(320);
      shownRecord = { ...inReview, versions: [v(1, "2026-10-07T08:00:00Z", { documents: [ethics] })] };
      signInAs(OWNER_ID, "Student");
      const { container } = renderPaper(`/records/${RECORD_ID}?section=review`);

      await userEvent.click(await screen.findByRole("button", { name: "Open review pane" }));
      const pane = screen.getByRole("dialog", { name: "Review pane" });
      within(pane).getByRole("tab", { name: "Readiness", selected: true }).focus();
      await userEvent.keyboard("{End}");
      const details = within(pane).getByRole("tabpanel", { name: "Details" });
      const list = within(await within(details).findByRole("list", { name: "Manuscript versions, oldest first" }));
      expect(lines(list.getByRole("list", { name: "Documents with v1" }))).toEqual(["Ethics Clearance v1 · submitted October 6, 2026"]);
      await expectNoBlockingA11yViolations(container);
    });
  });

  it("withholds who reviews, due dates and participants when the review is not readable (IR-681)", async () => {
    workspaceAt(1600);
    vi.mocked(recordsApi.tracker).mockResolvedValue({ data: { ...trackerPayload, reviews: null, review_comments: null,
      versions: null, parties: [partyRow("itso", "ITSO", { seats: null, due_at: "2026-11-04T08:00:00Z" })] } } as never);
    shownRecord = { ...inReview, ...reviewing, readiness: null,
      paper_details: { ...sidebarDetails, participants: null, due_dates: null } };
    signInAs(2, "ITSO");
    renderPaper(`/records/${RECORD_ID}?section=review`);
    const side = await openDetails();
    await within(side).findByRole("heading", { name: "Reviewers" });
    // Whose seat it is, and how far each has got, are review content.
    expect(within(side).queryByRole("list", { name: "Reviewing for ITSO" })).not.toBeInTheDocument();
    expect(within(side).getByText("ITSO").closest("li")).toHaveTextContent("Active");
    expect(within(side).queryByRole("heading", { name: "Due dates" })).not.toBeInTheDocument();
    expect(within(side).queryByRole("heading", { name: /participants?$/ })).not.toBeInTheDocument();
  });

  it.each([1600, 1100])("renders paper details from the payload at %ipx (IR-686)", async (width) => {
    workspaceAt(width);
    vi.mocked(recordsApi.tracker).mockResolvedValue({ data: { ...trackerPayload, parties: [
      partyRow("itso", "ITSO", { seats: [{ reviewer: 2, reviewer_name: "Ian Reviewer", state: "in_review", state_label: "In review", verdict: null, verdict_label: null }] }),
    ] } } as never);
    shownRecord = { ...inReview, ...reviewing, keywords: ["groundwater"], psced: "0613",
      authors: [{ id: 999, name: "An imported author, not an owner", role: null }],
      versions: [{ number: 1, cause: "submission", cause_label: "Submission", created_at: "2026-10-30T08:00:00Z", created_by_name: "Rhea Owner", manuscript_url: PAPER_URL }],
      files: [{ id: 88, filename: "consent.pdf", url: "/api/v1/files/88/download/" } as RecordDetail["files"][number]],
      paper_details: { ...sidebarDetails, colleges: ["College of Computer Studies"], programs: ["BS Computer Science"],
        adviser: adviserCard, author_flags: [{ office: "ktto", label: "KTTO", hint: "The author flagged possible commercialisation." }],
        due_dates: [
          { party: "itso", label: "ITSO", due_at: "2026-10-01T08:00:00Z", original_due_at: null, is_overdue: true, clock_paused: false },
          { party: "ierc", label: "IERC", due_at: null, original_due_at: null, is_overdue: false, clock_paused: true },
        ],
        participants: [researcherCard, adviserCard, { ...researcherCard, id: 2, name: "Ian Reviewer", role: "ITSO reviewer", office: "ITSO", email: null }],
      } };
    signInAs(2, "ITSO");
    renderPaper(`/records/${RECORD_ID}?section=review`);
    const side = await openDetails();
    await within(side).findByRole("heading", { name: "Researchers" });
    expect(within(side).getAllByRole("heading", { level: 3 }).map((h) => h.textContent)).toEqual([
      // IR-685: the heading no longer counts parties; every party is listed.
      // Changed deliberately by IR-1202: Version history replaces Version and Documents; Participants is gone.
      "Reviewers", "Researchers", "Adviser", "Classification", "Flagged by the authors", "Version history",
    ]);
    const section = (name: string) => within(within(side).getByRole("heading", { name }).closest("section")!);
    expect(section("Researchers").getByRole("button", { name: "Rhea Owner" })).toBeInTheDocument();
    expect(side).not.toHaveTextContent("An imported author, not an owner");
    expect(section("Classification").getByText("College of Computer Studies")).toBeInTheDocument();
    expect(section("Classification").getByText("BS Computer Science")).toBeInTheDocument();
    expect(section("Classification").getByText("0613")).toBeInTheDocument();
    expect(section("Flagged by the authors").getByText("KTTO")).toHaveAttribute("title", "The author flagged possible commercialisation.");
    expect(within(side).getByRole("heading", { name: "Version history" }).closest("section")).toHaveTextContent("Manuscript v1 · submitted October 30, 2026");
    // IR-1193: the due date is on the reviewer's own line, overdue emphasised; IERC asks for nobody here.
    expect(section("Classification").getByRole("list", { name: "Type, area and keywords" })).toHaveTextContent("groundwater");
    const ianRow = within(section("Reviewers").getByRole("list", { name: "Reviewing for ITSO" })).getByRole("listitem");
    expect(within(ianRow).getByText(/Overdue: was due/)).toHaveClass("text-brand");
    expect(side).not.toHaveTextContent("Clock paused while waiting on the submitter");
    // Changed deliberately by IR-1202: Details no longer downloads; files are the Documents tab's (IR-1203).
    expect(side).not.toHaveTextContent("consent.pdf");
    const adviser = section("Adviser").getByRole("button", { name: "Ada Adviser" });
    await userEvent.click(adviser);
    const profile = screen.getByRole("dialog", { name: "Ada Adviser" });
    expect(profile).toHaveTextContent("College of Computer Studies");
    expect(within(profile).getByRole("link", { name: "ada@cit.edu" })).toHaveAttribute("href", "mailto:ada@cit.edu");
    expect(within(profile).queryByText("Program")).not.toBeInTheDocument();
    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("dialog", { name: "Ada Adviser" })).not.toBeInTheDocument();
    expect(adviser).toHaveFocus();
    await userEvent.click(adviser);
    await userEvent.click(within(side).getByRole("heading", { name: "Classification" }));
    expect(screen.queryByRole("dialog", { name: "Ada Adviser" })).not.toBeInTheDocument();
    expect(adviser).toHaveFocus();
    const reviewer = within(side).getByRole("list", { name: "Reviewing for ITSO" });
    await userEvent.click(within(reviewer).getByRole("button", { name: "Ian Reviewer" }));
    const minimal = screen.getByRole("dialog", { name: "Ian Reviewer" });
    expect(minimal).toHaveTextContent("ITSO reviewer on this record");
    expect(minimal).toHaveTextContent("ITSO");
    expect(within(minimal).queryByText("Contact")).not.toBeInTheDocument();
  });

  it("shows withheld Classification and omits private sections from the payload (IR-686)", async () => {
    workspaceAt(1600);
    shownRecord = { ...inReview, ...reviewing, paper_details: { ...sidebarDetails, participants: null, due_dates: null } };
    signInAs(2, "ITSO");
    renderPaper(`/records/${RECORD_ID}?section=review`);
    const side = await openDetails();
    const classification = (await within(side).findByRole("heading", { name: "Classification" })).closest("section")!;
    expect(within(classification).getAllByText("Not disclosed")).toHaveLength(2);
    expect(within(side).queryByRole("heading", { name: "Due dates" })).not.toBeInTheDocument();
    expect(within(side).queryByRole("heading", { name: /participants?$/ })).not.toBeInTheDocument();
    const researcher = within(within(side).getByRole("heading", { name: "Researchers" }).closest("section")!);
    await userEvent.click(researcher.getByRole("button", { name: "Rhea Owner" }));
    const profile = screen.getByRole("dialog", { name: "Rhea Owner" });
    expect(within(profile).getByRole("link", { name: "owner@cit.edu" })).toBeInTheDocument();
    expect(within(profile).queryByText("College")).not.toBeInTheDocument();
    expect(within(profile).queryByText("Program")).not.toBeInTheDocument();
  });

  // IR-686's "reports an authenticated document download failure and allows
  // retry" was removed deliberately by IR-1202: Details no longer downloads
  // anything. The documents drawer keeps its own download tests.

  it("takes See what it depends on to Details and focuses the facts, in a narrow workspace too (IR-1094)", async () => {
    workspaceAt(1000);
    shownRecord = { ...inReview, ...reviewing, readiness: readinessFor([
      { kind: "due_date", severity: "info", label: "ITSO is due Fri 11 Sep.", party: "itso" },
    ]) };
    signInAs(2, "ITSO");
    renderPaper(`/records/${RECORD_ID}?section=review`);
    await userEvent.click(await screen.findByRole("button", { name: "See what it depends on" }));
    expect(screen.getByRole("tab", { name: "Details", selected: true })).toBeInTheDocument();
    const section = screen.getByRole("heading", { name: "Readiness" }).closest("section")!;
    await waitFor(() => expect(section).toHaveFocus());
    expect(within(section).getByText("ITSO is due Fri 11 Sep.")).toBeInTheDocument();
  });

  // IR-1203: documents are a tab of their own, for authors and reviewers. The
  // "All documents" drawer is gone; everything that opened it opens the tab.
  describe("the Documents tab (IR-1203)", () => {
    const paneTabs = () => within(screen.getByRole("tablist", { name: "Review pane sections" }))
      .getAllByRole("tab").map((t) => t.textContent?.replace(/\s*\d+$/, "").trim());
    const upload = (id: number, version: number, created_at: string) => ({
      id, record: RECORD_ID, slot: 3, slot_name: "Consent Paper", file: `consent-v${version}.pdf`, version,
      status: null, status_name: null, uploaded_by: OWNER_ID, uploaded_by_name: "Rhea Owner", created_at,
      reviews: [], delete_refused: null,
    });
    beforeEach(() => {
      vi.mocked(documentsApi.slotsForRecord).mockResolvedValue({ data: [
        // Newest first, as the server orders them.
        { id: 3, name: "Consent Paper", record_type: 1, is_required: false,
          uploads: [upload(12, 2, "2026-11-03T08:00:00Z"), upload(11, 1, "2026-10-08T08:00:00Z")] },
      ] } as never);
    });
    afterEach(() => {
      vi.mocked(documentsApi.slotsForRecord).mockResolvedValue({ data: [] } as never);
      documentRequests.mockResolvedValue({ data: [] });
    });

    it("is the reviewers' first tab, where they open, with one row per document", async () => {
      workspaceAt(1600);
      shownRecord = { ...inReview, ...reviewing };
      signInAs(2, "ITSO");
      renderPaper(`/records/${RECORD_ID}?section=review`);

      await screen.findByRole("region", { name: "Review pane content" });
      expect(paneTabs()).toEqual(["Documents", "Conversation", "Threads", "Changes", "Details"]);
      expect(screen.getByRole("tab", { name: "Documents", selected: true })).toBeInTheDocument();
      const panel = screen.getByRole("tabpanel", { name: "Documents" });
      const consent = await within(panel).findByRole("group", { name: "Consent Paper" });
      expect(consent).toHaveTextContent(`v2 · Rhea Owner · ${formatDate("2026-11-03T08:00:00Z")}`);
      expect(within(panel).getByRole("group", { name: "Manuscript" })).toBeInTheDocument();
      // A reviewer downloads; only an owner uploads.
      expect(within(consent).getByRole("button", { name: "Download Consent Paper version 2" })).toBeInTheDocument();
      expect(within(consent).queryByRole("button", { name: /^Upload/ })).not.toBeInTheDocument();
      expect(screen.queryByRole("dialog", { name: "All documents" })).not.toBeInTheDocument();
    });

    it("keeps older versions one click away", async () => {
      workspaceAt(1600);
      shownRecord = { ...inReview, ...reviewing };
      signInAs(2, "ITSO");
      renderPaper(`/records/${RECORD_ID}?section=review&documents=open`);

      const consent = await within(await screen.findByRole("tabpanel", { name: "Documents" }))
        .findByRole("group", { name: "Consent Paper" });
      expect(within(consent).queryByRole("list", { name: "Versions of Consent Paper" })).not.toBeInTheDocument();
      await userEvent.click(within(consent).getByRole("button", { name: "2 versions of Consent Paper" }));
      const versions = within(consent).getByRole("list", { name: "Versions of Consent Paper" });
      expect(within(versions).getAllByRole("listitem").map((li) => li.textContent?.match(/^Version \d/)?.[0]))
        .toEqual(["Version 2", "Version 1"]);
      expect(within(versions).getByRole("button", { name: "Download Consent Paper version 1" })).toBeInTheDocument();
    });

    it("comes second for the author, after Readiness, which has no Documents button", async () => {
      workspaceAt(1600);
      shownRecord = { ...inReview, capabilities: ["cite", "edit_details"] };
      signInAs(OWNER_ID, "Student");
      renderPaper(`/records/${RECORD_ID}?section=review`);

      const readiness = await screen.findByRole("tabpanel", { name: "Readiness" });
      expect(paneTabs()).toEqual(["Readiness", "Documents", "Conversation", "Threads", "Details"]);
      expect(within(readiness).queryByRole("button", { name: "Documents" })).not.toBeInTheDocument();
      // Read only once shown, as the drawer was: an author who stays on Readiness fetches nothing.
      expect(documentsApi.slotsForRecord).not.toHaveBeenCalled();
      await userEvent.click(screen.getByRole("tab", { name: "Documents" }));
      const consent = await within(screen.getByRole("tabpanel", { name: "Documents" }))
        .findByRole("group", { name: "Consent Paper" });
      // The owner of an editable record may add a version to any slot.
      expect(within(consent).getByRole("button", { name: /^Upload Consent Paper/ })).toBeInTheDocument();
    });

    it.each([
      ["an old Documents link", `?section=review&documents=open`],
      ["an old Files link", `?section=files`],
    ])("opens %s on the Documents tab, with no drawer", async (_, search) => {
      workspaceAt(1600);
      shownRecord = inReview;
      signInAs(OWNER_ID, "Student");
      renderPaper(`/records/${RECORD_ID}${search}`);

      expect(await screen.findByRole("tab", { name: "Review", selected: true })).toBeInTheDocument();
      expect(await screen.findByRole("tab", { name: "Documents", selected: true })).toBeInTheDocument();
      expect(await within(screen.getByRole("tabpanel", { name: "Documents" })).findByRole("group", { name: "Consent Paper" }))
        .toBeInTheDocument();
      expect(screen.queryByRole("dialog", { name: "All documents" })).not.toBeInTheDocument();
    });

    it("offers the owner Upload on a requested slot while the record is in review, and on no other", async () => {
      workspaceAt(1600);
      documentRequests.mockResolvedValue({ data: [{
        id: 1, party: "ierc", label: "IERC", state: "open", state_label: "Open", message: "The signed form, please.",
        requested_by: null, created_at: "2026-09-20T02:00:00Z", closed_at: null, can_manage: false,
        items: [{ id: 11, slot: 3, label: "Consent Paper", state: "missing", state_label: "Missing", upload: null,
          uploaded_at: null, rejection_reason: null, decided_at: null }],
      }] });
      vi.mocked(documentsApi.slotsForRecord).mockResolvedValue({ data: [
        { id: 3, name: "Consent Paper", record_type: 1, is_required: false, uploads: [upload(11, 1, "2026-10-08T08:00:00Z")] },
        { id: 4, name: "Ethics Clearance", record_type: 1, is_required: false, uploads: [upload(13, 1, "2026-10-06T08:00:00Z")] },
      ] } as never);
      // In review, and not editable: no `edit_details`.
      shownRecord = { ...inReview, capabilities: ["cite"] };
      signInAs(OWNER_ID, "Student");
      renderPaper(`/records/${RECORD_ID}?section=review&documents=open`);

      const panel = await screen.findByRole("tabpanel", { name: "Documents" });
      const consent = await within(panel).findByRole("group", { name: "Consent Paper" });
      expect(await within(consent).findByText("Requested by IERC.")).toBeInTheDocument();
      expect(within(consent).getByRole("button", { name: /^Upload Consent Paper/ })).toBeInTheDocument();
      expect(within(within(panel).getByRole("group", { name: "Ethics Clearance" })).queryByRole("button", { name: /^Upload/ }))
        .not.toBeInTheDocument();
    });

    it("opens a reviewer's pane on Documents at 320px, reached by keyboard, with no serious axe violations", async () => {
      workspaceAt(320);
      shownRecord = { ...inReview, ...reviewing };
      signInAs(2, "ITSO");
      const { container } = renderPaper(`/records/${RECORD_ID}?section=review`);

      await userEvent.click(await screen.findByRole("button", { name: "Open review pane" }));
      const pane = screen.getByRole("dialog", { name: "Review pane" });
      const tab = within(pane).getByRole("tab", { name: "Documents", selected: true });
      expect(await within(within(pane).getByRole("tabpanel", { name: "Documents" })).findByRole("group", { name: "Consent Paper" }))
        .toBeInTheDocument();
      tab.focus();
      await userEvent.keyboard("{End}");
      expect(within(pane).getByRole("tab", { name: "Details", selected: true })).toHaveFocus();
      await userEvent.keyboard("{Home}");
      expect(within(pane).getByRole("tab", { name: "Documents", selected: true })).toHaveFocus();
      await expectNoBlockingA11yViolations(container);
    });

    it("opens the author's pane on Documents at 320px, reached by keyboard, with no serious axe violations", async () => {
      workspaceAt(320);
      shownRecord = inReview;
      signInAs(OWNER_ID, "Student");
      const { container } = renderPaper(`/records/${RECORD_ID}?section=review&documents=open`);

      const pane = await screen.findByRole("dialog", { name: "Review pane" });
      const tab = within(pane).getByRole("tab", { name: "Documents", selected: true });
      expect(await within(within(pane).getByRole("tabpanel", { name: "Documents" })).findByRole("group", { name: "Consent Paper" }))
        .toBeInTheDocument();
      tab.focus();
      await userEvent.keyboard("{Home}");
      expect(within(pane).getByRole("tab", { name: "Readiness", selected: true })).toHaveFocus();
      await userEvent.keyboard("{ArrowRight}");
      expect(within(pane).getByRole("tab", { name: "Documents", selected: true })).toHaveFocus();
      await expectNoBlockingA11yViolations(container);
    });

    // Part (b): a document opens in the reader on the left.
    it("opens a reviewer's document in the reader, with nothing to highlight, and goes back", async () => {
      workspaceAt(1600);
      shownRecord = { ...inReview, ...reviewing };
      signInAs(2, "ITSO");
      renderPaper(`/records/${RECORD_ID}?section=review`);

      const consent = await screen.findByRole("group", { name: "Consent Paper" });
      await userEvent.click(within(consent).getByRole("button", { name: "Open Consent Paper version 2" }));

      expect(await screen.findByText(/reading upload 12/)).toBeInTheDocument();
      const shown = screen.getByRole("group", { name: "Shown in the reader" });
      expect(shown).toHaveTextContent("Consent Paper · version 2");
      // Highlights and Ask IRIS belong to the manuscript only.
      expect(screen.queryByRole("button", { name: /^Selection:/ })).not.toBeInTheDocument();

      await userEvent.click(within(shown).getByRole("button", { name: "Back to the manuscript" }));
      expect(await screen.findByText(/reading the current paper/)).toBeInTheDocument();
      expect(screen.queryByRole("group", { name: "Shown in the reader" })).not.toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Selection: Save highlight" })).toBeInTheDocument();
    });

    it("opens an author's older version and PDF attachment, while a Word file only downloads", async () => {
      workspaceAt(1600);
      shownRecord = inReview;
      signInAs(OWNER_ID, "Student");
      vi.mocked(documentsApi.files).mockResolvedValue({ data: [
        { id: 31, record: RECORD_ID, file: "x/survey.pdf", filename: "Survey results.pdf", uploaded_by: OWNER_ID,
          uploaded_by_name: "Rhea Owner", created_at: "2026-11-03T08:00:00Z", can_remove: false },
        { id: 32, record: RECORD_ID, file: "x/notes.docx", filename: "Interview notes.docx", uploaded_by: OWNER_ID,
          uploaded_by_name: "Rhea Owner", created_at: "2026-11-03T08:00:00Z", can_remove: false },
      ] } as never);
      const { container } = renderPaper(`/records/${RECORD_ID}?section=review&documents=open`);

      const consent = await screen.findByRole("group", { name: "Consent Paper" });
      await userEvent.click(within(consent).getByRole("button", { name: "2 versions of Consent Paper" }));
      await userEvent.click(within(consent).getByRole("button", { name: "Open Consent Paper version 1" }));
      expect(await screen.findByText(/reading upload 11/)).toBeInTheDocument();
      expect(screen.getByRole("group", { name: "Shown in the reader" })).toHaveTextContent("Consent Paper · version 1");

      const survey = await screen.findByRole("group", { name: "Survey results.pdf" });
      await userEvent.click(within(survey).getByRole("button", { name: "Open Survey results.pdf" }));
      expect(await screen.findByText(/reading file 31/)).toBeInTheDocument();
      await expectNoBlockingA11yViolations(container);

      const notes = screen.getByRole("group", { name: "Interview notes.docx" });
      expect(within(notes).queryByRole("button", { name: /^Open/ })).not.toBeInTheDocument();
      expect(within(notes).getByRole("button", { name: "Download Interview notes.docx" })).toBeInTheDocument();
      vi.mocked(documentsApi.files).mockResolvedValue({ data: [] } as never);
    });

    // The image half (IR-1203, after IR-1220): a scan opens as an image; an SVG, which can carry script, never does.
    it("opens a PNG or JPG attachment as an image in the reader, and never an SVG", async () => {
      workspaceAt(1600);
      shownRecord = inReview;
      signInAs(OWNER_ID, "Student");
      // jsdom has no object URLs; stubbed for this test and restored after it.
      const { createObjectURL, revokeObjectURL } = URL;
      URL.createObjectURL = vi.fn(() => "blob:scan");
      URL.revokeObjectURL = vi.fn();
      onTestFinished(() => {
        URL.createObjectURL = createObjectURL;
        URL.revokeObjectURL = revokeObjectURL;
      });
      vi.mocked(documentsApi.viewFile).mockResolvedValue({ data: new Blob(["png"], { type: "image/png" }) } as never);
      const file = (id: number, filename: string) => ({
        id, record: RECORD_ID, file: `x/${id}`, filename, uploaded_by: OWNER_ID,
        uploaded_by_name: "Rhea Owner", created_at: "2026-11-03T08:00:00Z", can_remove: false,
      });
      vi.mocked(documentsApi.files).mockResolvedValue({ data: [
        file(33, "Signed consent.JPG"), file(34, "diagram.svg"),
      ] } as never);
      const { container } = renderPaper(`/records/${RECORD_ID}?section=review&documents=open`);

      await screen.findByRole("group", { name: "Consent Paper" });
      const diagram = await screen.findByRole("group", { name: "diagram.svg" });
      expect(within(diagram).queryByRole("button", { name: /^Open/ })).not.toBeInTheDocument();

      const consent = screen.getByRole("group", { name: "Signed consent.JPG" });
      await userEvent.click(within(consent).getByRole("button", { name: "Open Signed consent.JPG" }));
      expect(await screen.findByRole("img", { name: "Signed consent.JPG" })).toHaveAttribute("src", "blob:scan");
      expect(documentsApi.viewFile).toHaveBeenCalledWith(33, expect.anything());
      // Not the PDF reader: an image has no pages to read.
      expect(screen.queryByText(/reading file 33/)).not.toBeInTheDocument();
      expect(screen.getByRole("group", { name: "Shown in the reader" })).toHaveTextContent("Signed consent.JPG");
      expect(within(screen.getByRole("toolbar", { name: "Image tools" }))
        .getByRole("button", { name: "Download Signed consent.JPG" })).toBeInTheDocument();
      await expectNoBlockingA11yViolations(container);

      await userEvent.click(screen.getByRole("button", { name: "Back to the manuscript" }));
      expect(await screen.findByText(/reading the current paper/)).toBeInTheDocument();
      expect(screen.queryByRole("img", { name: "Signed consent.JPG" })).not.toBeInTheDocument();
      vi.mocked(documentsApi.files).mockResolvedValue({ data: [] } as never);
    });

    it("closes the narrow pane when a document opens, so the reader is seen", async () => {
      workspaceAt(320);
      shownRecord = { ...inReview, ...reviewing };
      signInAs(2, "ITSO");
      renderPaper(`/records/${RECORD_ID}?section=review`);

      await userEvent.click(await screen.findByRole("button", { name: "Open review pane" }));
      const pane = screen.getByRole("dialog", { name: "Review pane" });
      const consent = await within(pane).findByRole("group", { name: "Consent Paper" });
      await userEvent.click(within(consent).getByRole("button", { name: "Open Consent Paper version 2" }));

      await waitFor(() => expect(screen.queryByRole("dialog", { name: "Review pane" })).not.toBeInTheDocument());
      expect(screen.getByText(/reading upload 12/)).toBeInTheDocument();
      // The pane that held Open is closed: focus is on what the reader now shows.
      expect(screen.getByRole("group", { name: "Shown in the reader" })).toHaveFocus();
    });

    it("is reached and left by keyboard, focus going to the document and back to Open, with no serious axe violations", async () => {
      workspaceAt(1600);
      shownRecord = { ...inReview, ...reviewing };
      signInAs(2, "ITSO");
      const { container } = renderPaper(`/records/${RECORD_ID}?section=review`);

      const consent = await screen.findByRole("group", { name: "Consent Paper" });
      const open = within(consent).getByRole("button", { name: "Open Consent Paper version 2" });
      open.focus();
      await userEvent.keyboard("{Enter}");

      const shown = await screen.findByRole("group", { name: "Shown in the reader" });
      // Focus says what the reader now shows: the strip's description names the document.
      expect(shown).toHaveFocus();
      expect(shown).toHaveAccessibleDescription("Consent Paper · version 2 · a supporting document, not the manuscript");
      await expectNoBlockingA11yViolations(container);

      await userEvent.tab();
      expect(within(shown).getByRole("button", { name: "Back to the manuscript" })).toHaveFocus();
      await userEvent.keyboard("{Enter}");
      expect(await screen.findByText(/reading the current paper/)).toBeInTheDocument();
      await waitFor(() => expect(within(screen.getByRole("group", { name: "Consent Paper" }))
        .getByRole("button", { name: "Open Consent Paper version 2" })).toHaveFocus());
    });

    it("opens the document's latest version over an earlier manuscript Version, and Back returns to that Version", async () => {
      workspaceAt(1600);
      const versionOf = (number: number) => ({
        number, cause: number === 1 ? "submission" : "revision", cause_label: number === 1 ? "Submission" : "Revision",
        created_at: `2026-09-0${number}T08:00:00Z`, created_by_name: "Rhea Owner",
        manuscript_url: `/api/v1/records/${RECORD_ID}/versions/${number}/manuscript/`,
      });
      shownRecord = { ...inReview, ...reviewing, versions: [versionOf(1), versionOf(2)] } as RecordDetail;
      signInAs(2, "ITSO");
      renderPaper(`/records/${RECORD_ID}?section=review&version=1`);
      expect(await screen.findByText(/reading v1/)).toBeInTheDocument();
      expect(screen.getByRole("combobox", { name: "Version" })).toBeInTheDocument();

      const consent = await screen.findByRole("group", { name: "Consent Paper" });
      await userEvent.click(within(consent).getByRole("button", { name: "Open Consent Paper version 2" }));
      expect(await screen.findByText(/reading upload 12/)).toBeInTheDocument();
      // The bar would describe the manuscript, so it says nothing of it while a document is shown.
      expect(screen.queryByRole("combobox", { name: "Version" })).not.toBeInTheDocument();

      await userEvent.click(screen.getByRole("button", { name: "Back to the manuscript" }));
      expect(await screen.findByText(/reading v1/)).toBeInTheDocument();
      expect(screen.getByRole("combobox", { name: "Version" })).toBeInTheDocument();
    });
  });

  describe("document requests and the viewer's due date (IR-684)", () => {
    const documentsAndDue = () => readinessFor([
      { kind: "document_request", severity: "blocker", label: "ITSO asked the author for a document.", party: "itso",
        actor_name: "Ito Itso", since: "2026-09-03T08:00:00Z", action: { kind: "open_documents", target: "5" } },
      { kind: "due_date", severity: "info", party: "itso", paused: true,
        label: "ITSO is due Fri 11 Sep. The clock is paused while ITSO's document request is open." },
    ]);

    it("renders both kinds in the server's words, and Open Documents opens the Documents tab", async () => {
      workspaceAt(1600);
      shownRecord = { ...inReview, ...reviewing, readiness: documentsAndDue() };
      signInAs(2, "ITSO");
      renderPaper(`/records/${RECORD_ID}?section=review`);
      const foot = await screen.findByRole("contentinfo", { name: "Your part" });
      expect(within(foot).getByText("ITSO asked the author for a document.")).toBeInTheDocument();
      await openDetails();
      const section = screen.getByRole("heading", { name: "Readiness" }).closest("section")!;
      const [request, due] = within(section).getAllByRole("listitem");
      expect(request).toHaveTextContent("Blocker: ITSO asked the author for a document.");
      expect(request).toHaveTextContent("Ito Itso");
      expect(request).toHaveTextContent(`since ${formatDate("2026-09-03T08:00:00Z")}`);
      expect(due).toHaveTextContent("ITSO is due Fri 11 Sep. The clock is paused while ITSO's document request is open.");
      expect(due).toHaveTextContent("clock paused");
      expect(due).not.toHaveTextContent("Blocker");
      expect(within(due).queryByRole("button")).not.toBeInTheDocument();

      // Changed on purpose by IR-879, then IR-1203: Documents is a tab, not a drawer.
      await userEvent.click(within(request).getByRole("button", { name: "Open Documents" }));
      expect(screen.getByRole("tab", { name: "Documents", selected: true })).toBeInTheDocument();
      expect(screen.queryByRole("dialog", { name: "All documents" })).not.toBeInTheDocument();
    });

    it("opens the Documents tab from a narrow workspace too", async () => {
      workspaceAt(1100);
      shownRecord = { ...inReview, ...reviewing, readiness: documentsAndDue() };
      signInAs(2, "ITSO");
      renderPaper(`/records/${RECORD_ID}?section=review`);
      await openDetails();
      await userEvent.click(await screen.findByRole("button", { name: "Open Documents" }));
      expect(screen.getByRole("tab", { name: "Documents", selected: true })).toBeInTheDocument();
    });

  });

  it("puts the paper beside the timeline, from the tracker", async () => {
    shownRecord = { ...inReview, ...reviewing };
    signInAs(2, "ITSO");
    const { container } = renderPaper(`/records/${RECORD_ID}?section=review`);

    expect(await screen.findByText(/paper reader open at page none/i)).toBeInTheDocument();
    // Changed on purpose by IR-1203: a reviewer opens on Documents, so Conversation is a click away.
    await openConversation();
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

    // Changed deliberately by IR-1206: an owner's Review opens on Readiness.
    await userEvent.click(await screen.findByRole("tab", { name: "Conversation" }));
    await screen.findByRole("list", { name: "Review timeline" });
    expect(screen.queryByRole("toolbar", { name: "Review actions" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Request documents" })).not.toBeInTheDocument();
  });

  it("gives the review discussion's composer only where the server offers comment_review", async () => {
    shownRecord = { ...inReview, is_participant: true, capabilities: ["cite", "comment_review"] };
    signInAs(OWNER_ID, "Student");
    const { unmount } = renderPaper(`/records/${RECORD_ID}?section=review`);

    // Changed deliberately by IR-1206: an owner's Review opens on Readiness.
    await userEvent.click(await screen.findByRole("tab", { name: "Conversation" }));
    await screen.findByRole("list", { name: "Review timeline" });
    expect(screen.getByRole("textbox", { name: "Comment" })).toBeInTheDocument();
    unmount();

    shownRecord = inReview;
    renderPaper(`/records/${RECORD_ID}?section=review`);
    await userEvent.click(await screen.findByRole("tab", { name: "Conversation" }));
    await screen.findByRole("list", { name: "Review timeline" });
    expect(screen.queryByRole("textbox", { name: "Comment" })).not.toBeInTheDocument();
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

  // Changed on purpose by IR-879 (ADR-032 §10, IR-372 kept): no Ask IRIS in
  // Review, and nothing that sends a participant to a Paper tab they no longer have.
  it("has no Ask IRIS and no Ask about this paper", async () => {
    shownRecord = { ...inReview, ...reviewing };
    signInAs(2, "ITSO");
    renderPaper(`/records/${RECORD_ID}?section=review`);

    // Changed on purpose by IR-1203: a reviewer opens on Documents, so Conversation is a click away.
    await openConversation();
    await screen.findByRole("list", { name: "Review timeline" });
    expect(screen.queryByRole("complementary", { name: "Ask IRIS" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Ask IRIS" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Ask about this paper" })).not.toBeInTheDocument();
  });

  it("offers no Ask about this paper when there is no paper to ask about", async () => {
    shownRecord = { ...inReview, abstract_file: null, files: [], ...reviewing };
    signInAs(2, "ITSO");
    renderPaper(`/records/${RECORD_ID}?section=review`);

    // Changed on purpose by IR-1203: a reviewer opens on Documents, so Conversation is a click away.
    await openConversation();
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

  // IR-906. A refusal is a refusal whichever status carries it: a hidden Record
  // and a missing id must not be told apart.
  it("treats a 403 exactly like a 404", async () => {
    vi.mocked(recordsApi.detail).mockRejectedValueOnce({ response: { status: 403, data: { detail: "You do not have permission." } } });
    signInAs(99, "Student");
    renderPaperView();

    expect(await screen.findByRole("heading", { name: "Record not available" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "We couldn't load this record" })).not.toBeInTheDocument();
  });

  it("shows a load that timed out as interrupted, and Retry reads again", async () => {
    shownRecord = record;
    vi.mocked(recordsApi.detail).mockRejectedValueOnce(new RequestTimeoutError(30_000, "get", "/records/1/"));
    signInAs(99, "Student");
    renderPaperView();

    expect(await screen.findByRole("heading", { name: "This took too long" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Record not available" })).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Retry" }));
    await waitForRecord(record.title);
  });

  it("falls to the same not-available state when a re-read finds access gone", async () => {
    shownRecord = { ...inReview, can_request_document: ["ierc"], capabilities: ["cite", "request_document"] };
    signInAs(2, "IERC");
    renderPaper(`/records/${RECORD_ID}?section=review`);

    await userEvent.click(await screen.findByRole("button", { name: "Request documents" }));
    const dialog = screen.getByRole("dialog", { name: "Request documents" });
    await userEvent.click(await within(dialog).findByRole("checkbox", { name: "Ethics Clearance" }));
    await userEvent.type(within(dialog).getByRole("textbox", { name: /Message to the owner/ }), "Please.");
    vi.mocked(recordsApi.detail).mockRejectedValueOnce({ response: { status: 404, data: { detail: "Not found." } } });
    await userEvent.click(within(dialog).getByRole("button", { name: "Send request" }));

    expect(await screen.findByRole("heading", { name: "Record not available" })).toBeInTheDocument();
    expect(screen.queryByRole("tablist")).not.toBeInTheDocument();
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

  // The menu is there whenever there is a version, so every paper's header
  // looks alike; with one version it lists that one alone (IR-1214).
  it("offers the picker with only v1, current and chosen", async () => {
    shownRecord = { ...record, versions: [version(1, "submission")] };
    const { container } = renderPaperView();
    await waitForRecord(record.title);

    const picker = screen.getByRole("combobox", PICKER);
    expect(picker).toHaveValue("1");
    expect(within(picker).getAllByRole("option").map((o) => o.textContent))
      .toEqual([expect.stringMatching(/^v1 · Submission · .* \(current\)$/)]);
    await expectNoBlockingA11yViolations(container);
  });

  it("offers no picker when no version is disclosed, or there is none", async () => {
    for (const versions of [null, []]) {
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

  // IR-1092: the one-row phone bar has no room for the picker, so below 640px
  // of the workspace it sits in the reader's toolbar -- there once, in the
  // tree, never drawn away -- and from 640px it stays in the bar.
  describe("where the Paper tab keeps the picker (IR-1092)", () => {
    const barOf = () => screen.getByRole("tablist", { name: "Paper view" }).parentElement as HTMLElement;
    const readerOf = () => screen.getByText(/paper reader open/i).parentElement as HTMLElement;

    it("is in the reader's toolbar, and not the bar, on a phone-width workspace", async () => {
      shownRecord = { ...record, versions: twoVersions };
      workspaceAt(360);
      renderPaper(`/records/${RECORD_ID}?section=paper`);
      await screen.findByText(/paper reader open/i);

      const picker = screen.getByRole("combobox", PICKER);
      expect(readerOf()).toContainElement(picker);
      expect(barOf()).not.toContainElement(picker);
    });

    it("keeps a single version's picker in the toolbar too, so a phone still says which it is reading", async () => {
      shownRecord = { ...record, versions: [version(1, "submission")] };
      workspaceAt(360);
      renderPaper(`/records/${RECORD_ID}?section=paper`);
      await screen.findByText(/paper reader open/i);

      const picker = screen.getByRole("combobox", PICKER);
      expect(picker).toHaveValue("1");
      expect(readerOf()).toContainElement(picker);
      expect(barOf()).not.toContainElement(picker);
    });

    it("stays in the bar from 640px", async () => {
      shownRecord = { ...record, versions: twoVersions };
      workspaceAt(1400);
      renderPaper(`/records/${RECORD_ID}?section=paper`);
      await screen.findByText(/paper reader open/i);

      const picker = screen.getByRole("combobox", PICKER);
      expect(barOf()).toContainElement(picker);
      expect(readerOf()).not.toContainElement(picker);
    });
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
    expect(within(picker).getByRole("option", { name: "Your revision (current)" }))
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
    expect(screen.getByRole("button", { name: "Save" })).not.toHaveClass("bg-brand");

    await userEvent.click(view);

    expect(await screen.findByRole("tab", { name: "Paper", selected: true })).toBeInTheDocument();
    expect(screen.getByRole("status", { name: "Location" })).toHaveTextContent("section=paper");
  });

  it("fills Save instead where there is no paper to view", async () => {
    shownRecord = { ...record, abstract_file: null, files: [] };
    renderPaperView();
    await waitForRecord(record.title);

    expect(screen.queryByRole("button", { name: "View" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save" })).toHaveClass("bg-brand");
  });

  it("lists the authors as chips, and leaves what the record is to Record details (IR-1089)", async () => {
    renderPaperView();
    await waitForRecord(record.title);

    const authors = screen.getByRole("list", { name: "Authors" });
    expect(within(authors).getByText("R. Dela Cruz")).toBeInTheDocument();
    const header = screen.getByRole("heading", { level: 1 }).closest("header") as HTMLElement;
    expect(within(header).queryByText("Thesis/Research")).not.toBeInTheDocument();
    expect(within(header).queryByText("Applied Research")).not.toBeInTheDocument();
    const details = screen.getByRole("complementary", { name: "Record details" });
    expect(within(details).getByText("Thesis/Research")).toBeInTheDocument();
    expect(within(details).getByText("Applied Research")).toBeInTheDocument();
  });

  it("sets the authors and the Adviser in one row, with the program line under them (IR-1142)", async () => {
    shownRecord = {
      ...record, origin: "institutional", adviser: ASSIGNED_ADVISER_ID, adviser_name: "Maria Santos",
      paper_details: { ...sidebarDetails, programs: ["BS Computer Science"] },
    };
    renderPaperView();
    await waitForRecord(record.title);

    const authors = screen.getByRole("list", { name: "Authors" });
    const adviser = screen.getByRole("list", { name: "Adviser" });
    expect(authors.parentElement).toBe(adviser.parentElement);
    // The Adviser is named once as a role; an author is a name, not a pill saying "Author".
    expect(within(adviser).getByText("Adviser")).toBeInTheDocument();
    expect(within(authors).queryByText("Author")).not.toBeInTheDocument();
    expect(screen.getByText(/^BS Computer Science · /)).toBeInTheDocument();
  });

  it("names the authors once and dates the work once, above the abstract (IR-1089)", async () => {
    shownRecord = { ...record, publication_year: 2025, access_count: 3 };
    renderPaperView();
    await waitForRecord(record.title);

    expect(screen.getAllByText("R. Dela Cruz")).toHaveLength(1);
    expect(screen.getAllByText(/^Completed /)).toHaveLength(1);
    expect(screen.queryByText(/^Added /)).not.toBeInTheDocument();
    const header = screen.getByRole("heading", { level: 1 }).closest("header") as HTMLElement;
    expect(within(header).getByText("Completed 2026")).toBeInTheDocument();
    // Neither the publication year nor the view count is a second date or a stat in the header.
    expect(within(header).queryByText(/Published \d{4}/)).not.toBeInTheDocument();
    expect(within(header).queryByText(/\d+ views?$/)).not.toBeInTheDocument();
  });

  it("keeps governance fields in Record details and out of the header (IR-1089)", async () => {
    shownRecord = {
      ...record, is_ip: true, ip_type: "patent", for_commercialization: true, community_extension: true,
      psced: "0613", publication_year: 2025, access_count: 3,
    };
    renderPaperView();
    await waitForRecord(record.title);

    const header = screen.getByRole("heading", { level: 1 }).closest("header") as HTMLElement;
    for (const label of [/Intellectual Property/, /Commercialization/, /Community Extension/, /Patent/]) {
      expect(within(header).queryByText(label)).not.toBeInTheDocument();
    }
    const details = screen.getByRole("complementary", { name: "Record details" });
    const row = (label: string) => within(details).getByText(label).parentElement as HTMLElement;
    expect(row("Published")).toHaveTextContent("2025");
    expect(row("Views")).toHaveTextContent("3");
    expect(row("PSCED")).toHaveTextContent("0613");
    expect(row("Community Extension")).toHaveTextContent("Yes");
    expect(row("IP Status")).toHaveTextContent("Patent");
    expect(row("Commercialization")).toHaveTextContent("Eligible");
  });

  it("reads its headings in order, none above its parent's size, inside the AI Overview (IR-1089)", async () => {
    const { aiApi } = await import("@/api/ai");
    vi.mocked(aiApi.overview).mockResolvedValueOnce({
      data: {
        state: "ready", cached: false,
        overview: { text: "## Methodology\n\nA network.\n\n### Data\n\nGauge records.", citations: [], degraded: false, model: "fake", generated_at: "2026-09-23T00:00:00Z" },
      },
    } as never);
    renderPaperView();
    await waitForRecord(record.title);
    await screen.findByRole("heading", { name: "Methodology" });

    const headings = screen.getAllByRole("heading").map((h) => ({
      level: Number(h.tagName.slice(1)), name: h.textContent ?? "",
    }));
    expect(headings[0]).toMatchObject({ level: 1, name: record.title });
    expect(headings.filter((h) => h.level === 1)).toHaveLength(1);
    // Never a step down of more than one level (an h2 straight to an h4).
    headings.slice(1).forEach((h, i) => expect(h.level, `"${h.name}" after "${headings[i].name}"`).toBeLessThanOrEqual(headings[i].level + 1));

    const overviewAt = headings.findIndex((h) => h.name.trim() === "AI Overview");
    const methodologyAt = headings.findIndex((h) => h.name === "Methodology");
    const dataAt = headings.findIndex((h) => h.name === "Data");
    expect(overviewAt).toBeGreaterThan(-1);
    expect([methodologyAt, dataAt]).toEqual([overviewAt + 1, overviewAt + 2]);
    // Inside the AI Overview no heading outranks the AI Overview's own.
    for (const inside of [methodologyAt, dataAt]) {
      expect(headings[inside].level).toBeGreaterThanOrEqual(headings[overviewAt].level);
    }
    expect(headings[dataAt].level).toBeGreaterThan(headings[methodologyAt].level);
  });

  it("never credits the submitting owner as an unrecorded author", async () => {
    shownRecord = { ...record, authors: [], origin: "imported_reference", owners: [
      { id: 1, user: 99, email: "loader@cit.edu", full_name: "Corpus Loader", is_primary: true },
    ] };
    renderPaperView();
    await waitForRecord(record.title);
    expect(screen.getByText("Authors not recorded")).toHaveClass("italic", "text-stone-500");
    expect(screen.queryByRole("list", { name: "Authors" })).not.toBeInTheDocument();
    expect(screen.getByText("Imported reference")).toBeInTheDocument();
  });

  it("shows a verified external reference without attributing it to CIT-U", async () => {
    shownRecord = { ...record, ...importedReference, year_accomplished: 2020 };
    renderPaperView();
    await waitForRecord(importedReference.title);
    const authors = screen.getByRole("list", { name: "Authors" });
    expect(within(authors).getAllByRole("listitem")).toHaveLength(8);
    expect(within(authors).getByText("Ashish Vaswani")).toBeInTheDocument();
    // The publication year is a governance field now, in Record details (IR-1089).
    const details = screen.getByRole("complementary", { name: "Record details" });
    expect(within(details).getByText("Published").parentElement).toHaveTextContent("2017");
    expect(screen.getByText("Completed 2020")).toBeInTheDocument();
    expect(screen.getByText("Imported reference")).toBeInTheDocument();
    expect(screen.queryByText("Example Research University")).not.toBeInTheDocument();
  });

  it("holds governance and documents in Record details, beside the page", async () => {
    renderPaperView();
    await waitForRecord(record.title);

    const details = screen.getByRole("complementary", { name: "Record details" });
    expect(within(details).getByRole("heading", { name: "Institutional Governance" })).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Record details" })).not.toBeInTheDocument();
  });

  // jsdom does no layout, so this pins the rule that keeps the panel whole
  // while it scrolls, not the pixels (IR-1178). The panel's own scrollbar
  // takes ~23px from the scroller; an aside fixed at the column's full width
  // overflowed by that much and the scroller clipped the right edge of every
  // row. The aside may still not fall below the width it holds while the
  // column folds, and must never outgrow what the scroller leaves it.
  it("keeps every Record details row inside the panel when the panel scrolls (IR-1178)", async () => {
    renderPaperView();
    await waitForRecord(record.title);

    const details = screen.getByRole("complementary", { name: "Record details" });
    const scroller = details.parentElement as HTMLElement;
    expect(scroller).toHaveClass("overview-wide:overflow-y-auto", "overview-wide:overflow-x-hidden");
    expect(scroller).toHaveClass("overview-wide:grid-cols-[minmax(0,1fr)]");
    expect(details).toHaveClass("overview-wide:w-[clamp(17rem,25cqw,22rem)]");
    expect(details).toHaveClass("overview-wide:max-w-full");
    expect(details).toHaveClass("overview-wide:min-w-[15rem]");
  });

  it("sets the reading sections apart with spacing, and draws Comments last (IR-569)", async () => {
    renderPaperView();
    await waitForRecord(record.title);

    const abstract = screen.getByRole("heading", { level: 2, name: "Abstract" }).closest("section");
    const group = abstract?.parentElement;
    expect(group).toHaveClass("space-y-8");
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

  it("keeps no place while the citation is re-read, so the old one never lands first (IR-573)", async () => {
    let answer: (value: unknown) => void = () => {};
    await conversationReads(() => new Promise((resolve) => { answer = resolve; }));

    renderPaper(ADDRESS);

    expect(await screen.findByText(/open at page none, 0 region\(s\)/i)).toBeInTheDocument();
    expect(screen.queryByText("Reader keeps the reader's place")).not.toBeInTheDocument();
    await act(async () => answer(answeredWith([current])));
    expect(await screen.findByText(/open at page 14, 2 region\(s\)/i)).toBeInTheDocument();
    expect(screen.getByText("Reader keeps the reader's place")).toBeInTheDocument();
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

    // Wait for the page: while the record loads, the skeleton is itself a status (IR-939).
    expect(await screen.findByText(/open at page 12, 0 region\(s\)/i)).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("That citation points at another paper, so nothing is highlighted here.");
  });

  it("highlights nothing from a citation the answer no longer has", async () => {
    await conversationReads(() => Promise.resolve(answeredWith([])));

    renderPaper(ADDRESS);

    expect(await screen.findByText(/open at page 12, 0 region\(s\)/i)).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent(/no longer part of the answer/);
    expect(screen.getByRole("button", { name: "Back to answer" })).toBeInTheDocument();
  });

  it("offers no way back into a conversation that is not the reader's", async () => {
    // Someone else's reads exactly like a missing one (IR-548).
    await conversationReads(() => Promise.reject({ response: { status: 404 } }));

    renderPaper(ADDRESS);

    expect(await screen.findByText(/open at page 12, 0 region\(s\)/i)).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent(/answer this citation came from is no longer available/);
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


// The embargo and its acts sit in Record details, beside what the paper is
// held under (IR-817). Which control shows is `EmbargoCard.test.tsx`'s.
describe("the embargo in Record details (IR-817)", () => {
  const underEmbargo: RecordDetail = {
    ...record,
    embargo: { state: "active", until: "2099-01-01" },
    capabilities: [...record.capabilities, "set_embargo", "release_embargo"],
  };

  beforeEach(() => {
    shownRecord = underEmbargo;
    signInAs(99, "Adviser");
  });

  it("shows the card in the rail, and a release reloads the record", async () => {
    workspaceAt(1400);
    renderPaperView();
    await waitForRecord(record.title);
    const rail = screen.getByRole("complementary", { name: "Record details" });
    const card = within(rail).getByRole("region", { name: "Embargo" });
    expect(within(card).getByText("Under embargo")).toBeInTheDocument();

    shownRecord = { ...underEmbargo, embargo: { state: "released", until: "2099-01-01" }, capabilities: record.capabilities };
    await userEvent.click(within(card).getByRole("button", { name: "Release embargo" }));
    await userEvent.click(within(screen.getByRole("dialog", { name: "Release this embargo?" })).getByRole("button", { name: "Release" }));

    expect(recordsApi.releaseEmbargo).toHaveBeenCalledWith(RECORD_ID);
    expect(await within(card).findByText("Released")).toBeInTheDocument();
    expect(within(card).queryByRole("button", { name: "Release embargo" })).not.toBeInTheDocument();
  });

  it("works on a phone, dialog included", async () => {
    workspaceAt(360);
    const { container } = renderPaperView();
    await waitForRecord(record.title);
    const card = within(screen.getByRole("complementary", { name: "Record details" })).getByRole("region", { name: "Embargo" });
    await expectNoBlockingA11yViolations(container);

    await userEvent.click(within(card).getByRole("button", { name: "Release embargo" }));
    expect(screen.getByRole("dialog", { name: "Release this embargo?" })).toBeInTheDocument();
    await expectNoBlockingA11yViolations(document.body);
    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));

    await userEvent.click(within(card).getByRole("button", { name: "Change date" }));
    expect(screen.getByRole("dialog", { name: "Change the review date" })).toBeInTheDocument();
    await expectNoBlockingA11yViolations(document.body);
  });

  it("says in Institutional Governance whether KTTO released the IP mark", async () => {
    shownRecord = { ...underEmbargo, is_ip: true, ip_type: "patent", ip_release: { released: true, released_at: "2026-11-03T02:00:00Z" } };
    workspaceAt(1400);
    renderPaperView();
    await waitForRecord(record.title);

    const governance = screen.getByRole("region", { name: "Institutional Governance" });
    expect(within(governance).getByText("Released for the AI by KTTO")).toBeInTheDocument();
  });
});


// Any owner names the Contact person from Record details, on every paper
// (ADR-051 decision 27, IR-803). What the card does is `ContactPersonCard.test.tsx`'s.
describe("the Contact person in Record details (IR-803)", () => {
  const owned: RecordDetail = {
    ...record,
    owners: [
      { id: 1, user: 42, email: "ana@cit.edu", full_name: "Ana Reyes", is_primary: true },
      { id: 2, user: 43, email: "ben@cit.edu", full_name: "Ben Cruz", is_primary: false },
    ],
    capabilities: [...record.capabilities, "change_contact_person"],
  };

  beforeEach(() => {
    shownRecord = owned;
    signInAs(42, "Student");
  });

  it("shows an owner the dropdown in the rail, and a save reads the paper again", async () => {
    workspaceAt(1400);
    renderPaperView();
    await waitForRecord(record.title);
    const rail = screen.getByRole("complementary", { name: "Record details" });
    const card = within(rail).getByRole("region", { name: "Contact person" });
    expect(within(card).getByRole("combobox", { name: "Contact person" })).toHaveDisplayValue("Ana Reyes");

    shownRecord = {
      ...owned,
      owners: owned.owners.map((owner) => ({ ...owner, is_primary: owner.user === 43 })),
    };
    await userEvent.selectOptions(within(card).getByRole("combobox", { name: "Contact person" }), "Ben Cruz");
    await userEvent.click(within(card).getByRole("button", { name: "Make Contact person" }));

    expect(recordsApi.changeContactPerson).toHaveBeenCalledWith(RECORD_ID, 43);
    expect(await within(card).findByRole("status")).toHaveTextContent("Ben Cruz is now the Contact person.");
    await waitFor(() => expect(within(card).getByRole("button", { name: "Make Contact person" })).toBeDisabled());
    expect(within(card).getByRole("combobox", { name: "Contact person" })).toHaveDisplayValue("Ben Cruz");
  });
});


// RDCO publishes an Unlisted paper from Record details, beside its embargo
// (ADR-047 §10, IR-878). What the card offers is `UnlistedCard.test.tsx`'s.
describe("publishing an Unlisted paper from Record details (IR-878)", () => {
  const unlisted: RecordDetail = {
    ...record,
    pipeline_status: "completed",
    embargo: { state: "released", until: null },
    publish_unlisted: { blocked: null },
    capabilities: [...record.capabilities, "publish_unlisted"],
  };

  beforeEach(() => {
    shownRecord = unlisted;
    signInAs(99, "RDCO");
  });

  it("shows the card in the rail, and publishing reloads the record", async () => {
    workspaceAt(1400);
    renderPaperView();
    await waitForRecord(record.title);
    const rail = screen.getByRole("complementary", { name: "Record details" });
    const card = within(rail).getByRole("region", { name: "Unlisted" });

    shownRecord = { ...unlisted, pipeline_status: "published", publish_unlisted: null, capabilities: record.capabilities };
    await userEvent.click(within(card).getByRole("button", { name: "Publish to Discover" }));
    await userEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Publish" }));

    expect(recordsApi.publishUnlisted).toHaveBeenCalledWith(RECORD_ID, "");
    expect(await within(rail).findByRole("status")).toHaveTextContent("Published. It is now in Discover.");
    expect(within(rail).queryByRole("region", { name: "Unlisted" })).not.toBeInTheDocument();
  });

  it("works on a phone, dialog included", async () => {
    workspaceAt(360);
    const { container } = renderPaperView();
    await waitForRecord(record.title);
    await expectNoBlockingA11yViolations(container);
    await userEvent.click(screen.getByRole("button", { name: "Publish to Discover" }));
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    await expectNoBlockingA11yViolations(document.body);
  });
});


// RDCO's controls on a paper in review sit in Record details (ADR-051 §10,
// IR-798). What each dialog says is `RdcoPaperControls.test.tsx`'s; here, the
// placement, and leaving a paper that a withdrawal deleted.
describe("RDCO's controls on a paper in review (IR-798)", () => {
  const inReview: RecordDetail = {
    ...record,
    pipeline_status: "in_review",
    capabilities: [...record.capabilities, "replace_adviser", "add_owner", "withdraw_paper"],
  };

  function ReviewQueue() {
    return <h1>Review queue</h1>;
  }

  beforeEach(() => {
    shownRecord = inReview;
    signInAs(99, "RDCO");
    useUIStore.setState({ toasts: [] });
  });

  it("offers the three acts in the rail, and a withdrawal leaves for the review queue", async () => {
    workspaceAt(1400);
    renderScreen(
      <Routes>
        <Route path="/records/:id" element={<PaperViewPage />} />
        <Route path="/review" element={<ReviewQueue />} />
      </Routes>,
      { route: `/records/${RECORD_ID}` },
    );
    await waitForRecord(record.title);
    const rail = screen.getByRole("complementary", { name: "Record details" });
    const card = within(rail).getByRole("region", { name: "RDCO controls" });
    expect(within(card).getAllByRole("button").map((b) => b.textContent)).toEqual([
      "Replace Adviser", "Add owner", "Withdraw paper",
    ]);

    await userEvent.click(within(card).getByRole("button", { name: "Withdraw paper" }));
    const dialog = screen.getByRole("dialog", { name: "Withdraw this paper?" });
    await userEvent.type(within(dialog).getByRole("textbox", { name: "Reason" }), "Duplicate submission.");
    await userEvent.click(within(dialog).getByRole("button", { name: "Withdraw paper" }));

    expect(recordsApi.rdcoWithdraw).toHaveBeenCalledWith(RECORD_ID, "Duplicate submission.");
    expect(await screen.findByRole("heading", { name: "Review queue" })).toBeInTheDocument();
    expect(useUIStore.getState().toasts.map((t) => t.message)).toEqual([
      "Paper withdrawn. Its owners and reviewers have been told.",
    ]);
  });

  it("is not shown when the server offers none of them", async () => {
    shownRecord = { ...inReview, capabilities: record.capabilities };
    workspaceAt(1400);
    renderPaperView();
    await waitForRecord(record.title);
    expect(screen.queryByRole("region", { name: "RDCO controls" })).not.toBeInTheDocument();
  });

  it("works on a phone, dialog included", async () => {
    workspaceAt(360);
    const { container } = renderPaperView();
    await waitForRecord(record.title);
    await expectNoBlockingA11yViolations(container);
    await userEvent.click(screen.getByRole("button", { name: "Withdraw paper" }));
    expect(screen.getByRole("dialog", { name: "Withdraw this paper?" })).toBeInTheDocument();
    await expectNoBlockingA11yViolations(document.body);
  });
});

// Private notes share Ask IRIS's one panel slot (IR-580, ADR-064): one tool
// open at a time, an icon for each beside the other when closed, and the note
// is read only once Notes is first opened.
describe("Notes in the reading workspace (IR-580)", () => {
  const ASK = { name: "Ask IRIS" };
  const NOTES = { name: "Notes" };

  beforeEach(() => {
    shownRecord = record;
    signInAs(99, "Student");
    useUIStore.setState({ sidebarCollapsed: false, sidebarOpen: false, readingRail: null });
    vi.mocked(libraryApi.note).mockClear();
  });

  afterEach(() => {
    localStorage.removeItem(PANEL_WIDTH_KEY);
    vi.unstubAllGlobals();
  });

  it("offers Notes beside the Ask IRIS icon, and reads no note until it is opened", async () => {
    workspaceAt(1400);
    renderPaperView();
    await waitForRecord(record.title);

    expect(screen.getByRole("button", ASK)).toBeInTheDocument();
    expect(screen.getByRole("button", NOTES)).toBeInTheDocument();
    expect(libraryApi.note).not.toHaveBeenCalled();

    await userEvent.click(screen.getByRole("button", NOTES));

    expect(await screen.findByRole("complementary", NOTES)).toBeInTheDocument();
    expect(screen.queryByRole("complementary", ASK)).not.toBeInTheDocument();
    expect(await screen.findByRole("textbox", { name: "Your note on this paper" })).toBeInTheDocument();
    expect(libraryApi.note).toHaveBeenCalledWith(RECORD_ID);
  });

  it("is the panel's only occupant: Notes and Ask IRIS swap, and the question draft is kept", async () => {
    workspaceAt(1400);
    renderPaperView();
    await waitForRecord(record.title);
    await userEvent.click(screen.getByRole("button", ASK));
    await userEvent.type(await screen.findByRole("textbox", { name: "Ask about this paper" }), "What was measured?");

    await userEvent.click(screen.getByRole("button", NOTES));
    expect(await screen.findByRole("complementary", NOTES)).toBeInTheDocument();
    expect(screen.queryByRole("complementary", ASK)).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", ASK));
    expect(await screen.findByRole("textbox", { name: "Ask about this paper" })).toHaveValue("What was measured?");
    expect(screen.queryByRole("complementary", NOTES)).not.toBeInTheDocument();
  });

  it("closing Notes shows both icons again, and the note is not read a second time", async () => {
    workspaceAt(1400);
    renderPaperView();
    await waitForRecord(record.title);
    await userEvent.click(screen.getByRole("button", NOTES));
    await screen.findByRole("textbox", { name: "Your note on this paper" });

    await userEvent.click(screen.getByRole("button", { name: "Close notes" }));
    expect(screen.queryByRole("complementary", NOTES)).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", NOTES));

    expect(await screen.findByRole("textbox", { name: "Your note on this paper" })).toBeInTheDocument();
    expect(libraryApi.note).toHaveBeenCalledTimes(1);
  });

  it("opens Ask IRIS, not Notes, when the reader enters the Paper section", async () => {
    workspaceAt(1400);
    renderPaperView();
    await waitForRecord(record.title);
    await userEvent.click(screen.getByRole("button", NOTES));
    await screen.findByRole("complementary", NOTES);

    await userEvent.click(screen.getByRole("tab", { name: "Paper" }));

    expect(await screen.findByRole("heading", { name: "Ask IRIS" })).toBeInTheDocument();
    expect(screen.queryByRole("complementary", NOTES)).not.toBeInTheDocument();
  });

  it("over the paper it is a dialog: Escape closes it and focus returns to the Notes icon", async () => {
    workspaceAt(924);
    renderPaperView();
    await waitForRecord(record.title);
    await userEvent.click(screen.getByRole("tab", { name: "Paper" }));
    await screen.findByRole("heading", { name: "Ask IRIS" });

    await userEvent.click(screen.getByRole("button", NOTES));
    const dialog = await screen.findByRole("dialog", NOTES);
    await waitFor(() => expect(dialog).toHaveFocus());

    await userEvent.keyboard("{Escape}");

    expect(screen.queryByRole("dialog", NOTES)).not.toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole("button", NOTES)).toHaveFocus());
  });

  it("beside the page, focus moves into Notes on opening and back to its icon on closing", async () => {
    workspaceAt(1400);
    renderPaperView();
    await waitForRecord(record.title);

    await userEvent.click(screen.getByRole("button", NOTES));
    const panel = await screen.findByRole("complementary", NOTES);
    await waitFor(() => expect(panel).toHaveFocus());

    await userEvent.click(screen.getByRole("button", { name: "Close notes" }));

    await waitFor(() => expect(screen.getByRole("button", NOTES)).toHaveFocus());
  });

  it("swapping to Ask IRIS and back moves focus into each panel", async () => {
    workspaceAt(1400);
    renderPaperView();
    await waitForRecord(record.title);
    await userEvent.click(screen.getByRole("button", NOTES));
    await screen.findByRole("complementary", NOTES);

    await userEvent.click(screen.getByRole("button", ASK));

    const ask = await screen.findByRole("complementary", ASK);
    await waitFor(() => expect(ask).toHaveFocus());
  });

  it("has no serious or critical accessibility violations with Notes open", async () => {
    workspaceAt(1400);
    const { container } = renderPaperView();
    await waitForRecord(record.title);
    await userEvent.click(screen.getByRole("button", NOTES));
    await screen.findByRole("textbox", { name: "Your note on this paper" });

    await expectNoBlockingA11yViolations(container);
  });
});


// Highlights (IR-583, ADR-065): the page asks for them whenever the paper is
// shown, hands the reader only those that belong to the bytes it shows, and
// saves a selection against the revision the reader was opened at.
describe("highlights on the paper (IR-583)", () => {
  const entry = (over: Record<string, unknown> = {}) => ({
    id: 1, record_id: RECORD_ID, available: true, state: "current", page: 3,
    quote: "Rainfall explained 62% of the variance in discharge.", prefix: "", suffix: "",
    regions: [{ page: 3, left: 0.1, top: 0.2, right: 0.9, bottom: 0.23 }], open_version: null,
    created_at: "2026-11-12T00:00:00Z", ...over,
  });
  const list = (...results: unknown[]) =>
    vi.mocked(libraryApi.highlights).mockResolvedValue({ data: { results } } as never);

  beforeEach(() => {
    shownRecord = record;
    signInAs(99, "Student");
    useUIStore.setState({ sidebarCollapsed: false, sidebarOpen: false, readingRail: null });
    vi.mocked(libraryApi.saveHighlight).mockReset();
    vi.mocked(libraryApi.highlights).mockReset();
    list();
  });

  afterEach(() => {
    localStorage.removeItem(PANEL_WIDTH_KEY);
    vi.unstubAllGlobals();
  });

  it("saves the selected passage against the revision the reader opened, and draws it", async () => {
    workspaceAt(1400);
    vi.mocked(libraryApi.saveHighlight).mockResolvedValue({ data: entry() } as never);
    renderPaper(`/records/${RECORD_ID}?section=paper`);
    await screen.findByText(/paper reader open/i);

    await userEvent.click(screen.getByRole("button", { name: "Selection: Save highlight" }));

    expect(libraryApi.saveHighlight).toHaveBeenCalledWith(RECORD_ID, {
      manuscript_revision: "rev-1", page: 3, quote: "robot arm", prefix: "A ", suffix: ", and another",
      regions: [{ page: 3, left: 0.1, top: 0.5, right: 0.4, bottom: 0.52 }],
    });
    expect(await screen.findByText("Highlight saved.")).toBeInTheDocument();
    expect(screen.getByText("1 saved highlight(s) drawn")).toBeInTheDocument();
  });

  it("says the paper was replaced, and draws and saves nothing, when the server refuses the revision", async () => {
    workspaceAt(1400);
    vi.mocked(libraryApi.saveHighlight).mockRejectedValue(
      Object.assign(new Error("conflict"), {
        isAxiosError: true, response: { status: 409, data: { code: "manuscript_changed" } },
      }),
    );
    renderPaper(`/records/${RECORD_ID}?section=paper`);
    await screen.findByText(/paper reader open/i);

    await userEvent.click(screen.getByRole("button", { name: "Selection: Save highlight" }));

    expect(await screen.findByText(/paper was replaced while you were reading/i)).toBeInTheDocument();
    expect(screen.queryByText("Highlight saved.")).not.toBeInTheDocument();
    expect(screen.getByText("0 saved highlight(s) drawn")).toBeInTheDocument();
  });

  it("hands the reader a highlight made on the bytes it shows, and not one from an earlier version", async () => {
    workspaceAt(1400);
    list(entry({ id: 1 }), entry({ id: 2, state: "stale", open_version: 1 }));
    renderPaper(`/records/${RECORD_ID}?section=paper`);

    expect(await screen.findByText("1 saved highlight(s) drawn")).toBeInTheDocument();
  });

  it("opens a highlight from Notes on its page and region", async () => {
    workspaceAt(1400);
    list(entry());
    renderPaper(`/records/${RECORD_ID}?section=paper`);
    await screen.findByText(/paper reader open at page none/i);
    await userEvent.click(screen.getByRole("button", { name: "Notes" }));

    await userEvent.click(await screen.findByRole("button", { name: /^Open page 3/ }));

    expect(await screen.findByText(/open at page 3, 1 region\(s\) to highlight, reading the current paper/i))
      .toBeInTheDocument();
  });

  it("opens a stale highlight in the version that still has its bytes, and draws it only there", async () => {
    workspaceAt(1400);
    const version = (number: number) => ({
      number, cause: number === 1 ? "submission" : "revision", cause_label: "Version",
      created_at: `2026-09-0${number}T08:00:00Z`, created_by_name: "Rhea Owner",
      manuscript_url: `/api/v1/records/${RECORD_ID}/versions/${number}/manuscript/`,
    });
    shownRecord = { ...record, versions: [version(1), version(2)] } as never;
    list(entry({ id: 2, state: "stale", open_version: 1 }));
    renderPaper(`/records/${RECORD_ID}?section=paper`);
    expect(await screen.findByText("0 saved highlight(s) drawn")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Notes" }));

    await userEvent.click(await screen.findByRole("button", { name: /^Open page 3 in v1/ }));

    expect(await screen.findByText(/open at page 3, 1 region\(s\) to highlight, reading v1/i)).toBeInTheDocument();
    expect(screen.getByText("1 saved highlight(s) drawn")).toBeInTheDocument();
  });

  it("asks for no highlights while only the overview is showing", async () => {
    workspaceAt(1400);
    renderPaper(`/records/${RECORD_ID}`);
    await waitForRecord(record.title);

    expect(libraryApi.highlights).not.toHaveBeenCalled();
  });
});

// Reading history follows the account (IR-756, ADR-044 Â§Amendment 2026-11-01):
// the page sends an explicit visit once the paper has loaded, and nothing at all
// while the reader has paused history.
describe("Reading history (IR-756)", () => {
  beforeEach(() => {
    shownRecord = record;
    vi.mocked(libraryApi.visit).mockClear();
    vi.mocked(libraryApi.preferences).mockClear();
  });

  /** A signed-in session: history belongs to an account, so a visitor sends nothing. */
  function signIn() {
    signInAs(99, "Student");
    useAuthStore.setState({ isAuthenticated: true, sessionEpoch: useAuthStore.getState().sessionEpoch + 1 });
  }

  it("sends nothing for a visitor who is not signed in", async () => {
    useAuthStore.setState({ user: null, isAuthenticated: false });
    renderPaperView();
    await waitForRecord(record.title);

    expect(libraryApi.preferences).not.toHaveBeenCalled();
    expect(libraryApi.visit).not.toHaveBeenCalled();
  });

  it("records the opened paper on the reader's account", async () => {
    signIn();
    renderPaperView();
    await waitForRecord(record.title);

    await waitFor(() => expect(libraryApi.visit).toHaveBeenCalledWith(RECORD_ID));
    expect(localStorage.getItem("iris_reading_history")).toBeNull();
  });

  it("asks the reader to keep the reader's place in the paper (IR-573)", async () => {
    signIn();
    renderPaperView();
    await userEvent.click(await screen.findByRole("tab", { name: "Paper" }));

    expect(await screen.findByText(/open at page none/i)).toBeInTheDocument();
    expect(screen.getByText("Reader keeps the reader's place")).toBeInTheDocument();
  });

  it("sends nothing while the reader has paused history", async () => {
    vi.mocked(libraryApi.preferences).mockResolvedValueOnce({ data: { keep_history: false } } as never);
    signIn();
    renderPaperView();
    await waitForRecord(record.title);

    await waitFor(() => expect(libraryApi.preferences).toHaveBeenCalled());
    expect(libraryApi.visit).not.toHaveBeenCalled();
  });
});

// Audit CMP-06: a pending download request is the paper's state, not a
// reading tool, so it sits in the record bar, not beside zoom (IR-1098). On a
// phone the bar has no room and it stays in the reader's toolbar, as the
// version does (IR-1092).
describe("a pending download request (IR-1098)", () => {
  const pending = {
    state: "pending" as const, allowed: false, message: "Your download request is waiting for RDCO's decision.",
    grant_expires_at: null, request: 3,
  };

  beforeEach(() => {
    shownRecord = { ...record, download: pending };
    signInAs(99, "Student");
  });

  afterEach(() => vi.unstubAllGlobals());

  it("sits in the record bar, out of the reader's toolbar", async () => {
    workspaceAt(1400);
    renderPaper(`/records/${RECORD_ID}?section=paper`);
    await screen.findByText(/paper reader open/i);

    const toolbar = screen.getByRole("toolbar", { name: "Reader toolbar" });
    expect(within(toolbar).queryByText("Request pending")).not.toBeInTheDocument();
    expect(screen.getByText("Request pending")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Cancel request" })).toBeInTheDocument();
  });

  it("stays in the reader's toolbar on a phone, where the bar has no room", async () => {
    workspaceAt(400);
    renderPaper(`/records/${RECORD_ID}?section=paper`);
    await screen.findByText(/paper reader open/i);

    const toolbar = screen.getByRole("toolbar", { name: "Reader toolbar" });
    expect(within(toolbar).getByText("Request pending")).toBeInTheDocument();
    expect(screen.getAllByText("Request pending")).toHaveLength(1);
  });
});
