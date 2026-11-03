/**
 * The prefill's polling (IR-409; IR-833).
 *
 * Driven with fake timers, so the backoff and the two-minute foreground budget
 * are asserted as calls made, not as time waited. IR-833 replaced IR-409's
 * 2 s / 5 s / 90 s schedule, after which a long paper silently offered
 * nothing, with a backoff that ends in `stalled` and *Check again*.
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
  it("backs off from 2 s by half again each time, to at most 15 s", () => {
    expect(nextPollDelay(0, 0)).toBe(2000);
    expect(nextPollDelay(1, 2000)).toBe(3000);
    expect(nextPollDelay(2, 5000)).toBe(4500);
    expect(nextPollDelay(5, 30_000)).toBe(15_000);
    expect(nextPollDelay(20, 60_000)).toBe(15_000);
  });

  it("never schedules past two minutes, and stops there", () => {
    expect(nextPollDelay(10, 116_000)).toBe(4000);
    expect(nextPollDelay(10, 120_000)).toBeNull();
    expect(nextPollDelay(10, 300_000)).toBeNull();
  });
});

describe("usePrefill", () => {
  it("asks nothing while inactive or without a record", async () => {
    mount({ recordId: 42, active: false, generation: 0 });
    mount({ recordId: null, active: true, generation: 0 });
    await advance(10_000);

    expect(fetchSuggestions).not.toHaveBeenCalled();
  });

  it("asks again while pending, less often each time", async () => {
    fetchSuggestions.mockResolvedValue(reply("pending"));
    const { result } = mount({ recordId: 42, active: true, generation: 0 });

    await advance(0);
    expect(fetchSuggestions).toHaveBeenCalledTimes(1);
    expect(result.current.status).toBe("pending");

    await advance(2000);
    expect(fetchSuggestions).toHaveBeenCalledTimes(2);
    await advance(2999);
    expect(fetchSuggestions).toHaveBeenCalledTimes(2);
    await advance(1);
    expect(fetchSuggestions).toHaveBeenCalledTimes(3);
  });

  it("stops after two minutes as stalled, and Check again asks afresh", async () => {
    fetchSuggestions.mockResolvedValue(reply("pending"));
    const { result } = mount({ recordId: 42, active: true, generation: 0 });

    await advance(120_000);
    const calls = fetchSuggestions.mock.calls.length;
    expect(result.current.status).toBe("stalled");
    await advance(60_000);
    expect(fetchSuggestions).toHaveBeenCalledTimes(calls);

    fetchSuggestions.mockResolvedValue(reply("ready", "A Found Title"));
    act(() => result.current.checkAgain());
    await advance(0);
    expect(fetchSuggestions).toHaveBeenCalledTimes(calls + 1);
    expect(result.current.status).toBe("ready");
    expect(result.current.fields.title?.value).toBe("A Found Title");
  });

  it("keeps asking through a retrying phase", async () => {
    fetchSuggestions
      .mockResolvedValueOnce({ data: { state: "pending", phase: "retrying", suggestions: { title: null, abstract: null }, source: "pdf_structure" } } as never)
      .mockResolvedValueOnce(reply("ready", "After The Retry"));
    const { result } = mount({ recordId: 42, active: true, generation: 0 });

    await advance(0);
    expect(result.current.phase).toBe("retrying");
    await advance(2000);
    expect(result.current.fields.title?.value).toBe("After The Retry");
  });

  it("stops once the suggestions are ready, and returns them", async () => {
    fetchSuggestions
      .mockResolvedValueOnce(reply("pending"))
      .mockResolvedValueOnce(reply("ready", "A Found Title", null));
    const { result } = mount({ recordId: 42, active: true, generation: 0 });

    await advance(2000);
    expect(result.current.status).toBe("ready");
    expect(result.current.fields.title?.value).toBe("A Found Title");
    expect(result.current.fields.abstract).toBeNull();

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
    expect(result.current.fields.title?.value).toBe("Later Title");
  });

  it("forgets the previous file's suggestions when a new one is uploaded", async () => {
    fetchSuggestions.mockResolvedValueOnce(reply("ready", "Old Title")).mockResolvedValue(reply("pending"));
    const { result, rerender } = mount({ recordId: 42, active: true, generation: 0 });

    await advance(0);
    expect(result.current.fields.title?.value).toBe("Old Title");

    rerender({ recordId: 42, active: true, generation: 1 });
    expect(result.current.fields.title).toBeNull();
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

    expect(result.current.fields.title).toBeNull();
    expect(result.current.status).toBe("pending");
  });
});
