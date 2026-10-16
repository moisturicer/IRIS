/**
 * The streaming state machine driving Ask IRIS's live progress (IR-329,
 * reworked to the public `activity` frames by IR-596).
 *
 * `aiApi.askStream` is mocked as an async generator yielding the same
 * `{event, data}` shape `readSSE` produces -- the seam this hook actually
 * calls, so a test here does not need a real fetch or a real SSE body.
 */
import { act, renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { StreamDetached, useAskStream } from "./useAskStream";

const askStream = vi.fn();
const resumeAskRun = vi.fn();
const cancelRun = vi.fn();

vi.mock("@/api/ai", () => ({
  aiApi: {
    askStream: (...args: unknown[]) => askStream(...args),
    resumeAskRun: (...args: unknown[]) => resumeAskRun(...args),
    cancelRun: (...args: unknown[]) => cancelRun(...args),
  },
}));

async function* eventsOf(...events: { event: string; data: unknown; id?: string }[]) {
  for (const event of events) yield event;
}

it("keeps the checked comparison on the finished answer and forwards explicit paper selection", async () => {
  const comparison = { records: [{ record_id: 7, title: "Flood Prediction" }], rows: [],
    coverage: [{ record_id: 7, state: "read_fully" }], removed_claims: 0 };
  askStream.mockReturnValue(eventsOf({ event: "done", data: { answer: "Compared papers.", comparison } }));
  const { result } = renderHook(() => useAskStream());
  const outcome = await act(() => result.current.ask("Compare", { comparisonRecordIds: [7, 9] }));
  expect(outcome.message.comparison).toEqual(comparison);
  expect(askStream).toHaveBeenCalledWith("Compare", { comparisonRecordIds: [7, 9] }, expect.any(AbortSignal));
});

describe("a complete stream", () => {
  it("follows the server's activity frames and ends on the finished answer", async () => {
    let release: () => void = () => {};
    const gate = new Promise<void>((resolve) => { release = resolve; });
    const frame = (state: string, label: string) => ({ event: "activity", data: { state, label } });

    askStream.mockReturnValue(
      (async function* () {
        yield frame("thinking", "Thinking…");
        await gate;
        yield frame("preparing", "Preparing your answer…");
        yield { event: "text_delta", data: { text: "Rainfall gauges feed the model." } };
        yield { event: "citations_resolved", data: { citations: [] } };
        yield {
          event: "done",
          data: {
            answer: "Rainfall gauges feed the model.", citations: [], sources: [],
            message: null, mode: "generative", degraded: false,
            conversation_id: 9, resolved_question: null, widened: false,
          },
        };
      })(),
    );

    const { result } = renderHook(() => useAskStream());

    let pending!: Promise<unknown>;
    act(() => {
      pending = result.current.ask("What predicts flooding?", { conversationId: 9 });
    });

    expect(result.current.streaming?.label).toBe("Waiting…");
    expect(result.current.streaming?.startedAt).toBeTypeOf("number");
    await waitFor(() => expect(result.current.streaming?.label).toBe("Thinking…"));

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
        { event: "activity", data: { state: "thinking", label: "Thinking…" } },
        {
          event: "done",
          data: {
            answer: null, citations: [], sources: [], message: "No readable sources matched.",
            mode: "no_results", degraded: false, conversation_id: null, resolved_question: null,
            widened: false,
          },
        },
      ),
    );

    const { result } = renderHook(() => useAskStream());

    const outcome = await act(() => result.current.ask("anything"));

    expect(outcome.message.content).toBe("No readable sources matched.");
  });
});

