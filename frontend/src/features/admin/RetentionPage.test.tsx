/**
 * IR-795: the System Admin's Retention page. Each kind of data with its period
 * and when the cleanup last ran; a plain statement that a blank period erases
 * nothing and that the data protection officer approves a period first; a
 * period that would erase existing data asks first and says how much; and a
 * refused value shows against its field.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";

import { expectNoBlockingA11yViolations } from "@/test/axe";
import { renderScreen, screen, userEvent, waitFor, within } from "@/test/render";

import RetentionPage from "./RetentionPage";

const KEY = "retention.download_notes_days";
const getSetting = vi.fn();
const updateSetting = vi.fn();
const retentionPreview = vi.fn();
const listAudit = vi.fn();

vi.mock("@/api/accounts", () => ({
  accountsApi: {
    getSetting: (...args: unknown[]) => getSetting(...args),
    updateSetting: (...args: unknown[]) => updateSetting(...args),
    retentionPreview: (...args: unknown[]) => retentionPreview(...args),
  },
}));
vi.mock("@/api/audit", () => ({
  auditApi: { list: (...args: unknown[]) => listAudit(...args) },
}));

function setting(value: string) {
  return { data: { key: KEY, value, updated_by: null, updated_at: "2026-11-05T08:00:00Z" } };
}

const RUN = {
  id: 1, event_type: "RETENTION_CLEANUP_RUN", user: null, user_name: null, record: null, record_title: null,
  metadata: { counts: { download_notes: 3 } }, created_at: "2026-11-07T19:00:00Z",
};

function refusal(data: Record<string, unknown>) {
  return Object.assign(new Error("400"), { response: { status: 400, data } });
}

async function item() {
  return screen.findByRole("listitem", { name: "Download request notes" });
}

beforeEach(() => {
  getSetting.mockReset().mockResolvedValue(setting(""));
  updateSetting.mockReset().mockImplementation((_key: string, value: string) => Promise.resolve(setting(value)));
  retentionPreview.mockReset();
  listAudit.mockReset().mockResolvedValue({ data: { count: 0, results: [] } });
});

describe("RetentionPage", () => {
  it("lists each kind of data with its period and last run, and passes axe", async () => {
    getSetting.mockResolvedValue(setting("365"));
    listAudit.mockResolvedValue({ data: { count: 1, results: [RUN] } });
    const { container } = renderScreen(<RetentionPage />);

    const row = await item();
    expect(within(row).getByText("365 days")).toBeInTheDocument();
    expect(within(row).getByText(/Erased the notes of 3 download requests\./)).toBeInTheDocument();
    expect(within(row).getByRole("textbox", { name: /Period in days/ })).toHaveValue("365");
    expect(getSetting).toHaveBeenCalledWith(KEY, expect.anything());
    expect(listAudit).toHaveBeenCalledWith(
      { event_type: "RETENTION_CLEANUP_RUN", page_size: 1 }, expect.anything(),
    );
    await expectNoBlockingA11yViolations(container);
  });

  it("says plainly that blank erases nothing and the data protection officer approves first", async () => {
    renderScreen(<RetentionPage />);

    const row = await item();
    expect(screen.getByText(/A blank period erases nothing\./)).toBeInTheDocument();
    expect(screen.getByText(/data protection officer has approved it/)).toBeInTheDocument();
    expect(within(row).getByText("Not set. Nothing is erased.")).toBeInTheDocument();
    expect(within(row).getByText("The cleanup hasn't run yet.")).toBeInTheDocument();
  });

  it("asks before saving a period that would erase existing data, and says how much", async () => {
    retentionPreview.mockResolvedValue({ data: { key: KEY, days: 30, count: 12 } });
    const { container } = renderScreen(<RetentionPage />);
    const row = await item();

    await userEvent.type(within(row).getByRole("textbox", { name: /Period in days/ }), "30");
    await userEvent.click(within(row).getByRole("button", { name: "Save period" }));

    const dialog = await screen.findByRole("dialog", { name: "Erase existing data?" });
    expect(dialog).toHaveTextContent("erases the notes of 12 download requests");
    expect(retentionPreview).toHaveBeenCalledWith(KEY, "30");
    expect(updateSetting).not.toHaveBeenCalled();
    expect(within(dialog).getByRole("button", { name: "Cancel" })).toHaveFocus();
    await expectNoBlockingA11yViolations(container);

    await userEvent.click(within(dialog).getByRole("button", { name: "Save and erase" }));

    await waitFor(() => expect(updateSetting).toHaveBeenCalledWith(KEY, "30"));
    expect(await within(row).findByRole("status")).toHaveTextContent("The period is now 30 days.");
    expect(within(row).getByText("30 days")).toBeInTheDocument();
  });

  it("saves nothing when the confirmation is cancelled", async () => {
    retentionPreview.mockResolvedValue({ data: { key: KEY, days: 30, count: 1 } });
    renderScreen(<RetentionPage />);
    const row = await item();

    await userEvent.type(within(row).getByRole("textbox", { name: /Period in days/ }), "30");
    await userEvent.click(within(row).getByRole("button", { name: "Save period" }));
    const dialog = await screen.findByRole("dialog", { name: "Erase existing data?" });
    expect(dialog).toHaveTextContent("the notes of 1 download request,");
    await userEvent.click(within(dialog).getByRole("button", { name: "Cancel" }));

    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(updateSetting).not.toHaveBeenCalled();
    expect(within(row).getByText("Not set. Nothing is erased.")).toBeInTheDocument();
  });

  it("saves at once when the period would erase nothing, and when it is cleared", async () => {
    retentionPreview.mockResolvedValue({ data: { key: KEY, days: 3650, count: 0 } });
    renderScreen(<RetentionPage />);
    const row = await item();
    const field = within(row).getByRole("textbox", { name: /Period in days/ });

    await userEvent.type(field, "3650");
    await userEvent.click(within(row).getByRole("button", { name: "Save period" }));
    await waitFor(() => expect(updateSetting).toHaveBeenCalledWith(KEY, "3650"));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();

    await userEvent.clear(field);
    await userEvent.click(within(row).getByRole("button", { name: "Save period" }));
    await waitFor(() => expect(updateSetting).toHaveBeenLastCalledWith(KEY, ""));
    // Clearing a period erases nothing, so the server isn't asked to count.
    expect(retentionPreview).toHaveBeenCalledTimes(1);
    expect(await within(row).findByRole("status")).toHaveTextContent("Nothing of this kind is erased.");
  });

  it("shows a refused period against its field, and passes axe", async () => {
    retentionPreview.mockRejectedValue(refusal({
      days: ["Enter a whole number of days, or leave it blank to erase nothing."],
    }));
    const { container } = renderScreen(<RetentionPage />);
    const row = await item();
    const field = within(row).getByRole("textbox", { name: /Period in days/ });

    await userEvent.type(field, "1.5");
    await userEvent.click(within(row).getByRole("button", { name: "Save period" }));

    await waitFor(() => expect(field).toHaveAttribute("aria-invalid", "true"));
    expect(field).toHaveAccessibleDescription("Enter a whole number of days, or leave it blank to erase nothing.");
    expect(updateSetting).not.toHaveBeenCalled();
    await expectNoBlockingA11yViolations(container);
  });

  it("shows a refusal on save against the field too", async () => {
    updateSetting.mockRejectedValue(refusal({ value: ["Enter a whole number of days, or leave it blank to erase nothing."] }));
    getSetting.mockResolvedValue(setting("30"));
    renderScreen(<RetentionPage />);
    const row = await item();
    const field = within(row).getByRole("textbox", { name: /Period in days/ });

    await userEvent.clear(field);
    await userEvent.click(within(row).getByRole("button", { name: "Save period" }));

    await waitFor(() => expect(field).toHaveAccessibleDescription(/Enter a whole number of days/));
    expect(within(row).getByText("30 days")).toBeInTheDocument();
  });

  it("says when the periods can't be loaded", async () => {
    getSetting.mockRejectedValue(new Error("500"));
    renderScreen(<RetentionPage />);

    expect(await screen.findByRole("alert")).toHaveTextContent("Failed to load retention periods.");
  });
});
