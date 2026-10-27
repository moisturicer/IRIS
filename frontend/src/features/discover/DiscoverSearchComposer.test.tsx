/** Discover's search box filters the catalogue as the reader types. */
import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { act, renderScreen, screen, userEvent } from "@/test/render";

import { DiscoverSearchComposer } from "./DiscoverSearchComposer";

function Harness() {
  const [value, setValue] = useState("");
  return <DiscoverSearchComposer value={value} onChange={setValue} />;
}

function renderDiscover() {
  return renderScreen(<Harness />);
}

describe("Discover search composer", () => {
  afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals(); });

  it("rotates whole example questions while empty and pauses while typing", () => {
    vi.useFakeTimers();
    const { rerender } = renderScreen(<DiscoverSearchComposer value="" onChange={() => {}} />);
    expect(screen.getByText("What research explores flood resilience in Cebu?")).toBeInTheDocument();
    act(() => { vi.advanceTimersByTime(3600); });
    expect(screen.getByText("What research explores flood resilience in Cebu?")).toHaveClass("opacity-0");
    act(() => { vi.advanceTimersByTime(180); });
    expect(screen.getByText("How can AI support learning at CIT-U?")).toHaveClass("opacity-100");
    rerender(<DiscoverSearchComposer value="flood" onChange={() => {}} />);
    expect(screen.queryByText("How can AI support learning at CIT-U?")).not.toBeInTheDocument();
    act(() => { vi.advanceTimersByTime(8000); });
    rerender(<DiscoverSearchComposer value="" onChange={() => {}} />);
    expect(screen.getByText("How can AI support learning at CIT-U?")).toBeInTheDocument();
  });

  it("keeps the example static when reduced motion is preferred", () => {
    vi.useFakeTimers();
    vi.stubGlobal("matchMedia", vi.fn(() => ({ matches: true, addEventListener: vi.fn(), removeEventListener: vi.fn() })));
    renderDiscover();
    act(() => { vi.advanceTimersByTime(12000); });
    expect(screen.getByText("What research explores flood resilience in Cebu?")).toHaveClass("opacity-100");
  });

  it("offers catalogue search without a competing action", () => {
    renderDiscover();

    expect(screen.getByRole("textbox", { name: /search records/i })).toBeTruthy();
    expect(screen.queryByRole("button", { name: /ask iris about this/i })).not.toBeInTheDocument();
  });

  it("keeps the typed query in the field on Enter", async () => {
    renderDiscover();

    await userEvent.type(screen.getByRole("textbox", { name: /search records/i }), "edge AI{Enter}");

    expect(screen.getByRole("textbox", { name: /search records/i })).toHaveValue("edge AI");
  });
});
