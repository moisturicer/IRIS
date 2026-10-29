/**
 * Workflow analytics (IR-626, ADR-043). Every query goes through the
 * accessible tree.
 */
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { expectNoBlockingA11yViolations } from "@/test/axe";
import { renderScreen, screen, waitFor, within } from "@/test/render";
import type { WorkflowAnalytics } from "@/types/reviews";

import ReviewAnalyticsPage from "./ReviewAnalyticsPage";

const analytics = vi.fn();

vi.mock("@/api/reviews", () => ({
  reviewsApi: { analytics: (query: unknown) => analytics(query) },
}));

function payload(overrides: Partial<WorkflowAnalytics> = {}): { data: WorkflowAnalytics } {
  return {
    data: {
      parties: [{ party: "itso", label: "ITSO" }],
      data_since: "2026-10-20T01:00:00Z",
      generated_at: "2026-10-29T01:00:00Z",
      range: { from: null, to: null },
      thresholds: { median: 5, p90: 10 },
      open_now: [{ party: "itso", open_count: 4, unseated: 1, open_seats: 4, undated: 1,
                   paused: 1, overdue: 1, overdue_seats: 2 }],
      time_in_stage: [
        { party: "itso", record_type: null, records: 12, turns: 12, median_hours: 30,
          p90_hours: 72, too_few_for: [] },
        { party: "itso", record_type: "Proposal", records: 3, turns: 3, median_hours: null,
          p90_hours: null, too_few_for: ["median", "p90"] },
      ],
      unmeasured: [{ party: "itso", started_before_log: 2, ended_not_completed: 1, still_open: 4 }],
      throughput: [{ party: "itso", week_start: "2026-10-26", entered: 3, left: 2 }],
      revision_cycles: [{ policy: "clearance_aware", cycles: 4, cycles_preserving: 3,
                          preserved_clearances: 5 }],
      preserved_by_office: [{ party: "itso", policy: "clearance_aware", preserved_clearances: 3 }],
      ...overrides,
    },
  };
}

describe("ReviewAnalyticsPage", () => {
  beforeEach(() => analytics.mockResolvedValue(payload()));
  afterEach(() => analytics.mockReset());

  it("says when the figures start, because the log has no history before then", async () => {
    renderScreen(<ReviewAnalyticsPage />);

    expect(await screen.findByText(/figures start on oct 20, 2026/i)).toBeInTheDocument();
  });

  it("shows a median only where there are enough records, and says why otherwise", async () => {
    renderScreen(<ReviewAnalyticsPage />);

    const table = await screen.findByRole("table", { name: /time in stage/i });
    const all = within(table).getByRole("row", { name: /all record types/i });
    expect(within(all).getByText("1.3 days")).toBeInTheDocument();
    expect(within(all).getByText("3.0 days")).toBeInTheDocument();
    const proposal = within(table).getByRole("row", { name: /proposal/i });
    expect(within(proposal).getAllByText(/too few records \(3 of 5\)|too few records \(3 of 10\)/i))
      .toHaveLength(2);
  });

  it("calls time in stage elapsed time, not effort", async () => {
    renderScreen(<ReviewAnalyticsPage />);

    expect(await screen.findByText(/not hands-on effort/i)).toBeInTheDocument();
  });

  it("reports open and overdue work, and what could not be measured", async () => {
    renderScreen(<ReviewAnalyticsPage />);

    const open = await screen.findByRole("table", { name: /open now/i });
    const itso = within(open).getByRole("row", { name: /itso/i });
    expect(within(itso).getAllByRole("cell").map((c) => c.textContent)).toEqual(
      ["4", "1", "4", "1", "2", "1", "1"]);
    expect(screen.getByText(/2 began before the log/i)).toBeInTheDocument();
  });

  it("lets RDCO narrow to one office", async () => {
    analytics.mockResolvedValue(payload({
      parties: [{ party: "itso", label: "ITSO" }, { party: "ierc", label: "IERC" }],
    }));
    renderScreen(<ReviewAnalyticsPage />);

    await userEvent.selectOptions(await screen.findByRole("combobox", { name: /office/i }), "ierc");

    await waitFor(() => expect(analytics).toHaveBeenLastCalledWith(
      { office: "ierc", from: "", to: "" }));
  });

  it("offers no office choice to a single office", async () => {
    renderScreen(<ReviewAnalyticsPage />);

    await screen.findByRole("table", { name: /open now/i });
    expect(screen.queryByRole("combobox", { name: /office/i })).not.toBeInTheDocument();
  });

  it("says so when the analytics could not be loaded", async () => {
    analytics.mockRejectedValue(new Error("boom"));
    renderScreen(<ReviewAnalyticsPage />);

    expect(await screen.findByText(/could not be loaded/i)).toBeInTheDocument();
  });

  it("retries a failed load without leaving the page", async () => {
    analytics.mockRejectedValueOnce(new Error("offline"));
    renderScreen(<ReviewAnalyticsPage />);
    await userEvent.click(await screen.findByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("table", { name: /open now/i })).toBeInTheDocument();
    expect(analytics).toHaveBeenCalledTimes(2);
  });

  it("rejects a reversed date range before requesting figures", async () => {
    renderScreen(<ReviewAnalyticsPage />);
    await screen.findByRole("table", { name: /open now/i });
    const from = screen.getByLabelText("From");
    const to = screen.getByLabelText("To");
    // Native date values are set as complete dates.
    const { fireEvent } = await import("@testing-library/react");
    fireEvent.change(from, { target: { value: "2026-11-10" } });
    await waitFor(() => expect(analytics).toHaveBeenLastCalledWith(
      { office: "", from: "2026-11-10", to: "" }));
    const requests = analytics.mock.calls.length;
    fireEvent.change(to, { target: { value: "2026-11-01" } });
    expect(await screen.findByRole("alert")).toHaveTextContent("From must be on or before To.");
    expect(analytics).toHaveBeenCalledTimes(requests);
  });

  it("states the empty-log state without suggesting completed data exists", async () => {
    analytics.mockResolvedValue(payload({ data_since: null, time_in_stage: [],
      throughput: [], revision_cycles: [], preserved_by_office: [] }));
    renderScreen(<ReviewAnalyticsPage />);
    expect(await screen.findByText(/No workflow events have been recorded yet/)).toBeInTheDocument();
    expect(screen.getByText("No completed turns in this range.")).toBeInTheDocument();
  });

  it("has no blocking accessibility violations", async () => {
    const { container } = renderScreen(<ReviewAnalyticsPage />);
    await screen.findByRole("table", { name: /open now/i });

    await expectNoBlockingA11yViolations(container);
  });
});
