/**
 * Ask IRIS on the AI runtime, when the deployment's switch says so (IR-863).
 *
 * The runtime's answers are the ones `backend/apps/ai/tests/test_runtime_reader_e2e.py`
 * recorded from Django's edge grant, the gateway and the recording provider on
 * PostgreSQL, so this replays what the server actually serves rather than a
 * hand-written guess at it. Requests are answered at the axios adapter, below
 * every client this page uses.
 */
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import type { AxiosAdapter, InternalAxiosRequestConfig } from "axios";
import { Route, Routes, useLocation } from "react-router-dom";
import { renderScreen, screen, userEvent, waitFor, within } from "@/test/render";
import { expectNoBlockingA11yViolations } from "@/test/axe";
import { apiClient } from "@/api/client";
import { resetReaderPath } from "@/api/runtimeReader";
import recorded from "@/test/fixtures/runtimeReader.recorded.json";
import RAGChatPage from "./RAGChatPage";

type Reply = { status?: number; data: unknown };
let route: (config: InternalAxiosRequestConfig) => Reply;
let sent: InternalAxiosRequestConfig[];
let originalAdapter: InternalAxiosRequestConfig["adapter"];
let address = "";

const { live, conversation } = recorded;
const CONVERSATION = `/ai/runtime/conversations/${conversation.id}`;

/** Answers the recorded run; anything else unexpected fails the test loudly. */
function runtime(config: InternalAxiosRequestConfig): Reply {
  const url = config.url ?? "";
  if (url === "/ai/reader/") return { data: { path: "runtime" } };
  if (url === "/ai/runtime/runs" && config.method === "post") return { status: 201, data: live };
  if (url === `/ai/runtime/runs/${live.id}`) return { data: live };
  if (url === CONVERSATION) return { data: conversation };
  throw new Error(`unexpected request ${config.method} ${url}`);
}

function Address() {
  address = useLocation().pathname;
  return null;
}

function renderAsk(at: string) {
  return renderScreen(
    <>
      <Routes>
        <Route path="/ai" element={<RAGChatPage />} />
        <Route path="/ai/conversations/:conversationId" element={<RAGChatPage />} />
      </Routes>
      <Address />
    </>,
    { route: at },
  );
}

/** What a reader sees of the answer: its text, then each citation in order. */
function answerAsRead() {
  const article = screen.getByRole("article", { name: "Research question" });
  const citations = within(article).getByRole("list", { name: "Cited passages" });
  return {
    question: within(article).getByText(live.question).textContent,
    answer: within(article).getByText(conversation.turns[0].answer).textContent,
    citations: within(citations).getAllByRole("listitem").map((item) => ({
      link: within(item).getByRole("link").getAttribute("href"),
      text: item.textContent,
    })),
  };
}

beforeEach(() => {
  Element.prototype.scrollIntoView = vi.fn();
  resetReaderPath();
  sent = [];
  route = runtime;
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

it("delivers a question through the runtime and reopens the same answer after a reload", async () => {
  const user = userEvent.setup();
  const first = renderAsk("/ai");
  const box = await screen.findByRole("textbox", { name: "Ask about the research corpus" });
  await user.type(box, live.question);
  await user.click(screen.getByRole("button", { name: "Send message" }));

  expect(await screen.findByText(conversation.turns[0].answer)).toBeInTheDocument();
  expect(screen.getByText("Compare how each study samples water")).toBeInTheDocument();
  expect(screen.getByText("Answer ready")).toBeInTheDocument();
  expect(screen.getByText(/can make mistakes/)).toBeInTheDocument();
  await waitFor(() => expect(address).toBe(`/ai/conversations/${conversation.id}`));
  const delivered = answerAsRead();
  expect(delivered.citations).toEqual([
    { link: "/records/1?page=3", text: expect.stringContaining("river gauges measure water level hourly") },
    { link: "/records/2?page=5", text: expect.stringContaining("pond water sampled weekly for turbidity") },
  ]);
  await expectNoBlockingA11yViolations(first.container);

  // Every runtime request went through the same-origin proxy and carried no
  // credential of the browser's own: nginx adds the grant and service secret.
  const runtimeRequests = sent.filter((config) => config.url?.startsWith("/ai/runtime/"));
  expect(runtimeRequests.length).toBeGreaterThan(0);
  for (const config of runtimeRequests) {
    expect(config.baseURL).toBe("/api/v1");
    expect(config.headers["X-IRIS-Protocol"]).toBe("runs-reader-1");
    expect(config.headers["X-IRIS-Reader-Grant"]).toBeUndefined();
    expect(config.headers["X-IRIS-Service-Secret"]).toBeUndefined();
  }
  first.unmount();

  resetReaderPath();
  const reopened = renderAsk(`/ai/conversations/${conversation.id}`);
  expect(await screen.findByText(conversation.turns[0].answer)).toBeInTheDocument();
  expect(answerAsRead()).toEqual(delivered);
  await expectNoBlockingA11yViolations(reopened.container);
});

it.each([
  ["busy", { status: 503, data: { status: "busy" } }, /IRIS is busy/, true],
  ["unavailable", { status: 503, data: { status: "unavailable" } }, /Ask IRIS is unavailable right now/, true],
  ["refused", { status: 403, data: "" }, /can't open research for you/, false],
])("a %s submission shows its own safe state", async (_name, reply, message, canReconnect) => {
  route = (config) => (config.url === "/ai/runtime/runs" ? reply : runtime(config));
  const user = userEvent.setup();
  const { container } = renderAsk("/ai");
  await user.type(await screen.findByRole("textbox", { name: "Ask about the research corpus" }), "Compare");
  await user.click(screen.getByRole("button", { name: "Send message" }));
  expect(await screen.findByRole("alert")).toHaveTextContent(message);
  expect(screen.queryByRole("button", { name: "Reconnect" }) !== null).toBe(canReconnect);
  expect(screen.getByText(/can make mistakes/)).toBeInTheDocument();
  await expectNoBlockingA11yViolations(container);
});

it("a conversation that cannot be opened says so and offers a new one", async () => {
  route = (config) => (config.url === CONVERSATION ? { status: 404, data: { status: "not_found" } } : runtime(config));
  renderAsk(`/ai/conversations/${conversation.id}`);
  expect(await screen.findByRole("alert")).toHaveTextContent(/conversation is not available/);
  expect(screen.getByRole("link", { name: "Start a new conversation" })).toHaveAttribute("href", "/ai");
});

it("a stopped run reads as stopped, from a keyboard-operated Stop", async () => {
  const running = { ...live, state: "running", turn_id: null, finished_at: null };
  const stopped = { ...running, state: "cancelled" };
  const open = { ...conversation, runs: [running], turns: [] };
  route = (config) => {
    if (config.url === `/ai/runtime/runs/${live.id}/cancel`) return { data: stopped };
    if (config.url === CONVERSATION) return { data: open };
    if (config.url === `/ai/runtime/runs/${live.id}`) return { data: running };
    return runtime(config);
  };
  const user = userEvent.setup();
  renderAsk(`/ai/conversations/${conversation.id}`);
  const stop = await screen.findByRole("button", { name: "Stop research" });
  stop.focus();
  await user.keyboard("{Enter}");
  expect(await screen.findByText("Stopped")).toBeInTheDocument();
  expect(screen.getByText(/can make mistakes/)).toBeInTheDocument();
});
