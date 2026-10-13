/**
 * The research planner's steps and coverage notes (IR-504): live while the
 * run goes, collapsed on the finished answer, and the same on a reopened
 * transcript.
 */
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { turnToMessages } from "@/lib/chatMessages";
import { expectNoBlockingA11yViolations } from "@/test/axe";
import { renderScreen, screen, within } from "@/test/render";
import type { AgentStepEvent, ConversationTurn } from "@/types/ai";
import type { StreamingState } from "../hooks/useAskStream";

import { ChatMessageBubble } from "./ChatMessageBubble";
import { CoverageNotes, ResearchSteps } from "./ResearchSteps";
import { statusLineText } from "./StreamStatusLine";

function step(position: number, overrides: Partial<AgentStepEvent>): AgentStepEvent {
  return {
    position, kind: "tool", status: "ok", tool: "", duplicate: false,
    latency_ms: 500, coverage: null, found: null, ...overrides,
  };
}

const FINISHED = [
  step(0, { kind: "plan" }),
  step(1, { tool: "plan_research" }),
  step(2, { kind: "plan" }),
  step(3, { tool: "search_passages", found: 4, coverage: "sample" }),
  step(4, { kind: "answer", status: "generated" }),
];

describe("the live step trail", () => {
  it("lists each step as it happens, naming the one running", () => {
    renderScreen(
      <ResearchSteps live steps={[...FINISHED.slice(0, 3), step(3, { tool: "search_passages", status: "running" })]} />,
    );
    const items = within(screen.getByRole("list", { name: "Research steps" })).getAllByRole("listitem");
    expect(items.map((item) => item.textContent)).toEqual([
      "Planned the research",
      "Searching passages…",
    ]);
  });

  it("puts the running step in the progress line", () => {
    const state: StreamingState = {
      stage: "searching", foundInfo: null, text: "", reasoning: "", citations: [],
      steps: [step(0, { kind: "plan", status: "running" })],
    };
    expect(statusLineText(state)).toBe("Deciding the next step…");
  });
});

describe("a finished research answer", () => {
  it("starts collapsed and opens to the steps with their counts", async () => {
    const { container } = renderScreen(<ResearchSteps steps={FINISHED} />);
    const toggle = screen.getByRole("button", { name: /researched in 3 steps/i });
    expect(toggle.getAttribute("aria-expanded")).toBe("false");
    expect(screen.queryByRole("list", { name: "Research steps" })).toBeNull();

    await userEvent.click(toggle);
    const list = screen.getByRole("list", { name: "Research steps" });
    expect(within(list).getByText("4 found · a sample")).toBeTruthy();
    await expectNoBlockingA11yViolations(container);
  });

  it("shows coverage notes apart from the answer", async () => {
    const { container } = renderScreen(
      <CoverageNotes notes={[{ code: "stopped_early", reason: "max_tool_calls", text: "Research stopped early." }]} />,
    );
    expect(screen.getByRole("complementary", { name: "Coverage" }).textContent).toContain("Research stopped early.");
    await expectNoBlockingA11yViolations(container);
  });

  it("replays steps and coverage notes on a reopened conversation", () => {
    const turn = {
      id: 7, question: "What do the flood papers find?", resolved_question: null,
      answer: "Rainfall gauges feed the model [1].", message: null, state: "generative",
      degraded: false, widened: false, partial: false, had_reasoning: false, reasoning: null,
      created_at: "2026-10-12T00:00:00Z", citations: [],
      research: {
        run_id: "r", stop_reason: "max_tool_calls", steps: FINISHED,
        coverage_notes: [{ code: "stopped_early", text: "Research stopped early." }],
      },
    } as unknown as ConversationTurn;
    const [, reply] = turnToMessages(turn);
    renderScreen(<ChatMessageBubble message={reply} />);
    expect(screen.getByRole("button", { name: /researched in 3 steps/i })).toBeTruthy();
    expect(screen.getByRole("complementary", { name: "Coverage" }).textContent).toContain("Research stopped early.");
    expect(screen.queryByText(/Research stopped early/, { selector: "p.whitespace-pre-wrap" })).toBeNull();
  });
});
