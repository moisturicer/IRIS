/**
 * Two independent concerns on the same screen, merged into one file because
 * `@/api/records` can only be mocked once per module.
 *
 * **Arriving from a citation (IR-284).** `lib/citedPage` is unit-tested on
 * both halves — reading the page off the query string, and asking the PDF
 * viewer for it — but the two halves being right does not make the *join*
 * right, and the join is what a reader actually walks: a citation link
 * carries `?page=N`, and this screen has to turn that into a paper opened at
 * that page. So this test starts where the citation sends them and asserts
 * where they end up.
 *
 * **Who sees "Mark as completed" (IR-267).** ADR-021 §3: a Proposal is
 * completed by its assigned Adviser or by RDCO. The button follows the same
 * rule the server enforces -- RDCO, or the Adviser whose id is the record's
 * `adviser` -- and nobody else sees it. The server still refuses everyone
 * else; this only keeps the page from offering an action that would be
 * refused.
 *
 * **Who sees the review and resubmit controls (IR-259).** Both read the API,
 * never the stored stage: "Review this record" appears exactly when `can_act`
 * names a party for this viewer, and "Resubmit for review" exactly when the
 * record is `awaiting_resubmission` and the viewer owns it. The records below
 * carry a `pipeline_status` that would have said the opposite, so a gate that
 * still read the stage would fail here.
 *
 * Every query goes through the accessible tree, by role and accessible name.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { Route, Routes } from "react-router-dom";

import { expectNoBlockingA11yViolations } from "@/test/axe";
import { renderScreen, screen, userEvent, waitFor } from "@/test/render";
import { useAuthStore } from "@/store/auth.store";
import type { User } from "@/types/auth";
import type { RecordDetail } from "@/types/records";

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
};

/** Which record `recordsApi.detail` resolves with. Reset per describe block,
 * since the two concerns below need different records shown. */
let shownRecord: RecordDetail = record;

const completeProposal = vi.fn((_id: number) => Promise.resolve({ data: { detail: "ok" } }));

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
    updateTags:       vi.fn(),
    completeProposal: (id: number) => completeProposal(id),
  },
}));

vi.mock("@/api/reviews", () => ({ reviewsApi: { resubmit: vi.fn() } }));

// The AI overview asks a question of its own; this screen is not what that
// behaviour is tested through (`PaperAiOverview.test.tsx` is).
vi.mock("@/api/ai", () => ({
  aiApi: { ask: vi.fn(() => Promise.reject(new Error("not under test"))) },
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
function renderPaper(route: string) {
  return renderScreen(
    <Routes>
      <Route path="/records/:id" element={<PaperViewPage />} />
    </Routes>,
    { route },
  );
}

function renderPaperView() {
  return renderPaper(`/records/${RECORD_ID}`);
}

describe("arriving from a citation", () => {
  beforeEach(() => {
    shownRecord = record;
  });

  it("opens the paper at the cited page", async () => {
    renderPaper(`/records/${RECORD_ID}?page=12`);

    const link = await screen.findByRole("link", { name: /View Paper at page 12/i });
    expect(link.getAttribute("href")).toBe(`${PAPER_URL}#page=12`);
  });

  it("opens the paper plainly when no page was named", async () => {
    renderPaper(`/records/${RECORD_ID}`);

    const link = await screen.findByRole("link", { name: /^View Paper$/i });
    expect(link.getAttribute("href")).toBe(PAPER_URL);
  });

  it("ignores a page that is not a page", async () => {
    renderPaper(`/records/${RECORD_ID}?page=not-a-page`);

    const link = await screen.findByRole("link", { name: /^View Paper$/i });
    expect(link.getAttribute("href")).toBe(PAPER_URL);
  });
});

const MARK_COMPLETED = { name: /mark as completed/i };

describe("Mark as completed on an approved Proposal", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    shownRecord = approvedProposal;
  });

  it("is offered to the assigned Adviser, and completes the Proposal", async () => {
    signInAs(ASSIGNED_ADVISER_ID, "Adviser");
    const { container } = renderPaperView();

    const button = await screen.findByRole("button", MARK_COMPLETED);
    await expectNoBlockingA11yViolations(container);
    await userEvent.click(button);

    await waitFor(() => expect(completeProposal).toHaveBeenCalledWith(RECORD_ID));
  });

  it("is offered to RDCO", async () => {
    signInAs(1, "RDCO");
    renderPaperView();

    expect(await screen.findByRole("button", MARK_COMPLETED)).toBeInTheDocument();
  });

  it.each([
    ["an Adviser who is not assigned", 99, "Adviser"],
    ["ITSO", 2, "ITSO"],
    ["IERC", 3, "IERC"],
    ["KTTO", 4, "KTTO"],
    ["a student", 5, "Student"],
  ] as const)("is not offered to %s", async (_label, id, role) => {
    signInAs(id, role);
    renderPaperView();

    // Wait for the record to render before asserting an absence, or the
    // assertion would pass against the loading skeleton.
    await screen.findByRole("heading", { name: approvedProposal.title });
    expect(screen.queryByRole("button", MARK_COMPLETED)).not.toBeInTheDocument();
  });

  it("is not offered once the Proposal is completed", async () => {
    shownRecord = { ...approvedProposal, pipeline_status: "completed" };
    signInAs(ASSIGNED_ADVISER_ID, "Adviser");
    renderPaperView();

    await screen.findByRole("heading", { name: approvedProposal.title });
    expect(screen.queryByRole("button", MARK_COMPLETED)).not.toBeInTheDocument();
  });
});

const OWNER_ID = 40;
const REVIEW_THIS = { name: "Review this record" } as const;
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

    expect(await screen.findByRole("link", REVIEW_THIS)).toBeInTheDocument();
    await expectNoBlockingA11yViolations(container);
  });

  it("is not offered to a same-role viewer the API does not name, whatever the stage", async () => {
    // `parallel_review` is a stage an ITSO reviewer used to be shown the
    // control at by role alone. The API says this one cannot act.
    shownRecord = { ...inReview, pipeline_status: "parallel_review", can_act: [] };
    signInAs(2, "ITSO");
    renderPaperView();

    await waitForRecord(inReview.title);
    expect(screen.queryByRole("link", REVIEW_THIS)).not.toBeInTheDocument();
  });

  it("is not offered to the owner", async () => {
    shownRecord = inReview;
    signInAs(OWNER_ID, "Student");
    renderPaperView();

    await waitForRecord(inReview.title);
    expect(screen.queryByRole("link", REVIEW_THIS)).not.toBeInTheDocument();
  });
});

describe("the resubmit control follows workflow_state", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  const awaiting: RecordDetail = {
    ...inReview,
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
    created_at: "2026-09-20T02:00:00Z", closed_at: null,
    items: [{
      id: 11, slot: 3, label: "Ethics Clearance", state: "missing",
      state_label: "Missing", upload: null, uploaded_at: null,
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

  it("offers Request documents exactly when the API names a party", async () => {
    shownRecord = { ...inReview, can_request_document: ["ierc"] };
    signInAs(2, "IERC");
    renderPaperView();

    expect(await screen.findByRole("button", { name: "Request documents" })).toBeInTheDocument();
  });

  it("does not offer Request documents otherwise", async () => {
    shownRecord = inReview;
    signInAs(2, "IERC");
    renderPaperView();

    await waitForRecord(inReview.title);
    expect(screen.queryByRole("button", { name: "Request documents" })).not.toBeInTheDocument();
  });
});
