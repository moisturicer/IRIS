/**
 * What a reader can actually check (IR-284, redesigned for inline chips by
 * IR-329).
 *
 * The claim this ticket makes is that an answer now shows *which sentence*
 * supports it and *which page* that sentence is on, as a clickable chip
 * sitting inline in the sentence itself rather than a card repeated below
 * the message a second time.
 *
 * Every query goes through the accessible tree, by role and accessible name.
 */
import { describe, expect, it } from "vitest";

import { expectNoBlockingA11yViolations } from "@/test/axe";
import { renderScreen, screen } from "@/test/render";
import type { Citation } from "@/types/ai";
import type { ChatMessage } from "@/types/chat";

import { ChatMessageBubble } from "./ChatMessageBubble";

const citation: Citation = {
  marker:       1,
  chunk_id:     11,
  record_id:    7,
  record_title: "Flood Prediction in the Mananga Catchment",
  page:         4,
  text:         "we trained a convolutional neural network on rainfall gauge data to predict flooding",
  context_path: ["Flood Prediction in the Mananga Catchment", "Methods"],
};

function assistantMessage(overrides: Partial<ChatMessage> = {}): ChatMessage {
  return {
    id:        "m1",
    role:      "assistant",
    content:   "Rainfall gauge data was used [1].",
    citations: [citation],
    createdAt: "2026-09-20T00:00:00.000Z",
    ...overrides,
  };
}

describe("a cited answer", () => {
  it("shows the marker as a clickable chip, right where it sits in the sentence", () => {
    renderScreen(<ChatMessageBubble message={assistantMessage()} />);

    const chip = screen.getByRole("link", {
      name: /Open Flood Prediction in the Mananga Catchment at page 4/i,
    });
    expect(chip.getAttribute("href")).toBe("/records/7?page=4");
    expect(chip.textContent).toBe("1");
  });

  it("gives a second citation its own chip, keyed to its own page", () => {
    const second: Citation = { ...citation, marker: 2, chunk_id: 12, page: 9 };
    renderScreen(
      <ChatMessageBubble
        message={assistantMessage({
          content: "Rainfall gauge data was used [1] and validated separately [2].",
          citations: [citation, second],
        })}
      />,
    );

    expect(
      screen.getByRole("link", { name: /at page 9/i }).getAttribute("href"),
    ).toBe("/records/7?page=9");
  });

  it("links to the record without a page when extraction could not place one", () => {
    renderScreen(
      <ChatMessageBubble message={assistantMessage({ citations: [{ ...citation, page: null }] })} />,
    );

    const link = screen.getByRole("link", {
      name: /Open Flood Prediction in the Mananga Catchment$/i,
    });
    // No invented page: a confident wrong page is worse than no page.
    expect(link.getAttribute("href")).toBe("/records/7");
  });

  it("says when the answer came from the degraded path", () => {
    renderScreen(<ChatMessageBubble message={assistantMessage({ degraded: true })} />);

    expect(screen.getByText(/keyword matching, not meaning/i)).toBeTruthy();
  });

  it("says nothing about degrading when retrieval was healthy", () => {
    renderScreen(<ChatMessageBubble message={assistantMessage()} />);

    expect(screen.queryByText(/keyword matching, not meaning/i)).toBeNull();
  });

  it("renders a replayed citation as a bare chip when there is no quote to show", () => {
    // A reopened Conversation's stored citation is a pointer only -- record,
    // chunk, page -- until IR-299 re-resolves the quote (IR-298).
    renderScreen(
      <ChatMessageBubble
        message={assistantMessage({
          citations: [{ marker: 1, record_id: 7, chunk_id: 11, page: 4 }],
        })}
      />,
    );

    const link = screen.getByRole("link", { name: /Open the source at page 4/i });
    expect(link.getAttribute("href")).toBe("/records/7?page=4");
  });

  it("says when the answer left the paper being read", () => {
    renderScreen(<ChatMessageBubble message={assistantMessage({ widened: true })} />);

    expect(screen.getByText(/Searched all papers/i)).toBeTruthy();
  });

  it("says nothing about scope when the answer was not widened", () => {
    renderScreen(<ChatMessageBubble message={assistantMessage()} />);

    expect(screen.queryByText(/Searched all papers/i)).toBeNull();
  });

  it("says when the reply was cut off before it finished (IR-328)", () => {
    renderScreen(<ChatMessageBubble message={assistantMessage({ partial: true })} />);

    expect(screen.getByText(/cut off before it finished/i)).toBeTruthy();
  });

  it("says nothing about being cut off for a complete answer", () => {
    renderScreen(<ChatMessageBubble message={assistantMessage()} />);

    expect(screen.queryByText(/cut off before it finished/i)).toBeNull();
  });

  it("has no serious or critical accessibility violations", async () => {
    const { container } = renderScreen(
      <ChatMessageBubble message={assistantMessage({ degraded: true })} />,
    );

    await expectNoBlockingA11yViolations(container);
  });
});
