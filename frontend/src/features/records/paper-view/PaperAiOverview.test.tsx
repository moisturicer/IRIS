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
import { act, renderScreen, screen, userEvent, waitFor } from "@/test/render";
import type { Citation, RecordOverviewResponse } from "@/types/ai";
import type { RecordDetail } from "@/types/records";

import { PaperAiOverview } from "./PaperAiOverview";

// An overview's marker is the page it cites (IR-434).
const citation: Citation = {
  marker:       12,
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
      text: "## Methodology\n\nThe work trains a convolutional network on gauge data [12].",
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

  it("explains that generation is pending and polls until the overview is ready", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    overview
      .mockResolvedValueOnce({ data: { state: "generating", overview: null } })
      .mockResolvedValueOnce({ data: response() });
    try {
      renderScreen(<PaperAiOverview record={record} />);

      expect(await screen.findByRole("status")).toHaveTextContent(/being prepared/i);
      await act(async () => {
        vi.advanceTimersByTime(2500);
      });

      expect(await screen.findByRole("heading", { level: 2, name: "Methodology" })).toBeTruthy();
      expect(overview).toHaveBeenCalledTimes(2);
    } finally {
      vi.useRealTimers();
    }
  });

  it("renders the summary as markdown", async () => {
    renderScreen(<PaperAiOverview record={record} />);

    expect(await screen.findByRole("heading", { level: 2, name: "Methodology" })).toBeTruthy();
  });

  it("sits on the page under a heading, with no card around it (IR-569)", async () => {
    renderScreen(<PaperAiOverview record={record} />);

    const heading = await screen.findByRole("heading", { level: 2, name: "AI Overview" });
    const section = heading.closest("section");
    expect(section).not.toBeNull();
    for (const card of ["bg-white", "ring-1", "rounded-2xl", "shadow-card", "border-t-2"]) {
      expect(section).not.toHaveClass(card);
    }
  });

  it("carries no label about how it was made (IR-569)", async () => {
    renderScreen(<PaperAiOverview record={record} />);
    await screen.findByRole("heading", { level: 2, name: "Methodology" });

    expect(screen.queryByText(/RAG-indexed/i)).not.toBeInTheDocument();
  });

  it("copies the overview as prose, without its page markers, and says so", async () => {
    const writeText = vi.fn(() => Promise.resolve());
    Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
    renderScreen(<PaperAiOverview record={record} />);

    await userEvent.click(await screen.findByRole("button", { name: "Copy" }));

    expect(writeText).toHaveBeenCalledWith("## Methodology\n\nThe work trains a convolutional network on gauge data.");
    expect(await screen.findByRole("button", { name: "Copied" })).toBeInTheDocument();
  });

  it("says when it could not copy, rather than failing silently", async () => {
    Object.defineProperty(navigator, "clipboard", {
      value: { writeText: vi.fn(() => Promise.reject(new Error("no permission"))) },
      configurable: true,
    });
    renderScreen(<PaperAiOverview record={record} />);

    await userEvent.click(await screen.findByRole("button", { name: "Copy" }));

    expect(await screen.findByRole("button", { name: /couldn.t copy/i })).toBeInTheDocument();
  });

  it("names a cited page as the page, 'p12'", async () => {
    renderScreen(<PaperAiOverview record={record} />);

    expect((await screen.findByRole("link", { name: /at page 12/i })).textContent).toBe("p12");
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
