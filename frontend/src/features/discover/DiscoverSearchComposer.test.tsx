/**
 * Discover's search box offers two distinct operations (IR-559): the catalogue
 * filter that runs as you type, and an explicit hand-off to Ask IRIS. Typing
 * or pressing Enter must never silently run the second.
 */
import { useState } from "react";
import { describe, expect, it } from "vitest";
import { Route, Routes, useLocation } from "react-router-dom";

import { renderScreen, screen, userEvent } from "@/test/render";

import { DiscoverSearchComposer } from "./DiscoverSearchComposer";

function Harness() {
  const [value, setValue] = useState("");
  return <DiscoverSearchComposer value={value} onChange={setValue} />;
}

function Ask() {
  const { state, search } = useLocation();
  return <output aria-label="ask page">{JSON.stringify({ state, search })}</output>;
}

function renderDiscover() {
  return renderScreen(
    <Routes>
      <Route path="/" element={<Harness />} />
      <Route path="/ai" element={<Ask />} />
    </Routes>,
  );
}

describe("Discover search composer", () => {
  it("offers catalogue search and Ask IRIS as two separate actions", () => {
    renderDiscover();

    expect(screen.getByRole("textbox", { name: /search records/i })).toBeTruthy();
    expect(screen.getByRole("button", { name: /ask iris about this/i })).toBeTruthy();
  });

  it("does not hand off while typing or on Enter", async () => {
    renderDiscover();

    await userEvent.type(screen.getByRole("textbox", { name: /search records/i }), "edge AI{Enter}");

    expect(screen.queryByLabelText("ask page")).toBeNull();
  });

  it("disables Ask IRIS until there is a question", () => {
    renderDiscover();

    expect((screen.getByRole("button", { name: /ask iris about this/i }) as HTMLButtonElement).disabled).toBe(true);
  });

  it("hands the exact question over in route state, not the URL, on explicit Ask", async () => {
    renderDiscover();

    await userEvent.type(screen.getByRole("textbox", { name: /search records/i }), "Who works on edge AI & IoT?");
    await userEvent.click(screen.getByRole("button", { name: /ask iris about this/i }));

    const handed = JSON.parse(screen.getByLabelText("ask page").textContent ?? "{}");
    expect(handed).toEqual({ state: { draft: "Who works on edge AI & IoT?" }, search: "" });
  });
});
