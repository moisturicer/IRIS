/**
 * The request timeout, cancellation and retry policy of `apiClient` (IR-914,
 * ADR-061). The adapter is replaced, as `installApiStub` does, so the real
 * request pipeline and interceptors run; the timeout itself is the adapter's
 * work, so these tests make it fail the way axios's adapters do.
 */
import { AxiosError, type AxiosAdapter } from "axios";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { recordsApi } from "./records";
import { documentsApi } from "./documents";
import { apiClient } from "./client";
import {
  DEFAULT_TIMEOUT_MS,
  TRANSFER_TIMEOUT_MS,
  RequestTimeoutError,
  isRequestTimeout,
} from "./requestPolicy";

vi.mock("@/lib/authSession", () => ({ redirectToLoginSessionExpired: vi.fn() }));

describe("request timeout policy", () => {
  const original = apiClient.defaults.adapter;
  let seen: { method?: string; url?: string; timeout?: number }[];
  let mode: "ok" | "timeout";

  beforeEach(() => {
    seen = [];
    mode = "ok";
    const adapter: AxiosAdapter = async (config) => {
      seen.push({ method: config.method, url: config.url, timeout: config.timeout });
      if (mode === "timeout") {
        // What axios's adapters reject with when `timeout` elapses and
        // `transitional.clarifyTimeoutError` is on.
        throw new AxiosError("timeout of 30000ms exceeded", AxiosError.ETIMEDOUT, config);
      }
      return { data: {}, status: 200, statusText: "OK", headers: {}, config };
    };
    apiClient.defaults.adapter = adapter;
  });
  afterEach(() => {
    apiClient.defaults.adapter = original;
  });

  it("gives an ordinary request the default timeout", async () => {
    await apiClient.get("/records/");
    expect(seen[0].timeout).toBe(DEFAULT_TIMEOUT_MS);
  });

  it("states a longer timeout for uploads and blobs, explicitly", async () => {
    await recordsApi.manuscriptBlob(1);
    await documentsApi.downloadUpload(1);
    await recordsApi.uploadManuscript(1, new File(["x"], "a.pdf"));

    expect(TRANSFER_TIMEOUT_MS).toBeGreaterThan(DEFAULT_TIMEOUT_MS);
    expect(seen.map((s) => s.timeout)).toEqual([TRANSFER_TIMEOUT_MS, TRANSFER_TIMEOUT_MS, TRANSFER_TIMEOUT_MS]);
  });

  it("fails a request that exceeds the timeout with a typed error the UI can show", async () => {
    mode = "timeout";

    const err = await apiClient.get("/records/").catch((e: unknown) => e);

    expect(err).toBeInstanceOf(RequestTimeoutError);
    expect(isRequestTimeout(err)).toBe(true);
    expect(err).toMatchObject({ timeoutMs: DEFAULT_TIMEOUT_MS, method: "get", url: "/records/" });
  });

  it("does not mistake other failures for a timeout", async () => {
    expect(isRequestTimeout(new Error("boom"))).toBe(false);
    expect(isRequestTimeout(null)).toBe(false);
  });

  it("never retries a write on its own, timed out or not", async () => {
    mode = "timeout";

    await apiClient.post("/records/", { title: "t" }).catch(() => undefined);
    await apiClient.patch("/records/1/", { title: "t" }).catch(() => undefined);

    expect(seen.map((s) => s.method)).toEqual(["post", "patch"]);
  });

  it("does not retry a read on its own either; the reader's Retry does", async () => {
    mode = "timeout";

    await apiClient.get("/records/").catch(() => undefined);

    expect(seen).toHaveLength(1);
  });
});
