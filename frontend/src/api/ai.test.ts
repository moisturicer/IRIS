import { afterEach, describe, expect, it, vi } from "vitest";
import { aiApi } from "./ai";

const post = vi.hoisted(() => vi.fn());
const get = vi.hoisted(() => vi.fn());
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

    expect(post).toHaveBeenCalledWith("/ai/conversations/", { record: 5 });
    expect(data).toEqual({ ...created, turns: [], latest_run: null });
  });

  it("does the same when Paper Chat starts its Record's first conversation", async () => {
    get.mockResolvedValue({ data: [] });
    post.mockResolvedValue({ data: created });

    const { data } = await aiApi.conversations.findOrCreateForRecord(5);

    expect(data.turns).toEqual([]);
  });
});

afterEach(() => { vi.unstubAllGlobals(); vi.clearAllMocks(); });

describe("answer route overrides", () => {
  it("sends the chosen lane with the question and scope to the JSON endpoint", () => {
    aiApi.ask("Original question", { conversationId: 42, widen: true, routeOverride: "listing", routeOverrideTurnId: 3 });
    expect(post).toHaveBeenCalledWith("/ai/ask/", {
      question: "Original question", top_k: 5, conversation_id: 42, widen: true, route_override: "listing", route_override_turn_id: 3,
    });
  });

  it("sends the chosen lane to the streaming endpoint", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response('event: done\ndata: {}\n\n', {
      headers: { "Content-Type": "text/event-stream" },
    }));
    vi.stubGlobal("fetch", fetchMock);
    for await (const event of aiApi.askStream("Original question", { conversationId: 42, widen: false, routeOverride: "passage", routeOverrideTurnId: 3 })) {
      expect(event.event).toBe("done");
    }
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({
      question: "Original question", top_k: 5, conversation_id: 42, widen: false, route_override: "passage", route_override_turn_id: 3,
    });
  });

  it("omits route_override on ordinary questions", () => {
    aiApi.ask("Ordinary question");
    expect(post.mock.calls[0][1]).not.toHaveProperty("route_override");
    expect(post.mock.calls[0][1]).not.toHaveProperty("route_override_turn_id");
  });
});
