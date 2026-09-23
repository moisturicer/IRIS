import { describe, expect, it, vi } from "vitest";

import { fireEvent, renderScreen, screen } from "@/test/render";

import { ResponseStyleSelect } from "./ResponseStyleSelect";

describe("ResponseStyleSelect", () => {
  it("shows the current style and reports a change", () => {
    const onChange = vi.fn();
    renderScreen(<ResponseStyleSelect value="balanced" onChange={onChange} />);

    const select = screen.getByLabelText("Answer style") as HTMLSelectElement;
    expect(select.value).toBe("balanced");

    fireEvent.change(select, { target: { value: "thorough" } });
    expect(onChange).toHaveBeenCalledWith("thorough");
  });

  it("offers concise, balanced and thorough, nothing else", () => {
    renderScreen(<ResponseStyleSelect value="concise" onChange={vi.fn()} />);

    const select = screen.getByLabelText("Answer style") as HTMLSelectElement;
    const values = Array.from(select.options).map((o) => o.value);
    expect(values).toEqual(["concise", "balanced", "thorough"]);
  });

  it("is disabled while a question is in flight", () => {
    renderScreen(<ResponseStyleSelect value="balanced" onChange={vi.fn()} disabled />);
    expect(screen.getByLabelText("Answer style")).toBeDisabled();
  });
});
