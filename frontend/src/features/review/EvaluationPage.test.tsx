/**
 * The office evaluation screen: reaching the evidence without losing the
 * decision (IR-237).
 *
 * **What changed, and why the previous assertions are gone.**
 *
 * This file used to assert that both links carried `target="_blank"` and *no*
 * `rel`, guarding IR-235's fix for a reviewer being signed out in the new tab.
 * Those assertions are deliberately replaced rather than quietly deleted,
 * because the behaviour they pinned does not work:
 *
 *   - `target="_blank"` has *implied* `noopener` since Chrome 88 (Firefox 79,
 *     Safari 12.1), so removing `rel` changed nothing. Measured on a bare
 *     same-origin page: with `rel` and without it, `sessionStorage` was not
 *     cloned and `window.opener` was null both times.
 *   - The refresh token lives only in `sessionStorage` (FR-M6-01), so the new
 *     tab had nothing to restore and the route guard sent the reviewer to the
 *     login screen -- which is what a human hit in manual testing after IR-235
 *     merged.
 *
 * The old suite could not have caught that, and said so in its own docstring:
 * jsdom has a single browsing context, so "is the new tab signed in?" was
 * never testable here. It could only check the `rel` attribute, which was the
 * wrong mechanism. **A green suite over the wrong assertion is how a no-op
 * ships** -- worth remembering next time a fix cannot be tested at the level
 * it operates on.
 *
 * So the links navigate in-app now, and what gets protected instead is the
 * reviewer's unsent decision (`lib/reviewDraft.ts`), which *is* testable here
 * and covers more: an accidental back, a reload, an expired session.
 *
 * Every query goes through the accessible tree, by role and accessible name.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { Route, Routes, useLocation } from "react-router-dom";

import { expectNoBlockingA11yViolations } from "@/test/axe";
import { renderScreen, screen, userEvent, waitFor } from "@/test/render";
import { readReviewDraft, writeReviewDraft } from "@/lib/reviewDraft";
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

const submitReview = vi.fn((_payload: unknown) => Promise.resolve({ data: {} }));
// The factory is hoisted above the imports, so it must not *read*
// `submitReview` until it is called -- by which time the const exists.
vi.mock("@/api/reviews", () => ({
  reviewsApi: {
    submit: (payload: unknown) => submitReview(payload),
  },
}));

/** Plain names now -- nothing claims a new tab, because nothing opens one. */
const DOCUMENTS_LINK = "View & Attach Documents";
const DETAIL_LINK = "Record Detail";

/** Renders wherever the router ends up, so a navigation is observable. */
function LandedOn() {
  const location = useLocation();
  return <h1>{`landed on ${location.pathname}`}</h1>;
}

function renderEvaluationScreen() {
  return renderScreen(
    <Routes>
      <Route path="/review/:id/evaluate" element={<EvaluationPage />} />
      <Route path="*" element={<LandedOn />} />
    </Routes>,
    { route: `/review/${RECORD_ID}/evaluate` },
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  sessionStorage.clear();
});

afterEach(() => {
  sessionStorage.clear();
});

describe("the office evaluation screen", () => {
  it("names both routes to the evidence", async () => {
    renderEvaluationScreen();

    // `findBy` rather than `getBy`: the screen renders a skeleton until the
    // record arrives.
    expect(await screen.findByRole("link", { name: DOCUMENTS_LINK })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: DETAIL_LINK })).toBeInTheDocument();
  });

  it("reaches the documents without leaving the app", async () => {
    renderEvaluationScreen();

    const documents = await screen.findByRole("link", { name: DOCUMENTS_LINK });

    expect(documents).toHaveAttribute("href", `/records/${RECORD_ID}/documents`);
    // The regression guard, and the point of IR-237. A new tab is a fresh
    // browsing context that never receives the `sessionStorage` the refresh
    // token lives in, so opening one signs the reviewer out at exactly the
    // moment they are deciding a clearance.
    expect(documents).not.toHaveAttribute("target");
  });

  it("reaches the record detail without leaving the app", async () => {
    renderEvaluationScreen();

    const detail = await screen.findByRole("link", { name: DETAIL_LINK });

    expect(detail).toHaveAttribute("href", `/records/${RECORD_ID}`);
    expect(detail).not.toHaveAttribute("target");
  });

  it("actually navigates in-tab when the link is followed", async () => {
    // Asserting the absence of `target` says the tab will not be replaced;
    // this says the link goes where it claims.
    const user = userEvent.setup();
    renderEvaluationScreen();

    await user.click(await screen.findByRole("link", { name: DOCUMENTS_LINK }));

    expect(
      await screen.findByRole("heading", { name: `landed on /records/${RECORD_ID}/documents` }),
    ).toBeInTheDocument();
  });

  it("has no serious or critical accessibility violations", async () => {
    const { container } = renderEvaluationScreen();

    await screen.findByRole("link", { name: DOCUMENTS_LINK });

    await expectNoBlockingA11yViolations(container);
  });
});

/**
 * The half-written clearance decision (IR-237).
 *
 * This is the requirement IR-143 was protecting with a new tab, met directly.
 */
describe("the reviewer's unsent decision", () => {
  const commentBox = () => screen.getByRole("textbox");

  it("is kept as the reviewer types", async () => {
    const user = userEvent.setup();
    renderEvaluationScreen();

    await screen.findByRole("link", { name: DOCUMENTS_LINK });
    await user.type(commentBox(), "Consent forms are missing from section 3.");

    await waitFor(() => {
      expect(readReviewDraft(RECORD_ID)?.comment).toBe(
        "Consent forms are missing from section 3.",
      );
    });
  });

  it("comes back after leaving the screen and returning", async () => {
    // The whole journey the ticket is about: read the evidence, come back,
    // find the comment still there.
    writeReviewDraft(RECORD_ID, {
      status: "declined",
      comment: "Consent forms are missing from section 3.",
    });

    renderEvaluationScreen();

    await screen.findByRole("link", { name: DOCUMENTS_LINK });
    expect(commentBox()).toHaveValue("Consent forms are missing from section 3.");
    expect(screen.getByRole("radio", { name: /Request Revision/ })).toBeChecked();
  });

  it("does not borrow another record's draft", async () => {
    writeReviewDraft(RECORD_ID + 1, { status: "rejected", comment: "A different submission." });

    renderEvaluationScreen();

    await screen.findByRole("link", { name: DOCUMENTS_LINK });
    expect(commentBox()).toHaveValue("");
  });

  it("is cleared once the review is submitted", async () => {
    // Otherwise the next visit to this record opens with a comment about a
    // decision that has already been made.
    const user = userEvent.setup();
    writeReviewDraft(RECORD_ID, { status: "approved", comment: "Looks complete." });

    renderEvaluationScreen();

    await screen.findByRole("link", { name: DOCUMENTS_LINK });
    await user.click(screen.getByRole("button", { name: /Submit/i }));

    await waitFor(() => {
      expect(submitReview).toHaveBeenCalled();
    });
    expect(readReviewDraft(RECORD_ID)).toBeNull();
  });

  it("renders the form even when the browser refuses storage", async () => {
    // A private window can throw from the accessor itself. Losing the draft is
    // acceptable; failing to render the decision form is not.
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("access denied");
    });

    renderEvaluationScreen();

    expect(await screen.findByRole("link", { name: DOCUMENTS_LINK })).toBeInTheDocument();
    expect(commentBox()).toHaveValue("");
  });
});
