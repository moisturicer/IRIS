/**
 * Calls & Conferences (IR-530): the deadline board, and posting from it.
 *
 * Every query goes through the accessible tree. Whether Post, Edit and Delete
 * are offered is the server's `can_post` / `can_edit`; these tests feed those
 * fields and check the page draws exactly what they say.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { expectNoBlockingA11yViolations } from "@/test/axe";
import { fireEvent, renderScreen, screen, userEvent, waitFor, within } from "@/test/render";
import type { Opportunity, OpportunityBoard } from "@/types/opportunities";

import { CallsAndConferencesPage } from "./CallsAndConferencesPage";

const board = vi.fn<() => Promise<OpportunityBoard>>();
const create = vi.fn();
const update = vi.fn();
const remove = vi.fn();
const calendar = vi.fn();

vi.mock("@/api/opportunities", () => ({
  opportunitiesApi: {
    board: () => board(),
    create: (input: unknown) => create(input),
    update: (id: number, input: unknown) => update(id, input),
    remove: (id: number) => remove(id),
    calendar: (id: number) => calendar(id),
  },
}));

let nextId = 1;
function call(overrides: Partial<Opportunity> = {}): Opportunity {
  const id = overrides.id ?? nextId++;
  return {
    id,
    opportunity_type: "internal_call",
    type_display: "Internal Call",
    title: `Call ${id}`,
    posting_office: "Research & Development Coordinating Office (RDCO)",
    audience: "Faculty researchers",
    description: "A description.",
    funding_ceiling: null,
    external_url: "https://www.cit.edu/research/",
    due_date: "2026-11-01",
    is_featured: false,
    tags: [],
    source: "internal",
    posted_by: 3,
    posted_by_name: "Maria Santos",
    created_at: "2026-10-01T00:00:00Z",
    updated_at: "2026-10-01T00:00:00Z",
    days_left: 20,
    is_closed: false,
    can_edit: false,
    ...overrides,
  };
}

const soon    = () => call({ id: 101, title: "Seed Grant Cycle B", days_left: 3, due_date: "2026-10-14", funding_ceiling: "150000.00" });
const month   = () => call({ id: 102, title: "ICACSIS 2026 paper deadline", opportunity_type: "conference_deadline", type_display: "Conference Deadline", days_left: 19, due_date: "2026-10-30" });
const later   = () => call({ id: 103, title: "DOST-PCIEERD funding window", opportunity_type: "funding_window", type_display: "Funding Window", days_left: 60, due_date: "2026-12-10", source: "external" });
const closed  = () => call({ id: 104, title: "Last term's capstone call", days_left: -4, is_closed: true, due_date: "2026-10-07" });

function serve(items: Opportunity[], canPost = false) {
  board.mockResolvedValue({ items, can_post: canPost });
}

async function renderBoard() {
  const view = renderScreen(<CallsAndConferencesPage />);
  await screen.findByRole("heading", { level: 1, name: "Calls & Conferences" });
  await waitFor(() => expect(screen.queryByRole("status", { busy: true })).toBeNull());
  return view;
}

beforeEach(() => {
  nextId = 1;
  localStorage.clear();
});

afterEach(() => vi.clearAllMocks());

describe("the board", () => {
  it("groups calls by how soon they close, soonest first, closed last", async () => {
    serve([later(), closed(), soon(), month()]);
    await renderBoard();

    const headings = screen.getAllByRole("heading", { level: 2 }).map((h) => h.textContent);
    expect(headings).toEqual([
      "Closes within a week1 call",
      "Closes within a month1 call",
      "Closes later1 call",
      "Recently closed1 call",
    ]);

    const week = screen.getByRole("region", { name: /Closes within a week/ });
    const row = within(week).getByRole("article", { name: "Seed Grant Cycle B" });
    expect(within(row).getByText("3 days left")).toBeInTheDocument();
    expect(within(row).getByText("Up to ₱150,000")).toBeInTheDocument();
    expect(within(row).getByRole("link", { name: /View & apply/ })).toHaveAttribute("target", "_blank");

    const done = screen.getByRole("region", { name: /Recently closed/ });
    const old = within(done).getByRole("article", { name: "Last term's capstone call" });
    expect(within(old).getByText("Closed")).toBeInTheDocument();
    // A closed call has no deadline left to put in a calendar.
    expect(within(old).queryByRole("button", { name: /to your calendar/ })).toBeNull();
  });

  it("says when an outside body published a call", async () => {
    serve([later()]);
    await renderBoard();
    const row = screen.getByRole("article", { name: "DOST-PCIEERD funding window" });
    expect(within(row).getByText("From an outside body")).toBeInTheDocument();
  });

  it("says who to ask when a call has no link, rather than drawing a dead button", async () => {
    serve([call({ title: "Unlinked call", external_url: "" })]);
    await renderBoard();
    const row = screen.getByRole("article", { name: "Unlinked call" });
    expect(within(row).queryByRole("link")).toBeNull();
    expect(within(row).getByText(/No link given. Ask Research & Development Coordinating Office./)).toBeInTheDocument();
  });

  it("has no serious accessibility violations", async () => {
    serve([soon(), month(), later(), closed()], true);
    const { container } = await renderBoard();
    await expectNoBlockingA11yViolations(container);
  });
});

describe("order", () => {
  it("runs by date inside a group, with featuring as a mark rather than a jump", async () => {
    serve([
      call({ title: "Featured, later", is_featured: true, days_left: 28, due_date: "2026-11-08" }),
      call({ title: "Plain, sooner", days_left: 12, due_date: "2026-10-23" }),
    ]);
    await renderBoard();

    const month = screen.getByRole("region", { name: /Closes within a month/ });
    const titles = within(month).getAllByRole("article").map((a) => within(a).getByRole("heading").textContent);
    expect(titles).toEqual(["Plain, sooner", "Featured, later"]);
    expect(within(within(month).getAllByRole("article")[1]).getByText("Featured")).toBeInTheDocument();
  });
});

describe("filters", () => {
  it("counts each type and narrows the board to it", async () => {
    serve([soon(), month(), later()]);
    await renderBoard();
    const user = userEvent.setup();

    const types = screen.getByRole("group", { name: "Filter by type" });
    const conference = within(types).getByRole("button", { name: /Conference deadline\s*1/ });
    await user.click(conference);

    expect(conference).toHaveAttribute("aria-pressed", "true");
    expect(screen.getAllByRole("article")).toHaveLength(1);
    expect(screen.getByRole("article", { name: "ICACSIS 2026 paper deadline" })).toBeInTheDocument();
    expect(screen.getByText("Showing 1 of 3 calls.")).toBeInTheDocument();
  });

  it("offers to clear the filters when nothing matches", async () => {
    serve([soon(), month()]);
    await renderBoard();
    const user = userEvent.setup();

    await user.type(screen.getByRole("searchbox", { name: "Search calls by title, office or tag" }), "zzz");
    expect(screen.getByRole("heading", { name: "Nothing matches these filters" })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Clear filters" }));
    expect(screen.getAllByRole("article")).toHaveLength(2);
  });

  it("keeps saved calls in this browser and can show only them", async () => {
    serve([soon(), month()]);
    await renderBoard();
    const user = userEvent.setup();

    const save = screen.getByRole("button", { name: "Save ICACSIS 2026 paper deadline" });
    await user.click(save);
    expect(save).toHaveAttribute("aria-pressed", "true");
    expect(JSON.parse(localStorage.getItem("iris_saved_opportunities") ?? "[]")).toEqual([102]);
    expect(screen.getByRole("status")).toHaveTextContent("Saved calls are kept in this browser only.");
    // Said to the save control itself, not only in a tooltip.
    expect(save).toHaveAccessibleDescription("Saved calls are kept in this browser only.");

    await user.click(screen.getByRole("button", { name: /^Saved\s*1/ }));
    expect(screen.getAllByRole("article")).toHaveLength(1);
    expect(screen.getByRole("article", { name: "ICACSIS 2026 paper deadline" })).toBeInTheDocument();
  });
});

describe("saved calls", () => {
  it("forgets saved calls that are no longer on the board, and counts only what is", async () => {
    localStorage.setItem("iris_saved_opportunities", JSON.stringify([101, 999]));
    serve([soon(), month()]);
    await renderBoard();

    expect(screen.getByRole("button", { name: /^Saved\s*1/ })).toBeInTheDocument();
    expect(JSON.parse(localStorage.getItem("iris_saved_opportunities") ?? "[]")).toEqual([101]);
  });
});

describe("states", () => {
  it("shows no counts until there is a board to count", async () => {
    let resolve!: (b: OpportunityBoard) => void;
    board.mockReturnValueOnce(new Promise((r) => { resolve = r; }));
    renderScreen(<CallsAndConferencesPage />);

    const all = screen.getByRole("button", { name: "All" });
    expect(all).toHaveTextContent(/^All$/);

    resolve({ items: [soon()], can_post: false });
    await waitFor(() => expect(all).toHaveTextContent(/^All\s*1$/));
  });

  it("says the board failed to load, and loads again on request", async () => {
    board.mockRejectedValueOnce(new Error("offline"));
    renderScreen(<CallsAndConferencesPage />);

    const alert = await screen.findByRole("alert");
    expect(within(alert).getByRole("heading", { name: "Could not load calls and conferences" })).toBeInTheDocument();
    // Nothing to filter, so nothing offers to.
    expect(screen.getByRole("button", { name: "All" })).toBeDisabled();
    expect(screen.getByRole("searchbox", { name: "Search calls by title, office or tag" })).toBeDisabled();

    serve([soon()]);
    await userEvent.setup().click(within(alert).getByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("article", { name: "Seed Grant Cycle B" })).toBeInTheDocument();
  });

  it("invites a poster to post the first call on an empty board", async () => {
    serve([], true);
    await renderBoard();
    expect(screen.getByRole("heading", { name: "No calls posted yet" })).toBeInTheDocument();
    // The header's button and the empty state's own.
    expect(screen.getAllByRole("button", { name: "Post a call" })).toHaveLength(2);
  });

  it("tells a reader who posts calls, and offers no post button", async () => {
    serve([], false);
    await renderBoard();
    expect(screen.getByText(/RDCO, KTTO and advisers post calls here/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Post a call" })).toBeNull();
  });

  it("reports a calendar failure on its row and leaves the board standing", async () => {
    serve([soon(), month()]);
    calendar.mockRejectedValueOnce(new Error("500"));
    await renderBoard();

    await userEvent.setup().click(
      screen.getByRole("button", { name: "Add the Seed Grant Cycle B deadline to your calendar" }),
    );

    const row = screen.getByRole("article", { name: "Seed Grant Cycle B" });
    expect(await within(row).findByRole("alert")).toHaveTextContent("Could not build the calendar file.");
    expect(screen.getAllByRole("article")).toHaveLength(2);
  });
});

describe("posting and changing calls", () => {
  it("offers Edit and Delete only on calls the server says this viewer may change", async () => {
    serve([call({ title: "Mine", can_edit: true }), call({ title: "Someone else's" })], true);
    await renderBoard();

    const mine = screen.getByRole("article", { name: "Mine" });
    expect(within(mine).getByRole("button", { name: "Edit Mine" })).toBeInTheDocument();
    expect(within(mine).getByRole("button", { name: "Delete Mine" })).toBeInTheDocument();

    const theirs = screen.getByRole("article", { name: "Someone else's" });
    expect(within(theirs).queryByRole("button", { name: /^Edit/ })).toBeNull();
    expect(within(theirs).queryByRole("button", { name: /^Delete/ })).toBeNull();
  });

  it("posts a call and puts it on the board where a reload would", async () => {
    serve([month()], true);
    create.mockImplementation(async (input: Record<string, unknown>) => ({
      data: call({ ...(input as Partial<Opportunity>), id: 900, days_left: 5, can_edit: true, type_display: "Funding Window" }),
    }));
    await renderBoard();
    const user = userEvent.setup();

    await user.click(screen.getByRole("button", { name: "Post a call" }));
    const dialog = await screen.findByRole("dialog", { name: "Post a call" });

    // Nothing filled: the browser names what is missing, and sends nothing.
    await user.click(within(dialog).getByRole("button", { name: "Post call" }));
    expect(within(dialog).getByText("Choose what kind of call this is.")).toBeInTheDocument();
    expect(within(dialog).getByText("Give the call a title.")).toBeInTheDocument();
    expect(create).not.toHaveBeenCalled();

    await user.selectOptions(within(dialog).getByRole("combobox", { name: "Type" }), "funding_window");
    await user.type(within(dialog).getByRole("textbox", { name: "Title" }), "CHED research window");
    await user.type(within(dialog).getByRole("textbox", { name: "Posting office" }), "KTTO");
    fireEvent.change(within(dialog).getByLabelText("Deadline"), { target: { value: "2026-10-16" } });
    await user.type(within(dialog).getByRole("textbox", { name: "Funding ceiling in pesos (optional)" }), "250,000");
    await user.type(within(dialog).getByRole("textbox", { name: "Tags (optional)" }), "CHED, Research, ");
    await user.click(within(dialog).getByRole("button", { name: "Post call" }));

    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(create).toHaveBeenCalledWith(expect.objectContaining({
      opportunity_type: "funding_window",
      title: "CHED research window",
      posting_office: "KTTO",
      due_date: "2026-10-16",
      funding_ceiling: "250000",
      tags: ["CHED", "Research"],
      source: "internal",
      is_featured: false,
    }));

    const week = screen.getByRole("region", { name: /Closes within a week/ });
    expect(within(week).getByRole("article", { name: "CHED research window" })).toBeInTheDocument();
  });

  it("shows the server's objection against the field it is about", async () => {
    serve([], true);
    create.mockRejectedValueOnce({
      response: { status: 400, data: { external_url: ["Enter a valid URL."] } },
    });
    await renderBoard();
    const user = userEvent.setup();

    await user.click(screen.getAllByRole("button", { name: "Post a call" })[0]);
    const dialog = await screen.findByRole("dialog", { name: "Post a call" });
    await user.selectOptions(within(dialog).getByRole("combobox", { name: "Type" }), "internal_call");
    await user.type(within(dialog).getByRole("textbox", { name: "Title" }), "A call");
    await user.type(within(dialog).getByRole("textbox", { name: "Posting office" }), "CCS");
    fireEvent.change(within(dialog).getByLabelText("Deadline"), { target: { value: "2026-11-20" } });
    await user.type(within(dialog).getByRole("textbox", { name: "Link (optional)" }), "not a url");
    await user.click(within(dialog).getByRole("button", { name: "Post call" }));

    const link = await within(dialog).findByRole("textbox", { name: "Link (optional)", description: "Enter a valid URL." });
    expect(link).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByRole("dialog", { name: "Post a call" })).toBeInTheDocument();
  });

  it("edits a call from its saved values", async () => {
    const mine = call({ id: 7, title: "Old title", can_edit: true, tags: ["One", "Two"], funding_ceiling: "5000.00" });
    serve([mine], true);
    update.mockImplementation(async (_id: number, input: Record<string, unknown>) => ({
      data: { ...mine, ...(input as Partial<Opportunity>) },
    }));
    await renderBoard();
    const user = userEvent.setup();

    await user.click(screen.getByRole("button", { name: "Edit Old title" }));
    const dialog = await screen.findByRole("dialog", { name: "Edit call" });
    const title = within(dialog).getByRole("textbox", { name: "Title" });
    expect(title).toHaveValue("Old title");
    expect(within(dialog).getByRole("textbox", { name: "Tags (optional)" })).toHaveValue("One, Two");
    expect(within(dialog).getByRole("textbox", { name: "Funding ceiling in pesos (optional)" })).toHaveValue("5000");

    await user.clear(title);
    await user.type(title, "New title");
    await user.click(within(dialog).getByRole("button", { name: "Save changes" }));

    await waitFor(() => expect(update).toHaveBeenCalledWith(7, expect.objectContaining({ title: "New title" })));
    expect(await screen.findByRole("article", { name: "New title" })).toBeInTheDocument();
  });

  it("deletes a call only after it is confirmed", async () => {
    serve([call({ id: 8, title: "Doomed call", can_edit: true }), month()], true);
    remove.mockResolvedValue({});
    await renderBoard();
    const user = userEvent.setup();

    await user.click(screen.getByRole("button", { name: "Delete Doomed call" }));
    const confirm = await screen.findByRole("dialog", { name: "Delete this call?" });
    expect(remove).not.toHaveBeenCalled();

    await user.click(within(confirm).getByRole("button", { name: /Delete call/ }));
    await waitFor(() => expect(screen.queryByRole("article", { name: "Doomed call" })).toBeNull());
    expect(remove).toHaveBeenCalledWith(8);
  });

  it("has no serious accessibility violations with the sheet open", async () => {
    serve([], true);
    await renderBoard();
    await userEvent.setup().click(screen.getAllByRole("button", { name: "Post a call" })[0]);
    const dialog = await screen.findByRole("dialog", { name: "Post a call" });
    await expectNoBlockingA11yViolations(dialog);
  });
});
