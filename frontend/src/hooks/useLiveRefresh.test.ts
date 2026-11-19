/**
 * `useLiveRefresh` (ADR-073 decisions 6 and 8): a page refetches on a hint for
 * one of its topics, on a reconnect, and when shown again, once per burst.
 */
import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { emitLiveHint } from "@/lib/live";
import { LIVE_COALESCE_MS, useLiveRefresh } from "./useLiveRefresh";

beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

describe("useLiveRefresh", () => {
  it("reloads on a hint for one of its topics, and not for another's", () => {
    const reload = vi.fn();
    renderHook(() => useLiveRefresh(["reviews"], reload));

    act(() => { emitLiveHint(["library"]); vi.advanceTimersByTime(LIVE_COALESCE_MS); });
    expect(reload).not.toHaveBeenCalled();

    act(() => { emitLiveHint(["reviews", "record:4"]); vi.advanceTimersByTime(LIVE_COALESCE_MS); });
    expect(reload).toHaveBeenCalledTimes(1);
  });

  it("reloads once for a burst of hints", () => {
    const reload = vi.fn();
    renderHook(() => useLiveRefresh(["queues"], reload));

    act(() => {
      for (let i = 0; i < 5; i++) emitLiveHint(["queues"]);
      vi.advanceTimersByTime(LIVE_COALESCE_MS);
    });
    expect(reload).toHaveBeenCalledTimes(1);
  });

  it("reloads when the tab is shown again", () => {
    const reload = vi.fn();
    renderHook(() => useLiveRefresh(["reviews"], reload));

    act(() => { window.dispatchEvent(new Event("focus")); vi.advanceTimersByTime(LIVE_COALESCE_MS); });
    expect(reload).toHaveBeenCalledTimes(1);
  });

  it("does nothing when disabled or unmounted", () => {
    const reload = vi.fn();
    const { rerender, unmount } = renderHook(({ on }) => useLiveRefresh(["reviews"], reload, on), {
      initialProps: { on: false },
    });
    act(() => { emitLiveHint(["reviews"]); vi.advanceTimersByTime(LIVE_COALESCE_MS); });
    expect(reload).not.toHaveBeenCalled();

    rerender({ on: true });
    unmount();
    act(() => { emitLiveHint(["reviews"]); vi.advanceTimersByTime(LIVE_COALESCE_MS); });
    expect(reload).not.toHaveBeenCalled();
  });

  it("calls the latest reload, not the one from the first render", () => {
    const first = vi.fn();
    const second = vi.fn();
    const { rerender } = renderHook(({ fn }) => useLiveRefresh(["reviews"], fn), { initialProps: { fn: first } });
    rerender({ fn: second });

    act(() => { emitLiveHint(["reviews"]); vi.advanceTimersByTime(LIVE_COALESCE_MS); });
    expect(first).not.toHaveBeenCalled();
    expect(second).toHaveBeenCalledTimes(1);
  });
});
