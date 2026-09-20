/**
 * What a reader can actually check (IR-284).
 *
 * The claim this ticket makes is that an answer now shows *which sentence*
 * supports it and *which page* that sentence is on. That claim is only true
 * if those things are on the screen and reachable, so this asserts them the
 * way a reader meets them: by the text they read and the link they click.
 *
 * Every query goes through the accessible tree, by role and accessible name.
 */
import { describe, expect, it } from "vitest";

import { expectNoBlockingA11yViolations } from "@/test/axe";
import { renderScreen, screen } from "@/test/render";
import type { Citation } from "@/types/ai";
import type { ChatMessage } from "@/types/chat";

import { ChatMessageBubble } from "./ChatMessageBubble";

const QUOTE =
  "we trained a convolutional neural network on rainfall gauge data to predict flooding";

const citation: Citation = {
  marker:       1,
  chunk_id:     11,
  record_id:    7,
  record_title: "Flood Prediction in the Mananga Catchment",
  page:         4,
  text:         QUOTE,
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
  it("quotes the passage the claim rests on", () => {
    renderScreen(<ChatMessageBubble message={assistantMessage()} />);

    expect(screen.getByRole("blockquote").textContent).toBe(QUOTE);
  });

  it("names the page the passage sits on, in the link a reader follows", () => {
    renderScreen(<ChatMessageBubble message={assistantMessage()} />);

    const link = screen.getByRole("link", {
      name: /Open Flood Prediction in the Mananga Catchment at page 4/i,
    });
    expect(link.getAttribute("href")).toBe("/records/7?page=4");
  });

  it("counts passages rather than records, because two can come from one paper", () => {
    const second: Citation = { ...citation, marker: 2, chunk_id: 12, page: 9 };
    renderScreen(
      <ChatMessageBubble message={assistantMessage({ citations: [citation, second] })} />,
    );

    expect(screen.getByText(/Grounded in 2 passages/i)).toBeTruthy();
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

  it("hides the passage strip when the sources panel is showing them instead", () => {
    renderScreen(<ChatMessageBubble message={assistantMessage()} showSources={false} />);

    expect(screen.queryByRole("blockquote")).toBeNull();
  });

  it("has no serious or critical accessibility violations", async () => {
    const { container } = renderScreen(
      <ChatMessageBubble message={assistantMessage({ degraded: true })} />,
    );

    await expectNoBlockingA11yViolations(container);
  });
});
