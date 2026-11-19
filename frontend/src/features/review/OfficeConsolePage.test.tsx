/**
 * The coordinator console (IR-623). Every query goes through the accessible
 * tree; the API module is the seam, as on My Reviews.
 */
import userEvent from "@testing-library/user-event";
import { Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { RequestTimeoutError } from "@/api/requestPolicy";
import { expectNoBlockingA11yViolations } from "@/test/axe";
import { renderScreen, screen, waitFor, within } from "@/test/render";
import type { ClearanceStripEntry } from "@/types/records";
import type { OfficeConsole, OfficeConsoleRow } from "@/types/reviews";

import OfficeConsolePage from "./OfficeConsolePage";

const office = vi.fn();
const assignOptions = vi.fn();
const assign = vi.fn();
const reassign = vi.fn();
const extend = vi.fn();
const withdraw = vi.fn();

vi.mock("@/api/reviews", () => ({
  reviewsApi: { office: (o: string | null) => office(o) },
  seatsApi: {
    assignOptions: (id: number) => assignOptions(id),
    assign: (id: number, reviewer: number) => assign(id, reviewer),
    reassign: (id: number, reviewer: number, reason: string) => reassign(id, reviewer, reason),
    extend: (id: number, dueAt: string, reason: string) => extend(id, dueAt, reason),
    withdraw: (id: number) => withdraw(id),
  },
}));

/** What a resubmission left on a record: ITSO's clearance kept, IERC's reset (IR-1083). */
const KEPT: ClearanceStripEntry = {
  party: "itso", label: "ITSO", kind: "kept", text: "Cleared", note: "Kept from v1", version: 1,
};
const RESET: ClearanceStripEntry = {
  party: "ierc", label: "IERC", kind: "reviewing", text: "Reviewing v2", note: "Reset by v2", version: 2,
};

function row(overrides: Partial<OfficeConsoleRow> = {}): OfficeConsoleRow {
  return {
    key: "seat:1", kind: "seat", record: 7, title: "Smart Campus Energy Monitor",
    assignment: 3, seat: 1, reviewer: 5, reviewer_name: "Maria Reyes",
    seat_state: "in_review", seat_state_label: "In review",
    opened_at: "2026-10-01T02:00:00Z", due_at: "2026-10-06T15:59:00Z",
    original_due_at: "2026-10-06T15:59:00Z", is_overdue: true, clock_paused: false, can_extend: true,
    clearance_strip: [],
    authors_line: "Ada Lovelace · v2",
    status: { kind: "overdue", text: "Overdue by 3 days" },
    actions: ["reassign", "extend"],
    ...overrides,
  };
}

const POOL = row({
  key: "pool:4", kind: "pool", record: 8, title: "AI-Based Medical Imaging", assignment: 4,
  seat: null, reviewer: null, reviewer_name: null, seat_state: null, seat_state_label: null,
  is_overdue: false, authors_line: "Alan Turing · v1",
  status: { kind: "unassigned", text: "Unassigned" }, actions: ["assign", "extend"],
});

/** The table row holding a paper's title. */
function rowOf(title: string) {
  return within(screen.getByRole("table")).getByRole("link", { name: title }).closest("tr") as HTMLElement;
}

function payload(overrides: Partial<OfficeConsole> = {}): { data: OfficeConsole } {
  return {
    data: {
      office: "itso", office_label: "ITSO",
      rows: [row(), POOL],
      load: [
        { reviewer: 5, name: "Maria Reyes", open_count: 1, overdue: 1 },
        { reviewer: 6, name: "Juan Santos", open_count: 0, overdue: 0 },
      ],
      ...overrides,
    },
  };
}

function show() {
  return renderScreen(
    <Routes>
      <Route path="/review/office" element={<OfficeConsolePage />} />
      <Route path="/review" element={<p>My Reviews page</p>} />
    </Routes>,
    { route: "/review/office" },
  );
}

beforeEach(() => {
  office.mockReset().mockResolvedValue(payload());
  assignOptions.mockReset().mockResolvedValue({
    data: {
      assignment: 3, party: "itso", party_label: "ITSO",
      members: [{ id: 5, name: "Maria Reyes", seated: true }, { id: 6, name: "Juan Santos", seated: false }],
    },
  });
  assign.mockReset().mockResolvedValue({ data: {} });
  reassign.mockReset().mockResolvedValue({ data: {} });
  extend.mockReset().mockResolvedValue({ data: {} });
  withdraw.mockReset().mockResolvedValue({ data: {} });
});

describe("OfficeConsolePage", () => {
  it("shows a kept clearance and a reset one on each row, in the server's words (IR-1083)", async () => {
    office.mockResolvedValue(payload({
      rows: [
        row({ clearance_strip: [KEPT, RESET] }),
        row({ key: "seat:2", record: 9, title: "Rainwater Harvesting Survey", clearance_strip: [RESET] }),
        POOL,
      ],
    }));
    show();

    await screen.findByRole("table");
    const kept = rowOf("Smart Campus Energy Monitor");
    const strip = within(kept).getByRole("list", { name: "Clearances" });
    expect(strip).toHaveTextContent("ITSO: Cleared · Kept from v1");
    expect(strip).toHaveTextContent("IERC: Reviewing v2 · Reset by v2");

    const reset = rowOf("Rainwater Harvesting Survey");
    expect(within(reset).getByRole("list", { name: "Clearances" })).toHaveTextContent("Reset by v2");
    expect(within(reset).queryByText(/kept from/i)).not.toBeInTheDocument();

    expect(within(rowOf("AI-Based Medical Imaging")).queryByRole("list", { name: "Clearances" }))
      .not.toBeInTheDocument();
  });

  it("lists the office's open reviews in one table, in the server's words", async () => {
    const { container } = show();

    expect(await screen.findByRole("heading", { level: 1, name: "ITSO office console" })).toBeInTheDocument();
    expect(screen.getByText("Assign ITSO's reviews, and move due dates when a reviewer needs more time."))
      .toBeInTheDocument();
    const table = screen.getByRole("table", { name: /ITSO open reviews/ });
    expect(within(table).getAllByRole("columnheader").map((h) => h.textContent))
      .toEqual(["Paper", "Reviewer", "Due", "Status", "Actions"]);

    const held = rowOf("Smart Campus Energy Monitor");
    expect(within(held).getByRole("link", { name: "Smart Campus Energy Monitor" }))
      .toHaveAttribute("href", "/records/7?section=review");
    expect(held).toHaveTextContent("Ada Lovelace · v2");
    expect(held).toHaveTextContent("Maria Reyes");
    // Overdue is said in words, never by colour alone, and the words are the server's.
    expect(held).toHaveTextContent("Overdue by 3 days");

    const unclaimed = rowOf("AI-Based Medical Imaging");
    expect(unclaimed).toHaveTextContent("Nobody yet");
    expect(unclaimed).toHaveTextContent("Unassigned");

    const [maria, juan] = within(screen.getByRole("list", { name: "Workload" })).getAllByRole("listitem");
    expect(maria).toHaveTextContent("Maria Reyes · 1 open · 1 overdue");
    expect(juan).toHaveTextContent("Juan Santos · 0 open");
    expect(office).toHaveBeenCalledWith(null);
    await expectNoBlockingA11yViolations(container);
  });

  it("offers Assign on an unassigned row and a More actions menu on a held one", async () => {
    show();
    await screen.findByRole("table");

    expect(screen.getByRole("button", { name: "Assign reviewer: AI-Based Medical Imaging" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Assign reviewer: Smart Campus Energy Monitor" })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "More actions: Smart Campus Energy Monitor" }));
    const menu = await screen.findByRole("menu");
    expect(within(menu).getAllByRole("menuitem").map((i) => i.textContent))
      .toEqual(["Reassign…", "Extend due date…"]);
  });

  it("offers only what the server lists for the row", async () => {
    office.mockResolvedValue(payload({ rows: [row({ actions: ["reassign"] })] }));
    show();
    await userEvent.click(await screen.findByRole("button", { name: "More actions: Smart Campus Energy Monitor" }));
    expect(within(await screen.findByRole("menu")).getAllByRole("menuitem").map((i) => i.textContent))
      .toEqual(["Reassign…"]);
  });

  it("reassigns only with a reason, then reloads and says where it went", async () => {
    show();
    await userEvent.click(await screen.findByRole("button", { name: "More actions: Smart Campus Energy Monitor" }));
    await userEvent.click(await screen.findByRole("menuitem", { name: "Reassign…" }));
    const dialog = await screen.findByRole("dialog", { name: "Reassign a reviewer" });

    await userEvent.selectOptions(await within(dialog).findByRole("combobox", { name: "New reviewer at ITSO" }), "6");
    await userEvent.click(within(dialog).getByRole("button", { name: "Reassign" }));
    expect(reassign).not.toHaveBeenCalled();
    expect(within(dialog).getByRole("alert")).toHaveTextContent("Give a reason");

    await userEvent.type(within(dialog).getByRole("textbox", { name: /Reason/ }), "Maria is on leave.");
    await userEvent.click(within(dialog).getByRole("button", { name: "Reassign" }));

    expect(reassign).toHaveBeenCalledWith(1, 6, "Maria is on leave.");
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Reassigned to Juan Santos."));
    expect(office).toHaveBeenCalledTimes(2);
  });

  it("extends a due date to 23:59 Manila on the day picked, with a reason", async () => {
    show();
    await userEvent.click(await screen.findByRole("button", { name: "More actions: Smart Campus Energy Monitor" }));
    await userEvent.click(await screen.findByRole("menuitem", { name: "Extend due date…" }));
    const dialog = await screen.findByRole("dialog", { name: "Extend the due date" });

    await userEvent.type(within(dialog).getByLabelText("New due date"), "2026-10-12");
    await userEvent.type(within(dialog).getByRole("textbox", { name: /Reason/ }), "Committee meets Monday.");
    await userEvent.click(within(dialog).getByRole("button", { name: "Extend" }));

    expect(extend).toHaveBeenCalledWith(3, "2026-10-12T23:59:00+08:00", "Committee meets Monday.");
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Due date extended."));
  });

  it("offers no extension where the server allows none", async () => {
    office.mockResolvedValue(payload({ rows: [row({ can_extend: false, actions: ["reassign"] })] }));
    show();
    await userEvent.click(await screen.findByRole("button", { name: "More actions: Smart Campus Energy Monitor" }));
    expect(screen.queryByRole("menuitem", { name: /Extend due date/ })).not.toBeInTheDocument();
  });

  it("shows the server's refusal on a failed act, inside its dialog", async () => {
    extend.mockRejectedValue({ response: { data: { detail: "The deadline must be at 23:59 Asia/Manila." } } });
    show();
    await userEvent.click(await screen.findByRole("button", { name: "More actions: Smart Campus Energy Monitor" }));
    await userEvent.click(await screen.findByRole("menuitem", { name: "Extend due date…" }));
    const dialog = await screen.findByRole("dialog", { name: "Extend the due date" });
    await userEvent.type(within(dialog).getByLabelText("New due date"), "2026-10-12");
    await userEvent.type(within(dialog).getByRole("textbox", { name: /Reason/ }), "Late committee.");
    await userEvent.click(within(dialog).getByRole("button", { name: "Extend" }));

    expect(await within(dialog).findByRole("alert")).toHaveTextContent("23:59 Asia/Manila");
  });

  it("says when the office has nothing open, and offers the way back", async () => {
    office.mockResolvedValue(payload({ rows: [] }));
    show();

    expect(await screen.findByText("Nothing open at ITSO")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Back to My Reviews" })).toHaveAttribute("href", "/review");
  });

  it("offers Try again when the console could not load", async () => {
    office.mockRejectedValueOnce(new Error("offline"));
    show();

    expect(await screen.findByText("Could not load the console")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("table")).toBeInTheDocument();
  });

  it("shows a console that timed out as interrupted, and Retry reads again (IR-906)", async () => {
    office.mockRejectedValueOnce(new RequestTimeoutError(30_000, "get", "/reviews/office/"));
    show();

    expect(await screen.findByRole("heading", { name: "This took too long" })).toBeInTheDocument();
    expect(screen.queryByText("Could not load the console")).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByRole("table")).toBeInTheDocument();
  });

  it("tells a non-coordinator the console is not theirs, and links back", async () => {
    office.mockRejectedValue({ response: { status: 403, data: { detail: "Only a coordinator of that office may open its console." } } });
    show();

    expect(await screen.findByText("This console is for coordinators")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Try again" })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Back to My Reviews" })).toBeInTheDocument();
  });

  // --- taking a reviewer off (IR-1226) --------------------------------------------------

  /** Maria leaves one draft and one open thread; the counts are the server's. */
  const LEAVES = { drafts: 1, open_threads: 1, document_requests: 0, revision_requests: 0 };

  async function openMenuItem(name: string) {
    await userEvent.click(await screen.findByRole("button", { name: "More actions: Smart Campus Energy Monitor" }));
    await userEvent.click(await screen.findByRole("menuitem", { name }));
  }

  it("withdraws a reviewer after saying what they leave, then reloads", async () => {
    office.mockResolvedValue(payload({
      rows: [row({ actions: ["reassign", "withdraw", "extend"], unresolved: LEAVES, withdraw_completes_office: false })],
    }));
    show();
    await openMenuItem("Withdraw…");
    const dialog = await screen.findByRole("dialog", { name: "Withdraw a reviewer" });

    const warning = within(dialog).getByRole("region", { name: "What Maria Reyes leaves" });
    expect(within(warning).getAllByRole("listitem").map((i) => i.textContent)).toEqual([
      "1 unsent draft will be discarded.",
      "1 open thread they posted stays open, for the authors and whoever holds the seat.",
      "They will no longer act on this review. They can still read it.",
    ]);
    expect(within(dialog).queryByText(/This finishes/)).not.toBeInTheDocument();

    await userEvent.click(within(dialog).getByRole("button", { name: "Withdraw" }));
    expect(withdraw).toHaveBeenCalledWith(1);
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Maria Reyes was withdrawn."));
    expect(office).toHaveBeenCalledTimes(2);
  });

  it("says, in the menu and the dialog, when withdrawing finishes the office's review", async () => {
    office.mockResolvedValue(payload({
      rows: [row({ actions: ["reassign", "withdraw"], unresolved: LEAVES, withdraw_completes_office: true })],
    }));
    show();
    await openMenuItem("Withdraw… (finishes the review)");
    const dialog = await screen.findByRole("dialog", { name: "Withdraw a reviewer" });
    expect(within(dialog).getByText("This finishes ITSO's review, using the reviews already done.")).toBeInTheDocument();
  });

  it("warns, before reassigning, what the reviewer leaves", async () => {
    office.mockResolvedValue(payload({
      rows: [row({ unresolved: { ...LEAVES, document_requests: 2 } })],
    }));
    show();
    await openMenuItem("Reassign…");
    const dialog = await screen.findByRole("dialog", { name: "Reassign a reviewer" });
    const warning = within(dialog).getByRole("region", { name: "What Maria Reyes leaves" });
    expect(warning).toHaveTextContent("2 document requests they made stay open.");
    await expectNoBlockingA11yViolations(dialog);
  });
});
