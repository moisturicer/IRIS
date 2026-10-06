/**
 * One card for a research record (IR-405; spec §4.12). It will replace four
 * renderings: Discover's card, My Library's rows, My Workspace's case card and
 * the review queue's rows. It shows what the caller gives it. It fetches
 * nothing, decides nothing about permissions, and words no status itself:
 * status wording always comes from the server.
 */
import { describe, expect, it, vi } from "vitest";

import { expectNoBlockingA11yViolations } from "@/test/axe";
import { renderScreen, screen, userEvent, within } from "@/test/render";

import { ResearchCard } from "./ResearchCard";

const TITLE = "Predicting flood risk in Cebu with satellite rainfall data";

function fullCard(layout: "list" | "grid", onCite = vi.fn()) {
  return (
    <ResearchCard
      layout={layout}
      href="/records/41"
      title={TITLE}
      eyebrow="Environmental Science · Thesis / Research"
      meta="2026"
      byline="Ana Cruz, Ben Reyes"
      summary="We combine GPM rainfall estimates with drainage maps to forecast flooding."
      status={<span>In review</span>}
      nextStep="Upload the ethics clearance IERC asked for"
      actions={
        <button type="button" onClick={onCite}>
          Cite
        </button>
      }
      footer={<span>12 views</span>}
    />
  );
}

describe("ResearchCard", () => {
  it.each(["list", "grid"] as const)("in the %s layout, is an article named by its title", async (layout) => {
    const { container } = renderScreen(fullCard(layout));

    const card = screen.getByRole("article", { name: TITLE });
    expect(within(card).getByRole("link", { name: TITLE })).toHaveAttribute("href", "/records/41");
    await expectNoBlockingA11yViolations(container);
  });

  it("shows every slot it is given", () => {
    renderScreen(fullCard("list"));
    const card = screen.getByRole("article", { name: TITLE });

    for (const text of [
      "Environmental Science · Thesis / Research",
      "2026",
      "Ana Cruz, Ben Reyes",
      "We combine GPM rainfall estimates with drainage maps to forecast flooding.",
      "In review",
      "12 views",
    ]) {
      expect(within(card).getByText(text)).toBeInTheDocument();
    }
  });

  it("labels the next step as one", () => {
    renderScreen(fullCard("list"));

    expect(screen.getByRole("article", { name: TITLE })).toHaveTextContent(
      "Next step: Upload the ethics clearance IERC asked for",
    );
  });

  it("keeps its actions separate controls from the title link", async () => {
    const onCite = vi.fn();
    renderScreen(fullCard("grid", onCite));

    await userEvent.click(screen.getByRole("button", { name: "Cite" }));

    expect(onCite).toHaveBeenCalledOnce();
  });

  it("renders a bare record, title only, without empty slots", async () => {
    const { container } = renderScreen(<ResearchCard href="/records/7" title="Untitled draft" />);

    const card = screen.getByRole("article", { name: "Untitled draft" });
    expect(within(card).queryByText(/next step/i)).not.toBeInTheDocument();
    await expectNoBlockingA11yViolations(container);
  });
});
