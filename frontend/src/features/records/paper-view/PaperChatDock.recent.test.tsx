/**
 * Paper Chat continues a recent Conversation or starts a new one (IR-584).
 * Queries go through the accessible tree, by role and name.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";

import { renderScreen, screen, userEvent, waitFor } from "@/test/render";
import type { ConversationDetail, ConversationSummary, ConversationTurn } from "@/types/ai";
import type { RecordDetail } from "@/types/records";

import { PaperChatPanel } from "./PaperChatDock";

const record = { id: 7, title: "Flood Prediction in the Mananga Catchment" } as RecordDetail;

const list = vi.fn();
const findForRecord = vi.fn();
const create = vi.fn();
const askStream = vi.fn();
const get = vi.fn();

vi.mock("@/api/runtimeReader", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/api/runtimeReader")>()),
  useReaderPath: () => "django",
}));

vi.mock("@/api/ai", () => ({
  aiApi: {
    conversations: {
      list: (...a: unknown[]) => list(...(a as [])),
      findForRecord: (...a: unknown[]) => findForRecord(...(a as [])),
      create: (...a: unknown[]) => create(...(a as [])),
      get: (...a: unknown[]) => get(...(a as [])),
    },
    askStream: (...a: unknown[]) => askStream(...(a as [])),
    resumeAskRun: vi.fn(),
    cancelRun: vi.fn(),
    retryRun: vi.fn(),
  },
}));

function summary(id: number, title: string, overrides: Partial<ConversationSummary> = {}): ConversationSummary {
  return {
    id, title, record: record.id, record_title: record.title, turn_count: 1,
    created_at: "2026-09-20T00:00:00.000Z", updated_at: "2026-09-20T00:00:00.000Z", ...overrides,
  };
}

function turn(id: number, question: string, answer: string): ConversationTurn {
  return {
    id, question, resolved_question: null, answer, message: null, state: "generative",
    degraded: false, widened: false, created_at: "2026-09-20T00:00:00.000Z", citations: [],
  } as unknown as ConversationTurn;
}

function detail(id: number, title: string, turns: ConversationTurn[] = []): ConversationDetail {
  return { ...summary(id, title, { turn_count: turns.length }), turns, latest_run: null } as ConversationDetail;
}

const noop = () => {};

beforeEach(() => {
  vi.clearAllMocks();
  Element.prototype.scrollIntoView = vi.fn();
  list.mockResolvedValue({ data: [summary(42, "Datasets used"), summary(43, "Error rates")] });
  findForRecord.mockResolvedValue(detail(42, "Datasets used", [turn(1, "Which datasets?", "Gauge data from 2010.")]));
  get.mockImplementation(async (id: number) => ({
    data: id === 43
      ? detail(43, "Error rates", [turn(2, "How big is the error?", "Twelve per cent lower.")])
      : detail(42, "Datasets used", [turn(1, "Which datasets?", "Gauge data from 2010.")]),
  }));
  create.mockResolvedValue({ data: detail(99, "") });
  askStream.mockImplementation(async function* () {
    yield { event: "done", data: { answer: "ok", citations: [], sources: [], message: null, mode: "generative", degraded: false, conversation_id: 99, resolved_question: null, widened: false } };
  });
});

describe("recent chats and New chat (IR-584)", () => {
  it("lists the reader's own chats for this Record beside starters, and sends nothing on open or on a starter", async () => {
    findForRecord.mockResolvedValue(null);
    renderScreen(<PaperChatPanel record={record} onClose={noop} />);
    const recent = await screen.findByRole("list", { name: /recent chats about this paper/i });
    expect(recent).toHaveTextContent("Datasets used");
    expect(list).toHaveBeenCalledWith({ record: record.id });
    expect(screen.getByRole("button", { name: /new chat/i })).toBeInTheDocument();

    await userEvent.click(await screen.findByRole("button", { name: "What are the key findings?" }));
    expect(screen.getByRole("textbox", { name: /ask about this paper/i })).toHaveValue("What are the key findings?");
    expect(askStream).not.toHaveBeenCalled();
    expect(create).not.toHaveBeenCalled();
  });

  it("restores a recent chat's own messages, and keeps each chat's unsent draft apart", async () => {
    renderScreen(<PaperChatPanel record={record} onClose={noop} />);
    expect(await screen.findByText("Gauge data from 2010.")).toBeInTheDocument();
    const box = screen.getByRole("textbox", { name: /ask about this paper/i });
    await userEvent.type(box, "half a question");

    await userEvent.click(screen.getByRole("button", { name: /recent chats/i }));
    await userEvent.click(await screen.findByRole("button", { name: /error rates/i }));
    expect(await screen.findByText("Twelve per cent lower.")).toBeInTheDocument();
    expect(screen.queryByText("Gauge data from 2010.")).toBeNull();
    expect(screen.getByRole("textbox", { name: /ask about this paper/i })).toHaveValue("");

    await userEvent.click(screen.getByRole("button", { name: /recent chats/i }));
    await userEvent.click(await screen.findByRole("button", { name: /datasets used/i }));
    expect(await screen.findByText("Gauge data from 2010.")).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: /ask about this paper/i })).toHaveValue("half a question");
    expect(askStream).not.toHaveBeenCalled();
  });

  it("starts a distinct Conversation only with the first question after New chat", async () => {
    renderScreen(<PaperChatPanel record={record} onClose={noop} />);
    expect(await screen.findByText("Gauge data from 2010.")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: /new chat/i }));
    expect(await screen.findByRole("group", { name: /suggested questions/i })).toBeInTheDocument();
    expect(screen.queryByText("Gauge data from 2010.")).toBeNull();
    expect(create).not.toHaveBeenCalled();

    await userEvent.type(screen.getByRole("textbox", { name: /ask about this paper/i }), "A separate question{Enter}");
    await waitFor(() => expect(create).toHaveBeenCalledTimes(1));
    expect(create).toHaveBeenCalledWith({ record: record.id });
  });

  it("keeps a late answer in the chat that asked it after the reader switches", async () => {
    let release: () => void = () => {};
    const gate = new Promise<void>((r) => { release = r; });
    askStream.mockImplementation(() => (async function* () {
      await gate;
      yield { event: "done", data: { answer: "Late answer.", citations: [], sources: [], message: null, mode: "generative", degraded: false, conversation_id: 42, resolved_question: null, widened: false, turn_id: 7 } };
    })());
    renderScreen(<PaperChatPanel record={record} onClose={noop} />);
    await screen.findByText("Gauge data from 2010.");
    await userEvent.type(screen.getByRole("textbox", { name: /ask about this paper/i }), "Slow one{Enter}");

    await userEvent.click(screen.getByRole("button", { name: /recent chats/i }));
    await userEvent.click(await screen.findByRole("button", { name: /error rates/i }));
    await screen.findByText("Twelve per cent lower.");

    release();
    await new Promise((r) => setTimeout(r, 50));
    expect(screen.queryByText("Late answer.")).toBeNull();
  });

  it("shows no chat metadata when the list is refused", async () => {
    list.mockRejectedValue({ response: { status: 404 } });
    findForRecord.mockResolvedValue(null);
    renderScreen(<PaperChatPanel record={record} onClose={noop} />);
    await screen.findByRole("group", { name: /suggested questions/i });
    expect(screen.queryByRole("list", { name: /recent chats/i })).toBeNull();
    expect(screen.getByRole("button", { name: /recent chats/i })).toBeDisabled();
  });

  it("names the pinned subject after a cross-Record citation and still offers this paper's recent chats", async () => {
    get.mockImplementation(async (id: number) => ({
      data: { ...detail(id, "Elsewhere", []), record: 8, record_title: "Rainfall Gauges in Cebu" },
    }));
    renderScreen(
      <PaperChatPanel record={record} onClose={noop} returnTo={{ conversationId: 60, turnId: 1, key: "k" } as never} />,
    );
    expect(await screen.findByText(/chatting about rainfall gauges in cebu/i)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /recent chats/i }));
    expect(await screen.findByRole("button", { name: /datasets used/i })).toBeInTheDocument();
  });
});
