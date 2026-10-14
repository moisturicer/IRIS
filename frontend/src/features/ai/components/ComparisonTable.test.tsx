import { describe, expect, it } from "vitest";
import { useLocation } from "react-router-dom";
import { CitationOriginContext } from "@/lib/citedPage";
import { turnToMessages } from "@/lib/chatMessages";
import { renderScreen, screen, within, userEvent } from "@/test/render";
import { expectNoBlockingA11yViolations } from "@/test/axe";
import type { AnswerComparison, ConversationTurn } from "@/types/ai";
import { ChatMessageBubble } from "./ChatMessageBubble";
import { ComparisonTable } from "./ComparisonTable";

const comparison: AnswerComparison = {
  records: [{ record_id: 7, title: "Flood Prediction" }, { record_id: 9, title: "Water Quality" }],
  rows: [{ dimension: "method", label: "Method", cells: [
    { record_id: 9, state: "not_reported", values: [] },
    { record_id: 7, state: "reported", values: [{ value: "Rainfall gauges", citations: [{ page: 4, quote: "Used rainfall gauges", chunk_id: 11, marker: 4 }] }] },
  ] }, { dimension: "limitations", label: "Limitations", cells: [
    { record_id: 7, state: "unsupported", values: [{ value: "Invented limitation", citations: [] }] },
    { record_id: 9, state: "reported", values: [] },
  ] }],
  coverage: [{ record_id: 7, state: "read_fully" }, { record_id: 9, state: "read_by_section", reason: "section_budget" }],
  removed_claims: 1,
};

describe("a checked paper comparison", () => {
  it("preserves the citation and Paper Chat origin when the reader follows a page chip", async () => {
    function Destination() {
      const location = useLocation();
      return <output aria-label="Citation destination">{JSON.stringify(location.state)}</output>;
    }
    renderScreen(<CitationOriginContext.Provider value="paper-chat">
      <ComparisonTable comparison={comparison} /><Destination />
    </CitationOriginContext.Provider>);
    await userEvent.click(screen.getByRole("link", { name: "Open Flood Prediction at page 4" }));
    const navigation = JSON.parse(screen.getByLabelText("Citation destination").textContent!);
    expect(navigation.origin).toBe("paper-chat");
    expect(navigation.citation).toMatchObject({ record_id: 7, page: 4, chunk_id: 11, text: "Used rainfall gauges", marker: 4 });
  });

  it("keeps checked facts when the same cell also had unsupported claims", () => {
    renderScreen(<ComparisonTable comparison={{ ...comparison, rows: [{
      dimension: "method", label: "Method", cells: [{
        ...comparison.rows[0].cells[1], state: "unsupported",
      }],
    }], removed_claims: 2 }} />);
    expect(screen.getByText("Rainfall gauges")).toBeTruthy();
    expect(screen.getByText("Some claims could not be verified.")).toBeTruthy();
    expect(screen.getByText("2 unsupported claims removed.")).toBeTruthy();
  });
  it("renders facts in their paper columns with citations that open the cited page", async () => {
    const { container } = renderScreen(<ComparisonTable comparison={comparison} />);
    const table = screen.getByRole("table", { name: "Paper comparison" });
    const cells = within(table).getAllByRole("cell");
    expect(cells[0].textContent).toContain("Rainfall gauges");
    expect(cells[1].textContent).toBe("Not reported");
    const citation = within(table).getByRole("link", { name: "Open Flood Prediction at page 4" });
    expect(citation.getAttribute("href")).toBe("/records/7?page=4");
    expect(screen.getByRole("region", { name: "Paper comparison" }).getAttribute("tabindex")).toBe("0");
    await expectNoBlockingA11yViolations(container);
  });

  it("keeps unchecked facts distinct from a paper explicitly not reporting something", () => {
    renderScreen(<ComparisonTable comparison={comparison} />);
    expect(screen.getAllByText("Unverified")).toHaveLength(2);
    expect(screen.getAllByText("Not reported")).toHaveLength(1);
    expect(screen.queryByText("Invented limitation")).toBeNull();
    expect(screen.getByText("1 unsupported claim removed.")).toBeTruthy();
  });

  it("shows safe coverage wording and conceals forbidden identities and unknown reasons", () => {
    renderScreen(<ComparisonTable comparison={{ ...comparison,
      records: [...comparison.records, { record_id: 99, title: "Forbidden paper title" }],
      coverage: [...comparison.coverage,
        { record_id: 99, title: "Forbidden paper title", state: "not_permitted", reason: "Forbidden paper title" },
        { record_id: 9, state: "could_not_read", reason: "private backend traceback" },
      ],
    }} />);
    const coverage = screen.getByRole("complementary", { name: "Comparison coverage" });
    expect(coverage.textContent).toContain("Read in full");
    expect(coverage.textContent).toContain("Read by section");
    expect(coverage.textContent).toContain("Not permitted to read");
    expect(coverage.textContent).toContain("Could not read");
    expect(screen.queryByText(/Forbidden paper title/)).toBeNull();
    expect(screen.queryByText(/private backend traceback/)).toBeNull();
    expect(screen.getAllByText("Unavailable")).toHaveLength(2);
    expect(screen.queryByText("Not reported")).toBeNull();
  });

  it("replays the same comparison before the answer prose after reopening the chat", () => {
    const turn: ConversationTurn = {
      id: 5, question: "Compare these papers", resolved_question: null, answer: "These papers use different methods.",
      message: null, state: "generative", degraded: false, widened: false, created_at: "2026-10-14T00:00:00Z",
      citations: [], comparison,
    };
    const [, message] = turnToMessages(turn);
    renderScreen(<ChatMessageBubble message={message} />);
    const table = screen.getByRole("table", { name: "Paper comparison" });
    const prose = screen.getByText("These papers use different methods.");
    expect(table.compareDocumentPosition(prose) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });
});
