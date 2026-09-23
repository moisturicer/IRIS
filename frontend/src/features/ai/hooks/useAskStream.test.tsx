/**
 * The streaming state machine driving Ask IRIS's live progress (IR-329).
 *
 * `aiApi.askStream` is mocked as an async generator yielding the same
 * `{event, data}` shape `readSSE` produces -- the seam this hook actually
 * calls, so a test here does not need a real fetch or a real SSE body.
 */
import { act, renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { useAskStream } from "./useAskStream";

const askStream = vi.fn();

vi.mock("@/api/ai", () => ({
  aiApi: {
    askStream: (...args: unknown[]) => askStream(...args),
  },
}));

async function* eventsOf(...events: { event: string; data: unknown }[]) {
  for (const event of events) yield event;
}

describe("a complete stream", () => {
  it("moves through every pipeline stage in order", async () => {
    let release: () => void = () => {};
    const gate = new Promise<void>((resolve) => { release = resolve; });

    askStream.mockReturnValue(
      (async function* () {
        yield { event: "retrieval_started", data: {} };
        yield { event: "retrieval_finished", data: { passage_count: 3, record_count: 2, degraded: false } };
        yield { event: "generation_started", data: {} };
        await gate;
        yield { event: "text_delta", data: { text: "Rainfall gauges feed the model." } };
        yield { event: "citations_resolved", data: { citations: [] } };
        yield {
          event: "done",
          data: {
            answer: "Rainfall gauges feed the model.", citations: [], sources: [],
            message: null, mode: "generative", degraded: false,
            conversation_id: 9, resolved_question: null, widened: false, had_reasoning: false,
          },
        };
      })(),
    );

    const { result } = renderHook(() => useAskStream());

    let pending!: Promise<unknown>;
    act(() => {
      pending = result.current.ask("What predicts flooding?", { conversationId: 9 });
    });

    await waitFor(() => expect(result.current.streaming?.stage).toBe("thinking"));
    expect(result.current.streaming?.foundInfo).toEqual({ passageCount: 3, recordCount: 2 });

    release();
    const outcome = await pending as { message: { content: string; partial?: boolean }; conversationId: number | null };

    expect(outcome.message.content).toBe("Rainfall gauges feed the model.");
    expect(outcome.message.partial).toBeUndefined();
    expect(outcome.conversationId).toBe(9);
    await waitFor(() => expect(result.current.streaming).toBeNull());
  });

  it("matches the done event's shape for a non-generative answer", async () => {
    askStream.mockReturnValue(
      eventsOf(
        { event: "retrieval_started", data: {} },
        { event: "retrieval_finished", data: { passage_count: 0, record_count: 0, degraded: false } },
        {
          event: "done",
          data: {
            answer: null, citations: [], sources: [], message: "No readable sources matched.",
            mode: "no_results", degraded: false, conversation_id: null, resolved_question: null,
            widened: false, had_reasoning: false,
          },
        },
      ),
    );

    const { result } = renderHook(() => useAskStream());

    const outcome = await act(() => result.current.ask("anything"));

    expect(outcome.message.content).toBe("No readable sources matched.");
  });
});

describe("an interrupted stream (IR-328)", () => {
  it("keeps the partial text and citations rather than raising an error", async () => {
    askStream.mockReturnValue(
      (async function* () {
        yield { event: "retrieval_started", data: {} };
        yield { event: "retrieval_finished", data: { passage_count: 1, record_count: 1, degraded: false } };
        yield { event: "generation_started", data: {} };
        yield { event: "text_delta", data: { text: "Rainfall gauges feed the model [1]." } };
        throw new Error("connection reset");
      })(),
    );

    const { result } = renderHook(() => useAskStream());

    const outcome = await act(() => result.current.ask("What predicts flooding?", { conversationId: 4 }));

    expect(outcome.message.partial).toBe(true);
    expect(outcome.message.content).toBe("Rainfall gauges feed the model [1].");
    expect(result.current.streaming).toBeNull();
  });

  it("treats a clean close with no done event the same way", async () => {
    askStream.mockReturnValue(
      eventsOf(
        { event: "retrieval_started", data: {} },
        { event: "text_delta", data: { text: "Partial answer." } },
      ),
    );

    const { result } = renderHook(() => useAskStream());

    const outcome = await act(() => result.current.ask("anything"));

    expect(outcome.message.partial).toBe(true);
    expect(outcome.message.content).toBe("Partial answer.");
  });

  it("falls back to a placeholder message when nothing streamed before the cutoff", async () => {
    askStream.mockReturnValue(
      (async function* () {
        yield { event: "retrieval_started", data: {} };
        throw new Error("connection reset");
      })(),
    );

    const { result } = renderHook(() => useAskStream());

    const outcome = await act(() => result.current.ask("anything"));

    expect(outcome.message.partial).toBe(true);
    expect(outcome.message.content).toMatch(/interrupted/i);
  });
});

describe("a request that never starts streaming", () => {
  it("rejects rather than returning a false partial answer", async () => {
    // Deliberately no event: this stands in for `streamAsk` throwing before
    // the generator ever yields, e.g. a 400 from a blank question.
    askStream.mockReturnValue(
      // eslint-disable-next-line require-yield
      (async function* () {
        throw new Error("question is required.");
      })(),
    );

    const { result } = renderHook(() => useAskStream());

    await expect(act(() => result.current.ask(""))).rejects.toThrow("question is required.");
    expect(result.current.streaming).toBeNull();
  });
});
