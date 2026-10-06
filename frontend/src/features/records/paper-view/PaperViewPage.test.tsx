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
 * `highlightRegions`, and that the Abstract/Paper toggle follows along.
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
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { Link, Route, Routes } from "react-router-dom";

import { expectNoBlockingA11yViolations } from "@/test/axe";
import { renderScreen, screen, userEvent, waitFor, within } from "@/test/render";
import { useAuthStore } from "@/store/auth.store";
import type { User } from "@/types/auth";
import type { RecordDetail } from "@/types/records";

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
  }: {
    scrollToPage: number | null;
    highlightRegions: unknown[];
    toolbarStart?: ReactNode;
  }) => (
    <div>
      {toolbarStart}
      Paper reader open at page {scrollToPage ?? "none"}, {highlightRegions.length} region(s) to
      highlight
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

  it("opens on the Abstract tab, with the Paper tab one click away, when no page was named", async () => {
    renderPaper(`/records/${RECORD_ID}`);

    expect(await screen.findByRole("tab", { name: "Abstract", selected: true })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Paper", selected: false })).toBeEnabled();
  });

  it("ignores a page that is not a page and stays on Abstract", async () => {
    renderPaper(`/records/${RECORD_ID}?page=not-a-page`);

    expect(await screen.findByRole("tab", { name: "Abstract", selected: true })).toBeInTheDocument();
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
// else (IR-372, decided with the project lead 2026-09-25). The Abstract tab
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
      // The reader's own choice is left alone for the Abstract tab.
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

  it("gives the Abstract tab back its own layout, rail and floating chat included", async () => {
    await openPaperTab("floating");
    await userEvent.click(screen.getByRole("tab", { name: "Abstract" }));

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
    await userEvent.click(screen.getByRole("tab", { name: "Abstract" }));

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
  function renderWithPlainLink() {
    return renderScreen(
      <>
        <Routes>
          <Route path="/records/:id" element={<PaperViewPage />} />
        </Routes>
        <Link to={`/records/${OTHER_ID}`}>Go to the other paper</Link>
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
      within(panel()).getByRole("textbox", { name: "Ask about this paper" }),
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

    // The Paper tab fixes the dock (IR-372); the Abstract tab offers it.
    await userEvent.click(screen.getByRole("tab", { name: "Abstract" }));
    await userEvent.click(within(panel()).getByRole("button", { name: "Panel position" }));
    await userEvent.click(within(panel()).getByRole("button", { name: /Floating/ }));

    expect(within(panel()).getByText(PINNED_HEADER)).toHaveTextContent(`Chatting about ${record.title}`);
    expect(within(panel()).getByText(/Gauge density matters/)).toBeVisible();
    expect(await conversationsOpened()).toEqual([RECORD_ID]);
  });

  it("has no serious or critical accessibility violations while pinned", async () => {
    const { container } = await followToOtherPaper();

    await expectNoBlockingA11yViolations(container);
  });
});
