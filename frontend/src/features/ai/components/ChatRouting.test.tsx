import { describe, expect, it, vi } from "vitest";
import { renderScreen, screen, userEvent } from "@/test/render";
import { routingFixture } from "@/test/routingFixture";
import { turnToMessages } from "@/lib/chatMessages";
import type { ConversationTurn } from "@/types/ai";
import { ChatMessageBubble } from "./ChatMessageBubble";

const turn: ConversationTurn = {
  id: 1, question: "Find flooding papers", resolved_question: "Flooding at CIT-U",
  answer: "Retrieved papers", message: null, state: "generative", degraded: false,
  widened: true, created_at: "2026-10-11", citations: [], routing: routingFixture,
  listing: { completeness: "matches_found", wording: "Matches found; other papers may also match.",
    records: [{ record_id: 7, title: "Flood Prediction" }] },
};

describe("routing and listing on replayed answers", () => {
  it("shows the decision and permits one-action reruns using only allowed lanes", async () => {
    const rerun = vi.fn();
    const message = turnToMessages(turn)[1];
    renderScreen(<ChatMessageBubble message={message} onRouteOverride={rerun} />);
    expect(screen.getByText("Passages")).toBeInTheDocument();
    await userEvent.click(screen.getByText("Why this approach?"));
    expect(screen.getByText(/selected this approach to match/)).toBeVisible();
    expect(screen.queryByRole("button", { name: "Rerun with Research" })).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "Rerun with List papers" }));
    expect(rerun).toHaveBeenCalledWith(expect.objectContaining({ question: turn.question, widened: true }), "listing");
  });

  it("renders server listing rows as links with their completeness wording", () => {
    renderScreen(<ChatMessageBubble message={turnToMessages(turn)[1]} />);
    expect(screen.getByRole("link", { name: "Flood Prediction" })).toHaveAttribute("href", "/records/7");
    expect(screen.getByText(turn.listing!.wording)).toBeInTheDocument();
    expect(screen.queryByText(turn.answer!)).toBeNull();
  });

  it("does not invent routing controls when routing is absent", () => {
    renderScreen(<ChatMessageBubble message={turnToMessages({ ...turn, routing: undefined, listing: undefined })[1]} onRouteOverride={vi.fn()} />);
    expect(screen.queryByLabelText("Answer routing")).toBeNull();
    expect(screen.queryByLabelText("Rerun answer")).toBeNull();
  });

  it("explains restrictions and hides the rerun prompt when no alternatives exist", async () => {
    const message = turnToMessages({ ...turn, routing: { ...routingFixture, allowed_overrides: ["passage"], reason: "unknown_future_reason" } })[1];
    renderScreen(<ChatMessageBubble message={message} onRouteOverride={vi.fn()} />);
    await userEvent.click(screen.getByText("Why this approach?"));
    expect(screen.getByText(/stays within the current paper/)).toBeVisible();
    expect(screen.queryByText("unknown_future_reason")).toBeNull();
    expect(screen.queryByText("Try instead:")).toBeNull();
  });

  it("explains injection screening without exposing its internal reason code", async () => {
    const message = turnToMessages({ ...turn, routing: { ...routingFixture, injection_flagged: true, planner_allowed: false, reason: "question_injection", allowed_overrides: ["passage"] } })[1];
    renderScreen(<ChatMessageBubble message={message} onRouteOverride={vi.fn()} />);
    await userEvent.click(screen.getByText("Why this approach?"));
    expect(screen.getByText(/Only passage answers are available/)).toBeVisible();
    expect(screen.queryByText("question_injection")).toBeNull();
    expect(screen.queryByLabelText("Rerun answer")).toBeNull();
  });

  it("explains the research landscape limitation", async () => {
    const message = turnToMessages({ ...turn, routing: { ...routingFixture, lane: "landscape", allowed_overrides: ["landscape"] } })[1];
    renderScreen(<ChatMessageBubble message={message} onRouteOverride={vi.fn()} />);
    await userEvent.click(screen.getByText("Why this approach?"));
    expect(screen.getByText(/gap analysis is not available yet/)).toBeVisible();
    expect(screen.queryByText("Try instead:")).toBeNull();
  });

  it("disables reruns while busy and obeys restricted allowed overrides", () => {
    const message = turnToMessages({ ...turn, routing: { ...routingFixture, planner_allowed: false, allowed_overrides: ["passage", "count"] } })[1];
    renderScreen(<ChatMessageBubble message={message} onRouteOverride={vi.fn()} overrideDisabled />);
    expect(screen.getByRole("button", { name: "Rerun with Count papers" })).toBeDisabled();
    expect(screen.queryByRole("button", { name: "Rerun with List papers" })).toBeNull();
  });
});
