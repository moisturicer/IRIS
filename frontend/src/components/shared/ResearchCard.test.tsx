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

  it("is one tab stop for the card, then its own controls, and the focus ring outlines the whole card (IR-1095)", async () => {
    renderScreen(fullCard("grid"));
    const card = screen.getByRole("article", { name: TITLE });

    // The title is the only link: Tab reaches the card once, then the Cite button.
    expect(within(card).getAllByRole("link")).toHaveLength(1);
    await userEvent.tab();
    const title = within(card).getByRole("link", { name: TITLE });
    expect(title).toHaveFocus();
    await userEvent.tab();
    expect(within(card).getByRole("button", { name: "Cite" })).toHaveFocus();

    // The ring is drawn by the link's stretched ::after, which covers the card;
    // the title's own text no longer carries a second ring. jsdom cannot paint,
    // so this checks the classes that do.
    expect(title.className).toContain("focus-visible:after:ring-2");
    expect(title.className).toContain("after:inset-0");
    expect(title.className).not.toMatch(/(^|\s)focus-visible:ring-2/);
  });

  it("shows a caller's marked-up title in the link and keeps the plain title as its name", () => {
    renderScreen(<ResearchCard href="/records/7" title="Rainfall and Dengue" titleContent={<>Rainfall and <mark>Dengue</mark></>} />);

    const link = screen.getByRole("link", { name: "Rainfall and Dengue" });
    expect(link.querySelector("mark")).toHaveTextContent("Dengue");
    expect(screen.getByRole("article", { name: "Rainfall and Dengue" })).toBeInTheDocument();
  });

  it("renders a bare record, title only, without empty slots", async () => {
    const { container } = renderScreen(<ResearchCard href="/records/7" title="Untitled draft" />);

    const card = screen.getByRole("article", { name: "Untitled draft" });
    expect(within(card).queryByText(/next step/i)).not.toBeInTheDocument();
    await expectNoBlockingA11yViolations(container);
  });
});
