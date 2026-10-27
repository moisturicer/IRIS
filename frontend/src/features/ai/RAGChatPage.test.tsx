/**
 * Ask IRIS on persisted Conversations (IR-298).
 *
 * Chat history used to live in browser storage and every question glued the
 * whole prior transcript onto itself before sending it. Both are gone: this
 * asserts the replacement â€” the page reads and writes Conversations through
 * the API, a question is sent as itself, and a reader whose old chats
 * vanished is told why rather than left to wonder.
 *
 * Every query goes through the accessible tree, by role and accessible name.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { act, renderScreen, screen, userEvent, waitFor } from "@/test/render";
import type { AIAnswer, AIStatus, Citation, ConversationDetail, ConversationSummary, LatestAskRun } from "@/types/ai";

import RAGChatPage from "./RAGChatPage";

const LEGACY_STORAGE_KEY = "iris_rag_conversations";

function summary(overrides: Partial<ConversationSummary> = {}): ConversationSummary {
  return {
    id: 1, title: "Flooding", record: null, record_title: null, turn_count: 0,
    created_at: "2026-09-20T00:00:00.000Z", updated_at: "2026-09-20T00:00:00.000Z",
    ...overrides,
  };
}

function detail(overrides: Partial<ConversationDetail> = {}): ConversationDetail {
  return { ...summary(), turns: [], ...overrides };
}

function answer(overrides: Partial<AIAnswer> = {}): AIAnswer {
  return {
    answer: "Rainfall gauges predict flooding [1].", citations: [], sources: [],
    message: null, mode: "generative", degraded: false,
    conversation_id: 1, resolved_question: null, widened: false,
    ...overrides,
  };
}

/** A one-event stream: straight to `done`, the shape most of these tests need. */
async function* doneStreamOf(overrides: Partial<AIAnswer> = {}) {
  yield { event: "done", data: answer(overrides) };
}

const list = vi.fn();
const get = vi.fn();
const create = vi.fn();
const remove = vi.fn();
const askStream = vi.fn();
const resumeAskRun = vi.fn();
const cancelRun = vi.fn();
const retryRun = vi.fn();
const status = vi.fn();
const classifications = vi.fn();

vi.mock("@/api/ai", () => ({
  aiApi: {
    conversations: {
      list:   (...args: unknown[]) => list(...(args as [])),
      get:    (...args: unknown[]) => get(...(args as [])),
      create: (...args: unknown[]) => create(...(args as [])),
      remove: (...args: unknown[]) => remove(...(args as [])),
    },
    askStream: (...args: unknown[]) => askStream(...(args as [])),
    resumeAskRun: (...args: unknown[]) => resumeAskRun(...(args as [])),
    cancelRun: (...args: unknown[]) => cancelRun(...(args as [])),
    retryRun: (...args: unknown[]) => retryRun(...(args as [])),
    status:    (...args: unknown[]) => status(...(args as [])),
  },
}));

vi.mock("@/api/records", () => ({
  recordsApi: {
    classifications: (...args: unknown[]) => classifications(...(args as [])),
  },
}));

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
  Element.prototype.scrollIntoView = vi.fn();

  list.mockResolvedValue({ data: [] as ConversationSummary[] });
  create.mockResolvedValue({ data: detail() });
  get.mockResolvedValue({ data: detail() });
  askStream.mockImplementation(() => doneStreamOf());
  status.mockResolvedValue({ data: { generative: true, indexed_records: 4 } as AIStatus });
  classifications.mockResolvedValue({ data: { results: [] } });
});

