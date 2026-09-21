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
};

/** Which record `recordsApi.detail` resolves with. Reset per describe block,
 * since the two concerns below need different records shown. */
let shownRecord: RecordDetail = record;

const completeProposal = vi.fn((_id: number) => Promise.resolve({ data: { detail: "ok" } }));

vi.mock("@/api/records", () => ({
  recordsApi: {
    detail:           vi.fn(() => Promise.resolve({ data: shownRecord })),
    incrementAccess:  vi.fn(() => Promise.resolve({ data: {} })),
    similar:          vi.fn(() => Promise.resolve({ data: { results: [] } })),
    // The tracker panel loads itself; it has its own test file (IR-258).
    tracker:          vi.fn(() => Promise.reject(new Error("not under test"))),
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
