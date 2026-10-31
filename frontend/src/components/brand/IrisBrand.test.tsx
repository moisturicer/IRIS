import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { expectNoBlockingA11yViolations } from "@/test/axe";
import { Spinner } from "@/components/ui/Spinner";
import { AskIrisGlyph, IrisLoader, IrisMark, IrisWordmark, SearchGlyph } from "./IrisBrand";

describe("Folio Ribbon brand marks (IR-744)", () => {
  it("names the mark IRIS when given a title, and hides it when it is decorative", () => {
    render(
      <>
        <IrisMark title="IRIS" />
        <IrisMark />
        <IrisWordmark />
      </>,
    );
    expect(screen.getAllByRole("img")).toHaveLength(1);
    expect(screen.getByRole("img", { name: "IRIS" })).toBeInTheDocument();
  });

  it("announces a labelled loader as a status and stays silent without one", () => {
    const { rerender } = render(<IrisLoader label="Loading papers" />);
    expect(screen.getByRole("status", { name: "Loading papers" })).toBeInTheDocument();
    rerender(<IrisLoader />);
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("lets a page-level Spinner announce what is loading", () => {
    render(<Spinner size="lg" label="Loading sessions" />);
    expect(screen.getByRole("status", { name: "Loading sessions" })).toBeInTheDocument();
  });

  it("keeps a button-sized Spinner silent, beside the verb that names the wait", () => {
    render(<Spinner size="sm" />);
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
  });

  it("names the Ask IRIS and search glyphs only when asked to", () => {
    render(
      <>
        <AskIrisGlyph title="Ask IRIS" answering />
        <SearchGlyph title="Search" />
        <SearchGlyph />
      </>,
    );
    expect(screen.getByRole("img", { name: "Ask IRIS" })).toBeInTheDocument();
    expect(screen.getAllByRole("img", { name: "Search" })).toHaveLength(1);
  });

  it("has no serious accessibility violations", async () => {
    const { container } = render(
      <div>
        <IrisMark title="IRIS" />
        <IrisLoader label="Loading" />
        <AskIrisGlyph title="Ask IRIS" answering />
        <SearchGlyph />
      </div>,
    );
    await expectNoBlockingA11yViolations(container);
  });
});