describe("persisted conversations", () => {
  it("continues the most recent conversation rather than starting a new one", async () => {
    list.mockResolvedValue({ data: [summary({ id: 9, title: "Prior chat" })] });
    get.mockResolvedValue({
      data: detail({
        id: 9,
        turns: [
          {
            id: 1, question: "What does this paper conclude?", resolved_question: null,
            answer: "It concludes flooding is predictable.", message: null,
            state: "generative", degraded: false, widened: false,
            created_at: "2026-09-20T00:00:00.000Z", citations: [],
          },
        ],
      }),
    });

    renderScreen(<RAGChatPage />);

    expect(await screen.findByText("What does this paper conclude?")).toBeTruthy();
    expect(create).not.toHaveBeenCalled();
  });

  it("sends a follow-up as itself, not the whole transcript glued together", async () => {
    list.mockResolvedValue({ data: [summary({ id: 9 })] });
    get.mockResolvedValue({
      data: detail({
        id: 9,
        turns: [
          {
            id: 1, question: "What does this paper conclude?", resolved_question: null,
            answer: "It concludes flooding is predictable.", message: null,
            state: "generative", degraded: false, widened: false,
            created_at: "2026-09-20T00:00:00.000Z", citations: [],
          },
        ],
      }),
    });

    renderScreen(<RAGChatPage />);
    await screen.findByText("What does this paper conclude?");

    const input = screen.getByRole("textbox", { name: /ask a follow-up/i });
    await userEvent.type(input, "What about its limitations?");
    await userEvent.click(screen.getByRole("button", { name: /send message/i }));

    await waitFor(() => expect(askStream).toHaveBeenCalled());
    const [question, options] = askStream.mock.calls[0];
    expect(question).toBe("What about its limitations?");
    expect(options).toMatchObject({ conversationId: 9 });
  });

  it("opens the record deep link as a draft scoped to that Record, asking nothing", async () => {
    create.mockResolvedValue({ data: detail({ id: 9, record: 5 }) });

    renderScreen(<RAGChatPage />, { route: "/ai?record=5" });

    await waitFor(() => expect(create).toHaveBeenCalledWith({ record: 5 }));
    const input = await screen.findByRole("textbox", { name: /ask a follow-up/i });
    expect((input as HTMLTextAreaElement).value).toMatch(/record #5/i);
    expect(askStream).not.toHaveBeenCalled();
  });

  it("opens the record deep link on that Record's existing Conversation", async () => {
    list.mockResolvedValue({ data: [summary({ id: 7, record: 5 })] });
    get.mockResolvedValue({ data: detail({ id: 7, record: 5 }) });

    renderScreen(<RAGChatPage />, { route: "/ai?record=5" });

    await waitFor(() => expect(list).toHaveBeenCalledWith({ record: 5 }));
    await waitFor(() => expect(get).toHaveBeenCalledWith(7));
    expect(create).not.toHaveBeenCalled();
    expect(askStream).not.toHaveBeenCalled();
  });

  it("removes a conversation and falls back to what remains", async () => {
    list.mockResolvedValue({ data: [summary({ id: 9 })] });
    // The server answers for the conversation it was asked for (IR-548: the
    // page now shows the id the server returns, not the one it asked for).
    get.mockResolvedValue({ data: detail({ id: 9 }) });
    remove.mockResolvedValue({});

    renderScreen(<RAGChatPage />);
    await waitFor(() => expect(get).toHaveBeenCalled());
    list.mockResolvedValue({ data: [] });

    await userEvent.click(screen.getByRole("button", { name: /delete flooding/i }));

    await waitFor(() => expect(remove).toHaveBeenCalledWith(9));
    expect(create).toHaveBeenCalled();
  });
});

describe("the retired browser storage", () => {
  it("explains the sidebar emptying when old local chats are found", async () => {
    localStorage.setItem(LEGACY_STORAGE_KEY, "[]");

    renderScreen(<RAGChatPage />);

    expect(await screen.findByText(/your previous chats are gone/i)).toBeTruthy();
  });

  it("says nothing when there was never anything stored locally", async () => {
    renderScreen(<RAGChatPage />);
    await waitFor(() => expect(create).toHaveBeenCalled());

    expect(screen.queryByText(/your previous chats are gone/i)).toBeNull();
  });

  it("clears the legacy key once the notice is dismissed", async () => {
    localStorage.setItem(LEGACY_STORAGE_KEY, "[]");
    renderScreen(<RAGChatPage />);

    await userEvent.click(await screen.findByRole("button", { name: /dismiss/i }));

    expect(localStorage.getItem(LEGACY_STORAGE_KEY)).toBeNull();
    expect(screen.queryByText(/your previous chats are gone/i)).toBeNull();
  });
});

const PROHIBITED = [
  "Answer approach", "Why this approach", "Try instead", "Rerun with", "List papers",
  "search_passages", "find_records", "read_record_sections", "Research steps",
];

const SUMMARY = "These papers address the same problem, but their settings differ.";

/** A Turn as a pre-IR-595 server would have stored it: diagnostics included. */
function oldTurn(extra: Record<string, unknown> = {}) {
  return {
    id: 1, question: "Find flooding papers", resolved_question: null,
    answer: "Prior answer", message: null, state: "generative", degraded: false,
    widened: false, created_at: "2026-10-11", citations: [],
    routing: { lane: "listing", reason: "list_request", allowed_overrides: ["passage", "listing"] },
    research: { steps: [{ position: 0, tool: "search_passages", status: "ok" }], coverage_notes: [] },
    reasoning: "secret working",
    ...extra,
  } as never;
}

describe("clean answers (IR-596)", () => {
  function renderAt(route: string) {
    return renderScreen(
      <Routes>
        <Route path="/ai/conversations/:conversationId" element={<RAGChatPage />} />
      </Routes>,
      { route },
    );
  }

  it("reopens an old conversation as answer and citations only, with no diagnostics in the page", async () => {
    list.mockResolvedValue({ data: [summary({ id: 9 })] });
    get.mockResolvedValue({ data: detail({ id: 9, turns: [oldTurn()] }) });
    const { container } = renderAt("/ai/conversations/9");

    expect(await screen.findByText("Prior answer")).toBeInTheDocument();

    for (const prohibited of PROHIBITED) expect(screen.queryByText(new RegExp(prohibited, "i"))).toBeNull();
    expect(screen.queryByRole("button", { name: /reasoning|rerun|try instead/i })).toBeNull();
    expect(container.textContent).not.toContain("secret working");
  });

  it("shows a reopened turn's reasoning summary collapsed above its answer, and only when there is one", async () => {
    list.mockResolvedValue({ data: [summary({ id: 9 })] });
    get.mockResolvedValue({ data: detail({ id: 9, turns: [
      oldTurn({ id: 1, reasoning_summary: SUMMARY }),
      oldTurn({ id: 2, question: "And again?", answer: "Second answer" }),
    ] }) });
    renderAt("/ai/conversations/9");

    await screen.findByText("Prior answer");
    const toggles = screen.getAllByRole("button", { name: "Reasoning summary" });
    expect(toggles).toHaveLength(1);
    expect(toggles[0]).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByText(SUMMARY)).toBeNull();

    await userEvent.click(toggles[0]);
    expect(screen.getByText(SUMMARY)).toBeInTheDocument();
  });

  it("shows the persistent notice before any question is asked", async () => {
    renderScreen(<RAGChatPage />);

    expect(await screen.findByText(
      "Ask IRIS can make mistakes. Check important details against the cited papers.",
    )).toBeInTheDocument();
  });

  it("shows one status row from the activity frames, then the answer and summary, with no diagnostics", async () => {
    let release: () => void = () => {};
    const gate = new Promise<void>((resolve) => { release = resolve; });
    askStream.mockImplementation(() => (async function* () {
      yield { event: "activity", id: "1", data: { state: "thinking", label: "Thinking…" } };
      yield { event: "routing_decided", id: "1", data: { routing: { lane: "listing" } } };
      yield { event: "agent_step", id: "1", data: { position: 0, tool: "search_passages", status: "running" } };
      await gate;
      yield { event: "activity", id: "2", data: { state: "preparing", label: "Preparing your answer…" } };
      yield { event: "done", id: "3", data: answer({ answer: "Final answer.", reasoning_summary: SUMMARY }) };
    })());
    renderAt("/ai/conversations/1");

    await userEvent.type(await screen.findByRole("textbox", { name: /ask a follow-up/i }), "What predicts flooding?{Enter}");

    expect(await screen.findByRole("status")).toHaveTextContent("Thinking…");
    for (const prohibited of PROHIBITED) expect(screen.queryByText(new RegExp(prohibited, "i"))).toBeNull();

    release();
    expect(await screen.findByText("Final answer.")).toBeInTheDocument();
    expect(screen.queryByText("Thinking…")).toBeNull();
    expect(screen.queryByText("Preparing your answer…")).toBeNull();
    expect(screen.getByRole("button", { name: "Reasoning summary" })).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByText(SUMMARY)).toBeNull();
  });

  it("does not add a second message when a followed run's Turn is already on screen", async () => {
    const turn = oldTurn({ id: 41, answer: "Rainfall gauges feed the model." });
    list.mockResolvedValue({ data: [summary({ id: 9 })] });
    get.mockResolvedValue({ data: detail({ id: 9, turns: [turn], latest_run: { id: "r-5", state: "running", end_reason: "", question: "q", retry_of: null, last_sequence: 3 } }) });
    resumeAskRun.mockImplementation(() => (async function* () {
      yield { event: "done", id: "9", data: answer({ answer: "Rainfall gauges feed the model.", turn_id: 41, conversation_id: 9 }) };
    })());
    renderAt("/ai/conversations/9");

    await waitFor(() => expect(resumeAskRun).toHaveBeenCalled());
    await waitFor(() => expect(screen.queryByRole("status")).toBeNull());
    expect(screen.getAllByText("Rainfall gauges feed the model.")).toHaveLength(1);
  });
});


