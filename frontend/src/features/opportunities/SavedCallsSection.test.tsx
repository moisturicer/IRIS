/**
 * My Library's Saved calls (IR-766): every saved Call with its tags, Over
 * included, until the reader removes it; an unavailable one says so.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ToastContainer } from "@/components/ui/Toast";
import { useAuthStore } from "@/store/auth.store";
import { useSavedCallsStore } from "@/store/savedCalls.store";
import { useUIStore } from "@/store/ui.store";
import { expectNoBlockingA11yViolations } from "@/test/axe";
import { renderScreen, screen, userEvent, waitFor, within } from "@/test/render";

import { callFixture } from "./callFixture";
import { SavedCallsSection } from "./SavedCallsSection";

const saved = vi.fn();
const unsave = vi.fn();
vi.mock("@/api/opportunities", () => ({
  opportunitiesApi: { saved: () => saved(), save: vi.fn(), unsave: (id: number) => unsave(id) },
}));

const overCall = callFixture({
  id: 21, title: "Last year's symposium", status: "confirmed", status_label: "Confirmed",
  papers_state: "closed", papers_label: "Submissions closed", is_closed: true,
  event_state: "over", event_label: "Event over",
});
const openCall = callFixture({
  id: 22, title: "ICCE 2027", status: "confirmed", status_label: "Confirmed",
  event_state: "upcoming", event_label: "Upcoming", start_date: "2027-01-20",
});

beforeEach(() => {
  useAuthStore.setState({ isAuthenticated: true });
  useSavedCallsStore.setState({ load: "idle", items: {} });
});

afterEach(() => {
  vi.clearAllMocks();
  useUIStore.setState({ toasts: [] });
});

async function open(results: unknown[]) {
  saved.mockResolvedValue({ data: { results } });
  const view = renderScreen(<><SavedCallsSection /><ToastContainer /></>);
  await waitFor(() => expect(screen.queryByRole("status", { busy: true })).toBeNull());
  return view;
}

describe("Saved calls", () => {
  it("lists each saved call, newest first, with its tags, Over included", async () => {
    await open([
      { call_id: 22, available: true, saved_at: "2026-11-15T08:00:00Z", call: openCall },
      { call_id: 21, available: true, saved_at: "2026-11-10T08:00:00Z", call: overCall },
    ]);
    const list = screen.getByRole("list", { name: "Saved calls" });
    expect(within(list).getAllByRole("article").map((a) => within(a).getByRole("heading").textContent))
      .toEqual(["ICCE 2027", "Last year's symposium"]);

    const over = screen.getByRole("article", { name: "Last year's symposium" });
    expect(within(over).getByText("Submissions closed")).toBeInTheDocument();
    expect(within(over).getByText("Event over")).toBeInTheDocument();
    expect(within(screen.getByRole("article", { name: "ICCE 2027" })).getByText("Upcoming")).toBeInTheDocument();
    expect(within(over).getByRole("link", { name: /View call/ })).toHaveAttribute("target", "_blank");
  });

  it("lists a call sent back or rejected as unavailable, saying nothing more, and lets it be removed", async () => {
    unsave.mockResolvedValue({});
    await open([{ call_id: 9, available: false }]);
    const row = screen.getByRole("article", { name: "Unavailable call" });
    expect(within(row).getByText("This call is no longer on Calls & Conferences.")).toBeInTheDocument();

    await userEvent.setup().click(within(row).getByRole("button", { name: "Remove unavailable call" }));
    expect(unsave).toHaveBeenCalledWith(9);
    expect(await screen.findByRole("heading", { name: "No saved calls" })).toBeInTheDocument();
  });

  it("removes a call, and puts it back with a toast when that fails", async () => {
    unsave.mockRejectedValueOnce(new Error("Network Error"));
    await open([{ call_id: 22, available: true, saved_at: "2026-11-15T08:00:00Z", call: openCall }]);

    await userEvent.setup().click(screen.getByRole("button", { name: "Remove ICCE 2027" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Could not remove ICCE 2027. It is still saved.");
    expect(screen.getByRole("article", { name: "ICCE 2027" })).toBeInTheDocument();
  });

  it("points a reader with no saved calls to the board", async () => {
    await open([]);
    expect(screen.getByRole("heading", { name: "No saved calls" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Go to Calls & Conferences" })).toHaveAttribute("href", "/opportunities");
  });

  it("says when the list didn't load, and tries again", async () => {
    saved.mockRejectedValueOnce(new Error("offline"));
    renderScreen(<SavedCallsSection />);
    const alert = await screen.findByRole("alert");
    expect(within(alert).getByRole("heading", { name: "Could not load your saved calls" })).toBeInTheDocument();

    saved.mockResolvedValue({ data: { results: [{ call_id: 22, available: true, saved_at: "2026-11-15T08:00:00Z", call: openCall }] } });
    await userEvent.setup().click(within(alert).getByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("article", { name: "ICCE 2027" })).toBeInTheDocument();
  });

  it("says a read that took too long was interrupted, and retries", async () => {
    const { RequestTimeoutError } = await import("@/api/requestPolicy");
    saved.mockRejectedValueOnce(new RequestTimeoutError(30_000, "get", "/opportunities/saved/"));
    renderScreen(<SavedCallsSection />);
    expect(await screen.findByRole("heading", { name: "This took too long" })).toBeInTheDocument();

    saved.mockResolvedValue({ data: { results: [] } });
    await userEvent.setup().click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByRole("heading", { name: "No saved calls" })).toBeInTheDocument();
  });

  it("has no serious accessibility violations", async () => {
    const { container } = await open([
      { call_id: 22, available: true, saved_at: "2026-11-15T08:00:00Z", call: openCall },
      { call_id: 21, available: true, saved_at: "2026-11-10T08:00:00Z", call: overCall },
      { call_id: 9, available: false },
    ]);
    await expectNoBlockingA11yViolations(container);
  });
});
