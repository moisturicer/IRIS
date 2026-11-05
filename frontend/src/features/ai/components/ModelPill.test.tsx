import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { expectNoBlockingA11yViolations } from "@/test/axe";
import { renderScreen, screen } from "@/test/render";

import { ModelPill } from "./ModelPill";

const options = [
  { value: "a", short: "Alpha", label: "Alpha run", description: "First", icon: "fas fa-plus" },
  { value: "b", short: "Beta", label: "Beta run", description: "Second", icon: "fas fa-plus" },
] as const;

describe("the composer's setting pill", () => {
  it("names its current choice, and reports a new one", async () => {
    const onChange = vi.fn();
    const { container } = renderScreen(<ModelPill name="Depth" value="a" options={options} onChange={onChange} note="A note" />);

    await userEvent.click(screen.getByRole("button", { name: "Depth: Alpha" }));
    expect(screen.getByRole("menuitemradio", { name: /Alpha run/ })).toBeChecked();
    expect(screen.getByText("A note")).toBeInTheDocument();
    await expectNoBlockingA11yViolations(container);

    await userEvent.click(screen.getByRole("menuitemradio", { name: /Beta run/ }));
    expect(onChange).toHaveBeenCalledExactlyOnceWith("b");
    expect(screen.queryByRole("menu")).toBeNull();
  });

  it("moves by arrow key, and Escape returns focus to the pill", async () => {
    renderScreen(<ModelPill name="Depth" value="a" options={options} />);
    const pill = screen.getByRole("button", { name: "Depth: Alpha" });

    await userEvent.click(pill);
    expect(screen.getByRole("menuitemradio", { name: /Alpha run/ })).toHaveFocus();
    await userEvent.keyboard("{ArrowDown}");
    expect(screen.getByRole("menuitemradio", { name: /Beta run/ })).toHaveFocus();
    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("menu")).toBeNull();
    expect(pill).toHaveFocus();
  });

  it("closes when the reader presses outside it", async () => {
    renderScreen(<div><ModelPill name="Depth" value="a" options={options} /><button type="button">Elsewhere</button></div>);

    await userEvent.click(screen.getByRole("button", { name: "Depth: Alpha" }));
    await userEvent.click(screen.getByRole("button", { name: "Elsewhere" }));
    expect(screen.queryByRole("menu")).toBeNull();
  });
});
