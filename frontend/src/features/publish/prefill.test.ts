/**
 * The prefill's polling (IR-409; spec §4.5 client behaviour).
 *
 * Driven with fake timers, so the 2 s / 5 s / 90 s schedule is asserted as
 * calls made, not as time waited.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, renderHook } from "@testing-library/react";

import { nextPollDelay, usePrefill, type PrefillInput } from "./prefill";

vi.mock("@/api/records", () => ({
  recordsApi: { metadataSuggestions: vi.fn() },
}));

const { recordsApi } = await import("@/api/records");
const fetchSuggestions = vi.mocked(recordsApi.metadataSuggestions);

function reply(state: string, title: string | null = null, abstract: string | null = null) {
  return { data: { state, suggestions: { title, abstract }, source: "pdf_structure" } } as never;
}

/** Let the resolved fetch reach state, then move the clock. */
async function advance(ms: number) {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms);
  });
}

function mount(initial: PrefillInput) {
  return renderHook((props: PrefillInput) => usePrefill(props), { initialProps: initial });
}

beforeEach(() => {
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
  vi.clearAllMocks();
});

describe("nextPollDelay", () => {
  it("is 2 s for the first 20 s, then 5 s", () => {
    expect(nextPollDelay(0)).toBe(2000);
    expect(nextPollDelay(19_999)).toBe(2000);
    expect(nextPollDelay(20_000)).toBe(5000);
    expect(nextPollDelay(60_000)).toBe(5000);
  });

  it("never schedules past 90 s, and stops there", () => {
    expect(nextPollDelay(88_000)).toBe(2000);
    expect(nextPollDelay(90_000)).toBeNull();
    expect(nextPollDelay(120_000)).toBeNull();
  });
});

describe("usePrefill", () => {
  it("asks nothing while inactive or without a record", async () => {
    mount({ recordId: 42, active: false, generation: 0 });
    mount({ recordId: null, active: true, generation: 0 });
    await advance(10_000);

    expect(fetchSuggestions).not.toHaveBeenCalled();
  });

  it("polls every 2 s while pending, then every 5 s after 20 s", async () => {
    fetchSuggestions.mockResolvedValue(reply("pending"));
    const { result } = mount({ recordId: 42, active: true, generation: 0 });

    await advance(0);
    expect(fetchSuggestions).toHaveBeenCalledTimes(1);
    expect(result.current.status).toBe("pending");

    await advance(2000);
    expect(fetchSuggestions).toHaveBeenCalledTimes(2);

    // 0, 2, 4, … 20: eleven calls by the twentieth second.
    await advance(18_000);
    expect(fetchSuggestions).toHaveBeenCalledTimes(11);

    await advance(4999);
    expect(fetchSuggestions).toHaveBeenCalledTimes(11);
    await advance(1);
    expect(fetchSuggestions).toHaveBeenCalledTimes(12);
  });

  it("stops at 90 s and no longer reports pending", async () => {
    fetchSuggestions.mockResolvedValue(reply("pending"));
    const { result } = mount({ recordId: 42, active: true, generation: 0 });

    await advance(90_000);
    const calls = fetchSuggestions.mock.calls.length;
    expect(result.current.status).toBe("expired");

    await advance(60_000);
    expect(fetchSuggestions).toHaveBeenCalledTimes(calls);
  });

  it("stops once the suggestions are ready, and returns them", async () => {
    fetchSuggestions
      .mockResolvedValueOnce(reply("pending"))
      .mockResolvedValueOnce(reply("ready", "A Found Title", null));
    const { result } = mount({ recordId: 42, active: true, generation: 0 });

    await advance(2000);
    expect(result.current).toEqual({ status: "ready", suggestions: { title: "A Found Title", abstract: null } });

    await advance(30_000);
    expect(fetchSuggestions).toHaveBeenCalledTimes(2);
  });

  it.each(["failed", "unsupported"])("stops on %s", async (state) => {
    fetchSuggestions.mockResolvedValue(reply(state));
    const { result } = mount({ recordId: 42, active: true, generation: 0 });

    await advance(30_000);
    expect(result.current.status).toBe(state);
    expect(fetchSuggestions).toHaveBeenCalledTimes(1);
  });

  it("reads a request that fails as failed, never as an error", async () => {
    fetchSuggestions.mockRejectedValue(new Error("network"));
    const { result } = mount({ recordId: 42, active: true, generation: 0 });

    await advance(10_000);
    expect(result.current.status).toBe("failed");
    expect(fetchSuggestions).toHaveBeenCalledTimes(1);
  });

  it("stops when it becomes inactive, and starts again when it is active once more", async () => {
    fetchSuggestions.mockResolvedValue(reply("pending"));
    const { rerender } = mount({ recordId: 42, active: true, generation: 0 });

    await advance(2000);
    expect(fetchSuggestions).toHaveBeenCalledTimes(2);

    rerender({ recordId: 42, active: false, generation: 0 });
    await advance(30_000);
    expect(fetchSuggestions).toHaveBeenCalledTimes(2);

    rerender({ recordId: 42, active: true, generation: 0 });
    await advance(0);
    expect(fetchSuggestions).toHaveBeenCalledTimes(3);
  });

  it("asks again on re-entry after failed, so a retried extraction still gives suggestions", async () => {
    fetchSuggestions.mockResolvedValueOnce(reply("failed")).mockResolvedValueOnce(reply("ready", "Later Title"));
    const { result, rerender } = mount({ recordId: 42, active: true, generation: 0 });

    await advance(0);
    expect(result.current.status).toBe("failed");

    rerender({ recordId: 42, active: false, generation: 0 });
    rerender({ recordId: 42, active: true, generation: 0 });
    await advance(0);
    expect(result.current.suggestions.title).toBe("Later Title");
  });

  it("forgets the previous file's suggestions when a new one is uploaded", async () => {
    fetchSuggestions.mockResolvedValueOnce(reply("ready", "Old Title")).mockResolvedValue(reply("pending"));
    const { result, rerender } = mount({ recordId: 42, active: true, generation: 0 });

    await advance(0);
    expect(result.current.suggestions.title).toBe("Old Title");

    rerender({ recordId: 42, active: true, generation: 1 });
    expect(result.current.suggestions.title).toBeNull();
    await advance(0);
    expect(result.current.status).toBe("pending");
  });

  it("drops a reply that arrives after the file it was about was replaced", async () => {
    let settle!: (value: unknown) => void;
    fetchSuggestions
      .mockImplementationOnce(() => new Promise((resolve) => (settle = resolve)) as never)
      .mockResolvedValue(reply("pending"));
    const { result, rerender } = mount({ recordId: 42, active: true, generation: 0 });

    await advance(0);
    rerender({ recordId: 42, active: true, generation: 1 });
    await advance(0);
    await act(async () => settle(reply("ready", "Stale Title")));

    expect(result.current.suggestions.title).toBeNull();
    expect(result.current.status).toBe("pending");
  });
});
