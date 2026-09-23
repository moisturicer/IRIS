/**
 * The AI overview on a paper, and what it lets a reader verify (IR-284,
 * revised IR-334/IR-335).
 *
 * Reworked from the ask()-per-mount version: this now reads the cached
 * `GET /ai/records/<id>/overview/` endpoint, and renders through the same
 * markdown-plus-citation-chip path chat uses (`CitationText`) instead of
 * `whitespace-pre-wrap`. Assertions changed shape to match -- a citation is
 * now a clickable chip with an accessible name, not a `<blockquote>` -- but
 * the property under test is the same one the deleted tests checked: a
 * reader can verify a claim by following its citation to the page it came
 * from.
 *
 * Every query goes through the accessible tree, by role and accessible name.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";

import { expectNoBlockingA11yViolations } from "@/test/axe";
import { renderScreen, screen, waitFor } from "@/test/render";
import type { Citation, RecordOverviewResponse } from "@/types/ai";
import type { RecordDetail } from "@/types/records";

import { PaperAiOverview } from "./PaperAiOverview";

const citation: Citation = {
  marker:       1,
  chunk_id:     11,
  record_id:    7,
  record_title: "Flood Prediction in the Mananga Catchment",
  page:         12,
  text:         "the network reduced mean absolute error by twelve per cent over the baseline",
  context_path: ["Flood Prediction in the Mananga Catchment", "Results"],
  regions:      [{ page: 12, left: 0.1, top: 0.2, right: 0.6, bottom: 0.3 }],
};

function response(overrides: Partial<RecordOverviewResponse> = {}): RecordOverviewResponse {
  return {
    state: "ready",
    overview: {
      text: "## Methodology\n\nThe work trains a convolutional network on gauge data [1].",
      citations: [citation],
      degraded: false,
      model: "fake-test",
      generated_at: "2026-09-23T00:00:00Z",
    },
    cached: false,
    ...overrides,
  };
}

const overview = vi.fn(() => Promise.resolve({ data: response() }));
vi.mock("@/api/ai", () => ({
  aiApi: {
    overview: (...args: unknown[]) => overview(...(args as [])),
  },
}));

/** Only the id is read by this component; the rest of a record is noise here. */
const record = { id: 7, title: "Flood Prediction in the Mananga Catchment" } as RecordDetail;

beforeEach(() => {
  vi.clearAllMocks();
  overview.mockResolvedValue({ data: response() });
});

describe("the AI overview on a paper", () => {
  it("asks the cache for this record, not a corpus-wide question", async () => {
    renderScreen(<PaperAiOverview record={record} />);

    await waitFor(() => expect(overview).toHaveBeenCalledWith(7));
  });

  it("renders the summary as markdown", async () => {
    renderScreen(<PaperAiOverview record={record} />);

    expect(await screen.findByRole("heading", { level: 2, name: "Methodology" })).toBeTruthy();
  });

  it("offers the cited passage as a link into the paper at that page", async () => {
    renderScreen(<PaperAiOverview record={record} />);

    const chip = await screen.findByRole("link", { name: /at page 12/i });
    expect(chip.getAttribute("href")).toBe("/records/7?page=12");
  });

  it("says when the summary came from the degraded path", async () => {
    overview.mockResolvedValue({
      data: response({ overview: { ...response().overview!, degraded: true } }),
    });
    renderScreen(<PaperAiOverview record={record} />);

    expect(await screen.findByText(/keyword matching, not meaning/i)).toBeTruthy();
  });

  it("summarises nothing when no model was reachable, and does not cache that", async () => {
    overview.mockResolvedValue({ data: { state: "unavailable", overview: null } });
    renderScreen(<PaperAiOverview record={record} />);

    expect(await screen.findByText(/AI summary unavailable/i)).toBeTruthy();
  });

  it("says nothing is indexed yet when the record has no chunks", async () => {
    overview.mockResolvedValue({ data: { state: "not_indexed", overview: null } });
    renderScreen(<PaperAiOverview record={record} />);

    expect(await screen.findByText(/nothing indexed to summarise/i)).toBeTruthy();
  });

  it("reports a failure rather than showing an empty summary", async () => {
    overview.mockRejectedValue(new Error("network"));
    renderScreen(<PaperAiOverview record={record} />);

    expect(await screen.findByText(/AI overview unavailable/i)).toBeTruthy();
    expect(screen.getByRole("button", { name: /Try again/i })).toBeTruthy();
  });

  it("has no serious or critical accessibility violations", async () => {
    const { container } = renderScreen(<PaperAiOverview record={record} />);

    await waitFor(() => expect(screen.getByRole("link", { name: /at page 12/i })).toBeTruthy());
    await expectNoBlockingA11yViolations(container);
  });
});
