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
 * never the stored stage: "Open review" appears exactly when `can_act`
 * names a party for this viewer, and "Resubmit for review" exactly when the
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
import { renderScreen, screen, userEvent, waitFor, within } from "@/test/render";
import { useAuthStore } from "@/store/auth.store";
import type { User } from "@/types/auth";
import type { RecordDetail, ReviewerSeat } from "@/types/records";

import { recordsApi } from "@/api/records";
import { seatsApi } from "@/api/reviews";

import { DOCK_KEY } from "./PaperChatDock";
import { CONTAINED_LAYOUT_QUERY } from "./paneLayout";
import PaperViewPage from "./PaperViewPage";

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
  your_office: null,
  your_office_label: null,
  files: [],
  workflow_state: "published",
  workflow_state_label: "Published",
  current_holders: [],
  can_act: [],
  can_request_document: [],
  my_seats: [],
  is_participant: false,
  routing: { accept_and_route: false, route_as: null },
  office_review: { party: null, label: null, blocked: null, assignment: null },
  revision: { party: null, label: null, blocked: null, withdrawable: null, decision_blocked: null, open: [], new_version: null },
  versions: null,
  manuscript_unsubmitted: false,
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
  your_office: null,
  your_office_label: null,
  files: [],
  workflow_state: "approved",
  workflow_state_label: "Approved",
  current_holders: [],
  can_act: [],
  can_request_document: [],
  my_seats: [],
  is_participant: false,
  routing: { accept_and_route: false, route_as: null },
  office_review: { party: null, label: null, blocked: null, assignment: null },
  revision: { party: null, label: null, blocked: null, withdrawable: null, decision_blocked: null, open: [], new_version: null },
  versions: null,
  manuscript_unsubmitted: false,
};

/** Which record `recordsApi.detail` resolves with. Reset per describe block,
 * since the two concerns below need different records shown. */
let shownRecord: RecordDetail = record;

const completeProposal = vi.fn((_id: number) => Promise.resolve({ data: { detail: "ok" } }));

function page<T>(results: T[]) {
  return { data: { count: results.length, next: null, previous: null, results } };
}

const documentRequests = vi.fn(() => Promise.resolve({ data: [] as unknown[] }));

vi.mock("@/api/records", () => ({
  recordsApi: {
    detail:           vi.fn(() => Promise.resolve({ data: shownRecord })),
    incrementAccess:  vi.fn(() => Promise.resolve({ data: {} })),
    similar:          vi.fn(() => Promise.resolve({ data: { results: [] } })),
    // The tracker panel loads itself; it has its own test file (IR-258).
    tracker:          vi.fn(() => Promise.reject(new Error("not under test"))),
    // The Action required panel loads itself; its behaviour is tested in
    // features/document-requests (IR-262). Here only its placement is.
    documentRequests: () => documentRequests(),
    // Request documents, from the Review section's action bar (IR-412).
    documentRequestSlots:  vi.fn(() => Promise.resolve({ data: [{ id: 3, name: "Ethics Clearance" }] })),
    createDocumentRequest: vi.fn(() => Promise.resolve({ data: { id: 1 } })),
    updateTags:       vi.fn(),
    completeProposal: (id: number) => completeProposal(id),
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
    conversations: { findOrCreateForRecord: vi.fn(() => new Promise(() => {})) },
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
// role, so nobody is offered it any more (spec §4.6, IR-411).
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
    expect(completeProposal).not.toHaveBeenCalled();
  });
});

const OWNER_ID = 40;
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
  can_act: [],
  can_request_document: [],
  my_seats: [],
  is_participant: false,
  routing: { accept_and_route: false, route_as: null },
  office_review: { party: null, label: null, blocked: null, assignment: null },
  revision: { party: null, label: null, blocked: null, withdrawable: null, decision_blocked: null, open: [], new_version: null },
  versions: null,
  manuscript_unsubmitted: false,
};

async function waitForRecord(title: string) {
  // Assert absences only after the record renders, not against the skeleton.
  await screen.findByRole("heading", { name: title });
}

