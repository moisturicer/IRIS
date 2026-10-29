/**
 * "Related published research" on the owner's own Proposal (IR-312).
 *
 * The Novelty check of ADR-029 §2, shown where amendment item 9 puts it. The
 * figure is visible so a proposer can tell a near-duplicate from a loose
 * overlap, and an empty result says plainly that nothing close was found.
 *
 * Every query goes through the accessible tree, by role and accessible name.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";

import { expectNoBlockingA11yViolations } from "@/test/axe";
import { renderScreen, screen } from "@/test/render";
import type { SemanticSearchResult } from "@/types/ai";

import { RelatedPublishedResearch } from "./RelatedPublishedResearch";

const match = {
  id: 41,
  title: "Rainfall gauge networks for catchment flooding",
  year: 2023,
  classification: "Engineering",
  score: 0.8731,
} as SemanticSearchResult;

const relatedResearch = vi.fn();
vi.mock("@/api/records", () => ({
  recordsApi: {
    relatedResearch: (...args: unknown[]) => relatedResearch(...(args as [])),
  },
}));

describe("RelatedPublishedResearch", () => {
  beforeEach(() => {
    relatedResearch.mockReset();
  });

  it("lists each close published record as a link, with its similarity", async () => {
    relatedResearch.mockResolvedValue({ data: { checked: true, results: [match], threshold: 0.7 } });

    const { container } = renderScreen(<RelatedPublishedResearch recordId={7} />);

    const link = await screen.findByRole("link", { name: /Rainfall gauge networks/ });
    expect(link).toHaveAttribute("href", "/records/41");
    expect(screen.getByText("87% similar")).toBeInTheDocument();
    expect(relatedResearch).toHaveBeenCalledWith(7);
    await expectNoBlockingA11yViolations(container);
  });

  it("says nothing close was found rather than showing a weak match", async () => {
    relatedResearch.mockResolvedValue({ data: { checked: true, results: [], threshold: 0.7 } });

    renderScreen(<RelatedPublishedResearch recordId={7} />);

    expect(
      await screen.findByText(/No published research here is 70% or more similar/),
    ).toBeInTheDocument();
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
  });

  it("says the proposal has not been compared yet, rather than claiming nothing is close", async () => {
    relatedResearch.mockResolvedValue({ data: { checked: false, results: [], threshold: 0.7 } });

    renderScreen(<RelatedPublishedResearch recordId={7} />);

    expect(await screen.findByText(/has not been compared yet/)).toBeInTheDocument();
    expect(screen.queryByText(/No published research here/)).not.toBeInTheDocument();
  });

  it("says the check could not run, rather than claiming nothing is close", async () => {
    relatedResearch.mockRejectedValue(new Error("network"));

    renderScreen(<RelatedPublishedResearch recordId={7} />);

    expect(await screen.findByText(/could not be checked right now/)).toBeInTheDocument();
    expect(
      screen.queryByText(/No published research here is close/),
    ).not.toBeInTheDocument();
  });
});
