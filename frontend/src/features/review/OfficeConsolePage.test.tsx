/**
 * The coordinator console (IR-623). Every query goes through the accessible
 * tree; the API module is the seam, as on My Reviews.
 */
import userEvent from "@testing-library/user-event";
import { Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { expectNoBlockingA11yViolations } from "@/test/axe";
import { renderScreen, screen, waitFor, within } from "@/test/render";
import type { OfficeConsole, OfficeConsoleRow } from "@/types/reviews";

import OfficeConsolePage from "./OfficeConsolePage";

const office = vi.fn();
const assignOptions = vi.fn();
const assign = vi.fn();
const reassign = vi.fn();
const extend = vi.fn();

vi.mock("@/api/reviews", () => ({
  reviewsApi: { office: (o: string | null) => office(o) },
  seatsApi: {
    assignOptions: (id: number) => assignOptions(id),
    assign: (id: number, reviewer: number) => assign(id, reviewer),
    reassign: (id: number, reviewer: number, reason: string) => reassign(id, reviewer, reason),
    extend: (id: number, dueAt: string, reason: string) => extend(id, dueAt, reason),
  },
}));

function row(overrides: Partial<OfficeConsoleRow> = {}): OfficeConsoleRow {
  return {
    key: "seat:1", kind: "seat", record: 7, title: "Smart Campus Energy Monitor",
    assignment: 3, seat: 1, reviewer: 5, reviewer_name: "Maria Reyes",
    seat_state: "in_review", seat_state_label: "In review",
    opened_at: "2026-10-01T02:00:00Z", due_at: "2026-10-06T15:59:00Z",
    original_due_at: "2026-10-06T15:59:00Z", is_overdue: true, clock_paused: false, can_extend: true,
    ...overrides,
  };
}

const POOL = row({
  key: "pool:4", kind: "pool", record: 8, title: "AI-Based Medical Imaging", assignment: 4,
  seat: null, reviewer: null, reviewer_name: null, seat_state: null, seat_state_label: null,
  is_overdue: false,
});

function payload(overrides: Partial<OfficeConsole> = {}): { data: OfficeConsole } {
  return {
    data: {
      office: "itso", office_label: "ITSO",
      rows: [row(), POOL],
      load: [
        { reviewer: 5, name: "Maria Reyes", open: 1, overdue: 1 },
        { reviewer: 6, name: "Juan Santos", open: 0, overdue: 0 },
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
});

describe("OfficeConsolePage", () => {
  it("lists the office's open reviews and each reviewer's load", async () => {
    const { container } = show();

    expect(await screen.findByRole("heading", { level: 1, name: "ITSO console" })).toBeInTheDocument();
    const reviews = screen.getByRole("list", { name: "Open reviews" });
    const [held, unclaimed] = within(reviews).getAllByRole("listitem");
    expect(within(held).getByRole("link", { name: "Smart Campus Energy Monitor" }))
      .toHaveAttribute("href", "/records/7?section=review");
    expect(held).toHaveTextContent("Maria Reyes · In review");
    // Overdue is said in words, never by colour alone.
    expect(held).toHaveTextContent(/Overdue/);
    expect(unclaimed).toHaveTextContent("Unclaimed");
    expect(unclaimed).not.toHaveTextContent(/Overdue/);

    const load = screen.getByRole("table", { name: "Workload" });
    const [, maria, juan] = within(load).getAllByRole("row");
    expect(within(maria).getAllByRole("cell").map((c) => c.textContent)).toEqual(["Maria Reyes", "1", "1"]);
    expect(within(juan).getAllByRole("cell").map((c) => c.textContent)).toEqual(["Juan Santos", "0", "0"]);
    expect(office).toHaveBeenCalledWith(null);
    await expectNoBlockingA11yViolations(container);
  });

  it("offers Assign on an unclaimed record and Reassign on a held one", async () => {
    show();
    await screen.findByRole("list", { name: "Open reviews" });

    expect(screen.getByRole("button", { name: "Assign reviewer: AI-Based Medical Imaging" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reassign: Smart Campus Energy Monitor" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Reassign: AI-Based Medical Imaging" })).not.toBeInTheDocument();
  });

  it("reassigns only with a reason, then reloads and says where it went", async () => {
    show();
    await userEvent.click(await screen.findByRole("button", { name: "Reassign: Smart Campus Energy Monitor" }));
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
    await userEvent.click(await screen.findByRole("button", { name: "Extend due date: Smart Campus Energy Monitor" }));
    const dialog = await screen.findByRole("dialog", { name: "Extend the due date" });

    await userEvent.type(within(dialog).getByLabelText("New due date"), "2026-10-12");
    await userEvent.type(within(dialog).getByRole("textbox", { name: /Reason/ }), "Committee meets Monday.");
    await userEvent.click(within(dialog).getByRole("button", { name: "Extend" }));

    expect(extend).toHaveBeenCalledWith(3, "2026-10-12T23:59:00+08:00", "Committee meets Monday.");
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Due date extended."));
  });

  it("offers no extension where the server allows none", async () => {
    office.mockResolvedValue(payload({ rows: [row({ can_extend: false })] }));
    show();
    await screen.findByRole("list", { name: "Open reviews" });
    expect(screen.queryByRole("button", { name: /Extend due date/ })).not.toBeInTheDocument();
  });

  it("shows the server's refusal on a failed act, inside its dialog", async () => {
    extend.mockRejectedValue({ response: { data: { detail: "The deadline must be at 23:59 Asia/Manila." } } });
    show();
    await userEvent.click(await screen.findByRole("button", { name: "Extend due date: Smart Campus Energy Monitor" }));
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
    expect(await screen.findByRole("list", { name: "Open reviews" })).toBeInTheDocument();
  });

  it("tells a non-coordinator the console is not theirs, and links back", async () => {
    office.mockRejectedValue({ response: { status: 403, data: { detail: "Only a coordinator of that office may open its console." } } });
    show();

    expect(await screen.findByText("This console is for coordinators")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Try again" })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Back to My Reviews" })).toBeInTheDocument();
  });
});