describe("activity and the reasoning summary (IR-596)", () => {
  const finished = (extra: Record<string, unknown> = {}) => ({
    event: "done",
    data: {
      answer: "Rainfall gauges feed the model.", citations: [], sources: [],
      message: null, mode: "generative", degraded: false, conversation_id: null,
      resolved_question: null, widened: false, ...extra,
    },
  });

  it("keeps the same status object when an identical activity frame arrives", async () => {
    const seen: unknown[] = [];
    let release: () => void = () => {};
    const gate = new Promise<void>((resolve) => { release = resolve; });
    askStream.mockReturnValue(
      (async function* () {
        yield { event: "activity", id: "1", data: { state: "thinking", label: "Thinking…" } };
        await gate;
        yield { event: "activity", id: "1", data: { state: "thinking", label: "Thinking…" } };
        yield { event: "activity", id: "2", data: { state: "thinking", label: "Thinking…" } };
        await gate;
        yield finished();
      })(),
    );
    const { result } = renderHook(() => { const hook = useAskStream(); seen.push(hook.streaming); return hook; });
    let pending!: Promise<unknown>;
    act(() => { pending = result.current.ask("q"); });
    await waitFor(() => expect(result.current.streaming?.activity).toBe("thinking"));
    const settled = result.current.streaming;
    release();
    await pending;
    expect(seen.filter((state) => state === settled).length).toBeGreaterThan(0);
    expect(new Set(seen.filter((state) => state && (state as { activity: string }).activity === "thinking")).size).toBe(1);
  });

  it("puts a non-empty reasoning summary on the finished message", async () => {
    askStream.mockReturnValue(eventsOf(finished({ reasoning_summary: "  The papers differ in setting.  " })));
    const { result } = renderHook(() => useAskStream());

    const outcome = await act(() => result.current.ask("q"));

    expect(outcome.message.reasoningSummary).toBe("The papers differ in setting.");
  });

  it.each([undefined, "", "   ", null])("carries no summary when the server sends %j", async (summary) => {
    askStream.mockReturnValue(eventsOf(finished(summary === undefined ? {} : { reasoning_summary: summary })));
    const { result } = renderHook(() => useAskStream());

    const outcome = await act(() => result.current.ask("q"));

    expect(outcome.message.reasoningSummary).toBeUndefined();
  });

  it("never reads raw reasoning, routing or steps even if a server sends them", async () => {
    askStream.mockReturnValue(eventsOf(
      { event: "reasoning_delta", data: { text: "secret working" } },
      { event: "routing_decided", data: { routing: { lane: "listing" } } },
      { event: "agent_step", data: { position: 0, tool: "search_passages", status: "running" } },
      finished({ reasoning: "secret working", routing: { lane: "listing" } }),
    ));
    const { result } = renderHook(() => useAskStream());

    const outcome = await act(() => result.current.ask("q"));

    expect(JSON.stringify(outcome.message)).not.toMatch(/secret working|search_passages|listing"/);
    expect(outcome.message).not.toHaveProperty("reasoning");
    expect(outcome.message).not.toHaveProperty("routing");
  });

  it("applies a replayed done once and ignores records at or below the cursor", async () => {
    askStream.mockReturnValue(eventsOf(
      { event: "run_queued", id: "1", data: { run_id: "r-1", state: "queued" } },
      { event: "text_delta", id: "2", data: { text: "Rainfall " } },
      { event: "text_delta", id: "2", data: { text: "Rainfall " } },
      { event: "text_delta", id: "1", data: { text: "stale " } },
      { event: "run_failed", id: "3", data: { run_id: "r-1", state: "failed" } },
    ));
    const { result } = renderHook(() => useAskStream());

    const outcome = await act(() => result.current.ask("q", { conversationId: 9 }));

    expect(outcome.message.endedRun).toEqual({ id: "r-1", state: "failed" });
  });

  it("does not repeat text that a reconnect replays", async () => {
    askStream.mockReturnValue(
      (async function* () {
        yield { event: "run_queued", id: "1", data: { run_id: "r-2", state: "queued" } };
        yield { event: "text_delta", id: "2", data: { text: "Rainfall " } };
        throw new Error("connection reset");
      })(),
    );
    resumeAskRun.mockReturnValue(eventsOf(
      { event: "text_delta", id: "2", data: { text: "Rainfall " } },
      { event: "text_delta", id: "3", data: { text: "gauges." } },
      { event: "done", id: "4", data: { answer: null, message: null, turn_id: 5, conversation_id: 9, mode: "generative" } },
      { event: "done", id: "4", data: { answer: null, message: null, turn_id: 5, conversation_id: 9, mode: "generative" } },
    ));
    const { result } = renderHook(() => useAskStream());

    const outcome = await act(() => result.current.ask("q", { conversationId: 9 }));

    expect(resumeAskRun).toHaveBeenCalledWith("r-2", 2, expect.any(AbortSignal));
    expect(outcome.message.turnId).toBe(5);
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

it("carries terminal listing rows into the answer and sends no lane override", async () => {
  const listing = { completeness: "matches_found", wording: "Matches found", records: [{ record_id: 7, title: "Flood Prediction" }] };
  askStream.mockReturnValue(eventsOf({ event: "done", data: { answer: "Found papers", turn_id: 5, listing } }));
  const { result } = renderHook(() => useAskStream());
  const outcome = await act(() => result.current.ask("Find flooding papers", { conversationId: 9 }));
  expect(outcome.message.listing).toEqual(listing);
  expect(outcome.message.question).toBe("Find flooding papers");
  expect(outcome.message.turnId).toBe(5);
  expect(askStream).toHaveBeenCalledWith("Find flooding papers", { conversationId: 9 }, expect.any(AbortSignal));
});

describe("unknown events", () => {
  it("ignores an event type it does not know", async () => {
    askStream.mockReturnValue(
      eventsOf(
        { event: "some_future_event", data: { anything: true } },
        {
          event: "done",
          data: { answer: "Fine.", citations: [], sources: [], message: null, mode: "generative",
                  degraded: false, conversation_id: null, resolved_question: null, widened: false,
                },
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
          listing } };
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
    await waitFor(() => expect(result.current.streaming?.candidates).toBeUndefined());
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
      widened: false, turn_id: 41,
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

    expect(resumeAskRun).toHaveBeenCalledWith("r-1", 2, expect.any(AbortSignal));
    expect(outcome.message.content).toBe("Rainfall gauges feed the model.");
    expect(outcome.message.turnId).toBe(41);
    expect(outcome.message.partial).toBeFalsy();
  });

  it("shows it waiting, then starts over when a new attempt begins", async () => {
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

    await waitFor(() => expect(result.current.streaming?.runId).toBe("r-2"));
    expect(result.current.streaming?.label).toBe("Waiting…");
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
    expect(outcome.message.endedRun).toEqual({ id: "r-3", state: "expired" });
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

describe("an owned run, opened, cancelled and retried (IR-548)", () => {
  const done = {
    event: "done", id: "5",
    data: {
      answer: "Rainfall gauges feed the model.", citations: [], sources: [], message: null,
      mode: "generative", degraded: false, conversation_id: 9, resolved_question: null,
      widened: false, turn_id: 41,
    },
  };

  it("follows an existing run from its first event, replaying its progress", async () => {
    resumeAskRun.mockReturnValue(
      eventsOf(
        { event: "run_queued", id: "1", data: { run_id: "r-7", state: "queued" } },
        { event: "run_started", id: "2", data: { attempt: 1 } },
        done,
      ),
    );

    const { result } = renderHook(() => useAskStream());
    const outcome = await act(() => result.current.follow("r-7", "What predicts flooding?"));

    expect(resumeAskRun).toHaveBeenCalledWith("r-7", 0, expect.any(AbortSignal));
    expect(askStream).not.toHaveBeenCalledWith("What predicts flooding?", expect.anything(), expect.anything());
    expect(outcome.message.turnId).toBe(41);
    expect(outcome.message.question).toBe("What predicts flooding?");
  });

  it("names the run it is following, so it can be stopped", async () => {
    let release: () => void = () => {};
    const gate = new Promise<void>((resolve) => { release = resolve; });
    cancelRun.mockResolvedValue({ data: { run_id: "r-8", state: "cancelled" } });
    askStream.mockReturnValue(
      (async function* () {
        yield { event: "run_queued", id: "1", data: { run_id: "r-8", state: "queued" } };
        await gate;
        yield { event: "run_cancelled", id: "2", data: { run_id: "r-8", state: "cancelled", reason: "cancelled" } };
      })(),
    );

    const { result } = renderHook(() => useAskStream());
    let pending!: Promise<{ message: { content: string; partial?: boolean; endedRun?: unknown } }>;
    act(() => { pending = result.current.ask("q", { conversationId: 9 }); });

    await waitFor(() => expect(result.current.streaming?.runId).toBe("r-8"));
    await act(() => result.current.cancel());
    expect(cancelRun).toHaveBeenCalledWith("r-8");

    release();
    const outcome = await pending;
    expect(outcome.message.content).toMatch(/you stopped this question/i);
    expect(outcome.message.partial).toBeFalsy();
    expect(outcome.message.endedRun).toEqual({ id: "r-8", state: "cancelled" });
    await waitFor(() => expect(result.current.streaming).toBeNull());
  });

  it("stops following when detached, leaving the run to finish on the server", async () => {
    askStream.mockImplementation((_q: string, _o: unknown, signal: AbortSignal) =>
      (async function* () {
        yield { event: "run_queued", id: "1", data: { run_id: "r-9", state: "queued" } };
        await new Promise((_, reject) => signal.addEventListener("abort", () => reject(new Error("aborted"))));
      })(),
    );

    const { result } = renderHook(() => useAskStream());
    let pending!: Promise<unknown>;
    act(() => { pending = result.current.ask("q", { conversationId: 9 }); });
    await waitFor(() => expect(result.current.streaming?.runId).toBe("r-9"));

    act(() => result.current.detach());

    await expect(pending).rejects.toBeInstanceOf(StreamDetached);
    expect(result.current.streaming).toBeNull();
    expect(resumeAskRun).not.toHaveBeenCalledWith("r-9", expect.anything(), expect.anything());
    expect(cancelRun).not.toHaveBeenCalledWith("r-9");
  });
});
