import { routingFixture } from "@/test/routingFixture";
/**
 * Ask IRIS on persisted Conversations (IR-298).
 *
 * Chat history used to live in browser storage and every question glued the
 * whole prior transcript onto itself before sending it. Both are gone: this
 * asserts the replacement — the page reads and writes Conversations through
 * the API, a question is sent as itself, and a reader whose old chats
 * vanished is told why rather than left to wonder.
 *
 * Every query goes through the accessible tree, by role and accessible name.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useLocation } from "react-router-dom";
import { renderScreen, screen, userEvent, waitFor } from "@/test/render";
import type { AIAnswer, AIStatus, ConversationDetail, ConversationSummary } from "@/types/ai";

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

it("reruns an old answer using its original turn after newer discussion", async () => {
  list.mockResolvedValue({ data: [summary({ id: 9 })] });
  get.mockResolvedValue({ data: detail({ id: 9, turns: [{
    id: 1, question: "Find flooding papers", resolved_question: "A resolved question",
    answer: "Prior answer", message: null, state: "generative", degraded: false,
    widened: true, created_at: "2026-10-11", citations: [], routing: routingFixture,
  }, {
    id: 2, question: "Now discuss a different topic", resolved_question: null,
    answer: "Newer answer", message: null, state: "generative", degraded: false,
    widened: false, created_at: "2026-10-11", citations: [],
  }] }) });
  renderScreen(<RAGChatPage />);
  await userEvent.click(await screen.findByRole("button", { name: "Rerun with List papers" }));
  await waitFor(() => expect(askStream).toHaveBeenCalledWith("Find flooding papers", {
    conversationId: 9, routeOverride: "listing", widen: true, routeOverrideTurnId: 1,
  }));
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
    await waitFor(() => expect(screen.getByLabelText("address").textContent).toBe("/ai"));
    expect(askStream).not.toHaveBeenCalled();
  });

  it("does not refill a draft the reader has cleared", async () => {
    renderChat(`/ai?q=${encodeURIComponent(QUESTION)}`);
    const box = await draftBox();
    await waitFor(() => expect(box.value).toBe(QUESTION));
    await waitFor(() => expect(screen.getByLabelText("address").textContent).toBe("/ai"));

    await userEvent.clear(box);
    await new Promise((r) => setTimeout(r, 20));

    expect(box.value).toBe("");
    expect(create).toHaveBeenCalledTimes(1);
  });
});
