/**
 * My Calls (IR-765): a poster sees where each of their Calls stands, reads
 * RDCO's reason on a rejected one, and edits it to send it again, or deletes it.
 */
import { afterEach, describe, expect, it, vi } from "vitest";

import { ToastContainer } from "@/components/ui/Toast";
import { useUIStore } from "@/store/ui.store";
import { expectNoBlockingA11yViolations } from "@/test/axe";
import { renderScreen, screen, userEvent, waitFor, within } from "@/test/render";
import type { Opportunity } from "@/types/opportunities";

import { callFixture } from "./callFixture";
import { MyCallsPage } from "./MyCallsPage";

const mine = vi.fn<() => Promise<Opportunity[]>>();
const update = vi.fn();
const remove = vi.fn();

vi.mock("@/api/opportunities", () => ({
  opportunitiesApi: {
    mine: () => mine(),
    update: (id: number, input: unknown) => update(id, input),
    remove: (id: number) => remove(id),
  },
}));

const classifications = vi.fn();
vi.mock("@/api/records", () => ({ recordsApi: { classifications: () => classifications() } }));

afterEach(() => {
  vi.clearAllMocks();
  useUIStore.setState({ toasts: [] });
});

const waiting  = () => callFixture({ id: 1, title: "Waiting call", can_edit: true, can_delete: true });
const rejected = () => callFixture({
  id: 2, title: "Rejected call", status: "rejected", status_label: "Rejected",
  review_reason: "The link goes to last year's call.", can_edit: true, can_delete: true, edit_returns_to_pending: true,
});
const confirmed = () => callFixture({
  id: 3, title: "Confirmed call", status: "confirmed", status_label: "Confirmed",
  can_edit: true, can_delete: true, edit_returns_to_pending: true,
});

async function open(rows: Opportunity[]) {
  mine.mockResolvedValue(rows);
  classifications.mockResolvedValue({ data: { results: [{ id: 1, name: "Artificial Intelligence" }] } });
  const view = renderScreen(<><MyCallsPage /><ToastContainer /></>);
  await screen.findByRole("heading", { level: 1, name: "My Calls" });
  await waitFor(() => expect(screen.queryByRole("status", { busy: true })).toBeNull());
  return view;
}

describe("My Calls", () => {
  it("says where each call stands, in words", async () => {
    await open([waiting(), rejected(), confirmed()]);
    expect(within(screen.getByRole("article", { name: "Waiting call" })).getByText("Waiting for RDCO")).toBeInTheDocument();
    expect(within(screen.getByRole("article", { name: "Confirmed call" })).getByText("Confirmed")).toBeInTheDocument();
    const row = screen.getByRole("article", { name: "Rejected call" });
    expect(within(row).getByText("Rejected")).toBeInTheDocument();
    expect(within(row).getByText("The link goes to last year's call.")).toBeInTheDocument();
  });

  it("edits a rejected call and sends it to RDCO again, saying so before and after", async () => {
    update.mockImplementation(async (_id: number, input: Record<string, unknown>) => ({
      data: { ...rejected(), ...input, status: "pending", status_label: "Waiting for RDCO", review_reason: "" },
    }));
    await open([rejected()]);
    const user = userEvent.setup();

    await user.click(screen.getByRole("button", { name: "Edit and send again Rejected call" }));
    const dialog = await screen.findByRole("dialog", { name: "Edit call" });
    expect(within(dialog).getByText(/Saving sends this call back to RDCO/)).toBeInTheDocument();
    const link = within(dialog).getByRole("textbox", { name: "Link" });
    await user.clear(link);
    await user.type(link, "https://example.org/2027");
    await user.click(within(dialog).getByRole("button", { name: "Save changes" }));

    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(update).toHaveBeenCalledWith(2, expect.objectContaining({ external_url: "https://example.org/2027" }));
    const row = screen.getByRole("article", { name: "Rejected call" });
    expect(within(row).getByText("Waiting for RDCO")).toBeInTheDocument();
    expect(within(row).queryByText("The link goes to last year's call.")).toBeNull();
    expect(await screen.findByText(/sent to RDCO\. It appears on the board once RDCO confirms it\./)).toBeInTheDocument();
  });

  it("deletes a call only after asking", async () => {
    remove.mockResolvedValue({});
    await open([waiting(), rejected()]);
    const user = userEvent.setup();

    await user.click(screen.getByRole("button", { name: "Delete Rejected call" }));
    const dialog = await screen.findByRole("dialog", { name: "Delete this call?" });
    expect(remove).not.toHaveBeenCalled();
    await user.click(within(dialog).getByRole("button", { name: /Delete call/ }));

    await waitFor(() => expect(screen.queryByRole("article", { name: "Rejected call" })).toBeNull());
    expect(remove).toHaveBeenCalledWith(2);
  });

  it("offers Edit and Delete only where the server says", async () => {
    await open([callFixture({ id: 9, title: "Locked call" })]);
    expect(within(screen.getByRole("article", { name: "Locked call" })).queryByRole("button")).toBeNull();
  });

  it("points a poster with no calls to the board", async () => {
    await open([]);
    expect(screen.getByRole("heading", { name: "You haven't posted a call" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Go to Calls & Conferences" })).toHaveAttribute("href", "/opportunities");
  });

  it("has no serious accessibility violations, nor with the edit or delete dialog open", async () => {
    const { container } = await open([waiting(), rejected(), confirmed()]);
    await expectNoBlockingA11yViolations(container);
    const user = userEvent.setup();

    await user.click(screen.getByRole("button", { name: "Edit and send again Rejected call" }));
    await expectNoBlockingA11yViolations(await screen.findByRole("dialog", { name: "Edit call" }));
    await user.click(screen.getByRole("button", { name: "Cancel" }));

    await user.click(screen.getByRole("button", { name: "Delete Waiting call" }));
    await expectNoBlockingA11yViolations(await screen.findByRole("dialog", { name: "Delete this call?" }));
  });
});
