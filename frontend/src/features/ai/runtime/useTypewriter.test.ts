import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useTypewriter } from "./useTypewriter";

const words = (n: number) => Array.from({ length: n }, (_, i) => `word${i}`).join(" ");

describe("useTypewriter", () => {
  beforeEach(() => { vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout", "requestAnimationFrame", "cancelAnimationFrame", "performance"] }); });
  afterEach(() => { vi.useRealTimers(); });

  it("types a whole answer out in a couple of seconds, a whole word at a time", () => {
    const text = words(500);
    const { result } = renderHook(({ t }) => useTypewriter(t, "run"), { initialProps: { t: text } });
    const seen: number[] = [];
    for (let ms = 0; ms < 4000 && !result.current.done; ms += 16) {
      act(() => { vi.advanceTimersByTime(16); });
      seen.push(result.current.text.length);
    }
    expect(result.current.done).toBe(true);
    expect(seen.length * 16).toBeLessThan(3000);
    // Never backwards, and never stopping mid-word.
    seen.forEach((n, i) => expect(n).toBeGreaterThanOrEqual(seen[i - 1] ?? 0));
    seen.filter(n => n > 0 && n < text.length).forEach(n => expect(text[n]).toBe(" "));
  });

  it("starts gently instead of jumping", () => {
    const { result } = renderHook(() => useTypewriter(words(500), "run"));
    act(() => { vi.advanceTimersByTime(100); });
    expect(result.current.text.length).toBeLessThan(120);
  });
});
