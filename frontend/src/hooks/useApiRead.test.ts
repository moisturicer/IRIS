import { act, renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { RequestTimeoutError } from "@/api/requestPolicy";
import { useApiRead } from "./useApiRead";

/** A read the test settles by hand, so it decides which response arrives when. */
function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

describe("useApiRead", () => {
  it("loads, then hands over the data", async () => {
    const { result } = renderHook(() => useApiRead(async () => "papers", []));

    expect(result.current.status).toBe("loading");
    await waitFor(() => expect(result.current.status).toBe("ready"));
    expect(result.current.data).toBe("papers");
  });

  it("cancels an in-flight read when the screen unmounts", () => {
    const signals: AbortSignal[] = [];
    const { unmount } = renderHook(() =>
      useApiRead((signal) => {
        signals.push(signal);
        return new Promise<string>(() => undefined);
      }, []),
    );

    expect(signals[0].aborted).toBe(false);
    unmount();
    expect(signals[0].aborted).toBe(true);
  });

  it("cancels the earlier read when its inputs change", () => {
    const signals: AbortSignal[] = [];
    const { rerender } = renderHook(
      ({ q }) =>
        useApiRead((signal) => {
          signals.push(signal);
          return new Promise<string>(() => undefined);
        }, [q]),
      { initialProps: { q: "a" } },
    );

    rerender({ q: "b" });

    expect(signals).toHaveLength(2);
    expect(signals[0].aborted).toBe(true);
    expect(signals[1].aborted).toBe(false);
  });

  it("never lets a slow earlier response replace a newer one, even when the read ignores its signal", async () => {
    const first = deferred<string>();
    const second = deferred<string>();
    const reads = { a: first, b: second };
    const { result, rerender } = renderHook(
      ({ q }: { q: "a" | "b" }) => useApiRead(() => reads[q].promise, [q]),
      { initialProps: { q: "a" as "a" | "b" } },
    );

    rerender({ q: "b" });
    await act(async () => second.resolve("newer"));
    await waitFor(() => expect(result.current.data).toBe("newer"));

    await act(async () => first.resolve("older, late"));

    expect(result.current.data).toBe("newer");
    expect(result.current.status).toBe("ready");
  });

  it("reports a timed-out read as interrupted, and Retry reads again", async () => {
    let attempt = 0;
    const { result } = renderHook(() =>
      useApiRead(async () => {
        attempt += 1;
        if (attempt === 1) throw new RequestTimeoutError(30_000, "get", "/records/");
        return "second time";
      }, []),
    );

    await waitFor(() => expect(result.current.status).toBe("interrupted"));
    expect(result.current.data).toBeUndefined();

    act(() => result.current.retry());

    await waitFor(() => expect(result.current.status).toBe("ready"));
    expect(result.current.data).toBe("second time");
    expect(attempt).toBe(2);
  });

  it("reports any other failure as failed, with the error", async () => {
    const boom = new Error("boom");
    const { result } = renderHook(() =>
      useApiRead(async () => {
        throw boom;
      }, []),
    );

    await waitFor(() => expect(result.current.status).toBe("failed"));
    expect(result.current.error).toBe(boom);
  });

  it("reports a read that throws before returning a promise as failed", async () => {
    const { result } = renderHook(() =>
      useApiRead<string>(() => {
        throw new Error("sync");
      }, []),
    );

    await waitFor(() => expect(result.current.status).toBe("failed"));
  });

  it("says nothing about a read the screen itself cancelled", async () => {
    const pending = deferred<string>();
    const { result, unmount } = renderHook(() => useApiRead(() => pending.promise, []));

    unmount();
    await act(async () => pending.reject(Object.assign(new Error("canceled"), { code: "ERR_CANCELED" })));

    expect(result.current.status).toBe("loading");
  });
});

// ADR-073: a live-update hint refreshes quietly.
describe("useApiRead's refresh", () => {
  it("keeps showing the current data while it reads, then shows the new answer", async () => {
    let answer = "first";
    const { result } = renderHook(() => useApiRead(async () => answer, []));
    await waitFor(() => expect(result.current.data).toBe("first"));

    answer = "second";
    act(() => result.current.refresh());
    expect(result.current.status).toBe("ready");
    expect(result.current.data).toBe("first");
    await waitFor(() => expect(result.current.data).toBe("second"));
  });

  it("leaves the shown data in place when the refresh fails", async () => {
    let fail = false;
    const { result } = renderHook(() =>
      useApiRead(async () => { if (fail) throw new Error("offline"); return "kept"; }, []),
    );
    await waitFor(() => expect(result.current.data).toBe("kept"));

    fail = true;
    act(() => result.current.refresh());
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(result.current.status).toBe("ready");
    expect(result.current.data).toBe("kept");
  });

  it("retry still shows loading, as before", async () => {
    const { result } = renderHook(() => useApiRead(async () => "x", []));
    await waitFor(() => expect(result.current.status).toBe("ready"));
    act(() => result.current.retry());
    expect(result.current.status).toBe("loading");
  });
});
