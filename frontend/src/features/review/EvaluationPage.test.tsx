/**
 * The office evaluation screen's two routes to the evidence (IR-235).
 *
 * **What this file is guarding, and why it is not obvious.**
 *
 * The reviewer decides a clearance here, and reaches the documents that decision
 * is about through two links that open in a new tab. Those links used to carry
 * `rel="noopener noreferrer"` -- the near-universal advice for `target="_blank"`
 * -- and that silently signed the reviewer out of the new tab.
 *
 * **The mechanism is documented once, at the links themselves** -- see the
 * comment above the two anchors in `EvaluationPage.tsx`, which is where someone
 * is standing when they are tempted to re-add `rel`. Explaining it twice would
 * only give the two copies somewhere to drift apart. The short version: the
 * session lives in `sessionStorage`, and `noopener` is what stops the browser
 * cloning it into the new tab.
 *
 * **This suite cannot prove the fix.** jsdom has a single browsing context: it
 * cannot open a second tab and cannot reproduce `sessionStorage` cloning. What
 * it can do is fail if the `rel` attribute comes back, which is the realistic
 * regression -- someone hardening `target="_blank"` links in a sweep. The
 * "the new tab is signed in" check is manual today, and belongs to the
 * Playwright harness in IR-219.
 *
 * Every query goes through the accessible tree, by role and accessible name.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { Route, Routes } from "react-router-dom";

import { expectNoBlockingA11yViolations } from "@/test/axe";
import { renderScreen, screen } from "@/test/render";
import type { RecordDetail } from "@/types/records";

import EvaluationPage from "./EvaluationPage";

const RECORD_ID = 42;

/**
 * A record parked at parallel review -- the stage where an office records a
 * clearance, which is the state this screen exists to serve.
 */
const record: RecordDetail = {
  id: RECORD_ID,
  title: "Assistive Navigation for Low-Vision Commuters",
  abstract: "A study of wayfinding aids on urban transit.",
  year_accomplished: 2026,
  year_completed: null,
  abstract_file: null,
  classification_name: "Applied Research",
  classification: "Applied Research",
  psced: null,
  record_type_name: "Thesis/Research",
  record_type: "Thesis/Research",
  pipeline_status: "parallel_review",
  is_ip: false,
  ip_type: "",
  for_commercialization: false,
  community_extension: false,
  access_count: 0,
  file_count: 2,
  created_at: "2026-09-01T08:00:00Z",
  authors: [{ id: 1, name: "Mateo Villanueva", role: null }],
  adviser: null,
  added_by: null,
  requires_ethics_review: true,
  requested_itso: true,
  requested_ierc: true,
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
  stage_label: "Parallel Office Review",
  your_office: "ierc",
  your_office_label: "IERC",
  files: [],
};

vi.mock("@/api/records", () => ({
  recordsApi: {
    detail: vi.fn(() => Promise.resolve({ data: record })),
  },
}));

/** Both links announce the new tab, so that suffix is part of the name. */
const DOCUMENTS_LINK = "View & Attach Documents (opens in a new tab)";
const DETAIL_LINK = "Record Detail (opens in a new tab)";

function renderEvaluationScreen() {
  return renderScreen(
    <Routes>
      <Route path="/review/:id/evaluate" element={<EvaluationPage />} />
    </Routes>,
    { route: `/review/${RECORD_ID}/evaluate` },
  );
}

describe("the office evaluation screen", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("names both routes to the evidence, and says they open a new tab", async () => {
    renderEvaluationScreen();

    // `findBy` rather than `getBy`: the screen renders a skeleton until the
    // record arrives. Resolving by accessible *name* is also the assertion
    // that the "(opens in a new tab)" warning reaches assistive technology --
    // a sighted user sees a new tab appear, a screen reader user does not.
    expect(await screen.findByRole("link", { name: DOCUMENTS_LINK })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: DETAIL_LINK })).toBeInTheDocument();
  });

  it("opens the record's documents in a new tab without severing the session", async () => {
    renderEvaluationScreen();

    const documents = await screen.findByRole("link", { name: DOCUMENTS_LINK });

    expect(documents).toHaveAttribute("href", `/records/${RECORD_ID}/documents`);
    expect(documents).toHaveAttribute("target", "_blank");

    // The regression guard. `noreferrer` implies `noopener`, so either token
    // alone re-breaks the session -- which is why this asserts on the whole
    // attribute being absent rather than on one keyword.
    expect(documents).not.toHaveAttribute("rel");
  });

  it("opens the record detail in a new tab without severing the session", async () => {
    renderEvaluationScreen();

    const detail = await screen.findByRole("link", { name: DETAIL_LINK });

    expect(detail).toHaveAttribute("href", `/records/${RECORD_ID}`);
    expect(detail).toHaveAttribute("target", "_blank");
    expect(detail).not.toHaveAttribute("rel");
  });

  it("has no serious or critical accessibility violations", async () => {
    const { container } = renderEvaluationScreen();

    await screen.findByRole("link", { name: DOCUMENTS_LINK });

    await expectNoBlockingA11yViolations(container);
  });
});
