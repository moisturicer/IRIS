/**
 * A stand-in server for the API modules' tests (IR-916).
 *
 * The modules under `src/api/` are thin: each call is a method, a path and a
 * payload handed to `apiClient`. The risk is a wrong verb, a path with a typo,
 * a renamed body key or a param that is sent when it should be left off, and
 * none of those show up in a test that mocks `apiClient` itself, because the
 * mock accepts whatever it is given. This replaces only axios's *adapter*, the
 * last step before the network, so the real request pipeline runs (URL
 * building, JSON encoding, interceptors) and the test reads what would have
 * gone on the wire.
 *
 * Errors are rejected the way axios rejects them, as an `AxiosError` carrying
 * the response, so the callers' `err.response.status` and `err.response.data`
 * reads work against it.
 */
import { AxiosError, type AxiosAdapter, type AxiosResponse, type InternalAxiosRequestConfig } from "axios";
import { afterEach, beforeEach } from "vitest";

import { apiClient } from "@/api/client";

export interface RecordedCall {
  method: string;
  /** The path as the module wrote it, relative to the API base. */
  url: string;
  params: unknown;
  /** The JSON body parsed back, a `FormData` as is, or `undefined` when none was sent. */
  body: unknown;
  headers: Record<string, unknown>;
  responseType: string | undefined;
  config: InternalAxiosRequestConfig;
}

export interface StubReply {
  status?: number;
  data?: unknown;
}

export interface ApiStub {
  /** Every call so far, oldest first. */
  calls: RecordedCall[];
  /** The only call, failing the test if there were none or several. */
  only(): RecordedCall;
  /** What the next calls get back. Default is a 200 with `{}`. */
  reply(reply: StubReply): void;
}

/**
 * Installs the stand-in around each test in the calling file. Call it once at
 * the top level of the file, or inside a `describe`.
 */
export function installApiStub(): ApiStub {
  const original = apiClient.defaults.adapter;
  let next: StubReply = {};

  const stub: ApiStub = {
    calls: [],
    only() {
      if (stub.calls.length !== 1) {
        throw new Error(`expected exactly one request, saw ${stub.calls.length}`);
      }
      return stub.calls[0];
    },
    reply(reply) {
      next = reply;
    },
  };

  const adapter: AxiosAdapter = async (config) => {
    const raw = config.data as unknown;
    let body: unknown = raw;
    if (typeof raw === "string") {
      try {
        body = JSON.parse(raw);
      } catch {
        body = raw;
      }
    }
    stub.calls.push({
      method: String(config.method).toLowerCase(),
      url: String(config.url),
      params: config.params,
      body,
      headers: { ...(config.headers as unknown as Record<string, unknown>) },
      responseType: config.responseType,
      config,
    });

    const status = next.status ?? 200;
    const response: AxiosResponse = {
      data: next.data ?? {},
      status,
      statusText: String(status),
      headers: {},
      config,
    };
    if (status >= 400) {
      throw new AxiosError(
        `Request failed with status code ${status}`,
        status >= 500 ? AxiosError.ERR_BAD_RESPONSE : AxiosError.ERR_BAD_REQUEST,
        config,
        null,
        response,
      );
    }
    return response;
  };

  beforeEach(() => {
    stub.calls.length = 0;
    next = {};
    apiClient.defaults.adapter = adapter;
  });
  afterEach(() => {
    apiClient.defaults.adapter = original;
  });

  return stub;
}
