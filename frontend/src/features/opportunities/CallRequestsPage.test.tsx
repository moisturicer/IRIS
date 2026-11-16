/**
 * RDCO's Call Requests (IR-765). Every query goes through the accessible
 * tree; every control is fed from the Call's own `can_*` flags.
 */
import { afterEach, describe, expect, it, vi } from "vitest";

import { ToastContainer } from "@/components/ui/Toast";
import { useUIStore } from "@/store/ui.store";
import { expectNoBlockingA11yViolations } from "@/test/axe";
import { renderScreen, screen, userEvent, waitFor, within } from "@/test/render";
import type { Opportunity } from "@/types/opportunities";

import CallRequestsPage from "./CallRequestsPage";
import { callFixture } from "./callFixture";

const requests = vi.fn<() => Promise<Opportunity[]>>();
const confirm = vi.fn();
const reject = vi.fn();
const setFeatured = vi.fn();

vi.mock("@/api/opportunities", () => ({
  opportunitiesApi: {
    requests: () => requests(),
    confirm: (id: number, seen: string) => confirm(id, seen),
    reject: (id: number, seen: string, reason: string) => reject(id, seen, reason),
    setFeatured: (id: number, featured: boolean) => setFeatured(id, featured),
  },
}));

afterEach(() => {
  vi.clearAllMocks();
  useUIStore.setState({ toasts: [] });
});

const waiting = (o: Partial<Opportunity> = {}) => callFixture({
  id: 11, title: "ICCE 2027", can_confirm: true, can_reject: true, can_feature: true,
  start_date: "2027-01-20", end_date: "2027-01-22", registration_fee: "PHP 5,000",
  description: "Full papers on computing education.\nShort papers welcome.",
  ...o,
});

async function open(rows: Opportunity[]) {
  requests.mockResolvedValue(rows);
  const view = renderScreen(<><CallRequestsPage /><ToastContainer /></>);
  await screen.findByRole("heading", { level: 1, name: "Call Requests" });
  await waitFor(() => expect(screen.queryByRole("status", { busy: true })).toBeNull());
  return view;
}

