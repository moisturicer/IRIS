/**
 * The live hint stream's client (ADR-073, IR-1213), against a fake `fetch`.
 */
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  backoffMs, emitLiveHint, isLiveRunning, onLiveHint, onLiveResync, parseEvents, startLive, stopLive,
} from "./live";

function streamOf(...chunks: string[]): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();
  return new ReadableStream({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(encoder.encode(chunk));
      controller.close();
    },
  });
}

const ok = (...chunks: string[]) => ({ status: 200, ok: true, body: streamOf(...chunks) }) as unknown as Response;
const status = (code: number) => ({ status: code, ok: false, body: null }) as unknown as Response;

afterEach(() => stopLive());

describe("parseEvents", () => {
  it("reads each event's topics, skips comments, and keeps an unfinished tail", () => {
    const { hints, rest } = parseEvents(': connected\n\ndata: {"topics":["reviews"]}\n\n: ping\n\ndata: {"topics":["lib');
    expect(hints).toEqual([["reviews"]]);
    expect(rest).toBe('data: {"topics":["lib');
  });

  it("ignores a data line that is not a hint", () => {
    expect(parseEvents("data: not json\n\n").hints).toEqual([]);
  });
});

describe("backoffMs", () => {
  it("starts at a second, doubles, and stops at a minute", () => {
    expect(backoffMs(0, () => 0)).toBe(1000);
    expect(backoffMs(3, () => 0)).toBe(8000);
    expect(backoffMs(20, () => 0)).toBe(60_000);
    expect(backoffMs(0, () => 1)).toBe(1250);
  });
});

describe("the stream", () => {
  it("opens with the access token and delivers each hint to listeners", async () => {
    const heard: string[][] = [];
    const off = onLiveHint((topics) => heard.push(topics));
    const fetchImpl = vi.fn()
      .mockResolvedValueOnce(ok(': connected\n\ndata: {"topics":["reviews"]}\n', '\ndata: {"topics":["queues"]}\n\n'))
      .mockImplementation(() => new Promise(() => {})); // the next attempt never answers
    startLive({ token: () => "access-1", refresh: vi.fn(), fetchImpl, sleep: () => Promise.resolve() });

    await vi.waitFor(() => expect(heard).toEqual([["reviews"], ["queues"]]));
    const [url, init] = fetchImpl.mock.calls[0];
    expect(url).toBe("/api/v1/live/");
    expect((init as RequestInit).headers).toMatchObject({ Authorization: "Bearer access-1" });
    off();
  });

  it("refreshes the session on a 401 and reopens with the new token", async () => {
    let current = "expired";
    const refresh = vi.fn(async () => { current = "fresh"; return "fresh"; });
    const fetchImpl = vi.fn()
      .mockResolvedValueOnce(status(401))
      .mockImplementation(() => new Promise(() => {}));
    startLive({ token: () => current, refresh, fetchImpl, sleep: () => Promise.resolve() });

    await vi.waitFor(() => expect(fetchImpl).toHaveBeenCalledTimes(2));
    expect(refresh).toHaveBeenCalledTimes(1);
    expect((fetchImpl.mock.calls[1][1] as RequestInit).headers).toMatchObject({ Authorization: "Bearer fresh" });
  });

  it("stops for good when the session cannot be refreshed", async () => {
    const fetchImpl = vi.fn().mockResolvedValue(status(401));
    startLive({ token: () => "expired", refresh: async () => null, fetchImpl, sleep: () => Promise.resolve() });

    await vi.waitFor(() => expect(isLiveRunning()).toBe(false));
    expect(fetchImpl).toHaveBeenCalledTimes(1);
  });

  it("asks pages to resync on a reconnect, but not on the first connection", async () => {
    const resyncs = vi.fn();
    const off = onLiveResync(resyncs);
    const fetchImpl = vi.fn()
      .mockResolvedValueOnce(ok(": connected\n\n"))
      .mockResolvedValueOnce(ok(": connected\n\n"))
      .mockImplementation(() => new Promise(() => {}));
    startLive({ token: () => "access-1", refresh: vi.fn(), fetchImpl, sleep: () => Promise.resolve() });

    await vi.waitFor(() => expect(fetchImpl).toHaveBeenCalledTimes(3));
    expect(resyncs).toHaveBeenCalledTimes(1);
    off();
  });

  it("does not open without a token, and stopping aborts an open stream", async () => {
    const fetchImpl = vi.fn();
    startLive({ token: () => null, refresh: vi.fn(), fetchImpl });
    await vi.waitFor(() => expect(isLiveRunning()).toBe(false));
    expect(fetchImpl).not.toHaveBeenCalled();

    let signal: AbortSignal | undefined;
    const hanging = vi.fn((_url: string, init: RequestInit) => {
      signal = init.signal ?? undefined;
      return new Promise<Response>(() => {});
    });
    startLive({ token: () => "access-1", refresh: vi.fn(), fetchImpl: hanging as unknown as typeof fetch });
    await vi.waitFor(() => expect(hanging).toHaveBeenCalled());
    stopLive();
    expect(signal?.aborted).toBe(true);
  });

  it("emitLiveHint reaches every listener", () => {
    const a = vi.fn();
    const b = vi.fn();
    const offA = onLiveHint(a);
    const offB = onLiveHint(b);
    emitLiveHint(["library"]);
    expect(a).toHaveBeenCalledWith(["library"]);
    expect(b).toHaveBeenCalledWith(["library"]);
    offA();
    offB();
  });
});
