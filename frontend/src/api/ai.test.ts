import { afterEach, describe, expect, it, vi } from "vitest";
import { aiApi } from "./ai";

const post = vi.hoisted(() => vi.fn());
vi.mock("./client", () => ({ apiClient: { post } }));

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
