/**
 * A loader draws its placeholder shapes only once a load has taken 400 ms
 * (IR-1314). A fast answer, and above all an empty one, then goes straight to
 * its content or empty state and never flashes the shape of rows it won't have.
 *
 * The shapes are decoration, `aria-hidden`, so they have no role or name to
 * query by; these tests count what sits inside the `aria-hidden` wrapper, as
 * `CitationOverlay.test.tsx` does for its boxes. The label is queried by role.
 */
import { act } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { renderScreen, screen } from "@/test/render";

import { LoadingRegion } from "./LoadingRegion";
import { Skeleton, SkeletonBlock } from "./Skeleton";
import { SHOW_PLACEHOLDER_AFTER_MS, SLOW_AFTER_MS } from "./slowLoad";

beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

const wait = (ms: number) => act(() => { vi.advanceTimersByTime(ms); });

/** The shapes drawn inside the status region's `aria-hidden` wrapper. */
const shapes = () => screen.getByRole("status").querySelectorAll("[aria-hidden='true'] > *").length;

describe.each([
  [
    "LoadingRegion",
    () => (
      <LoadingRegion label="Loading your research…" className="min-h-64 space-y-3">
        <SkeletonBlock className="h-5" />
        <SkeletonBlock className="h-5" />
      </LoadingRegion>
    ),
  ],
  ["Skeleton", () => <Skeleton label="Loading your research…" rows={2} />],
] as const)("%s", (_name, loader) => {
  it("is announced as loading from the first frame", () => {
    renderScreen(loader());
    // Skeleton fills its label one tick after mount, so a screen reader hears a change.
    wait(0);
    expect(screen.getByRole("status")).toHaveTextContent("Loading your research…");
  });

  it("draws no shapes, and takes no room for them, before 400 ms", () => {
    renderScreen(loader());
    wait(SHOW_PLACEHOLDER_AFTER_MS - 1);
    expect(SHOW_PLACEHOLDER_AFTER_MS).toBe(400);
    expect(shapes()).toBe(0);
    // No min-height or padding holds the page open while it is blank.
    expect(screen.getByRole("status").outerHTML).not.toMatch(/min-h-64|p-8/);
  });

  it("draws its shapes once the load has taken 400 ms", () => {
    renderScreen(loader());
    wait(SHOW_PLACEHOLDER_AFTER_MS);
    expect(shapes()).toBe(2);
    expect(screen.getByRole("status")).toHaveTextContent("Loading your research…");
  });

  it("still says it is working at 2 s, counted from mount", () => {
    renderScreen(loader());
    wait(SLOW_AFTER_MS - 1);
    expect(screen.queryByText(/still working/i)).toBeNull();
    wait(1);
    expect(screen.getByText(/still working/i)).toBeVisible();
    expect(shapes()).toBe(2);
  });
});