/** Shows where the router is, so a test can read the address bar. */
function Address() {
  const { pathname, search } = useLocation();
  return <output aria-label="address">{pathname + search}</output>;
}

function renderChat(route: string, state?: unknown) {
  return renderScreen(
    <>
      <RAGChatPage />
      <Address />
    </>,
    { route, state },
  );
}

describe("a question handed off from Discover (IR-559)", () => {
  const QUESTION = "Who is working on edge AI at CIT-U?";

  async function draftBox() {
    return (await screen.findByRole("textbox", { name: /ask a follow-up/i })) as HTMLTextAreaElement;
  }

  it("shows the exact question in an editable draft and sends nothing", async () => {
    renderChat("/ai", { draft: QUESTION });

    const box = await draftBox();
    await waitFor(() => expect(box.value).toBe(QUESTION));
    expect(askStream).not.toHaveBeenCalled();

    await userEvent.type(box, " today");
    expect(box.value).toBe(`${QUESTION} today`);
    expect(askStream).not.toHaveBeenCalled();
  });

  it("opens a new Conversation for the handoff rather than continuing the latest", async () => {
    list.mockResolvedValue({ data: [summary({ id: 9 })] });

    renderChat("/ai", { draft: QUESTION });

    await waitFor(() => expect(create).toHaveBeenCalledWith());
    expect(get).not.toHaveBeenCalled();
  });

  it("creates exactly one Turn on explicit Send", async () => {
    create.mockResolvedValue({ data: detail({ id: 3 }) });
    renderChat("/ai", { draft: QUESTION });
    const box = await draftBox();
    await waitFor(() => expect(box.value).toBe(QUESTION));

    await userEvent.click(screen.getByRole("button", { name: /send message/i }));

    await waitFor(() => expect(askStream).toHaveBeenCalledTimes(1));
    expect(askStream.mock.calls[0][0]).toBe(QUESTION);
    expect(askStream.mock.calls[0][1]).toMatchObject({ conversationId: 3 });
  });

  it("fills the draft from a legacy ?q= link once and removes it from the address", async () => {
    renderChat(`/ai?q=${encodeURIComponent(QUESTION)}`);

    const box = await draftBox();
    await waitFor(() => expect(box.value).toBe(QUESTION));
    await waitFor(() => expect(screen.getByLabelText("address").textContent).toBe("/ai/conversations/1"));
    expect(askStream).not.toHaveBeenCalled();
  });

  it("does not refill a draft the reader has cleared", async () => {
    renderChat(`/ai?q=${encodeURIComponent(QUESTION)}`);
    const box = await draftBox();
    await waitFor(() => expect(box.value).toBe(QUESTION));
    await waitFor(() => expect(screen.getByLabelText("address").textContent).toBe("/ai/conversations/1"));

    await userEvent.clear(box);
    await new Promise((r) => setTimeout(r, 20));

    expect(box.value).toBe("");
    expect(create).toHaveBeenCalledTimes(1);
  });
});

