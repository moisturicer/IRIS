/**
 * A listing's candidates, live and finished (IR-546): pending cards that move
 * to a state by record id, a final list that separates every state in words,
 * and the same on a reopened conversation.
 */
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { turnToMessages } from "@/lib/chatMessages";
import { expectNoBlockingA11yViolations } from "@/test/axe";
import { renderScreen, screen, within } from "@/test/render";
import type { AnswerListing, CandidateRow, ConversationTurn } from "@/types/ai";
import type { StreamingState } from "../hooks/useAskStream";

import { ChatMessageBubble } from "./ChatMessageBubble";
import { LiveCandidates } from "./CandidateList";
import { statusLineText } from "./StreamStatusLine";
import { StreamingMessageBubble } from "./StreamingMessageBubble";

const PENDING: CandidateRow[] = [
  { record_id: 1, title: "Flood Prediction", state: "pending" },
  { record_id: 2, title: "Tilapia Ponds", state: "pending" },
  { record_id: 3, state: "unassessed", withheld: true },
];

describe("the live candidates", () => {
  it("names every paper as relevance pending and never as a match", async () => {
    const { container } = renderScreen(<LiveCandidates candidates={PENDING} />);
    const items = within(screen.getByRole("list", { name: "Candidates" })).getAllByRole("listitem");
    expect(items.map((item) => item.textContent)).toEqual([
      "Flood Prediction · Relevance pending",
      "Tilapia Ponds · Relevance pending",
      "A paper IRIS may not read · Could not be assessed",
    ]);
    expect(screen.queryByText(/Matches/)).toBeNull();
    await expectNoBlockingA11yViolations(container);
  });

  it("links each paper, and a withheld one never shows a title", () => {
    renderScreen(<LiveCandidates candidates={PENDING} />);
    expect(screen.getByRole("link", { name: "Flood Prediction" })).toHaveAttribute("href", "/records/1");
    expect(screen.getByRole("link", { name: "A paper IRIS may not read" })).toHaveAttribute("href", "/records/3");
  });

  it("announces progress once, in a status region, not a line per paper", () => {
    renderScreen(<LiveCandidates candidates={[{ ...PENDING[0], state: "included" }, PENDING[1]]} />);
    expect(screen.getByRole("status").textContent).toBe("1 of 2 candidate papers checked");
  });

  it("renders nothing for an empty preview", () => {
    const { container } = renderScreen(<LiveCandidates candidates={[]} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("puts the screening progress in the status line", () => {
    const state: StreamingState = {
      stage: "searching", foundInfo: null, text: "", reasoning: "", citations: [],
      candidates: [{ ...PENDING[0], state: "included" }, PENDING[1]],
    };
    expect(statusLineText(state)).toBe("Screening 2 candidate papers (1 checked)…");
    expect(statusLineText({ ...state, candidates: state.candidates!.map((row) => ({ ...row, state: "excluded" })) }))
      .toBe("Searching the repository…");
  });

  it("appears inside the streaming reply", () => {
    renderScreen(
      <StreamingMessageBubble state={{
        stage: "searching", foundInfo: null, text: "", reasoning: "", citations: [], candidates: PENDING,
      }} />,
    );
    expect(screen.getByRole("region", { name: "Candidate papers" })).toBeInTheDocument();
  });
});

const LISTING: AnswerListing = {
  completeness: "matches_found",
  wording: "Screened 5 candidate papers: 1 matched, 1 did not match, 1 uncertain, 2 could not be assessed. "
    + "These are matches found, not a complete list of the papers you can see.",
  records: [{ record_id: 1, title: "Flood Prediction" }],
  candidates: [
    { record_id: 1, title: "Flood Prediction", state: "included",
      quote: "rainfall gauge data to predict flooding", source: { field: "passage", page: 4, chunk_id: 9 } },
    { record_id: 2, title: "Tilapia Ponds", state: "excluded" },
    { record_id: 3, title: "Rainfall Note", state: "uncertain" },
    { record_id: 4, title: "Flood Hazard", state: "unassessed" },
    { record_id: 5, state: "unassessed", withheld: true },
  ],
  coverage: {
    limit: 20, selected: 5, included: 1, excluded: 1, uncertain: 1, unassessed: 2,
    more_available: false, search_degraded: false, changed: false,
  },
};

const TURN: ConversationTurn = {
  id: 3, question: "Which papers are about flooding?", resolved_question: null,
  answer: LISTING.wording, message: null, state: "generative", degraded: true, widened: false,
  partial: false, reasoning: null, created_at: "2026-10-14", citations: [],
  listing: LISTING,
};

describe("a finished listing", () => {
  it("leads with the matches, linked to the page the quote came from", async () => {
    const { container } = renderScreen(<ChatMessageBubble message={turnToMessages(TURN)[1]} />);
    expect(screen.getByText(LISTING.wording)).toBeInTheDocument();
    const matches = screen.getByRole("list", { name: "Matching papers" });
    expect(within(matches).getByRole("link", { name: "Flood Prediction" })).toHaveAttribute("href", "/records/1?page=4");
    expect(within(matches).getByText("rainfall gauge data to predict flooding")).toBeInTheDocument();
    expect(within(matches).queryByText(/Tilapia/)).toBeNull();
    await expectNoBlockingA11yViolations(container);
  });

  it("keeps every other state, in words, behind a disclosure", async () => {
    renderScreen(<ChatMessageBubble message={turnToMessages(TURN)[1]} />);
    await userEvent.click(screen.getByText("Other candidates (4)"));
    const others = within(screen.getByRole("list", { name: "Other candidates" })).getAllByRole("listitem");
    expect(others.map((item) => item.textContent)).toEqual([
      "Tilapia Ponds · Does not match",
      "Rainfall Note · Uncertain",
      "Flood Hazard · Could not be assessed",
      "A paper IRIS may not read · Could not be assessed",
    ]);
  });

  it("states an inconclusive result without listing a match or an empty-handed apology", () => {
    const inconclusive: ConversationTurn = {
      ...TURN,
      listing: {
        ...LISTING, completeness: "inconclusive", records: [],
        wording: "Inconclusive: none of the 2 candidate papers could be assessed, so this does not show whether any match.",
        candidates: [{ record_id: 4, title: "Flood Hazard", state: "unassessed" }, { record_id: 5, title: "Tilapia", state: "unassessed" }],
      },
    };
    renderScreen(<ChatMessageBubble message={turnToMessages(inconclusive)[1]} />);
    expect(screen.getByText(/Inconclusive: none of the 2 candidate papers/)).toBeInTheDocument();
    expect(screen.queryByRole("list", { name: "Matching papers" })).toBeNull();
    expect(screen.queryByText("No papers are listed for this answer.")).toBeNull();
  });

  it("still renders an older listing that has no candidate states", () => {
    const legacy: ConversationTurn = {
      ...TURN,
      listing: { completeness: "matches_found", wording: "Matches found.", records: [{ record_id: 7, title: "Old Listing" }] },
    };
    renderScreen(<ChatMessageBubble message={turnToMessages(legacy)[1]} />);
    expect(screen.getByRole("link", { name: "Old Listing" })).toHaveAttribute("href", "/records/7");
  });
});
