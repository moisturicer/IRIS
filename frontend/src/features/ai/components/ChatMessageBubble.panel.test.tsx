/**
 * A turn beside a Sources panel (IR-1237): the answer says how many passages from
 * how many papers it rests on, its chips open the panel, and Ask again moves from
 * the question to the answer. Without a panel the bubble is what it was.
 */
import { describe, expect, it, vi } from "vitest";

import { renderScreen, screen, userEvent } from "@/test/render";
import type { ChatMessage } from "@/types/chat";
import type { Citation } from "@/types/ai";

import { ChatMessageBubble } from "./ChatMessageBubble";

const cite = (marker: number, record_id: number, title: string): Citation => ({
  marker, chunk_id: marker, record_id, record_title: title, page: marker + 2,
  text: `passage ${marker}`, context_path: [], regions: [],
});
const answer: ChatMessage = {
  id: "a:1", role: "assistant", content: "Both studies sample water: [1] [2] [3].", question: "How do they sample?",
  citations: [cite(1, 1, "Flood sensors"), cite(2, 1, "Flood sensors"), cite(3, 2, "Pond sampling")],
  createdAt: "2026-11-04T00:00:00.000Z",
};
const question: ChatMessage = { id: "q:1", role: "user", content: "How do they sample?", createdAt: "2026-11-04T00:00:00.000Z" };

describe("an answer beside a Sources panel", () => {
  it("counts passages and distinct papers, and opens the panel without a highlight", async () => {
    const open = vi.fn();
    renderScreen(<ChatMessageBubble message={answer} onOpenSources={open} openMarker={null} />);

    await userEvent.click(screen.getByRole("button", { name: "3 passages from 2 papers" }));

    expect(open).toHaveBeenCalledExactlyOnceWith(answer, null);
  });

  it("says passage and paper in the singular for one of each", () => {
    renderScreen(<ChatMessageBubble message={{ ...answer, citations: [cite(1, 1, "Flood sensors")] }}
      onOpenSources={vi.fn()} openMarker={null} />);

    expect(screen.getByRole("button", { name: "1 passage from 1 paper" })).toBeInTheDocument();
  });

  it("opens the panel at a chip's own marker, and presses only the open one", async () => {
    const open = vi.fn();
    renderScreen(<ChatMessageBubble message={answer} onOpenSources={open} openMarker={2} sourcesSelected />);

    expect(screen.getByRole("button", { name: /^Source 2:/ })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: /^Source 1:/ })).toHaveAttribute("aria-pressed", "false");
    await userEvent.click(screen.getByRole("button", { name: /^Source 3:/ }));
    expect(open).toHaveBeenCalledExactlyOnceWith(answer, 3);
  });

  it("presses no chip when the panel shows another answer", () => {
    renderScreen(<ChatMessageBubble message={answer} onOpenSources={vi.fn()} openMarker={2} />);

    expect(screen.getByRole("button", { name: /^Source 2:/ })).toHaveAttribute("aria-pressed", "false");
  });

  it("puts Copy and Ask again under the answer", async () => {
    const again = vi.fn();
    renderScreen(<ChatMessageBubble message={answer} onOpenSources={vi.fn()} openMarker={null} onAskAgain={again} />);

    expect(screen.getByRole("button", { name: "Copy answer" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Ask again" }));
    expect(again).toHaveBeenCalledExactlyOnceWith("How do they sample?");
  });
});

describe("a question beside a Sources panel", () => {
  it("has Edit and Copy, and no Ask again", () => {
    renderScreen(<ChatMessageBubble message={question} onOpenSources={vi.fn()} onAskAgain={vi.fn()} onEdit={vi.fn()} />);

    expect(screen.getByRole("button", { name: "Edit" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Copy question" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Ask again" })).not.toBeInTheDocument();
  });
});

describe("without a panel", () => {
  it("keeps Ask again under the question and none under the answer", () => {
    renderScreen(<>
      <ChatMessageBubble message={question} onAskAgain={vi.fn()} onEdit={vi.fn()} />
      <ChatMessageBubble message={answer} onAskAgain={vi.fn()} />
    </>);

    expect(screen.getAllByRole("button", { name: "Ask again" })).toHaveLength(1);
  });
});
