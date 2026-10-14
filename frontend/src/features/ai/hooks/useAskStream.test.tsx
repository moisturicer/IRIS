import { routingFixture } from "@/test/routingFixture";
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
const resumeAskRun = vi.fn();

vi.mock("@/api/ai", () => ({
  aiApi: {
    askStream: (...args: unknown[]) => askStream(...args),
    resumeAskRun: (...args: unknown[]) => resumeAskRun(...args),
  },
}));

async function* eventsOf(...events: { event: string; data: unknown; id?: string }[]) {
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

describe("the reasoning channel (IR-381)", () => {
  it("accumulates reasoning deltas separately from the answer text", async () => {
    let release: () => void = () => {};
    const gate = new Promise<void>((resolve) => { release = resolve; });

    askStream.mockReturnValue(
      (async function* () {
        yield { event: "retrieval_started", data: {} };
        yield { event: "retrieval_finished", data: { passage_count: 1, record_count: 1, degraded: false } };
        yield { event: "generation_started", data: {} };
        yield { event: "reasoning_delta", data: { text: "Checking the sources. " } };
        yield { event: "reasoning_delta", data: { text: "Looks right." } };
        await gate;
        yield { event: "text_delta", data: { text: "Rainfall gauges feed the model." } };
        yield {
          event: "done",
          data: {
            answer: "Rainfall gauges feed the model.", citations: [], sources: [],
            message: null, mode: "generative", degraded: false, conversation_id: 9,
            resolved_question: null, widened: false, had_reasoning: true,
            reasoning: "Checking the sources. Looks right.",
          },
        };
      })(),
    );

    const { result } = renderHook(() => useAskStream());

    let pending!: Promise<unknown>;
    act(() => { pending = result.current.ask("What predicts flooding?", { conversationId: 9 }); });

    await waitFor(() =>
      expect(result.current.streaming?.reasoning).toBe("Checking the sources. Looks right."),
    );
    expect(result.current.streaming?.text).toBe("");
    expect(result.current.streaming?.stage).toBe("thinking");

    release();
    const outcome = await pending as { message: { content: string; reasoning?: string | null } };

    expect(outcome.message.reasoning).toBe("Checking the sources. Looks right.");
    expect(outcome.message.content).toBe("Rainfall gauges feed the model.");
  });

  it("does not pull the stage back to thinking once the answer is writing", async () => {
    let release: () => void = () => {};
    const gate = new Promise<void>((resolve) => { release = resolve; });

    askStream.mockReturnValue(
      (async function* () {
        yield { event: "retrieval_started", data: {} };
        yield { event: "generation_started", data: {} };
        yield { event: "text_delta", data: { text: "Rainfall gauges " } };
        yield { event: "reasoning_delta", data: { text: "second thoughts" } };
        await gate;
        yield { event: "text_delta", data: { text: "feed the model." } };
      })(),
    );

    const { result } = renderHook(() => useAskStream());

    let pending!: Promise<unknown>;
    act(() => { pending = result.current.ask("anything"); });

    await waitFor(() => expect(result.current.streaming?.reasoning).toBe("second thoughts"));
    expect(result.current.streaming?.stage).toBe("answering");

    release();
    await pending;
  });

  it("carries no reasoning when the model produced none", async () => {
    askStream.mockReturnValue(
      eventsOf(
        { event: "retrieval_started", data: {} },
        { event: "text_delta", data: { text: "Rainfall gauges feed the model." } },
        {
          event: "done",
          data: {
            answer: "Rainfall gauges feed the model.", citations: [], sources: [],
            message: null, mode: "generative", degraded: false, conversation_id: null,
            resolved_question: null, widened: false, had_reasoning: false, reasoning: null,
          },
        },
      ),
    );

    const { result } = renderHook(() => useAskStream());

    const outcome = await act(() => result.current.ask("anything"));

    expect(outcome.message.reasoning).toBeNull();
  });

  it("keeps the reasoning that arrived before an interrupted stream cut off", async () => {
    askStream.mockReturnValue(
      (async function* () {
        yield { event: "retrieval_started", data: {} };
        yield { event: "reasoning_delta", data: { text: "half a thought" } };
        yield { event: "text_delta", data: { text: "Rainfall gauges" } };
        throw new Error("connection reset");
      })(),
    );

    const { result } = renderHook(() => useAskStream());

    const outcome = await act(() => result.current.ask("anything"));

    expect(outcome.message.partial).toBe(true);
    expect(outcome.message.reasoning).toBe("half a thought");
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

it("keeps the live routing event and carries terminal listing rows into the answer", async () => {
  let release!: () => void;
  const gate = new Promise<void>((resolve) => { release = resolve; });
  const listing = { completeness: "matches_found", wording: "Matches found", records: [{ record_id: 7, title: "Flood Prediction" }] };
  askStream.mockReturnValue((async function* () {
    yield { event: "routing_decided", data: { routing: routingFixture } };
    await gate;
    yield { event: "done", data: { answer: "Found papers", turn_id: 5, routing: routingFixture, listing } };
  })());
  const { result } = renderHook(() => useAskStream());
  let pending!: ReturnType<typeof result.current.ask>;
  act(() => { pending = result.current.ask("Find flooding papers", { conversationId: 9, routeOverride: "listing", routeOverrideTurnId: 3 }); });
  await waitFor(() => expect(result.current.streaming?.routing).toEqual(routingFixture));
  let outcome!: Awaited<typeof pending>;
  await act(async () => { release(); outcome = await pending; });
  expect(outcome.message.routing).toEqual(routingFixture);
  expect(outcome.message.listing).toEqual(listing);
  expect(outcome.message.question).toBe("Find flooding papers");
  expect(outcome.message.turnId).toBe(5);
  expect(askStream).toHaveBeenCalledWith("Find flooding papers", { conversationId: 9, routeOverride: "listing", routeOverrideTurnId: 3 });
});

describe("the research lane (IR-504)", () => {
  it("tracks each step by position and keeps the finished trace", async () => {
    let release: () => void = () => {};
    const gate = new Promise<void>((resolve) => { release = resolve; });
    const step = { kind: "tool", tool: "search_passages", duplicate: false, latency_ms: 0, coverage: null, found: null };
    const research = { run_id: "r", stop_reason: "finish", steps: [], coverage_notes: [] };
    askStream.mockReturnValue(
      (async function* () {
        yield { event: "retrieval_started", data: {} };
        yield { event: "agent_step", data: { ...step, position: 0, status: "running" } };
        yield { event: "agent_step", data: { ...step, position: 0, status: "ok", found: 2 } };
        await gate;
        yield {
          event: "done",
          data: { answer: "A.", citations: [], sources: [], message: null, mode: "generative",
                  degraded: false, conversation_id: 3, resolved_question: null, widened: false,
                  had_reasoning: false, research },
        };
      })(),
    );
    const { result } = renderHook(() => useAskStream());
    let pending!: Promise<unknown>;
    act(() => { pending = result.current.ask("q"); });

    await waitFor(() => expect(result.current.streaming?.steps?.[0]?.status).toBe("ok"));
    expect(result.current.streaming?.steps).toHaveLength(1);
    release();
    const outcome = await pending as { message: { research?: unknown } };
    expect(outcome.message.research).toEqual(research);
  });

  it("ignores an event type it does not know", async () => {
    askStream.mockReturnValue(
      eventsOf(
        { event: "retrieval_started", data: {} },
        { event: "some_future_event", data: { anything: true } },
        {
          event: "done",
          data: { answer: "Fine.", citations: [], sources: [], message: null, mode: "generative",
                  degraded: false, conversation_id: null, resolved_question: null, widened: false,
                  had_reasoning: false },
        },
      ),
    );
    const { result } = renderHook(() => useAskStream());
    const outcome = await act(() => result.current.ask("q"));
    expect(outcome.message.content).toBe("Fine.");
    expect(outcome.message.partial).toBeUndefined();
  });
});

describe("a listing's candidates (IR-546)", () => {
  const preview = {
    event: "candidates_selected",
    data: { limit: 20, more_available: false, degraded: false, candidates: [
      { record_id: 1, title: "Flood Prediction", state: "pending" },
      { record_id: 2, title: "Tilapia Ponds", state: "pending" },
    ] },
  };
  const listing = {
    completeness: "matches_found", wording: "Screened 2 candidate papers: 1 matched, 1 did not match, 0 uncertain, 0 could not be assessed.",
    records: [{ record_id: 1, title: "Flood Prediction" }],
    candidates: [
      { record_id: 1, title: "Flood Prediction", state: "included" },
      { record_id: 2, title: "Tilapia Ponds", state: "excluded" },
    ],
  };

  it("shows the preview as pending, moves each paper by id, and ends on the final listing", async () => {
    let release: () => void = () => {};
    const gate = new Promise<void>((resolve) => { release = resolve; });
    askStream.mockReturnValue(
      (async function* () {
        yield preview;
        yield { event: "candidates_updated", data: { candidates: [{ record_id: 1, state: "included" }] } };
        // A replay or a repeat must not add a second card.
        yield { event: "candidates_updated", data: { candidates: [{ record_id: 1, state: "included" }] } };
        await gate;
        yield { event: "done", data: { answer: listing.wording, citations: [], sources: [], message: null,
          mode: "generative", degraded: false, conversation_id: 4, resolved_question: null, widened: false,
          had_reasoning: false, listing } };
      })(),
    );
    const { result } = renderHook(() => useAskStream());
    let pending!: Promise<unknown>;
    act(() => { pending = result.current.ask("Which papers are about flooding?"); });

    await waitFor(() => expect(result.current.streaming?.candidates?.[0]?.state).toBe("included"));
    expect(result.current.streaming?.candidates).toEqual([
      { record_id: 1, title: "Flood Prediction", state: "included" },
      { record_id: 2, title: "Tilapia Ponds", state: "pending" },
    ]);

    release();
    const outcome = await pending as { message: { listing?: typeof listing } };
    expect(outcome.message.listing?.candidates).toEqual(listing.candidates);
    await waitFor(() => expect(result.current.streaming).toBeNull());
  });

  it("starts the candidates over when a new attempt begins", async () => {
    let release: () => void = () => {};
    const gate = new Promise<void>((resolve) => { release = resolve; });
    askStream.mockReturnValue(
      (async function* () {
        yield { event: "run_queued", id: "1", data: { run_id: "r-9", state: "queued" } };
        yield { ...preview, id: "2" };
        yield { event: "run_started", id: "3", data: { run_id: "r-9", state: "running", attempt: 2 } };
        await gate;
        yield { event: "run_failed", id: "4", data: { run_id: "r-9", state: "failed" } };
      })(),
    );
    const { result } = renderHook(() => useAskStream());
    let pending!: Promise<unknown>;
    act(() => { pending = result.current.ask("q"); });
    await waitFor(() => expect(result.current.streaming?.stage).toBe("searching"));
    expect(result.current.streaming?.candidates).toBeUndefined();
    release();
    await pending;
  });
});

describe("a queued run (IR-544)", () => {
  const done = {
    event: "done", id: "9",
    data: {
      answer: "Rainfall gauges feed the model.", citations: [], sources: [], message: null,
      mode: "generative", degraded: false, conversation_id: 9, resolved_question: null,
      widened: false, had_reasoning: false, turn_id: 41,
    },
  };

  it("reconnects after a dropped connection from the last event it saw", async () => {
    askStream.mockReturnValue(
      (async function* () {
        yield { event: "run_queued", id: "1", data: { run_id: "r-1", state: "queued" } };
        yield { event: "run_started", id: "2", data: { run_id: "r-1", state: "running", attempt: 1 } };
        throw new Error("connection reset");
      })(),
    );
    resumeAskRun.mockReturnValue(
      eventsOf(
        { event: "text_delta", id: "3", data: { text: "Rainfall gauges feed the model." } },
        done,
      ),
    );

    const { result } = renderHook(() => useAskStream());
    const outcome = await act(() => result.current.ask("What predicts flooding?", { conversationId: 9 }));

    expect(resumeAskRun).toHaveBeenCalledWith("r-1", 2);
    expect(outcome.message.content).toBe("Rainfall gauges feed the model.");
    expect(outcome.message.turnId).toBe(41);
    expect(outcome.message.partial).toBeFalsy();
  });

  it("shows the queued stage, then starts over when a new attempt begins", async () => {
    let release: () => void = () => {};
    const gate = new Promise<void>((resolve) => { release = resolve; });
    let resume: () => void = () => {};
    const restarted = new Promise<void>((resolve) => { resume = resolve; });

    askStream.mockReturnValue(
      (async function* () {
        yield { event: "run_queued", id: "1", data: { run_id: "r-2", state: "queued" } };
        await gate;
        yield { event: "run_started", id: "2", data: { attempt: 1 } };
        yield { event: "text_delta", id: "3", data: { text: "half an ans" } };
        await restarted;
        yield { event: "run_started", id: "4", data: { attempt: 2 } };
        yield done;
      })(),
    );

    const { result } = renderHook(() => useAskStream());
    let pending!: Promise<unknown>;
    act(() => { pending = result.current.ask("q", { conversationId: 9 }); });

    await waitFor(() => expect(result.current.streaming?.stage).toBe("queued"));
    release();
    await waitFor(() => expect(result.current.streaming?.text).toBe("half an ans"));
    resume();
    const outcome = (await pending) as { message: { content: string } };
    expect(outcome.message.content).toBe("Rainfall gauges feed the model.");
  });

  it("ends with an explicit message when the run fails", async () => {
    askStream.mockReturnValue(
      eventsOf(
        { event: "run_queued", data: { run_id: "r-3", state: "queued" } },
        { event: "run_failed", data: { run_id: "r-3", state: "expired", reason: "deadline_exceeded" } },
      ),
    );

    const { result } = renderHook(() => useAskStream());
    const outcome = await act(() => result.current.ask("q", { conversationId: 9 }));

    expect(outcome.message.content).toMatch(/ran out of time/);
    expect(outcome.message.partial).toBe(true);
  });

  it("gives up after repeated reconnections bring nothing", async () => {
    askStream.mockReturnValue(eventsOf({ event: "run_queued", id: "1", data: { run_id: "r-4" } }));
    resumeAskRun.mockImplementation(() => eventsOf());

    const { result } = renderHook(() => useAskStream());
    const outcome = await act(() => result.current.ask("q", { conversationId: 9 }));

    expect(resumeAskRun).toHaveBeenCalledTimes(3);
    expect(outcome.message.partial).toBe(true);
  }, 10_000);

  it("ignores an event name it does not know", async () => {
    askStream.mockReturnValue(eventsOf({ event: "something_new", data: { x: 1 } }, done));

    const { result } = renderHook(() => useAskStream());
    const outcome = await act(() => result.current.ask("q"));

    expect(outcome.message.content).toBe("Rainfall gauges feed the model.");
  });
});
