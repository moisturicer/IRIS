/**
 * Paper Chat as a Conversation scoped to the Record being viewed (IR-298).
 *
 * The claim this ticket makes is that Paper Chat stopped being a second,
 * memoryless chat system: it opens or continues the Conversation already
 * scoped to this paper, it never prefixes the question with the paper's
 * title, and a reader can widen the search on purpose. These are the
 * assertions that would catch the old behaviour coming back.
 *
 * Every query goes through the accessible tree, by role and accessible name.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";

import { expectNoBlockingA11yViolations } from "@/test/axe";
import { renderScreen, screen, userEvent, waitFor } from "@/test/render";
import type { AIAnswer, ConversationDetail } from "@/types/ai";
import type { RecordDetail } from "@/types/records";

import { PaperChatPanel } from "./PaperChatDock";

const record = { id: 7, title: "Flood Prediction in the Mananga Catchment" } as RecordDetail;

function conversation(overrides: Partial<ConversationDetail> = {}): ConversationDetail {
  return {
    id:            42,
    title:         "",
    record:        record.id,
    record_title:  record.title,
    turn_count:    0,
    created_at:    "2026-09-20T00:00:00.000Z",
    updated_at:    "2026-09-20T00:00:00.000Z",
    turns:         [],
    ...overrides,
  };
}

function answer(overrides: Partial<AIAnswer> = {}): AIAnswer {
  return {
    answer:             "The network reduced mean absolute error by twelve per cent [1].",
    citations:          [],
    sources:            [],
    message:            null,
    mode:               "generative",
    degraded:           false,
    conversation_id:    42,
    resolved_question:  null,
    widened:            false,
    ...overrides,
  };
}

const findOrCreateForRecord = vi.fn();
const ask = vi.fn();

vi.mock("@/api/ai", () => ({
  aiApi: {
    conversations: {
      findOrCreateForRecord: (...args: unknown[]) => findOrCreateForRecord(...(args as [])),
    },
    ask: (...args: unknown[]) => ask(...(args as [])),
  },
}));

const noop = () => {};

beforeEach(() => {
  vi.clearAllMocks();
  // jsdom does not implement it; the panel calls it to keep the transcript
  // scrolled to the newest message.
  Element.prototype.scrollIntoView = vi.fn();
  findOrCreateForRecord.mockResolvedValue({ data: conversation() });
  ask.mockResolvedValue({ data: answer() });
});

describe("Paper Chat opens or continues a Conversation scoped to the Record", () => {
  it("starts a Conversation scoped to the Record when none exists yet", async () => {
    renderScreen(
      <PaperChatPanel record={record} dock="floating" onDockChange={noop} onClose={noop} />,
    );

    await waitFor(() => expect(findOrCreateForRecord).toHaveBeenCalledWith(record.id));
  });

  it("continues the existing Conversation for this Record rather than starting a new one", async () => {
    findOrCreateForRecord.mockResolvedValue({
      data: conversation({
        turns: [
          {
            id: 1, question: "What does this paper conclude?",
            resolved_question: null,
            answer: "It concludes rainfall gauges predict flooding well.",
            message: null, state: "generative", degraded: false, widened: false,
            created_at: "2026-09-20T00:00:00.000Z", citations: [],
          },
        ],
      }),
    });

    renderScreen(
      <PaperChatPanel record={record} dock="floating" onDockChange={noop} onClose={noop} />,
    );

    expect(await screen.findByText("What does this paper conclude?")).toBeTruthy();
    expect(
      screen.getByText("It concludes rainfall gauges predict flooding well."),
    ).toBeTruthy();
  });

  it("never prefixes the question with the paper's title", async () => {
    renderScreen(
      <PaperChatPanel record={record} dock="floating" onDockChange={noop} onClose={noop} />,
    );
    await waitFor(() => expect(findOrCreateForRecord).toHaveBeenCalled());

    const input = screen.getByRole("textbox", { name: /ask about this paper/i });
    await userEvent.type(input, "What datasets were used?");
    await userEvent.click(screen.getByRole("button", { name: /send/i }));

    await waitFor(() => expect(ask).toHaveBeenCalled());
    const [question] = ask.mock.calls[0];
    expect(question).toBe("What datasets were used?");
  });

  it("sends the Conversation id so the question is stored as a Turn", async () => {
    renderScreen(
      <PaperChatPanel record={record} dock="floating" onDockChange={noop} onClose={noop} />,
    );
    await waitFor(() => expect(findOrCreateForRecord).toHaveBeenCalled());

    await userEvent.type(
      screen.getByRole("textbox", { name: /ask about this paper/i }),
      "What datasets were used?",
    );
    await userEvent.click(screen.getByRole("button", { name: /send/i }));

    await waitFor(() => expect(ask).toHaveBeenCalled());
    const [, options] = ask.mock.calls[0];
    expect(options).toMatchObject({ conversationId: 42, widen: false });
  });
});

describe("the widen control", () => {
  it("defaults to searching only this paper", async () => {
    renderScreen(
      <PaperChatPanel record={record} dock="floating" onDockChange={noop} onClose={noop} />,
    );

    const toggle = await screen.findByRole("button", { name: "This paper" });
    expect(toggle.getAttribute("aria-pressed")).toBe("false");
  });

  it("widens the search only once the reader turns it on, never on its own", async () => {
    renderScreen(
      <PaperChatPanel record={record} dock="floating" onDockChange={noop} onClose={noop} />,
    );
    await waitFor(() => expect(findOrCreateForRecord).toHaveBeenCalled());

    await userEvent.click(await screen.findByRole("button", { name: "This paper" }));
    await userEvent.type(
      screen.getByRole("textbox", { name: /ask about this paper/i }),
      "How does this compare to other work?",
    );
    await userEvent.click(screen.getByRole("button", { name: /send/i }));

    await waitFor(() => expect(ask).toHaveBeenCalled());
    const [, options] = ask.mock.calls[0];
    expect(options).toMatchObject({ widen: true });
  });

  it("says when an answer left this paper's scope", async () => {
    ask.mockResolvedValue({ data: answer({ widened: true }) });
    renderScreen(
      <PaperChatPanel record={record} dock="floating" onDockChange={noop} onClose={noop} />,
    );
    await waitFor(() => expect(findOrCreateForRecord).toHaveBeenCalled());

    await userEvent.type(
      screen.getByRole("textbox", { name: /ask about this paper/i }),
      "How does this compare to other work?",
    );
    await userEvent.click(screen.getByRole("button", { name: /send/i }));

    expect(await screen.findByText(/Searched all papers/i)).toBeTruthy();
  });
});

describe("accessibility", () => {
  it("has no serious or critical accessibility violations", async () => {
    const { container } = renderScreen(
      <PaperChatPanel record={record} dock="floating" onDockChange={noop} onClose={noop} />,
    );
    await waitFor(() => expect(findOrCreateForRecord).toHaveBeenCalled());

    await expectNoBlockingA11yViolations(container);
  });
});
