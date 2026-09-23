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

  it("actually asks the record deep-link's prefilled question, rather than leaving it unanswered", async () => {
    // A `?record=` link starts a Conversation scoped to that Record and
    // used to only display the prefilled question as an inert user bubble,
    // never asking it -- fixed alongside the rest of this ticket so the
    // reader lands on a real answer, not a question nobody sent.
    create.mockResolvedValue({ data: detail({ id: 9, record: 5 }) });
    askStream.mockImplementation(() => doneStreamOf({ conversation_id: 9 }));

    renderScreen(<RAGChatPage />, { route: "/ai/ask?record=5" });

    await waitFor(() => expect(create).toHaveBeenCalledWith({ record: 5 }));
    await waitFor(() => expect(askStream).toHaveBeenCalled());
    const [question, options] = askStream.mock.calls[0];
    expect(question).toMatch(/record #5/i);
    expect(options).toMatchObject({ conversationId: 9 });

    // The `[1]` marker itself renders as an inline citation chip (IR-329),
    // not literal text -- with no citation supplied here it resolves to
    // nothing, so only the surrounding prose is asserted.
    expect(await screen.findByText(/Rainfall gauges predict flooding/)).toBeTruthy();
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
