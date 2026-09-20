/**
 * Landing on the page a citation pointed at (IR-284).
 *
 * `lib/citedPage` is unit-tested on both halves — reading the page off the
 * query string, and asking the PDF viewer for it — but the two halves being
 * right does not make the *join* right, and the join is what a reader
 * actually walks: a citation link carries `?page=N`, and this screen has to
 * turn that into a paper opened at that page. So this test starts where the
 * citation sends them and asserts where they end up.
 *
 * Every query goes through the accessible tree, by role and accessible name.
 */
import { describe, expect, it, vi } from "vitest";
import { Route, Routes } from "react-router-dom";

import { renderScreen, screen } from "@/test/render";
import type { RecordDetail } from "@/types/records";

import PaperViewPage from "./PaperViewPage";

const RECORD_ID = 7;
const PAPER_URL = "https://iris.test/media/manuscripts/thesis.pdf";

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
};

vi.mock("@/api/records", () => ({
  recordsApi: {
    detail:          vi.fn(() => Promise.resolve({ data: record })),
    incrementAccess: vi.fn(() => Promise.resolve({ data: {} })),
    similar:         vi.fn(() => Promise.resolve({ data: { results: [] } })),
    updateTags:      vi.fn(),
    completeProposal: vi.fn(),
  },
}));

vi.mock("@/api/reviews", () => ({ reviewsApi: { resubmit: vi.fn() } }));

// The overview asks a question of its own; this screen is not what that
// behaviour is tested through (`PaperAiOverview.test.tsx` is).
vi.mock("@/api/ai", () => ({
  aiApi: { ask: vi.fn(() => Promise.reject(new Error("not under test"))) },
}));

/** Mounted on its real path, so `useParams` sees the record id. */
function renderPaper(route: string) {
  return renderScreen(
    <Routes>
      <Route path="/records/:id" element={<PaperViewPage />} />
    </Routes>,
    { route },
  );
}

describe("arriving from a citation", () => {
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
