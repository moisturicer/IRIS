/**
 * The AI overview on a paper, and what it lets a reader verify (IR-284).
 *
 * The overview is a summary of one paper written by a model, which is exactly
 * the kind of text a reader should be able to check rather than trust. So the
 * assertions are about the checking: the quote is shown, the page is named,
 * and the link goes to that page.
 *
 * Every query goes through the accessible tree, by role and accessible name.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";

import { expectNoBlockingA11yViolations } from "@/test/axe";
import { renderScreen, screen, waitFor } from "@/test/render";
import type { AIAnswer, Citation } from "@/types/ai";
import type { RecordDetail } from "@/types/records";

import { PaperAiOverview } from "./PaperAiOverview";

const QUOTE = "the network reduced mean absolute error by twelve per cent over the baseline";

const citation: Citation = {
  marker:       1,
  chunk_id:     11,
  record_id:    7,
  record_title: "Flood Prediction in the Mananga Catchment",
  page:         12,
  text:         QUOTE,
  context_path: ["Flood Prediction in the Mananga Catchment", "Results"],
};

function answer(overrides: Partial<AIAnswer> = {}): AIAnswer {
  return {
    answer:    "The work trains a convolutional network on gauge data [1].",
    citations: [citation],
    sources:   [],
    message:   null,
    mode:      "generative",
    degraded:  false,
    ...overrides,
  };
}

const ask = vi.fn(() => Promise.resolve({ data: answer() }));
vi.mock("@/api/ai", () => ({
  aiApi: {
    ask: (...args: unknown[]) => ask(...(args as [])),
  },
}));

/** Only the title is read by this component; the rest of a record is noise here. */
const record = { id: 7, title: "Flood Prediction in the Mananga Catchment" } as RecordDetail;

beforeEach(() => {
  vi.clearAllMocks();
  ask.mockResolvedValue({ data: answer() });
});

describe("the AI overview on a paper", () => {
  it("quotes the passage behind the summary", async () => {
    renderScreen(<PaperAiOverview record={record} />);

    const quote = await screen.findByRole("blockquote");
    expect(quote.textContent).toBe(QUOTE);
  });

  it("offers the cited page as the way into the paper", async () => {
    renderScreen(<PaperAiOverview record={record} />);

    const link = await screen.findByRole("link", { name: /at page 12/i });
    expect(link.getAttribute("href")).toBe("/records/7?page=12");
  });

  it("says when the summary came from the degraded path", async () => {
    ask.mockResolvedValue({ data: answer({ degraded: true }) });
    renderScreen(<PaperAiOverview record={record} />);

    expect(await screen.findByText(/keyword matching, not meaning/i)).toBeTruthy();
  });

  it("summarises nothing when no model was reachable", async () => {
    ask.mockResolvedValue({
      data: answer({ answer: null, citations: [], mode: "unavailable", message: "no model" }),
    });
    renderScreen(<PaperAiOverview record={record} />);

    expect(await screen.findByText(/AI summary unavailable/i)).toBeTruthy();
    expect(screen.queryByText(QUOTE)).toBeNull();
  });

  it("reports a failure rather than showing an empty summary", async () => {
    ask.mockRejectedValue(new Error("network"));
    renderScreen(<PaperAiOverview record={record} />);

    expect(await screen.findByText(/AI overview unavailable/i)).toBeTruthy();
    expect(screen.getByRole("button", { name: /Try again/i })).toBeTruthy();
  });

  it("still names what it read when the model cited nothing", async () => {
    // A generative answer whose markers did not parse has sources and no
    // citations. It was still grounded in something, and saying so is more
    // honest than showing a summary with no provenance at all.
    ask.mockResolvedValue({
      data: answer({
        citations: [],
        sources: [
          {
            id: 7,
            title: "Flood Prediction in the Mananga Catchment",
            abstract: "",
            authors: "R. Dela Cruz",
            year: 2025,
            classification: null,
            score: 0.7,
          },
        ],
      }),
    });
    renderScreen(<PaperAiOverview record={record} />);

    const link = await screen.findByRole("link", {
      name: /Flood Prediction in the Mananga Catchment/i,
    });
    expect(link.getAttribute("href")).toBe("/records/7");
  });

  it("has no serious or critical accessibility violations", async () => {
    const { container } = renderScreen(<PaperAiOverview record={record} />);

    await waitFor(() => expect(screen.getByText(QUOTE)).toBeTruthy());
    await expectNoBlockingA11yViolations(container);
  });
});