describe("the review control follows can_act", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("is offered when the API says this viewer can act", async () => {
    shownRecord = { ...inReview, can_act: ["itso"] };
    signInAs(2, "ITSO");
    const { container } = renderPaperView();

    expect(await screen.findByRole("button", OPEN_REVIEW)).toBeInTheDocument();
    await expectNoBlockingA11yViolations(container);
  });

  // Until IR-260 retires it, the Review section's action bar reaches the
  // decision through the current form, which is left as it is (spec §4.7).
  it("opens the Review section, whose action bar reaches the current decision form", async () => {
    shownRecord = { ...inReview, can_act: ["itso"] };
    signInAs(2, "ITSO");
    renderPaperView();

    await userEvent.click(await screen.findByRole("button", OPEN_REVIEW));

    expect(await screen.findByRole("tab", { name: "Review", selected: true })).toBeInTheDocument();
    const bar = screen.getByRole("toolbar", { name: "Review actions" });
    expect(within(bar).getByRole("link", { name: "Record a decision (current form)" })).toHaveAttribute(
      "href",
      `/review/${RECORD_ID}/evaluate`,
    );
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
    shownRecord = { ...inReview, my_seats: [assigned], is_participant: true };
    signInAs(2, "ITSO");
    renderPaperView();

    await userEvent.click(await screen.findByRole("button", OPEN_REVIEW));

    expect(vi.mocked(seatsApi.open)).toHaveBeenCalledWith(77);
    expect(await screen.findByRole("tab", { name: "Review", selected: true })).toBeInTheDocument();
  });

  it("only navigates when every seat is already open", async () => {
    shownRecord = { ...inReview, can_act: ["itso"] };
    signInAs(2, "ITSO");
    renderPaperView();

    await userEvent.click(await screen.findByRole("button", OPEN_REVIEW));

    expect(await screen.findByRole("tab", { name: "Review", selected: true })).toBeInTheDocument();
    expect(vi.mocked(seatsApi.open)).not.toHaveBeenCalled();
  });

  it("is not offered to a same-role viewer the API does not name, whatever the stage", async () => {
    // `parallel_review` is a stage an ITSO reviewer used to be shown the
    // control at by role alone. The API says this one cannot act.
    shownRecord = { ...inReview, pipeline_status: "parallel_review", can_act: [] };
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

describe("the resubmit control follows workflow_state", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  // The legacy pipeline's revision: stored `declined`, which is what its
  // Resubmit answers. The adviser-first model's is the last case (IR-272).
  const awaiting: RecordDetail = {
    ...inReview,
    pipeline_status: "declined",
    workflow_state: "awaiting_resubmission",
    workflow_state_label: "Awaiting resubmission",
  };

  it("is offered to the owner of a record awaiting resubmission", async () => {
    shownRecord = awaiting;
    signInAs(OWNER_ID, "Student");
    renderPaperView();

    expect(await screen.findByRole("button", RESUBMIT)).toBeInTheDocument();
  });

  it("is not offered to someone who does not own it", async () => {
    shownRecord = awaiting;
    signInAs(99, "Student");
    renderPaperView();

    await waitForRecord(inReview.title);
    expect(screen.queryByRole("button", RESUBMIT)).not.toBeInTheDocument();
  });

  it("is not offered while the record is still in review, even if stored as declined", async () => {
    shownRecord = { ...inReview, pipeline_status: "declined" };
    signInAs(OWNER_ID, "Student");
    renderPaperView();

    await waitForRecord(inReview.title);
    expect(screen.queryByRole("button", RESUBMIT)).not.toBeInTheDocument();
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
    shownRecord = { ...inReview, pipeline_status: "rdco_review", workflow_state_label: "Final review", workflow_state: "final_review" };
    signInAs(99, "Student");
    renderPaperView();

    await waitForRecord(inReview.title);
    // Once as the badge, once as the governance ledger's status row.
    expect(screen.getAllByText("Final review")).toHaveLength(2);
    expect(screen.queryByText("RDCO Final Review")).not.toBeInTheDocument();
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

describe("the rail while Paper Chat is docked (IR-351)", () => {
  const RAIL = { name: "Institutional Governance" };

  beforeEach(() => {
    shownRecord = record;
    signInAs(99, "Student");
  });

  afterEach(() => localStorage.removeItem(DOCK_KEY));

  async function openChatDocked(mode: "left" | "right" | "floating") {
    localStorage.setItem(DOCK_KEY, mode);
    renderPaperView();
    await waitForRecord(record.title);
    await userEvent.click(screen.getByRole("button", { name: "Ask about this paper" }));
    await screen.findByRole("complementary", { name: "Paper Chat" });
  }

  // Docked beside the rail, the chat squeezed the paper under it; the rail is
  // not shown at all while docked. It is back as soon as the chat floats.
  it.each(["left", "right"] as const)("is not shown while docked %s", async (mode) => {
    await openChatDocked(mode);
    expect(screen.queryByRole("heading", RAIL)).not.toBeInTheDocument();
  });

  it("is shown while the chat floats", async () => {
    await openChatDocked("floating");
    expect(screen.getByRole("heading", RAIL)).toBeInTheDocument();
  });

  it("comes back when the docked chat is closed", async () => {
    await openChatDocked("right");
    await userEvent.click(screen.getByRole("button", { name: "Close Paper Chat" }));
    expect(await screen.findByRole("heading", RAIL)).toBeInTheDocument();
  });
});

// The Paper tab is the paper and Ask IRIS docked right, full width, nothing
// else (IR-372, decided with the project lead 2026-09-25). Overview
// keeps IR-351's rule above.
describe("the Paper tab (IR-372)", () => {
  const RAIL = { name: "Institutional Governance" };
  const REOPEN = { name: "Ask IRIS" };

  beforeEach(() => {
    shownRecord = record;
    signInAs(99, "Student");
  });

  afterEach(() => localStorage.removeItem(DOCK_KEY));

  async function openPaperTab(storedDock?: "left" | "right" | "floating") {
    if (storedDock) localStorage.setItem(DOCK_KEY, storedDock);
    renderPaperView();
    await waitForRecord(record.title);
    await userEvent.click(screen.getByRole("tab", { name: "Paper" }));
    await screen.findByText(/paper reader open/i);
  }

  it("shows no rail while the chat is closed", async () => {
    await openPaperTab("floating");
    expect(screen.queryByRole("heading", RAIL)).not.toBeInTheDocument();
  });

  it("offers Ask IRIS from the reader's toolbar, not a floating button over the paper", async () => {
    await openPaperTab("floating");
    expect(screen.queryByRole("button", { name: "Ask about this paper" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", REOPEN)).toBeInTheDocument();
  });

  it.each(["left", "right", "floating"] as const)(
    "opens the chat docked, with no rail and no way to move it, whatever was stored (%s)",
    async (stored) => {
      await openPaperTab(stored);
      await userEvent.click(screen.getByRole("button", REOPEN));

      expect(await screen.findByRole("complementary", { name: "Paper Chat" })).toBeInTheDocument();
      expect(screen.queryByRole("heading", RAIL)).not.toBeInTheDocument();
      expect(screen.queryByRole("button", { name: "Panel position" })).not.toBeInTheDocument();
      // The reader's own choice is left alone for Overview.
      expect(localStorage.getItem(DOCK_KEY)).toBe(stored);
    },
  );

  it("leaves the paper full width once the chat is closed, with the toolbar control back", async () => {
    await openPaperTab();
    await userEvent.click(screen.getByRole("button", REOPEN));
    await userEvent.click(await screen.findByRole("button", { name: "Close Paper Chat" }));

    expect(screen.queryByRole("complementary", { name: "Paper Chat" })).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", RAIL)).not.toBeInTheDocument();
    expect(screen.getByRole("button", REOPEN)).toBeInTheDocument();
  });

  it("gives Overview back its own layout, rail and floating chat included", async () => {
    await openPaperTab("floating");
    await userEvent.click(screen.getByRole("tab", { name: "Overview" }));

    expect(await screen.findByRole("heading", RAIL)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Ask about this paper" }));
    await screen.findByRole("complementary", { name: "Paper Chat" });
    expect(screen.getByRole("button", { name: "Panel position" })).toBeInTheDocument();
    expect(screen.getByRole("heading", RAIL)).toBeInTheDocument();
  });

  it("keeps an open chat's conversation when the reader switches tabs", async () => {
    const { aiApi } = await import("@/api/ai");
    const findOrCreate = vi.mocked(aiApi.conversations.findOrCreateForRecord);
    findOrCreate.mockClear();

    localStorage.setItem(DOCK_KEY, "right");
    renderPaperView();
    await waitForRecord(record.title);
    await userEvent.click(screen.getByRole("button", { name: "Ask about this paper" }));
    await screen.findByRole("complementary", { name: "Paper Chat" });

    await userEvent.click(screen.getByRole("tab", { name: "Paper" }));
    await userEvent.click(screen.getByRole("tab", { name: "Overview" }));

    expect(screen.getByRole("complementary", { name: "Paper Chat" })).toBeInTheDocument();
    expect(findOrCreate).toHaveBeenCalledTimes(1);
  });

  it("has no serious or critical accessibility violations with the chat open", async () => {
    const { container } = await (async () => {
      const view = renderPaperView();
      await waitForRecord(record.title);
      await userEvent.click(screen.getByRole("tab", { name: "Paper" }));
      await screen.findByText(/paper reader open/i);
      await userEvent.click(screen.getByRole("button", REOPEN));
      await screen.findByRole("complementary", { name: "Paper Chat" });
      return view;
    })();
    await expectNoBlockingA11yViolations(container);
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
    vi.mocked(aiApi.conversations.findOrCreateForRecord).mockImplementation(() =>
      Promise.resolve({
        data: {
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
        },
      } as never),
    );
  });

  afterEach(async () => {
    const { aiApi } = await import("@/api/ai");
    vi.mocked(aiApi.conversations.findOrCreateForRecord).mockImplementation(() => new Promise(() => {}));
    vi.unstubAllGlobals();
  });

  async function followCitationFromChat() {
    renderPaperView();
    await waitForRecord(record.title);
    await userEvent.click(screen.getByRole("tab", { name: "Paper" }));
    await userEvent.click(await screen.findByRole("button", { name: "Ask IRIS" }));
    await userEvent.click(await screen.findByRole("link", CITED));
    await screen.findByText(/open at page 12, 1 region\(s\)/i);
  }

  it("minimizes the sheet below lg, and restores it with the answer still there", async () => {
    await followCitationFromChat();

    const bar = await screen.findByRole("button", { name: "Show Paper Chat" });
    expect(screen.queryByRole("textbox", { name: "Ask about this paper" })).not.toBeInTheDocument();

    await userEvent.click(bar);

    expect(screen.getByRole("link", CITED)).toBeVisible();
    expect(screen.getByRole("textbox", { name: "Ask about this paper" })).toBeInTheDocument();
  });

  function atLg() {
    vi.stubGlobal("matchMedia", (query: string) => ({
      matches: query === CONTAINED_LAYOUT_QUERY,
      media: query,
      addEventListener: () => {},
      removeEventListener: () => {},
    }));
  }

  it("leaves the docked column as it is at lg, where it covers nothing", async () => {
    atLg();

    await followCitationFromChat();

    expect(screen.queryByRole("button", { name: "Show Paper Chat" })).not.toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "Ask about this paper" })).toBeInTheDocument();
  });

  it("keeps the passage highlighted when the chat is closed and opened again", async () => {
    atLg();
    await followCitationFromChat();

    await userEvent.click(screen.getByRole("button", { name: "Close Paper Chat" }));
    expect(screen.getByText(/open at page 12, 1 region\(s\)/i)).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Ask IRIS" }));
    await screen.findByRole("complementary", { name: "Paper Chat" });
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
    localStorage.setItem(DOCK_KEY, "right");
    // At `lg` the docked chat is a column and never minimizes (IR-354), so
    // the transcript stays readable after a citation is followed.
    vi.stubGlobal("matchMedia", (query: string) => ({
      matches: query === CONTAINED_LAYOUT_QUERY,
      media: query,
      addEventListener: () => {},
      removeEventListener: () => {},
    }));

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
    vi.mocked(aiApi.conversations.findOrCreateForRecord).mockReset();
    vi.mocked(aiApi.conversations.findOrCreateForRecord).mockImplementation(
      ((id: number) => Promise.resolve({ data: conversations[id] })) as never,
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

  afterEach(async () => {
    heldBack = null;
    localStorage.removeItem(DOCK_KEY);
    vi.unstubAllGlobals();
    const { recordsApi } = await import("@/api/records");
    vi.mocked(recordsApi.detail).mockImplementation((() => Promise.resolve({ data: shownRecord })) as never);
    const { aiApi } = await import("@/api/ai");
    vi.mocked(aiApi.conversations.findOrCreateForRecord).mockImplementation(() => new Promise(() => {}));
  });

  async function conversationsOpened(): Promise<number[]> {
    const { aiApi } = await import("@/api/ai");
    return vi.mocked(aiApi.conversations.findOrCreateForRecord).mock.calls.map(([id]) => id as number);
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
    return screen.getByRole("complementary", { name: "Paper Chat" });
  }

  /** On X, chat open, "All papers" on, the answer citing Y on screen. */
  async function openChatOnX() {
    const view = renderWithPlainLink();
    await waitForRecord(record.title);
    await userEvent.click(screen.getByRole("button", { name: "Ask about this paper" }));
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

    await userEvent.click(within(panel()).getByRole("button", { name: "Close Paper Chat" }));
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

    await userEvent.click(screen.getByRole("button", { name: "Ask IRIS" }));

    expect(await within(panel()).findByText(QUESTION_ON_Y)).toBeInTheDocument();
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

  it("keeps the pin when the panel changes position", async () => {
    await followToOtherPaper();

    // The Paper tab fixes the dock (IR-372); Overview offers it.
    await userEvent.click(screen.getByRole("tab", { name: "Overview" }));
    await userEvent.click(within(panel()).getByRole("button", { name: "Panel position" }));
    await userEvent.click(within(panel()).getByRole("button", { name: /Floating/ }));

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
    shownRecord = { ...inReview, can_act: ["itso"] };
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
    shownRecord = { ...inReview, workflow_state: "awaiting_resubmission", workflow_state_label: "Revision requested" };
    signInAs(OWNER_ID, "Student");
    renderPaperView();

    expect(await screen.findByRole("button", { name: "Edit details" })).toBeInTheDocument();
  });

  it("offers nobody but the owner Edit details on a draft", async () => {
    shownRecord = draft;
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
    can_act: [],
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
    localStorage.removeItem(DOCK_KEY);
  });

  const bar = () => screen.getByRole("toolbar", { name: "Review actions" });

  it("puts the paper beside the timeline, from the tracker", async () => {
    shownRecord = { ...inReview, can_act: ["itso"] };
    signInAs(2, "ITSO");
    const { container } = renderPaper(`/records/${RECORD_ID}?section=review`);

    expect(await screen.findByText(/paper reader open at page none/i)).toBeInTheDocument();
    const timeline = await screen.findByRole("list", { name: "Review timeline" });
    expect(within(timeline).getByText("Submitted to ITSO")).toBeInTheDocument();
    expect(recordsApi.tracker).toHaveBeenCalledWith(RECORD_ID);
    await expectNoBlockingA11yViolations(container);
  });

  it("offers a reviewer who may request documents exactly that, and the current form", async () => {
    shownRecord = { ...inReview, can_act: ["ierc"], can_request_document: ["ierc"] };
    signInAs(2, "IERC");
    renderPaper(`/records/${RECORD_ID}?section=review`);

    await screen.findByRole("tab", { name: "Review", selected: true });
    expect(within(bar()).getAllByRole("button").map((b) => b.textContent?.trim())).toEqual([
      "Request documents",
    ]);
    expect(within(bar()).getByRole("link", { name: "Record a decision (current form)" })).toBeInTheDocument();
  });

  it("offers Request documents alone to a party that may ask but not decide", async () => {
    shownRecord = { ...inReview, can_request_document: ["ierc"] };
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
    shownRecord = { ...inReview, can_request_document: ["ierc"] };
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
    shownRecord = { ...inReview, can_act: ["itso"] };
    signInAs(2, "ITSO");
    renderWithProbe(`/records/${RECORD_ID}?section=review`);

    await screen.findByRole("list", { name: "Review timeline" });
    expect(screen.queryByRole("complementary", { name: "Paper Chat" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Ask IRIS" })).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Ask about this paper" }));

    expect(await screen.findByRole("tab", { name: "Paper", selected: true })).toBeInTheDocument();
    expect(await screen.findByRole("complementary", { name: "Paper Chat" })).toBeInTheDocument();
    expect(screen.getByRole("status", { name: "Location" })).toHaveTextContent(
      `/records/${RECORD_ID}?section=paper`,
    );
  });

  it("offers no Ask about this paper when there is no paper to ask about", async () => {
    shownRecord = { ...inReview, abstract_file: null, files: [], can_act: ["itso"] };
    signInAs(2, "ITSO");
    renderPaper(`/records/${RECORD_ID}?section=review`);

    await screen.findByRole("list", { name: "Review timeline" });
    expect(screen.queryByText(/paper reader open/i)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Ask about this paper" })).not.toBeInTheDocument();
  });

  it("lands a citation on its passage in the Review section's reader too", async () => {
    shownRecord = { ...inReview, can_act: ["itso"] };
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

  afterEach(() => localStorage.removeItem(DOCK_KEY));

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

  it("tells Paper Chat's reader that answers are about the current version", async () => {
    shownRecord = { ...record, versions: twoVersions };
    renderPaper(`/records/${RECORD_ID}?section=paper&version=1`);
    await screen.findByText(/reading v1/i);

    await userEvent.click(screen.getByRole("button", { name: "Ask IRIS" }));

    const panel = await screen.findByRole("complementary", { name: "Paper Chat" });
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