describe("owned conversation URLs (IR-548)", () => {
  /** The page under its real routes, with the address bar and a Back button. */
  function Chrome() {
    const navigate = useNavigate();
    return (
      <>
        <RAGChatPage />
        <Address />
        <button type="button" onClick={() => navigate(-1)}>Go back</button>
      </>
    );
  }

  function renderRoutes(route: string, state?: unknown) {
    return renderScreen(
      <Routes>
        <Route path="/ai" element={<Chrome />} />
        <Route path="/ai/conversations/:conversationId" element={<Chrome />} />
      </Routes>,
      { route, state },
    );
  }

  const address = () => screen.getByLabelText("address").textContent;

  function run(overrides: Partial<LatestAskRun> = {}): LatestAskRun {
    return {
      id: "r-1", state: "running", end_reason: "", question: "What predicts flooding?",
      retry_of: null, last_sequence: 3, ...overrides,
    };
  }

  async function* runEvents(runId: string, ...events: { event: string; data: unknown }[]) {
    yield { event: "run_queued", id: "1", data: { run_id: runId, state: "queued" } };
    for (const event of events) yield event;
  }

  it("gives the opened conversation its own address", async () => {
    list.mockResolvedValue({ data: [summary({ id: 9 })] });
    get.mockResolvedValue({ data: detail({ id: 9 }) });

    renderRoutes("/ai");

    await waitFor(() => expect(address()).toBe("/ai/conversations/9"));
  });

  it("opens the conversation its address names, not the latest one", async () => {
    list.mockResolvedValue({ data: [summary({ id: 9 }), summary({ id: 7, title: "Older" })] });
    get.mockResolvedValue({ data: detail({ id: 7, title: "Older" }) });

    renderRoutes("/ai/conversations/7");

    await waitFor(() => expect(get).toHaveBeenCalledWith(7));
    expect(get).not.toHaveBeenCalledWith(9);
    expect(create).not.toHaveBeenCalled();
  });

  it("moves between conversations by address, and back again", async () => {
    list.mockResolvedValue({ data: [summary({ id: 9, title: "Flooding" }), summary({ id: 7, title: "Bridges" })] });
    get.mockImplementation(async (id: number) => ({
      data: detail({ id, title: id === 9 ? "Flooding" : "Bridges", turns: [{
        id: id * 10, question: `Question in ${id}`, resolved_question: null, answer: "An answer",
        message: null, state: "generative", degraded: false, widened: false,
        created_at: "2026-10-14", citations: [],
      }] }),
    }));

    renderRoutes("/ai/conversations/9");
    expect(await screen.findByText("Question in 9")).toBeTruthy();

    await userEvent.click(screen.getByRole("link", { name: /^Bridges/ }));
    expect(await screen.findByText("Question in 7")).toBeTruthy();
    expect(address()).toBe("/ai/conversations/7");

    await userEvent.click(screen.getByRole("button", { name: "Go back" }));
    expect(await screen.findByText("Question in 9")).toBeTruthy();
    expect(address()).toBe("/ai/conversations/9");
  });

  it("says a missing or someone else's conversation is unavailable, and asks nothing", async () => {
    get.mockRejectedValue({ response: { status: 404 } });

    renderRoutes("/ai/conversations/404");

    expect(await screen.findByText(/this conversation is not available/i)).toBeTruthy();
    expect(create).not.toHaveBeenCalled();
    expect(askStream).not.toHaveBeenCalled();
    expect((screen.getByRole("textbox", { name: /ask a follow-up/i }) as HTMLTextAreaElement).disabled).toBe(true);
  });

  it("follows a run still answering when the conversation is opened", async () => {
    get.mockResolvedValue({ data: detail({ id: 9, latest_run: run({ id: "r-5" }) }) });
    resumeAskRun.mockReturnValue(runEvents("r-5", {
      event: "done", data: { ...answer({ answer: "Rainfall gauges help." }), turn_id: 50 },
    }));

    renderRoutes("/ai/conversations/9");

    expect(await screen.findByText("Rainfall gauges help.")).toBeTruthy();
    expect(screen.getByText("What predicts flooding?")).toBeTruthy();
    expect(resumeAskRun).toHaveBeenCalledWith("r-5", 0, expect.any(AbortSignal));
    expect(askStream).not.toHaveBeenCalled();
  });

  it("stops a run when the reader asks, and shows it stopped", async () => {
    let release: () => void = () => {};
    const gate = new Promise<void>((resolve) => { release = resolve; });
    get.mockResolvedValue({ data: detail({ id: 9, latest_run: run({ id: "r-6" }) }) });
    resumeAskRun.mockReturnValue((async function* () {
      yield { event: "run_queued", id: "1", data: { run_id: "r-6", state: "queued" } };
      await gate;
      yield { event: "run_cancelled", id: "2", data: { run_id: "r-6", state: "cancelled", reason: "cancelled" } };
    })());
    cancelRun.mockImplementation(async () => { release(); return { data: { run_id: "r-6", state: "cancelled" } }; });

    renderRoutes("/ai/conversations/9");
    await userEvent.click(await screen.findByRole("button", { name: /stop answering/i }));

    expect(cancelRun).toHaveBeenCalledWith("r-6");
    expect(await screen.findByText(/you stopped this question/i)).toBeTruthy();
    expect(screen.getByRole("button", { name: /retry/i })).toBeTruthy();
  });

  it("retries a stopped question as a new run and shows its answer", async () => {
    get.mockResolvedValue({
      data: detail({ id: 9, latest_run: run({ id: "r-7", state: "cancelled", end_reason: "cancelled" }) }),
    });
    retryRun.mockResolvedValue({ data: { run_id: "r-8", retry_of: "r-7", state: "queued" } });
    resumeAskRun.mockReturnValue(runEvents("r-8", {
      event: "done", data: { ...answer({ answer: "Answered on retry." }), turn_id: 51 },
    }));

    renderRoutes("/ai/conversations/9");
    expect(await screen.findByText(/you stopped this question/i)).toBeTruthy();
    expect(resumeAskRun).not.toHaveBeenCalled();

    await userEvent.click(screen.getByRole("button", { name: /retry/i }));

    expect(retryRun).toHaveBeenCalledWith("r-7");
    expect(await screen.findByText("Answered on retry.")).toBeTruthy();
    expect(resumeAskRun).toHaveBeenCalledWith("r-8", 0, expect.any(AbortSignal));
    expect(screen.queryByRole("button", { name: /retry/i })).toBeNull();
  });

  it("keeps a Record's conversation and its draft under the conversation's address", async () => {
    create.mockResolvedValue({ data: detail({ id: 4, record: 5 }) });
    get.mockResolvedValue({ data: detail({ id: 4, record: 5 }) });

    renderRoutes("/ai?record=5");

    await waitFor(() => expect(address()).toBe("/ai/conversations/4"));
    const box = (await screen.findByRole("textbox", { name: /ask a follow-up/i })) as HTMLTextAreaElement;
    await waitFor(() => expect(box.value).toMatch(/record #5/i));
    expect(askStream).not.toHaveBeenCalled();
  });
});

/**
 * jsdom lays nothing out, so the page is measured as `width` wide: the width
 * that decides whether history and sources sit beside the answer or open as
 * drawers over it (IR-570).
 */
function pageAt(width: number) {
  const watching = new Set<{ target: Element; callback: ResizeObserverCallback; observer: ResizeObserver }>();
  const report = (target: Element, callback: ResizeObserverCallback, observer: ResizeObserver, w: number) =>
    callback([{ target, contentRect: { width: w } } as unknown as ResizeObserverEntry], observer);
  vi.stubGlobal(
    "ResizeObserver",
    class {
      constructor(private readonly callback: ResizeObserverCallback) {}
      observe(target: Element) {
        const entry = { target, callback: this.callback, observer: this as unknown as ResizeObserver };
        watching.add(entry);
        report(target, this.callback, entry.observer, width);
      }
      unobserve() {}
      disconnect() {}
    },
  );
  return {
    resizeTo: (next: number) =>
      act(() => watching.forEach((w) => report(w.target, w.callback, w.observer, next))),
  };
}

/** Whether `el` sits inside an inert subtree, which a reader cannot reach. */
function inert(el: Element): boolean {
  return el.closest("[inert]") !== null;
}

describe("Ask IRIS on a phone (IR-570)", () => {
  const citation: Citation = {
    marker: 1, chunk_id: 11, record_id: 7, record_title: "Flood Prediction", page: 4,
    text: "gauges predicted flooding a day ahead", context_path: ["Flood Prediction"], regions: [],
  };

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  async function openAt360() {
    list.mockResolvedValue({ data: [summary({ id: 9, title: "Prior chat" })] });
    get.mockResolvedValue({ data: detail({ id: 9 }) });
    pageAt(360);
    renderScreen(<RAGChatPage />);
    return (await screen.findByRole("textbox", { name: /ask a follow-up/i })) as HTMLTextAreaElement;
  }

  it("gives the answer the whole width, with history and sources closed", async () => {
    const composer = await openAt360();

    expect(screen.queryByRole("complementary", { name: "Chat history" })).not.toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(inert(composer)).toBe(false);
    composer.focus();
    expect(composer).toHaveFocus();
    // One line on a phone; its accessible name keeps the whole phrase.
    expect(composer).toHaveAttribute("placeholder", "Ask a follow-up…");
  });

  it("opens history as a labelled drawer, keeps focus in it and gives it back on close", async () => {
    await openAt360();
    const opener = screen.getByRole("button", { name: "Show chat history" });

    await userEvent.click(opener);

    const drawer = screen.getByRole("dialog", { name: "Chat history" });
    expect(drawer).toContainElement(document.activeElement as HTMLElement);
    expect(screen.getByRole("link", { name: /Prior chat/ })).toBeInTheDocument();
    // Everything behind the drawer waits, so focus cannot wander out to it.
    expect(inert(screen.getByRole("textbox", { name: /ask a follow-up/i }))).toBe(true);

    await userEvent.keyboard("{Escape}");

    expect(screen.queryByRole("dialog", { name: "Chat history" })).not.toBeInTheDocument();
    await waitFor(() => expect(opener).toHaveFocus());
    expect(inert(screen.getByRole("textbox", { name: /ask a follow-up/i }))).toBe(false);
  });

  it("closes the history drawer from its own close button", async () => {
    await openAt360();
    const opener = screen.getByRole("button", { name: "Show chat history" });
    await userEvent.click(opener);

    await userEvent.click(screen.getByRole("button", { name: "Close chat history" }));

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    await waitFor(() => expect(opener).toHaveFocus());
  });

  it("offers New chat inside the history drawer, where a phone has room for it", async () => {
    await openAt360();
    create.mockResolvedValue({ data: detail({ id: 12 }) });
    await userEvent.click(screen.getByRole("button", { name: "Show chat history" }));

    await userEvent.click(screen.getByRole("button", { name: "New chat" }));

    await waitFor(() => expect(create).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  it("keeps an answer's sources closed until asked for, then opens them as a drawer", async () => {
    const composer = await openAt360();
    askStream.mockImplementation(() => doneStreamOf({ citations: [citation] }));

    await userEvent.type(composer, "What predicts flooding?");
    await userEvent.click(screen.getByRole("button", { name: /send message/i }));
    await screen.findByText(/Rainfall gauges predict flooding/);

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    const opener = screen.getByRole("button", { name: "Show sources" });
    await userEvent.click(opener);

    const drawer = screen.getByRole("dialog", { name: "Referenced passages" });
    expect(drawer).toContainElement(document.activeElement as HTMLElement);
    expect(screen.getByText(/gauges predicted flooding a day ahead/)).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Hide sources panel" }));

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    await waitFor(() => expect(opener).toHaveFocus());
  });

  it("closes a drawer and returns to the columns when the page widens", async () => {
    list.mockResolvedValue({ data: [summary({ id: 9, title: "Prior chat" })] });
    get.mockResolvedValue({ data: detail({ id: 9 }) });
    const page = pageAt(360);
    renderScreen(<RAGChatPage />);
    await screen.findByRole("textbox", { name: /ask a follow-up/i });
    await userEvent.click(screen.getByRole("button", { name: "Show chat history" }));

    page.resizeTo(1100);

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.getByRole("complementary", { name: "Chat history" })).toBeInTheDocument();
  });

  it("keeps history beside the answer on a desktop, as before", async () => {
    list.mockResolvedValue({ data: [summary({ id: 9, title: "Prior chat" })] });
    get.mockResolvedValue({ data: detail({ id: 9 }) });
    pageAt(1100);
    renderScreen(<RAGChatPage />);

    await screen.findByRole("textbox", { name: /ask a follow-up/i });

    expect(screen.getByRole("complementary", { name: "Chat history" })).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});
