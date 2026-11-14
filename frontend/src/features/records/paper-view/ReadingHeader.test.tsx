/**
 * The record bar (IR-569, IR-1092).
 *
 * On a phone Back and the section control share one 56 px row (audit RES-03:
 * the chrome used to take a fifth of the screen), with every control 44 px.
 * jsdom has no layout and does not read the `reading` container, so what is
 * checked is what the markup commits to: no wrapping, the 56 px row, the
 * controls' size classes, and that nothing a screen reader needs goes with the
 * visual labels the phone drops. The 390 / 360 px look is the by-hand check on
 * the PR.
 *
 * Every query goes through the accessible tree, by role and accessible name.
 */
import { describe, expect, it, vi } from "vitest";

import { render, screen } from "@/test/render";

import { CONTROL_SIZE } from "./controls";
import { ReadingHeader } from "./ReadingHeader";

function renderBar(props: Partial<Parameters<typeof ReadingHeader>[0]> = {}) {
  return render(
    <ReadingHeader
      sections={["overview", "paper", "review"]}
      section="paper"
      onSelect={vi.fn()}
      onTabKeyDown={vi.fn()}
      tabId={(s) => `tab-${s}`}
      onBack={vi.fn()}
      title="A study of robot arms"
      version={<span>v2</span>}
      {...props}
    />,
  );
}

/** The bar itself: the tablist's parent. */
const bar = () => screen.getByRole("tablist", { name: "Paper view" }).parentElement as HTMLElement;

describe("the record bar on a phone (IR-1092)", () => {
  it("is one 56 px row that never wraps, at any width", () => {
    renderBar();

    expect(bar()).toHaveClass("h-14", "flex-nowrap");
    expect(bar()).not.toHaveClass("flex-wrap");
  });

  it("gives the section control the room Back and the title leave, in the same row", () => {
    renderBar();

    const tabs = screen.getByRole("tablist", { name: "Paper view" });
    expect(tabs).toHaveClass("flex-1", "min-w-0");
    // Not its own full-width row.
    expect(tabs).not.toHaveClass("w-full");
  });

  it("keeps Back's name when its label is dropped, so only the icon shows on a phone", () => {
    renderBar();

    const back = screen.getByRole("button", { name: "Back" });
    expect(back).toHaveClass("min-w-11");
    expect(back.querySelector("span")).toHaveClass("sr-only", "reading-split:not-sr-only");
  });

  it("does the same for Back to answer, which a citation adds beside Back", () => {
    renderBar({ onBackToAnswer: vi.fn() });

    const toAnswer = screen.getByRole("button", { name: "Back to answer" });
    expect(toAnswer).toHaveClass("min-w-11");
    expect(toAnswer.querySelector("span")).toHaveClass("sr-only", "reading-split:not-sr-only");
  });

  it("keeps the paper's title as the page heading while showing it only from reading-split", () => {
    renderBar();

    const title = screen.getByRole("heading", { level: 1, name: "A study of robot arms" });
    expect(title).toHaveClass("sr-only", "reading-split:not-sr-only");
  });

  it("shows the version beside the title only where there is room for it", () => {
    renderBar();

    expect(screen.getByText("v2").parentElement).toHaveClass("hidden", "reading-split:flex");
  });

  it("makes every section a 44 px touch target that follows the control scale", () => {
    renderBar();

    for (const name of ["Overview", "Paper", "Review"]) {
      const tab = screen.getByRole("tab", { name });
      for (const cls of CONTROL_SIZE.split(" ")) expect(tab).toHaveClass(cls);
    }
  });

  it("keeps the sections reachable and selected as before", () => {
    renderBar({ section: "review" });

    expect(screen.getByRole("tab", { name: "Review", selected: true })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Overview", selected: false })).toBeInTheDocument();
  });
});
