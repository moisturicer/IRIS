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
import { useState } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { expectNoBlockingA11yViolations } from "@/test/axe";
import { renderScreen, screen, userEvent, waitFor, within } from "@/test/render";
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

/** A one-event stream: straight to `done`, the shape most of these tests need. */
async function* doneStreamOf(overrides: Partial<AIAnswer> = {}) {
  yield { event: "done", data: answer(overrides) };
}

const findForRecord = vi.fn();
const create = vi.fn();
const askStream = vi.fn();

vi.mock("@/api/ai", () => ({
  aiApi: {
    conversations: {
      findForRecord: (...args: unknown[]) => findForRecord(...(args as [])),
      create: (...args: unknown[]) => create(...(args as [])),
    },
    askStream: (...args: unknown[]) => askStream(...(args as [])),
  },
}));

const noop = () => {};

beforeEach(() => {
  vi.clearAllMocks();
  // jsdom does not implement it. The panel must not call it (IR-351); the
  // stub is here so a regression fails an assertion rather than throwing.
  Element.prototype.scrollIntoView = vi.fn();
  findForRecord.mockResolvedValue(conversation());
  create.mockResolvedValue({ data: conversation({ id: 43 }) });
  askStream.mockImplementation(() => doneStreamOf());
});

describe("Paper Chat opens or continues a Conversation scoped to the Record", () => {
  it("opens on no Conversation, and starts one scoped to the Record only with the first question (IR-569)", async () => {
    findForRecord.mockResolvedValue(null);
    renderScreen(
      <PaperChatPanel record={record} onClose={noop} />,
    );

    await waitFor(() => expect(findForRecord).toHaveBeenCalledWith(record.id));
    expect(await screen.findByRole("group", { name: /suggested questions/i })).toBeInTheDocument();
    expect(create).not.toHaveBeenCalled();

    await userEvent.type(screen.getByRole("textbox", { name: /ask about this paper/i }), "What datasets were used?");
    await userEvent.click(screen.getByRole("button", { name: /send/i }));

    await waitFor(() => expect(askStream).toHaveBeenCalled());
    expect(create).toHaveBeenCalledWith({ record: record.id });
    expect(askStream.mock.calls[0][1]).toMatchObject({ conversationId: 43 });
  });

  it("continues the existing Conversation for this Record rather than starting a new one", async () => {
    findForRecord.mockResolvedValue(conversation({
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
    );

    renderScreen(
      <PaperChatPanel record={record} onClose={noop} />,
    );

    expect(await screen.findByText("What does this paper conclude?")).toBeTruthy();
    expect(
      screen.getByText("It concludes rainfall gauges predict flooding well."),
    ).toBeTruthy();
  });

  it("never prefixes the question with the paper's title", async () => {
    renderScreen(
      <PaperChatPanel record={record} onClose={noop} />,
    );
    await waitFor(() => expect(findForRecord).toHaveBeenCalled());

    const input = screen.getByRole("textbox", { name: /ask about this paper/i });
    await userEvent.type(input, "What datasets were used?");
    await userEvent.click(screen.getByRole("button", { name: /send/i }));

    await waitFor(() => expect(askStream).toHaveBeenCalled());
    const [question] = askStream.mock.calls[0];
    expect(question).toBe("What datasets were used?");
  });

  it("sends the Conversation id so the question is stored as a Turn", async () => {
    renderScreen(
      <PaperChatPanel record={record} onClose={noop} />,
    );
    await waitFor(() => expect(findForRecord).toHaveBeenCalled());

    await userEvent.type(
      screen.getByRole("textbox", { name: /ask about this paper/i }),
      "What datasets were used?",
    );
    await userEvent.click(screen.getByRole("button", { name: /send/i }));

    await waitFor(() => expect(askStream).toHaveBeenCalled());
    const [, options] = askStream.mock.calls[0];
    expect(options).toMatchObject({ conversationId: 42, widen: false });
  });
});

describe("the widen control", () => {
  it("defaults to searching only this paper", async () => {
    renderScreen(
      <PaperChatPanel record={record} onClose={noop} />,
    );

    const toggle = await screen.findByRole("button", { name: "This paper" });
    expect(toggle.getAttribute("aria-pressed")).toBe("false");
  });

  it("widens the search only once the reader turns it on, never on its own", async () => {
    renderScreen(
      <PaperChatPanel record={record} onClose={noop} />,
    );
    await waitFor(() => expect(findForRecord).toHaveBeenCalled());

    await userEvent.click(await screen.findByRole("button", { name: "This paper" }));
    await userEvent.type(
      screen.getByRole("textbox", { name: /ask about this paper/i }),
      "How does this compare to other work?",
    );
    await userEvent.click(screen.getByRole("button", { name: /send/i }));

    await waitFor(() => expect(askStream).toHaveBeenCalled());
    const [, options] = askStream.mock.calls[0];
    expect(options).toMatchObject({ widen: true });
  });

  it("says when an answer left this paper's scope", async () => {
    askStream.mockImplementation(() => doneStreamOf({ widened: true }));
    renderScreen(
      <PaperChatPanel record={record} onClose={noop} />,
    );
    await waitFor(() => expect(findForRecord).toHaveBeenCalled());

    await userEvent.type(
      screen.getByRole("textbox", { name: /ask about this paper/i }),
      "How does this compare to other work?",
    );
    await userEvent.click(screen.getByRole("button", { name: /send/i }));

    expect(await screen.findByText(/Searched all papers/i)).toBeTruthy();
  });
});

describe("starter questions (IR-356)", () => {
  it("fill the composer with a suggested question, without sending it", async () => {
    renderScreen(
      <PaperChatPanel record={record} onClose={noop} />,
    );

    const suggestions = await screen.findByRole("group", { name: /suggested questions/i });
    await userEvent.click(
      within(suggestions).getByRole("button", { name: "What are the key findings?" }),
    );

    expect(screen.getByRole("textbox", { name: /ask about this paper/i })).toHaveValue(
      "What are the key findings?",
    );
    expect(askStream).not.toHaveBeenCalled();
  });

  it("are not offered once the conversation has turns", async () => {
    findForRecord.mockResolvedValue(conversation({
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
    );
    renderScreen(
      <PaperChatPanel record={record} onClose={noop} />,
    );

    await screen.findByText("What does this paper conclude?");
    expect(screen.queryByRole("group", { name: /suggested questions/i })).not.toBeInTheDocument();
  });
});

describe("keeping the newest message in view (IR-351)", () => {
  // `scrollIntoView` scrolls every scrollable ancestor, the window included:
  // opening docked Paper Chat at page 6 of a paper used to throw the reader
  // back to the top of the record. The transcript must scroll itself only.
  it("scrolls its own transcript, never an ancestor, as messages arrive", async () => {
    const scrollTopSet = vi.spyOn(Element.prototype, "scrollTop", "set");
    renderScreen(
      <PaperChatPanel record={record} onClose={noop} />,
    );
    await waitFor(() => expect(findForRecord).toHaveBeenCalled());

    await userEvent.type(
      screen.getByRole("textbox", { name: /ask about this paper/i }),
      "What datasets were used?",
    );
    await userEvent.click(screen.getByRole("button", { name: /send/i }));
    await screen.findByText(/reduced mean absolute error/i);

    expect(Element.prototype.scrollIntoView).not.toHaveBeenCalled();

    const panel = screen.getByRole("complementary", { name: "Ask IRIS" });
    const scrolled = scrollTopSet.mock.contexts as Element[];
    expect(scrolled.length).toBeGreaterThan(0);
    for (const el of scrolled) {
      expect(el).not.toBe(panel);
      expect(panel.contains(el)).toBe(true);
    }
  });
});

describe("accessibility", () => {
  it("has no serious or critical accessibility violations", async () => {
    const { container } = renderScreen(
      <PaperChatPanel record={record} onClose={noop} />,
    );
    await waitFor(() => expect(findForRecord).toHaveBeenCalled());

    await expectNoBlockingA11yViolations(container);
  });
});

/**
 * Below `lg` the docked panel is a bottom sheet over the paper. Following a
 * citation from it minimizes it to a bar, so the passage it lands on is not
 * underneath it (IR-354); the page decides when, the panel how.
 */
describe("minimized to a bar while the reader reads a citation (IR-354)", () => {
  const ANSWER = "It concludes rainfall gauges predict flooding well.";

  beforeEach(() => {
    findForRecord.mockResolvedValue(conversation({
        turns: [
          {
            id: 1, question: "What does this paper conclude?",
            resolved_question: null,
            answer: ANSWER,
            message: null, state: "generative", degraded: false, widened: false,
            created_at: "2026-09-20T00:00:00.000Z", citations: [],
          },
        ],
      }),
    );
  });

  /** The page's side of it: minimized until the bar is activated. */
  function MinimizedPanel() {
    const [minimized, setMinimized] = useState(true);
    return (
      <PaperChatPanel
        record={record}
        onClose={noop}
        minimized={minimized}
        onRestore={() => setMinimized(false)}
      />
    );
  }

  it("shows only a named bar, with the conversation and the composer out of the way", async () => {
    renderScreen(<MinimizedPanel />);

    expect(await screen.findByRole("button", { name: "Ask IRIS: back to the answer" })).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText(ANSWER)).not.toBeVisible());
    expect(screen.queryByRole("textbox", { name: "Ask about this paper" })).not.toBeInTheDocument();
  });

  it("restores on activation, with the answer the reader came from and no second fetch", async () => {
    renderScreen(<MinimizedPanel />);
    await waitFor(() => expect(screen.getByText(ANSWER)).not.toBeVisible());

    await userEvent.click(screen.getByRole("button", { name: "Ask IRIS: back to the answer" }));

    expect(screen.getByText(ANSWER)).toBeVisible();
    expect(screen.getByRole("textbox", { name: "Ask about this paper" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Ask IRIS: back to the answer" })).not.toBeInTheDocument();
    expect(findForRecord).toHaveBeenCalledTimes(1);
  });

  it("has no serious or critical accessibility violations while minimized", async () => {
    const { container } = renderScreen(<MinimizedPanel />);
    await screen.findByRole("button", { name: "Ask IRIS: back to the answer" });

    await expectNoBlockingA11yViolations(container);
  });
});

const PROHIBITED = [
  "Answer approach", "Why this approach", "Try instead", "Rerun with", "List papers",
  "search_passages", "find_records", "read_record_sections", "Research steps",
];

const SUMMARY = "These papers address the same problem, but their settings differ.";

describe("clean answers in Paper Chat (IR-596)", () => {
  const oldTurn = (extra: Record<string, unknown> = {}) => ({
    id: 1, question: "Find flooding papers", resolved_question: null,
    answer: "Prior answer", message: null, state: "generative", degraded: false,
    widened: false, created_at: "2026-10-11", citations: [],
    routing: { lane: "listing", reason: "list_request", allowed_overrides: ["passage", "listing"] },
    research: { steps: [{ position: 0, tool: "search_passages", status: "ok" }], coverage_notes: [] },
    reasoning: "secret working",
    ...extra,
  }) as never;

  it("reopens as answer and citations only, with the summary collapsed when there is one", async () => {
    findForRecord.mockResolvedValue(conversation({ turns: [oldTurn({ reasoning_summary: SUMMARY })] }));
    const { container } = renderScreen(<PaperChatPanel record={record} onClose={noop} />);

    expect(await screen.findByText("Prior answer")).toBeInTheDocument();
    for (const prohibited of PROHIBITED) expect(screen.queryByText(new RegExp(prohibited, "i"))).toBeNull();
    expect(container.textContent).not.toContain("secret working");
    expect(screen.queryByText(SUMMARY)).toBeNull();

    const toggle = screen.getByRole("button", { name: "Reasoning summary" });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    toggle.focus();
    await userEvent.keyboard("{Enter}");
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText(SUMMARY)).toBeInTheDocument();
  });

  it("offers no summary control for a turn without one", async () => {
    findForRecord.mockResolvedValue(conversation({ turns: [oldTurn()] }));
    renderScreen(<PaperChatPanel record={record} onClose={noop} />);

    await screen.findByText("Prior answer");
    expect(screen.queryByRole("button", { name: /reasoning/i })).toBeNull();
  });

  it("shows the persistent notice below the composer before any question", async () => {
    renderScreen(<PaperChatPanel record={record} onClose={noop} />);

    const notice = await screen.findByText(
      "Ask IRIS can make mistakes. Check important details against the cited papers.",
    );
    const composer = screen.getByRole("textbox", { name: /ask about this paper/i });
    expect(composer.compareDocumentPosition(notice) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("shows one status row while answering, and no diagnostics", async () => {
    let release: () => void = () => {};
    const gate = new Promise<void>((resolve) => { release = resolve; });
    askStream.mockImplementation(() => (async function* () {
      yield { event: "activity", id: "1", data: { state: "waiting", label: "Waiting…" } };
      yield { event: "agent_step", id: "1", data: { position: 0, tool: "search_passages", status: "running" } };
      await gate;
      yield { event: "done", id: "2", data: answer({ answer: "Final answer." }) };
    })());
    renderScreen(<PaperChatPanel record={record} onClose={noop} />);

    await userEvent.type(await screen.findByRole("textbox", { name: /ask about this paper/i }), "What datasets?{Enter}");

    expect(await screen.findByRole("status")).toHaveTextContent("Waiting…");
    for (const prohibited of PROHIBITED) expect(screen.queryByText(new RegExp(prohibited, "i"))).toBeNull();

    release();
    expect(await screen.findByText("Final answer.")).toBeInTheDocument();
  });

  it("has no serious or critical accessibility violations with a summary open", async () => {
    findForRecord.mockResolvedValue(conversation({ turns: [oldTurn({ reasoning_summary: SUMMARY })] }));
    const { container } = renderScreen(<PaperChatPanel record={record} onClose={noop} />);
    await userEvent.click(await screen.findByRole("button", { name: "Reasoning summary" }));

    await expectNoBlockingA11yViolations(container);
  });
});
