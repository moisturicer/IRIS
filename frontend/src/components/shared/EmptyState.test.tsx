/**
 * The shared empty state (IR-405). Discover kept a private copy because the
 * shared one had no way to offer a next step; this one carries an action slot
 * and an error tone, so there is one empty state again.
 */
import { describe, expect, it, vi } from "vitest";

import { expectNoBlockingA11yViolations } from "@/test/axe";
import { renderScreen, screen, userEvent } from "@/test/render";

import { EmptyState } from "./EmptyState";

describe("EmptyState", () => {
  it("names the empty state with a heading and explains it", async () => {
    const { container } = renderScreen(
      <EmptyState title="No research papers found" message="Nothing has been published yet." />,
    );

    expect(screen.getByRole("heading", { name: "No research papers found" })).toBeInTheDocument();
    expect(screen.getByText("Nothing has been published yet.")).toBeInTheDocument();
    await expectNoBlockingA11yViolations(container);
  });

  it("offers the next step through its action slot", async () => {
    const onReset = vi.fn();
    renderScreen(
      <EmptyState
        title="No research papers found"
        action={<button type="button" onClick={onReset}>Reset all filters</button>}
      />,
    );

    await userEvent.click(screen.getByRole("button", { name: "Reset all filters" }));

    expect(onReset).toHaveBeenCalledOnce();
  });

  it("announces an error state, and only an error state", async () => {
    const { container, rerender } = renderScreen(
      <EmptyState tone="error" title="Something went wrong" message="The server did not answer." />,
    );

    expect(screen.getByRole("alert")).toHaveTextContent("Something went wrong");
    expect(screen.getByRole("alert")).toHaveTextContent("The server did not answer.");
    await expectNoBlockingA11yViolations(container);

    rerender(<EmptyState title="No notifications yet." />);

    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  // A structural query on purpose, as in Button.test.tsx: whether a glyph is
  // hidden is exactly what the accessibility tree cannot show.
  it("keeps its icon out of the accessibility tree", () => {
    const { container } = renderScreen(<EmptyState icon="fa-bell-slash" title="No notifications yet." />);

    expect(container.querySelector("i.fa-bell-slash")).toHaveAttribute("aria-hidden", "true");
  });
});
