/**
 * `useFocusRefresh` (ADR-073 amendment 2026-11-28, IR-1351): a page refetches
 * when the tab is shown again, once per burst, and never on a live hint.
 */
import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { emitLiveHint } from "@/lib/live";
import { REFRESH_COALESCE_MS, useFocusRefresh } from "./useFocusRefresh";
import { useLiveRefresh } from "./useLiveRefresh";

beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

function setVisibility(state: DocumentVisibilityState) {
  Object.defineProperty(document, "visibilityState", { configurable: true, get: () => state });
}

afterEach(() => setVisibility("visible"));

describe("useFocusRefresh", () => {
  it("reloads when the window gains focus", () => {
    const reload = vi.fn();
    renderHook(() => useFocusRefresh(reload));

    act(() => { window.dispatchEvent(new Event("focus")); vi.advanceTimersByTime(REFRESH_COALESCE_MS); });
    expect(reload).toHaveBeenCalledTimes(1);
  });

  it("reloads when the page becomes visible, and not when it is hidden", () => {
    const reload = vi.fn();
    renderHook(() => useFocusRefresh(reload));

    setVisibility("hidden");
    act(() => { document.dispatchEvent(new Event("visibilitychange")); vi.advanceTimersByTime(REFRESH_COALESCE_MS); });
    expect(reload).not.toHaveBeenCalled();

    setVisibility("visible");
    act(() => { document.dispatchEvent(new Event("visibilitychange")); vi.advanceTimersByTime(REFRESH_COALESCE_MS); });
    expect(reload).toHaveBeenCalledTimes(1);
  });

  it("reloads once when focus and visibility arrive together", () => {
    const reload = vi.fn();
    renderHook(() => useFocusRefresh(reload));

    act(() => {
      document.dispatchEvent(new Event("visibilitychange"));
      window.dispatchEvent(new Event("focus"));
      vi.advanceTimersByTime(REFRESH_COALESCE_MS);
    });
    expect(reload).toHaveBeenCalledTimes(1);
  });

  it("ignores live hints of every topic", () => {
    const reload = vi.fn();
    renderHook(() => useFocusRefresh(reload));

    act(() => { emitLiveHint(["queues", "reviews", "library", "record:4"]); vi.advanceTimersByTime(REFRESH_COALESCE_MS); });
    expect(reload).not.toHaveBeenCalled();
  });

  it("does nothing when disabled, and drops a pending reload when disabled or unmounted", () => {
    const reload = vi.fn();
    const { rerender, unmount } = renderHook(({ on }) => useFocusRefresh(reload, on), { initialProps: { on: false } });
    act(() => { window.dispatchEvent(new Event("focus")); vi.advanceTimersByTime(REFRESH_COALESCE_MS); });
    expect(reload).not.toHaveBeenCalled();

    rerender({ on: true });
    act(() => { window.dispatchEvent(new Event("focus")); });
    rerender({ on: false });
    act(() => { vi.advanceTimersByTime(REFRESH_COALESCE_MS); });
    expect(reload).not.toHaveBeenCalled();

    rerender({ on: true });
    act(() => { window.dispatchEvent(new Event("focus")); });
    unmount();
    act(() => { vi.advanceTimersByTime(REFRESH_COALESCE_MS); });
    expect(reload).not.toHaveBeenCalled();
  });

  it("calls the latest reload, not the one from the first render", () => {
    const first = vi.fn();
    const second = vi.fn();
    const { rerender } = renderHook(({ fn }) => useFocusRefresh(fn), { initialProps: { fn: first } });
    rerender({ fn: second });

    act(() => { window.dispatchEvent(new Event("focus")); vi.advanceTimersByTime(REFRESH_COALESCE_MS); });
    expect(first).not.toHaveBeenCalled();
    expect(second).toHaveBeenCalledTimes(1);
  });
});

describe("useLiveRefresh on top of it", () => {
  it("reloads once when a hint and the tab being shown arrive together", () => {
    const reload = vi.fn();
    renderHook(() => useLiveRefresh(["reviews"], reload));

    act(() => {
      emitLiveHint(["reviews"]);
      window.dispatchEvent(new Event("focus"));
      vi.advanceTimersByTime(REFRESH_COALESCE_MS);
    });
    expect(reload).toHaveBeenCalledTimes(1);
  });
});
