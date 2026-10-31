import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { expectNoBlockingA11yViolations } from "@/test/axe";
import { AskIrisGlyph, IrisLoader, IrisLockup, IrisMark, SearchGlyph } from "./IrisBrand";

describe("Folio Ribbon brand marks (IR-744)", () => {
  it("names the mark IRIS when given a title, and hides it when it is decorative", () => {
    const { container } = render(
      <>
        <IrisMark title="IRIS" />
        <IrisMark />
      </>,
    );
    expect(screen.getByRole("img", { name: "IRIS" })).toBeInTheDocument();
    expect(screen.getAllByRole("img")).toHaveLength(1);
    expect(container.querySelectorAll("svg")).toHaveLength(2);
  });

  it("draws the mark from its four ribbon pieces in the current colour", () => {
    const { container } = render(<IrisMark title="IRIS" />);
    const paths = container.querySelectorAll("path");
    expect(paths).toHaveLength(4);
    expect(container.querySelector("svg")).toHaveAttribute("fill", "currentColor");
  });

  it("reads the lockup as one image named IRIS", () => {
    render(<IrisLockup title="IRIS" />);
    expect(screen.getByRole("img", { name: "IRIS" })).toBeInTheDocument();
  });

  it("announces a labelled loader as a status and stays silent without one", () => {
    const { rerender } = render(<IrisLoader label="Loading papers" />);
    expect(screen.getByRole("status", { name: "Loading papers" })).toBeInTheDocument();
    rerender(<IrisLoader />);
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("gives the loader the motion classes that reduced motion turns into a fade", () => {
    const { container } = render(<IrisLoader />);
    expect(container.querySelector("svg")).toHaveClass("iris-loading");
  });

  it("animates the Ask IRIS lines only while answering", () => {
    const { container, rerender } = render(<AskIrisGlyph title="Ask IRIS" />);
    expect(screen.getByRole("img", { name: "Ask IRIS" })).not.toHaveClass("iris-answering");
    rerender(<AskIrisGlyph title="Ask IRIS" answering />);
    expect(container.querySelector("svg")).toHaveClass("iris-answering");
  });

  it("names the search glyph only when asked to", () => {
    render(<SearchGlyph title="Search" />);
    expect(screen.getByRole("img", { name: "Search" })).toBeInTheDocument();
  });

  it("has no serious accessibility violations", async () => {
    const { container } = render(
      <div>
        <IrisLockup title="IRIS" />
        <IrisLoader label="Loading" />
        <AskIrisGlyph title="Ask IRIS" answering />
        <SearchGlyph />
      </div>,
    );
    await expectNoBlockingA11yViolations(container);
  });
});
