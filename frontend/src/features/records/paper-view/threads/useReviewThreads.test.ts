/**
 * `useReviewThreads` live (ADR-073, IR-1284): the review discussion is read
 * again on a `record:<id>` hint and on focus, quietly -- a failed quiet read
 * keeps what is shown.
 */
import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { LIVE_COALESCE_MS } from "@/hooks/useLiveRefresh";
import { emitLiveHint } from "@/lib/live";
import type { ReviewComment } from "@/types/records";

import { useReviewThreads } from "./useReviewThreads";

const api = vi.hoisted(() => ({ reviewComments: vi.fn() }));
vi.mock("@/api/records", () => ({ recordsApi: api }));
const reviewComments = api.reviewComments;

function answer(rows: Partial<ReviewComment>[]) {
  return Promise.resolve({ data: rows as ReviewComment[] });
}

async function settle() {
  await act(async () => { await Promise.resolve(); await Promise.resolve(); await Promise.resolve(); });
}

async function hint(topics: string[]) {
  act(() => { emitLiveHint(topics); vi.advanceTimersByTime(LIVE_COALESCE_MS); });
  await settle();
}

beforeEach(() => {
  vi.useFakeTimers();
  reviewComments.mockReset();
});
afterEach(() => vi.useRealTimers());

describe("useReviewThreads, live", () => {
  it("reads the discussion again on a hint for its record, and not for another", async () => {
    reviewComments.mockReturnValue(answer([]));
    renderHook(() => useReviewThreads(7, true));
    await settle();
    expect(reviewComments).toHaveBeenCalledTimes(1);

    await hint(["record:8"]);
    expect(reviewComments).toHaveBeenCalledTimes(1);

    await hint(["record:7"]);
    expect(reviewComments).toHaveBeenCalledTimes(2);
    expect(reviewComments).toHaveBeenLastCalledWith(7);
  });

  it("reads it again when the tab is shown", async () => {
    reviewComments.mockReturnValue(answer([]));
    renderHook(() => useReviewThreads(7, true));
    await settle();

    act(() => { window.dispatchEvent(new Event("focus")); vi.advanceTimersByTime(LIVE_COALESCE_MS); });
    await settle();
    expect(reviewComments).toHaveBeenCalledTimes(2);
  });

  it("keeps what it shows when a quiet read fails", async () => {
    reviewComments.mockReturnValueOnce(answer([]));
    const { result } = renderHook(() => useReviewThreads(7, true));
    await settle();
    expect(result.current.loaded).toBe(true);

    reviewComments.mockReturnValueOnce(Promise.reject(new Error("offline")));
    await hint(["record:7"]);
    expect(reviewComments).toHaveBeenCalledTimes(2);
    expect(result.current.failed).toBe(false);
    expect(result.current.loaded).toBe(true);
  });

  it("does not listen while disabled", async () => {
    reviewComments.mockReturnValue(answer([]));
    renderHook(() => useReviewThreads(7, false));
    await hint(["record:7"]);
    expect(reviewComments).not.toHaveBeenCalled();
  });
});
