/**
 * A quoted Passage renders an equation it contains (IR-429): chunk content
 * carries formulas as `$$...$$` (IR-427), and the citation panel shows it.
 */
import { describe, expect, it } from "vitest";

import { renderScreen, screen } from "@/test/render";

import { PassageQuote } from "./PassageQuote";

describe("a quoted passage", () => {
  it("renders a displayed formula as mathematics", () => {
    const { container } = renderScreen(
      <PassageQuote text={"The loss is\n\n$$\nL = x_i\n$$\n\nwhere x is input."} />,
    );

    expect(screen.getByText("L = x_i", { selector: "annotation" })).toBeTruthy();
    expect(container.querySelector(".katex-display")).not.toBeNull();
    expect(screen.getByText(/The loss is/)).toBeTruthy();
    expect(screen.getByText(/where x is input\./)).toBeTruthy();
  });

  it("leaves text with no formula exactly as written, markdown characters included", () => {
    renderScreen(<PassageQuote text="Costs were $5 and $10, rated *high* # 1." />);

    expect(screen.getByText("Costs were $5 and $10, rated *high* # 1.")).toBeTruthy();
  });

  it("shows unparseable LaTeX as source rather than failing", () => {
    renderScreen(<PassageQuote text={"Bad: $$\n\frac{\n$$"} />);

    expect(screen.getByText(/Bad:/)).toBeTruthy();
  });
});
