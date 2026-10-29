import { afterEach, describe, expect, it, vi } from "vitest";
import { aiApi } from "./ai";

const { post, get } = vi.hoisted(() => ({ post: vi.fn(), get: vi.fn() }));
vi.mock("./client", () => ({ apiClient: { post, get } }));
describe("starting a conversation (IR-548)", () => {
  // The server answers POST with the summary shape, which has no `turns`.
  const created = {
    id: 4, title: "", record: 5, record_title: "Flooding", turn_count: 0,
    created_at: "2026-10-14", updated_at: "2026-10-14",
  };

  it("gives a new conversation an empty transcript and no run", async () => {
    post.mockResolvedValue({ data: created });

    const { data } = await aiApi.conversations.create({ record: 5 });

    expect(post).toHaveBeenCalledWith("/ai/conversations/", { record: 5 }, { headers: { "X-IRIS-Protocol": "public-1" } });
    expect(data).toEqual({ ...created, turns: [], latest_run: null });
  });

});

describe("finding a Record's conversation (IR-569)", () => {
  it("finds none without starting one, so opening Paper Chat creates nothing", async () => {
    get.mockResolvedValue({ data: [] });

    expect(await aiApi.conversations.findForRecord(5)).toBeNull();
    expect(get).toHaveBeenCalledWith("/ai/conversations/", { params: { record: 5, default: true } });
    expect(post).not.toHaveBeenCalled();
  });

  it("reads the existing one in full", async () => {
    const detail = { id: 4, turns: [], latest_run: null };
    get.mockResolvedValueOnce({ data: [{ id: 4 }] }).mockResolvedValueOnce({ data: detail });

    expect(await aiApi.conversations.findForRecord(5)).toEqual(detail);
    expect(get).toHaveBeenLastCalledWith("/ai/conversations/4/", { headers: { "X-IRIS-Protocol": "public-1" } });
  });
});

afterEach(() => { vi.unstubAllGlobals(); vi.clearAllMocks(); });

describe("the public reader protocol (IR-596)", () => {
  const PROTOCOL = { "X-IRIS-Protocol": "public-1" };

  it("opts the JSON endpoint in and sends no lane override", () => {
    aiApi.ask("Original question", { conversationId: 42, widen: true });
    expect(post).toHaveBeenCalledWith(
      "/ai/ask/",
      { question: "Original question", top_k: 5, conversation_id: 42, widen: true, request_id: expect.any(String) },
      { headers: PROTOCOL },
    );
  });

  it("opts the streaming endpoint in", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response("event: done\ndata: {}\n\n", {
      headers: { "Content-Type": "text/event-stream" },
    }));
    vi.stubGlobal("fetch", fetchMock);
    for await (const event of aiApi.askStream("Original question", { conversationId: 42, widen: false })) {
      expect(event.event).toBe("done");
    }
    expect(fetchMock.mock.calls[0][1].headers).toMatchObject(PROTOCOL);
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({
      question: "Original question", top_k: 5, conversation_id: 42, widen: false, request_id: expect.any(String),
    });
  });

  it("opts a reconnect to a run in", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response("event: done\ndata: {}\n\n"));
    vi.stubGlobal("fetch", fetchMock);
    for await (const event of aiApi.resumeAskRun("run-1", 4)) expect(event.event).toBe("done");
    expect(fetchMock.mock.calls[0][0]).toContain("/ai/ask/runs/run-1/stream/?after=4");
    expect(fetchMock.mock.calls[0][1].headers).toMatchObject(PROTOCOL);
  });

  it("opts conversation detail in, for a reopened chat and for Paper Chat", async () => {
    get.mockResolvedValueOnce({ data: { id: 4, turns: [] } });
    await aiApi.conversations.get(4);
    expect(get).toHaveBeenLastCalledWith("/ai/conversations/4/", { headers: PROTOCOL });
  });
});

describe("comparison paper limits", () => {
  it("requires two distinct papers before submitting", async () => {
    await expect(aiApi.ask("Compare", { comparisonRecordIds: [1] })).rejects.toThrow("at least 2");
    await expect(aiApi.ask("Compare", { comparisonRecordIds: [1, 1] })).rejects.toThrow("distinct valid");
    expect(post).not.toHaveBeenCalled();
  });
  it("reads the configured limit and sends selected papers to the JSON endpoint", async () => {
    get.mockResolvedValue({ data: { comparison_max_records: 2 } });
    await aiApi.ask("Compare these papers", { comparisonRecordIds: [7, 9] });
    expect(get).toHaveBeenCalledWith("/ai/status/");
    expect(post.mock.calls[0][1].comparison_record_ids).toEqual([7, 9]);
  });

  it("rejects a JSON comparison above the configured limit before submitting", async () => {
    get.mockResolvedValue({ data: { comparison_max_records: 2 } });
    await expect(aiApi.ask("Compare", { comparisonRecordIds: [1, 2, 3] })).rejects.toThrow("Compare at most 2 papers");
    expect(post).not.toHaveBeenCalled();
  });

  it("rejects a streamed comparison above the configured limit before submitting", async () => {
    get.mockResolvedValue({ data: { comparison_max_records: 2 } });
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    await expect(aiApi.askStream("Compare", { comparisonRecordIds: [1, 2, 3] }).next()).rejects.toThrow("Compare at most 2 papers");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("sends selected papers in a streamed comparison", async () => {
    get.mockResolvedValue({ data: { comparison_max_records: 3 } });
    const fetchMock = vi.fn().mockResolvedValue(new Response('event: done\ndata: {}\n\n'));
    vi.stubGlobal("fetch", fetchMock);
    for await (const event of aiApi.askStream("Compare", { comparisonRecordIds: [7, 9] })) expect(event.event).toBe("done");
    expect(JSON.parse(fetchMock.mock.calls[0][1].body).comparison_record_ids).toEqual([7, 9]);
  });

  it("uses the default six-paper limit when status cannot be read", async () => {
    get.mockRejectedValue(new Error("offline"));
    await expect(aiApi.ask("Compare", { comparisonRecordIds: [1, 2, 3, 4, 5, 6, 7] })).rejects.toThrow("Compare at most 6 papers");
    expect(post).not.toHaveBeenCalled();
  });

  it("does not fetch comparison configuration for an ordinary question", () => {
    aiApi.ask("What is this about?");
    expect(get).not.toHaveBeenCalled();
  });
});
