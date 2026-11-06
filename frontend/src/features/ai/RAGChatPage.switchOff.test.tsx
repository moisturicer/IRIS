/**
 * With the reader-path switch off, Ask IRIS sends exactly what it sent before
 * IR-863 (acceptance criterion 1).
 *
 * The snapshot was captured from the page *before* the switch existed: every
 * request the reader makes to open Ask IRIS and ask one question, at the wire
 * (axios adapter and `fetch`), with only the per-request id and idle counter
 * made stable. The one request IR-863 adds, reading the switch itself, is
 * asserted separately and left out of the comparison.
 */
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import type { AxiosAdapter, InternalAxiosRequestConfig } from "axios";
import { Route, Routes } from "react-router-dom";
import { renderScreen, screen, userEvent, waitFor } from "@/test/render";
import { apiClient } from "@/api/client";
import RAGChatPage from "./RAGChatPage";

interface Sent { method: string; url: string; params?: unknown; body?: unknown; protocol?: string }

const conversation = {
  id: 7, title: "", record: null, record_title: null, turn_count: 0,
  created_at: "2026-11-04T00:00:00.000Z", updated_at: "2026-11-04T00:00:00.000Z",
  turns: [], latest_run: null,
};
const answer = {
  answer: "Rainfall gauges predict flooding.", citations: [], sources: [], message: null,
  mode: "generative", degraded: false, conversation_id: 7, resolved_question: null, widened: false,
};

let sent: Sent[];
let readerPathReads: number;
let originalAdapter: InternalAxiosRequestConfig["adapter"];

function stable(body: unknown): unknown {
  if (typeof body === "string") {
    try { return stable(JSON.parse(body)); } catch { return body; }
  }
  if (body && typeof body === "object" && "request_id" in body) return { ...body, request_id: "<uuid>" };
  return body;
}

function respond(config: InternalAxiosRequestConfig): unknown {
  const url = config.url ?? "";
  if (url === "/ai/reader/") return { path: "django" };
  if (url === "/ai/status/") {
    return { embedding_space: null, generative: true, comparison_max_records: 5, indexed_records: 3 };
  }
  if (url === "/ai/conversations/" && config.method === "post") return conversation;
  if (url === "/ai/conversations/") return [];
  if (url === "/ai/conversations/7/") return conversation;
  return { results: [], count: 0, next: null, previous: null };
}

beforeEach(() => {
  Element.prototype.scrollIntoView = vi.fn();
  sent = [];
  readerPathReads = 0;
  originalAdapter = apiClient.defaults.adapter;
  const adapter: AxiosAdapter = async (config) => {
    if (config.url === "/ai/reader/") readerPathReads += 1;
    else {
      sent.push({
        method: (config.method ?? "get").toUpperCase(), url: config.url ?? "",
        ...(config.params ? { params: config.params } : {}),
        ...(config.data ? { body: stable(config.data) } : {}),
        ...(config.headers?.["X-IRIS-Protocol"] ? { protocol: String(config.headers["X-IRIS-Protocol"]) } : {}),
      });
    }
    return { data: respond(config), status: 200, statusText: "OK", headers: {}, config };
  };
  apiClient.defaults.adapter = adapter;
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const headers = (init?.headers ?? {}) as Record<string, string>;
    sent.push({
      method: init?.method ?? "GET", url: String(input), body: stable(init?.body),
      ...(headers["X-IRIS-Protocol"] ? { protocol: headers["X-IRIS-Protocol"] } : {}),
    });
    return new Response(`event: done\ndata: ${JSON.stringify(answer)}\n\n`, {
      status: 200, headers: { "Content-Type": "text/event-stream" },
    });
  });
});

afterEach(() => {
  apiClient.defaults.adapter = originalAdapter;
  vi.restoreAllMocks();
});

it("asks through Django with the same requests as before the switch existed", async () => {
  const user = userEvent.setup();
  renderScreen(
    <Routes>
      <Route path="/ai" element={<RAGChatPage />} />
      <Route path="/ai/conversations/:conversationId" element={<RAGChatPage />} />
    </Routes>,
    { route: "/ai" },
  );
  const box = await screen.findByRole("textbox", { name: /ask a follow-up/i });
  await waitFor(() => expect(box).toBeEnabled());
  await user.type(box, "What predicts flooding?");
  await user.click(screen.getByRole("button", { name: "Send message" }));
  expect(await screen.findByText("Rainfall gauges predict flooding.")).toBeInTheDocument();
  await waitFor(() => expect(sent.filter((r) => r.url === "/ai/conversations/").length).toBeGreaterThan(1));
  expect(sent).toMatchSnapshot();
  expect(readerPathReads).toBeLessThanOrEqual(1);
});