describe("Call Requests", () => {
  it("lists each waiting call with every field", async () => {
    await open([waiting()]);
    const row = screen.getByRole("article", { name: "ICCE 2027" });
    for (const text of [
      "Conference", "Cebu City, Philippines", "Artificial Intelligence",
      "Event: Jan 20, 2027 to Jan 22, 2027", "Fee: PHP 5,000", "Dec 1, 2026",
    ]) {
      expect(within(row).getByText(text)).toBeInTheDocument();
    }
    // About in full, not clamped to two lines.
    expect(within(row).getByText(/Short papers welcome\./)).toBeInTheDocument();
    expect(within(row).getByRole("link", { name: /https:\/\/example\.org\/call/ })).toHaveAttribute("target", "_blank");
    expect(within(row).getByText(/Ana Reyes, Nov 10, 2026/)).toBeInTheDocument();
  });

  it("confirms a call after asking, naming the version RDCO read, and takes it off the list", async () => {
    confirm.mockResolvedValue({ data: {} });
    await open([waiting()]);
    const user = userEvent.setup();

    await user.click(screen.getByRole("button", { name: "Confirm ICCE 2027" }));
    const dialog = await screen.findByRole("dialog", { name: "Confirm ICCE 2027?" });
    expect(confirm).not.toHaveBeenCalled();
    await user.click(within(dialog).getByRole("button", { name: "Confirm call" }));

    await waitFor(() => expect(screen.queryByRole("article", { name: "ICCE 2027" })).toBeNull());
    expect(confirm).toHaveBeenCalledWith(11, "2026-11-10T00:00:00Z");
    expect(await screen.findByText("ICCE 2027 confirmed. It's on Calls & Conferences.")).toBeInTheDocument();
  });

  it("rejects only with a reason, which the Adviser is sent", async () => {
    reject.mockResolvedValue({ data: {} });
    await open([waiting()]);
    const user = userEvent.setup();

    await user.click(screen.getByRole("button", { name: "Reject ICCE 2027" }));
    const dialog = await screen.findByRole("dialog", { name: "Reject this call" });
    expect(within(dialog).getByRole("button", { name: "Reject call" })).toBeDisabled();
    await user.type(within(dialog).getByRole("textbox", { name: "Reason to the Adviser" }), "The link is broken.");
    await user.click(within(dialog).getByRole("button", { name: "Reject call" }));

    await waitFor(() => expect(screen.queryByRole("article", { name: "ICCE 2027" })).toBeNull());
    expect(reject).toHaveBeenCalledWith(11, "2026-11-10T00:00:00Z", "The link is broken.");
  });

  it("shows the server's refusal of a stale decision, and reloads rather than pretending", async () => {
    confirm.mockRejectedValueOnce({
      response: { status: 409, data: { detail: "This call was changed after you opened it. Reload it and decide again." } },
    });
    await open([waiting()]);
    requests.mockResolvedValue([waiting({ title: "ICCE 2027 (edited)", updated_at: "2026-11-12T00:00:00Z" })]);
    const user = userEvent.setup();

    await user.click(screen.getByRole("button", { name: "Confirm ICCE 2027" }));
    await user.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Confirm call" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("This call was changed after you opened it.");
    expect(await screen.findByRole("article", { name: "ICCE 2027 (edited)" })).toBeInTheDocument();
    expect(screen.queryByText(/confirmed\. It's on/)).toBeNull();
  });

  it("keeps the reason typed when a rejection doesn't go through", async () => {
    reject.mockRejectedValueOnce(new Error("Network Error"));
    await open([waiting()]);
    const user = userEvent.setup();

    await user.click(screen.getByRole("button", { name: "Reject ICCE 2027" }));
    const dialog = await screen.findByRole("dialog", { name: "Reject this call" });
    await user.type(within(dialog).getByRole("textbox", { name: "Reason to the Adviser" }), "Broken link.");
    await user.click(within(dialog).getByRole("button", { name: "Reject call" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Could not reject ICCE 2027.");
    expect(within(dialog).getByRole("textbox", { name: "Reason to the Adviser" })).toHaveValue("Broken link.");
  });

  it("shows a refusal of the reason itself under the field, not in a toast", async () => {
    reject.mockRejectedValueOnce({ response: { status: 400, data: { reason: ["This field may not be blank."] } } });
    await open([waiting()]);
    const user = userEvent.setup();

    await user.click(screen.getByRole("button", { name: "Reject ICCE 2027" }));
    const dialog = await screen.findByRole("dialog", { name: "Reject this call" });
    await user.type(within(dialog).getByRole("textbox", { name: "Reason to the Adviser" }), "   x");
    await user.click(within(dialog).getByRole("button", { name: "Reject call" }));

    const field = await within(dialog).findByRole("textbox", { name: "Reason to the Adviser", description: "This field may not be blank." });
    expect(field).toHaveAttribute("aria-invalid", "true");
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("sets and clears Featured, and decides on the version that change produced", async () => {
    setFeatured.mockResolvedValue({ data: waiting({ is_featured: true, updated_at: "2026-11-11T00:00:00Z" }) });
    confirm.mockResolvedValue({ data: {} });
    await open([waiting()]);
    const user = userEvent.setup();

    await user.click(screen.getByRole("button", { name: "Featured: ICCE 2027" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Featured: ICCE 2027" })).toHaveAttribute("aria-pressed", "true"));
    expect(setFeatured).toHaveBeenCalledWith(11, true);

    await user.click(screen.getByRole("button", { name: "Confirm ICCE 2027" }));
    await user.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Confirm call" }));
    await waitFor(() => expect(confirm).toHaveBeenCalledWith(11, "2026-11-11T00:00:00Z"));
  });

  it("offers only what the server says", async () => {
    await open([waiting({ can_confirm: false, can_reject: false, can_feature: false })]);
    const row = screen.getByRole("article", { name: "ICCE 2027" });
    expect(within(row).queryByRole("button")).toBeNull();
  });

  it("says when nothing waits", async () => {
    await open([]);
    expect(screen.getByRole("heading", { name: "No calls waiting" })).toBeInTheDocument();
  });

  it("offers Try again when the list didn't load", async () => {
    requests.mockRejectedValueOnce(new Error("offline"));
    renderScreen(<CallRequestsPage />);
    const alert = await screen.findByRole("alert");
    expect(within(alert).getByRole("heading", { name: "Could not load call requests" })).toBeInTheDocument();

    requests.mockResolvedValue([waiting()]);
    await userEvent.setup().click(within(alert).getByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("article", { name: "ICCE 2027" })).toBeInTheDocument();
  });

  it("has no serious accessibility violations, nor in either dialog", async () => {
    const { container } = await open([waiting()]);
    await expectNoBlockingA11yViolations(container);
    const user = userEvent.setup();

    await user.click(screen.getByRole("button", { name: "Reject ICCE 2027" }));
    await expectNoBlockingA11yViolations(await screen.findByRole("dialog", { name: "Reject this call" }));
    await user.click(screen.getByRole("button", { name: "Cancel" }));

    await user.click(screen.getByRole("button", { name: "Confirm ICCE 2027" }));
    await expectNoBlockingA11yViolations(await screen.findByRole("dialog", { name: "Confirm ICCE 2027?" }));
  });
});
