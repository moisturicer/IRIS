/**
 * Edit details (IR-411; spec §4.6, Appendix F · F5): the record's metadata in
 * a dialog over Paper View, on the same `MetadataForm` Publish uses. It
 * replaces the Edit Record page.
 *
 * Whether it is *offered* is the capabilities adapter's decision, tested in
 * `capabilities.test.ts` and on the page in `PaperViewPage.test.tsx`. Here:
 * it opens on the record's saved values, saves them as one PATCH, and hands
 * the re-read record back so the page shows the change at once.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { expectNoBlockingA11yViolations } from "@/test/axe";
import { makeUser } from "@/test/authFixtures";
import { renderScreen, screen, userEvent, waitFor, within } from "@/test/render";
import { ROLES } from "@/lib/constants";
import type { RecordDetail } from "@/types/records";

import { EditDetailsDialog } from "./EditDetailsDialog";

vi.mock("@/api/records", () => ({
  recordsApi: {
    classifications: vi.fn(),
    pscedList: vi.fn(),
    update: vi.fn(),
    detail: vi.fn(),
  },
}));
vi.mock("@/api/accounts", () => ({ accountsApi: { listAdvisers: vi.fn() } }));

const { recordsApi } = await import("@/api/records");
const { accountsApi } = await import("@/api/accounts");

const OWNER_ID = 40;
const ADVISER_ID = 21;

function page<T>(results: T[]) {
  return { data: { count: results.length, next: null, previous: null, results } };
}

const saved = {
  id: 9,
  title: "Clearance-aware resubmission in a research office",
  abstract: "An abstract that is comfortably longer than the thirty-character minimum.",
  year_accomplished: 2026,
  adviser: ADVISER_ID,
  authors: [{ id: 1, name: "Ada Reyes", role: null }],
  classification: "Computing",
  psced: null,
  is_ip: true,
  requires_ethics_review: false,
  for_commercialization: false,
  pipeline_status: "draft",
  workflow_state: "draft",
} as unknown as RecordDetail;

beforeEach(() => {
  vi.mocked(recordsApi.classifications).mockResolvedValue(page([{ id: 5, name: "Computing" }]) as never);
  vi.mocked(recordsApi.pscedList).mockResolvedValue(page([{ id: 9, name: "Information Technology" }]) as never);
  vi.mocked(accountsApi.listAdvisers).mockResolvedValue(
    page([makeUser({ id: ADVISER_ID, first_name: "Maria", last_name: "Santos", role_name: ROLES.ADVISER })]) as never,
  );
  vi.mocked(recordsApi.update).mockResolvedValue({ data: { id: 9 } } as never);
  vi.mocked(recordsApi.detail).mockResolvedValue({ data: { ...saved, title: "A sharper title for the study" } } as never);
});

afterEach(() => vi.clearAllMocks());

function renderDialog(onSaved = vi.fn(), onClose = vi.fn()) {
  renderScreen(<EditDetailsDialog record={saved} selfId={OWNER_ID} onSaved={onSaved} onClose={onClose} />);
  return { onSaved, onClose };
}

describe("Edit details", () => {
  it("opens as a dialog on the record's saved values", async () => {
    renderDialog();

    const dialog = await screen.findByRole("dialog", { name: "Edit details" });
    expect(await within(dialog).findByRole("textbox", { name: /Title/ })).toHaveValue(saved.title);
    expect(within(dialog).getByRole("textbox", { name: /Abstract/ })).toHaveValue(saved.abstract);
    expect(within(dialog).getByRole("list", { name: "Authors added" })).toHaveTextContent("Ada Reyes");
  });

  it("saves the details as one PATCH and hands back the re-read record", async () => {
    const user = userEvent.setup();
    const { onSaved } = renderDialog();
    const dialog = await screen.findByRole("dialog", { name: "Edit details" });
    const title = await within(dialog).findByRole("textbox", { name: /Title/ });

    await user.clear(title);
    await user.type(title, "A sharper title for the study");
    await user.click(within(dialog).getByRole("button", { name: "Save details" }));

    await waitFor(() => expect(recordsApi.update).toHaveBeenCalledTimes(1));
    const [id, payload] = vi.mocked(recordsApi.update).mock.calls[0];
    expect(id).toBe(9);
    expect(payload).toMatchObject({
      title: "A sharper title for the study",
      adviser: ADVISER_ID,
      authors: ["Ada Reyes"],
      classification: 5,
      is_ip: true,
    });
    // Hints stay hints: no office is requested from here (ADR-032, IR-408).
    expect(payload).not.toHaveProperty("requested_itso");
    await waitFor(() =>
      expect(onSaved).toHaveBeenCalledWith(expect.objectContaining({ title: "A sharper title for the study" })),
    );
  });

  it("does not save details the schema refuses, and says which", async () => {
    const user = userEvent.setup();
    renderDialog();
    const dialog = await screen.findByRole("dialog", { name: "Edit details" });
    const title = await within(dialog).findByRole("textbox", { name: /Title/ });

    await user.clear(title);
    await user.click(within(dialog).getByRole("button", { name: "Save details" }));

    expect(await within(dialog).findByText(/Title must be at least 5 characters/)).toBeInTheDocument();
    expect(recordsApi.update).not.toHaveBeenCalled();
  });

  it("keeps the dialog open with the server's reason when the save is refused", async () => {
    const user = userEvent.setup();
    vi.mocked(recordsApi.update).mockRejectedValueOnce({
      response: { status: 400, data: { detail: "This record can no longer be edited." } },
    });
    const { onSaved } = renderDialog();
    const dialog = await screen.findByRole("dialog", { name: "Edit details" });
    await within(dialog).findByRole("textbox", { name: /Title/ });

    await user.click(within(dialog).getByRole("button", { name: "Save details" }));

    expect(await within(dialog).findByRole("alert")).toHaveTextContent("This record can no longer be edited.");
    expect(onSaved).not.toHaveBeenCalled();
  });

  it("closes on Cancel without saving", async () => {
    const user = userEvent.setup();
    const { onClose } = renderDialog();
    const dialog = await screen.findByRole("dialog", { name: "Edit details" });
    await within(dialog).findByRole("textbox", { name: /Title/ });

    await user.click(within(dialog).getByRole("button", { name: "Cancel" }));

    expect(onClose).toHaveBeenCalled();
    expect(recordsApi.update).not.toHaveBeenCalled();
  });

  it("has no serious or critical accessibility violations", async () => {
    renderDialog();
    const dialog = await screen.findByRole("dialog", { name: "Edit details" });
    await within(dialog).findByRole("textbox", { name: /Title/ });

    await expectNoBlockingA11yViolations(document.body);
  });
});

// IR-507 (ADR-032 §10 Amendment): once submitted, the Adviser and the hints
// are fixed. The server refuses a change to them; the form neither offers one
// nor sends them.
describe("Edit details while a revision is asked for", () => {
  const revising = {
    ...saved,
    pipeline_status: "in_review",
    workflow_state: "awaiting_resubmission",
  } as unknown as RecordDetail;

  function renderRevising() {
    renderScreen(<EditDetailsDialog record={revising} selfId={OWNER_ID} onSaved={vi.fn()} onClose={vi.fn()} />);
  }

  it("shows the Adviser and the hints but offers no way to change them", async () => {
    renderRevising();
    const dialog = await screen.findByRole("dialog", { name: "Edit details" });
    await within(dialog).findByRole("textbox", { name: /Title/ });

    expect(within(dialog).getByText("Maria Santos")).toBeInTheDocument();
    expect(within(dialog).queryByRole("combobox", { name: /Adviser/, hidden: true })).not.toBeInTheDocument();
    // The hints sit inside More details, closed by default: `hidden` reads it shut.
    expect(
      within(dialog).getByRole("list", { name: "Flagged for your adviser", hidden: true }),
    ).toHaveTextContent("Possible intellectual property");
    expect(within(dialog).queryByRole("checkbox", { hidden: true })).not.toBeInTheDocument();
  });

  it("saves the details without the fixed fields", async () => {
    const user = userEvent.setup();
    renderRevising();
    const dialog = await screen.findByRole("dialog", { name: "Edit details" });
    const title = await within(dialog).findByRole("textbox", { name: /Title/ });

    await user.clear(title);
    await user.type(title, "A sharper title for the study");
    await user.click(within(dialog).getByRole("button", { name: "Save details" }));

    await waitFor(() => expect(recordsApi.update).toHaveBeenCalledTimes(1));
    const [, payload] = vi.mocked(recordsApi.update).mock.calls[0];
    expect(payload).toMatchObject({ title: "A sharper title for the study", authors: ["Ada Reyes"] });
    for (const field of ["adviser", "is_ip", "requires_ethics_review", "for_commercialization"]) {
      expect(payload).not.toHaveProperty(field);
    }
  });

  it("saves a legacy record that has no Adviser recorded", async () => {
    // Found in the browser check: the hidden Adviser was still validated, so
    // Save sent nothing and said nothing.
    const user = userEvent.setup();
    const legacy = { ...revising, adviser: null } as unknown as RecordDetail;
    renderScreen(<EditDetailsDialog record={legacy} selfId={OWNER_ID} onSaved={vi.fn()} onClose={vi.fn()} />);
    const dialog = await screen.findByRole("dialog", { name: "Edit details" });
    await within(dialog).findByRole("textbox", { name: /Title/ });

    expect(within(dialog).getByText("None recorded")).toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: "Save details" }));

    await waitFor(() => expect(recordsApi.update).toHaveBeenCalledTimes(1));
    expect(vi.mocked(recordsApi.update).mock.calls[0][1]).not.toHaveProperty("adviser");
  });

  it("has no serious or critical accessibility violations", async () => {
    renderRevising();
    const dialog = await screen.findByRole("dialog", { name: "Edit details" });
    await within(dialog).findByRole("textbox", { name: /Title/ });

    await expectNoBlockingA11yViolations(document.body);
  });
});
