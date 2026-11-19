/**
 * A conversation list that fails to load offers Try again, and every error shows
 * once (IR-1238, part of IR-1229).
 *
 * Page-level: the real page and the real `runtimeReader`, with requests answered
 * at the axios adapter, below every client the page uses.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { AxiosAdapter, InternalAxiosRequestConfig } from "axios";
import { Route, Routes } from "react-router-dom";
import { renderScreen, screen, userEvent, waitFor } from "@/test/render";
import { expectNoBlockingA11yViolations } from "@/test/axe";
import { apiClient } from "@/api/client";
import recorded from "@/test/fixtures/runtimeReader.recorded.json";
import RAGChatPage from "./RAGChatPage";

// A 401 reaches the page only once the session could not be refreshed; the
// refresh is refused and the redirect to sign-in is left out of jsdom.
vi.mock("@/api/sessionRefresh", () => ({ requestNewTokens: vi.fn().mockRejectedValue(new Error("no session")) }));
vi.mock("@/lib/authSession", async (original) => ({
  ...(await original<typeof import("@/lib/authSession")>()),
  redirectToLoginSessionExpired: vi.fn(),
}));

type Reply = { status?: number; data: unknown };
let route: (config: InternalAxiosRequestConfig) => Reply;
let list: () => Reply;
let sent: InternalAxiosRequestConfig[];
let originalAdapter: InternalAxiosRequestConfig["adapter"];

const { live, conversation } = recorded;
const CONVERSATION = `/ai/runtime/conversations/${conversation.id}`;
const LIST = "/ai/runtime/conversations";
const TRY_AGAIN = "IRIS couldn't load your conversations. Your new questions still work.";

const listed = (...titles: string[]): Reply => ({ data: {
  protocol: "runs-reader-1", next: null,
  conversations: titles.map(title => ({ id: `id-${title}`, title, record_id: null, updated_at: "2026-11-01T10:00:00+00:00" })),
} });
const down = (status = 500, data: unknown = {}): Reply => ({ status, data });

function runtime(config: InternalAxiosRequestConfig): Reply {
  const url = config.url ?? "";
  if (url === "/ai/conversations/" && config.method === "get") return { data: [] };
  if (url === LIST && config.method === "get") return list();
  if (url === "/ai/runtime/runs" && config.method === "post") return { status: 201, data: live };
  if (url === `/ai/runtime/runs/${live.id}`) return { data: live };
  if (url === CONVERSATION) return { data: conversation };
  throw new Error(`unexpected request ${config.method} ${url}`);
}

function renderAsk(at: string) {
  return renderScreen(
    <Routes>
      <Route path="/ai" element={<RAGChatPage />} />
      <Route path="/ai/conversations/:conversationId" element={<RAGChatPage />} />
    </Routes>,
    { route: at },
  );
}

async function ask(user: ReturnType<typeof userEvent.setup>, question = "Compare") {
  await user.type(await screen.findByRole("textbox", { name: "Ask about the research in IRIS" }), question);
  await user.click(screen.getByRole("button", { name: "Send message" }));
}

beforeEach(() => {
  Element.prototype.scrollIntoView = vi.fn();
  sent = [];
  route = runtime;
  list = () => listed();
  originalAdapter = apiClient.defaults.adapter;
  const adapter: AxiosAdapter = async (config) => {
    sent.push(config);
    const reply = route(config);
    const status = reply.status ?? 200;
    const response = { data: reply.data, status, statusText: "", headers: {}, config };
    if (status >= 400) {
      throw Object.assign(new Error(`HTTP ${status}`), { isAxiosError: true, response, config });
    }
    return response;
  };
  apiClient.defaults.adapter = adapter;
});

afterEach(() => {
  apiClient.defaults.adapter = originalAdapter;
  vi.restoreAllMocks();
});

describe("a conversation list that fails to load", () => {
  it("says so once, offers Try again, and shows the list when the next request succeeds", async () => {
    let attempts = 0;
    list = () => (++attempts === 1 ? down() : listed("Flood methods"));
    const user = userEvent.setup();
    const { container } = renderAsk("/ai");

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(TRY_AGAIN);
    expect(screen.getAllByRole("alert")).toHaveLength(1);
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
    // Search has nothing to search; the question box is untouched.
    expect(screen.getByRole("searchbox", { name: "Search your past conversations" })).toBeDisabled();
    expect(screen.getByRole("textbox", { name: "Ask about the research in IRIS" })).toBeEnabled();
    await expectNoBlockingA11yViolations(container);

    await user.click(screen.getByRole("button", { name: "Try again" }));

    expect(await screen.findByRole("link", { name: /Flood methods/ })).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Try again" })).not.toBeInTheDocument();
    expect(screen.getByRole("searchbox", { name: "Search your past conversations" })).toBeEnabled();
  });

  it("stays on the message when the retry fails too, and a question can still be submitted", async () => {
    list = () => down(503, { status: "unavailable" });
    const user = userEvent.setup();
    renderAsk("/ai");
    await user.click(await screen.findByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(TRY_AGAIN);

    await ask(user);

    expect(await screen.findByText((_, element) =>
      element?.tagName === "P" && /^Both studies sample water/.test(element.textContent ?? ""))).toBeInTheDocument();
    expect(sent.some(config => config.url === "/ai/runtime/runs" && config.method === "post")).toBe(true);
    expect(screen.getAllByRole("alert")).toHaveLength(1);
    expect(screen.getByRole("alert")).toHaveTextContent(TRY_AGAIN);
  });
});

describe("every error shows once", () => {
  // The same cause reaches the list and the chat: the reader sees it in the chat only.
  it.each([
    ["session ended (401)", down(401), /Your session has ended/],
    ["busy (503)", down(503, { status: "busy" }), /IRIS is busy right now/],
    ["busy (429)", down(429), /IRIS is busy right now/],
    ["protocol mismatch", { data: { protocol: "runs-reader-9" } } as Reply, /Please reload to reconnect/],
  ])("%s, while the list fails the same way", async (_name, failure, message) => {
    route = (config) => {
      if (config.url === "/ai/runtime/runs" || config.url === LIST) return failure;
      return runtime(config);
    };
    const user = userEvent.setup();
    const { container } = renderAsk("/ai");
    // The list has failed alone first: its own message is the one alert.
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent(TRY_AGAIN));

    await ask(user);

    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent(message));
    expect(screen.getAllByRole("alert")).toHaveLength(1);
    expect(screen.queryByText(TRY_AGAIN)).not.toBeInTheDocument();
    await expectNoBlockingA11yViolations(container);
  });

  it("not available (404): a conversation that cannot be opened", async () => {
    route = (config) => (config.url === CONVERSATION ? down(404, { status: "not_found" }) : runtime(config));
    list = () => listed("Flood methods");
    const { container } = renderAsk(`/ai/conversations/${conversation.id}`);

    expect(await screen.findByRole("alert")).toHaveTextContent("This conversation is not available.");
    await screen.findByRole("link", { name: /Flood methods/ });
    expect(screen.getAllByRole("alert")).toHaveLength(1);
    await expectNoBlockingA11yViolations(container);
  });

  it("a failed run keeps its Retry, and the list failing beside it still says its own piece once", async () => {
    const failed = { ...live, state: "failed", turn_id: null, base_revision: conversation.revision };
    const open = { ...conversation, runs: [failed], turns: [] };
    route = (config) => {
      if (config.url === CONVERSATION) return { data: open };
      if (config.url === `/ai/runtime/runs/${live.id}/retry`) return { status: 201, data: live };
      return runtime(config);
    };
    list = () => down();
    const user = userEvent.setup();
    renderAsk(`/ai/conversations/${conversation.id}`);

    await user.click(await screen.findByRole("button", { name: "Try this question again" }));
    await waitFor(() => expect(sent.some(config => config.url === `/ai/runtime/runs/${live.id}/retry`)).toBe(true));
    expect(screen.getAllByRole("alert")).toHaveLength(1);
  });

  it("asks the list again once the chat's problem is cleared, so it is not left silent", async () => {
    let attempts = 0;
    let submits = 0;
    list = () => (++attempts <= 2 ? down(503, { status: "busy" }) : listed("Flood methods"));
    route = (config) => (config.url === "/ai/runtime/runs" && ++submits === 1 ? down(503, { status: "busy" }) : runtime(config));
    const user = userEvent.setup();
    renderAsk("/ai");
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent(TRY_AGAIN));
    await ask(user);
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent(/IRIS is busy right now/));

    await user.click(screen.getByRole("button", { name: "Reconnect" }));

    expect(await screen.findByRole("link", { name: /Flood methods/ })).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});
