/**
 * Conversations saved before citations were Passages (IR-284).
 *
 * The chat history lives in `localStorage`, so a reader who used Ask IRIS
 * before this change has replies whose `citations` are bare record ids. The
 * rendering code now expects objects, and a number where an object belongs
 * renders as an empty citation card — something that looks like evidence and
 * carries none. This is the seam that stops that reaching a screen.
 */
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { getConversation, listConversations, saveConversation } from "./chatStorage";
import type { Conversation } from "@/types/chat";

const STORAGE_KEY = "iris_rag_conversations";

const passage = {
  marker:       1,
  chunk_id:     11,
  record_id:    7,
  record_title: "Flood Prediction",
  page:         4,
  text:         "rainfall gauge data",
  context_path: ["Flood Prediction", "Methods"],
};

/** Written the way the pre-IR-284 build wrote it: citations as record ids. */
function seedLegacyConversation() {
  localStorage.setItem(
    STORAGE_KEY,
    JSON.stringify([
      {
        id:        "c1",
        title:     "An older chat",
        createdAt: "2026-09-01T00:00:00.000Z",
        updatedAt: "2026-09-01T00:00:00.000Z",
        messages: [
          { id: "m1", role: "user", content: "what about floods?", createdAt: "2026-09-01T00:00:00.000Z" },
          {
            id: "m2",
            role: "assistant",
            content: "Two records discuss flooding [1].",
            citations: [7, 9],
            createdAt: "2026-09-01T00:00:00.000Z",
          },
        ],
      },
    ]),
  );
}

beforeEach(() => localStorage.clear());
afterEach(() => localStorage.clear());

describe("a conversation saved before citations were Passages", () => {
  it("keeps the reply a reader wrote and received", () => {
    seedLegacyConversation();

    const conversation = getConversation("c1");
    expect(conversation?.messages.map((m) => m.content)).toEqual([
      "what about floods?",
      "Two records discuss flooding [1].",
    ]);
  });

  it("drops the record ids rather than rendering them as empty citations", () => {
    seedLegacyConversation();

    // Nothing can recover a quote or a page from an id, and a citation card
    // with neither looks like evidence while carrying none.
    expect(getConversation("c1")?.messages[1].citations).toEqual([]);
  });

  it("drops them in the list view too, not only when one is opened", () => {
    seedLegacyConversation();

    expect(listConversations()[0].messages[1].citations).toEqual([]);
  });
});

describe("a conversation saved with Passages", () => {
  it("comes back with its citations untouched", () => {
    const conversation: Conversation = {
      id:        "c2",
      title:     "A newer chat",
      createdAt: "2026-09-20T00:00:00.000Z",
      updatedAt: "2026-09-20T00:00:00.000Z",
      messages: [
        {
          id:        "m1",
          role:      "assistant",
          content:   "Yes [1].",
          citations: [passage],
          degraded:  true,
          createdAt: "2026-09-20T00:00:00.000Z",
        },
      ],
    };
    saveConversation(conversation);

    const restored = getConversation("c2");
    expect(restored?.messages[0].citations).toEqual([passage]);
    // The degraded flag survives too, so a reopened reply still admits how it
    // was found rather than silently looking like a healthy one.
    expect(restored?.messages[0].degraded).toBe(true);
  });
});
