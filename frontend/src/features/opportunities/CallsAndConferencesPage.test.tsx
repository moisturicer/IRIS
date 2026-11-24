/**
 * Calls & Conferences (IR-530): the deadline board, and posting from it.
 *
 * Every query goes through the accessible tree. Whether Post, Edit and Delete
 * are offered is the server's `can_post` / `can_edit`; these tests feed those
 * fields and check the page draws exactly what they say.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ToastContainer } from "@/components/ui/Toast";
import { useAuthStore } from "@/store/auth.store";
import { useSavedCallsStore } from "@/store/savedCalls.store";
import { useUIStore } from "@/store/ui.store";
import { expectNoBlockingA11yViolations } from "@/test/axe";
import { fireEvent, renderScreen, screen, userEvent, waitFor, within } from "@/test/render";
import type { Opportunity, OpportunityBoard } from "@/types/opportunities";

import { CallsAndConferencesPage } from "./CallsAndConferencesPage";

const board = vi.fn<() => Promise<OpportunityBoard>>();
const create = vi.fn();
const update = vi.fn();
const remove = vi.fn();
const calendar = vi.fn();
const setFeatured = vi.fn();
const removeWithReason = vi.fn();
const saved = vi.fn();
const saveCall = vi.fn();
const unsaveCall = vi.fn();

vi.mock("@/api/opportunities", () => ({
  opportunitiesApi: {
    board: () => board(),
    create: (input: unknown) => create(input),
    update: (id: number, input: unknown) => update(id, input),
    remove: (id: number) => remove(id),
    calendar: (id: number) => calendar(id),
    setFeatured: (id: number, featured: boolean) => setFeatured(id, featured),
    removeWithReason: (id: number, reason: string) => removeWithReason(id, reason),
    saved: () => saved(),
    save: (id: number) => saveCall(id),
    unsave: (id: number) => unsaveCall(id),
  },
}));

const classifications = vi.fn();
vi.mock("@/api/records", () => ({
  recordsApi: { classifications: () => classifications() },
}));

const AREAS = [
  { id: 1, name: "Artificial Intelligence" },
  { id: 2, name: "Clean Energy" },
];

let nextId = 1;
function call(overrides: Partial<Opportunity> = {}): Opportunity {
  const id = overrides.id ?? nextId++;
  return {
    id,
    opportunity_type: "conference",
    type_display: "Conference",
    title: `Call ${id}`,
    description: "A description.",
    external_url: "https://www.cit.edu/research/",
    due_date: "2026-11-01",
    location: "Cebu City, Philippines",
    areas: [1],
    area_names: ["Artificial Intelligence"],
    start_date: null,
    end_date: null,
    registration_fee: "",
    is_featured: false,
    posted_by: 3,
    posted_by_name: "Maria Santos",
    created_at: "2026-10-01T00:00:00Z",
    updated_at: "2026-10-01T00:00:00Z",
    days_left: 20,
    is_closed: false,
    papers_state: "accepting",
    papers_label: "Accepting papers",
    event_state: null,
    event_label: null,
    status: "confirmed",
    status_label: "Confirmed",
    review_reason: "",
    reviewed_at: null,
    can_edit: false,
    can_delete: false,
    can_remove: false,
    can_confirm: false,
    can_reject: false,
    can_feature: false,
    edit_returns_to_pending: false,
    ...overrides,
  };
}

const soon    = () => call({ id: 101, title: "Workshop on Edge AI", opportunity_type: "workshop", type_display: "Workshop", days_left: 3, due_date: "2026-10-14" });
const month   = () => call({ id: 102, title: "ICACSIS 2026 paper deadline", days_left: 19, due_date: "2026-10-30" });
const later   = () => call({ id: 103, title: "Energy Letters special issue", opportunity_type: "journal", type_display: "Journal", days_left: 60, due_date: "2026-12-10", location: "Online", area_names: ["Clean Energy"] });
const closed  = () => call({ id: 104, title: "Last term's symposium", opportunity_type: "symposium", type_display: "Symposium", days_left: -4, is_closed: true, papers_state: "closed", papers_label: "Submissions closed", due_date: "2026-10-07" });

function serve(items: Opportunity[], canPost = false, canFeature = false) {
  board.mockResolvedValue({ items, can_post: canPost, can_feature: canFeature });
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
  // Saves follow the account (IR-766): a signed-in reader, with none yet.
  useAuthStore.setState({ isAuthenticated: true });
  useSavedCallsStore.setState({ load: "idle", items: {} });
  saved.mockResolvedValue({ data: { results: [] } });
  classifications.mockResolvedValue({ data: { count: 2, next: null, previous: null, results: AREAS } });
});

afterEach(() => {
  vi.clearAllMocks();
  useUIStore.setState({ toasts: [] });
});

describe("the board", () => {
  it("groups calls by how soon they close, soonest first, closed last", async () => {
    serve([later(), closed(), soon(), month()]);
    await renderBoard();

    const headings = screen.getAllByRole("heading", { level: 2 }).map((h) => h.textContent);
    expect(headings).toEqual([
      "Closes within a week1 call",
      "Closes within a month1 call",
      "Closes later1 call",
      "Submissions closed1 call",
    ]);

    const week = screen.getByRole("region", { name: /Closes within a week/ });
    const row = within(week).getByRole("article", { name: "Workshop on Edge AI" });
    expect(within(row).getByText("Accepting papers")).toBeInTheDocument();
    expect(within(row).getByText("3 days left")).toBeInTheDocument();
    expect(within(row).getByRole("link", { name: /View & apply/ })).toHaveAttribute("target", "_blank");

    const done = screen.getByRole("region", { name: /Submissions closed/ });
    const old = within(done).getByRole("article", { name: "Last term's symposium" });
    expect(within(old).getByText("Submissions closed")).toBeInTheDocument();
    // A closed call has no deadline left to put in a calendar.
    expect(within(old).queryByRole("button", { name: /to your calendar/ })).toBeNull();
  });

  it("says where a call is and which Areas it is for", async () => {
    serve([later()]);
    await renderBoard();
    const row = screen.getByRole("article", { name: "Energy Letters special issue" });
    expect(within(row).getByText("Journal")).toBeInTheDocument();
    expect(within(row).getByText("Online")).toBeInTheDocument();
    expect(within(row).getByText("Clean Energy")).toBeInTheDocument();
  });

  it("shows everything a row carries: about, event dates, fee, Areas, link and who posted it", async () => {
    serve([call({
      title: "ICCE 2027", description: "Full papers on computing education.",
      start_date: "2027-01-20", end_date: "2027-01-22", registration_fee: "PHP 5,000",
      area_names: ["Artificial Intelligence", "Clean Energy"],
    })]);
    await renderBoard();
    const row = screen.getByRole("article", { name: "ICCE 2027" });
    expect(within(row).getByText("Conference")).toBeInTheDocument();
    expect(within(row).getByText("Full papers on computing education.")).toBeInTheDocument();
    expect(within(row).getByText("Event: Jan 20, 2027 to Jan 22, 2027")).toBeInTheDocument();
    expect(within(row).getByText("Fee: PHP 5,000")).toBeInTheDocument();
    expect(within(row).getByText("Cebu City, Philippines")).toBeInTheDocument();
    expect(within(row).getByText("Clean Energy")).toBeInTheDocument();
    expect(within(row).getByRole("link", { name: /View & apply/ })).toHaveAttribute("href", "https://www.cit.edu/research/");
    expect(within(row).getByText("Posted by Maria Santos")).toBeInTheDocument();
  });

  it("leaves out the fee and event dates when there are none", async () => {
    serve([later()]);
    await renderBoard();
    const row = screen.getByRole("article", { name: "Energy Letters special issue" });
    expect(within(row).queryByText(/^Fee:/)).toBeNull();
    expect(within(row).queryByText(/^Event:/)).toBeNull();
  });

  it("shows Happening now beside the papers tag while the event runs, and no other event tag", async () => {
    serve([
      call({ title: "Running now", event_state: "happening", event_label: "Happening now", start_date: "2026-10-10", end_date: "2026-10-12" }),
      call({ title: "Still ahead", event_state: "upcoming", event_label: "Upcoming", start_date: "2027-01-10" }),
    ]);
    await renderBoard();
    const running = screen.getByRole("article", { name: "Running now" });
    expect(within(running).getByText("Accepting papers")).toBeInTheDocument();
    expect(within(running).getByText("Happening now")).toBeInTheDocument();
    expect(within(screen.getByRole("article", { name: "Still ahead" })).queryByText("Upcoming")).toBeNull();
  });

  it("stars a Featured call and says so in words", async () => {
    serve([call({ title: "Starred", is_featured: true })]);
    await renderBoard();
    expect(within(screen.getByRole("article", { name: "Starred" })).getByText("Featured")).toBeInTheDocument();
  });

  it("draws no link and no fallback for a migrated call that lacks one", async () => {
    // Only a Call migrated from a Conference Deadline can lack one (IR-760);
    // the "ask the office" fallback is gone (IR-764).
    serve([call({ title: "Unlinked call", external_url: "" })]);
    await renderBoard();
    const row = screen.getByRole("article", { name: "Unlinked call" });
    expect(within(row).queryByRole("link")).toBeNull();
    expect(within(row).queryByText(/Ask /)).toBeNull();
  });

  it("has no serious accessibility violations", async () => {
    serve([soon(), month(), later(), closed()], true);
    const { container } = await renderBoard();
    await expectNoBlockingA11yViolations(container);
  });
});

// The Full Text Rule (IR-1219; DESIGN.md "The five allowed cuts"): the board
// clamps a call's About to two lines only with Show more, because nothing else
// on the board reaches the rest. jsdom lays nothing out, so "runs past two
// lines" is an element whose content is taller than its box.
describe("a call's About on the board", () => {
  const LONG = "Funding for applied research in energy, materials and manufacturing, open to state and private HEIs.";

  beforeEach(() => {
    vi.spyOn(HTMLElement.prototype, "scrollHeight", "get").mockImplementation(function (this: HTMLElement) {
      return (this.textContent ?? "").includes(LONG) ? 80 : 40;
    });
    vi.spyOn(HTMLElement.prototype, "clientHeight", "get").mockReturnValue(40);
  });

  afterEach(() => vi.restoreAllMocks());

  it("offers Show more when it runs past two lines, and Show less once it is whole", async () => {
    serve([call({ title: "DOST Research Grant", description: LONG })]);
    await renderBoard();
    const row = screen.getByRole("article", { name: "DOST Research Grant" });
    const more = within(row).getByRole("button", { name: "Show more" });
    expect(more).toHaveAttribute("aria-expanded", "false");

    await userEvent.click(more);
    const less = within(row).getByRole("button", { name: "Show less" });
    expect(less).toHaveAttribute("aria-expanded", "true");

    await userEvent.click(less);
    expect(within(row).getByRole("button", { name: "Show more" })).toHaveAttribute("aria-expanded", "false");
  });

  it("offers nothing when it fits", async () => {
    serve([call({ title: "ICCE 2027", description: "Full papers on computing education." })]);
    await renderBoard();
    const row = screen.getByRole("article", { name: "ICCE 2027" });
    expect(within(row).queryByRole("button", { name: /Show (more|less)/ })).toBeNull();
  });
});

describe("order", () => {
  it("never moves a Featured call ahead of one due the same day", async () => {
    serve([
      call({ id: 201, title: "Plain, posted first", due_date: "2026-10-23", days_left: 12 }),
      call({ id: 202, title: "Featured, posted later", is_featured: true, due_date: "2026-10-23", days_left: 12 }),
    ]);
    await renderBoard();
    const titles = screen.getAllByRole("article").map((a) => within(a).getByRole("heading").textContent);
    expect(titles).toEqual(["Plain, posted first", "Featured, posted later"]);
  });

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
    const conference = within(types).getByRole("button", { name: /^Conference\s*1/ });
    await user.click(conference);

    expect(conference).toHaveAttribute("aria-pressed", "true");
    expect(screen.getAllByRole("article")).toHaveLength(1);
    expect(screen.getByRole("article", { name: "ICACSIS 2026 paper deadline" })).toBeInTheDocument();
    expect(screen.getByText("Showing 1 of 3 calls.")).toBeInTheDocument();
  });

  it("narrows the board to one Area", async () => {
    serve([soon(), month(), later()]);
    await renderBoard();
    const user = userEvent.setup();

    const area = screen.getByRole("combobox", { name: "Area" });
    expect(within(area).getAllByRole("option").map((o) => o.textContent))
      .toEqual(["All Areas", "Artificial Intelligence", "Clean Energy"]);
    await user.selectOptions(area, "Clean Energy");

    expect(screen.getAllByRole("article")).toHaveLength(1);
    expect(screen.getByRole("article", { name: "Energy Letters special issue" })).toBeInTheDocument();
    expect(screen.getByText("Showing 1 of 3 calls.")).toBeInTheDocument();
  });

  // IR-1313: the Area box is one width from `sm` up, so the row does not move
  // when the board's Areas arrive or change; the chosen Area is named on hover.
  it("keeps the Area filter one width, and names the chosen Area on hover", async () => {
    serve([soon(), month(), later()]);
    await renderBoard();

    const area = screen.getByRole("combobox", { name: "Area" });
    expect(area).toHaveClass("sm:w-72");
    expect(area).toHaveAttribute("title", "All Areas");
    await userEvent.setup().selectOptions(area, "Artificial Intelligence");
    expect(area).toHaveAttribute("title", "Artificial Intelligence");
  });

  it("offers to clear the filters when nothing matches", async () => {
    serve([soon(), month()]);
    await renderBoard();
    const user = userEvent.setup();

    await user.type(screen.getByRole("searchbox", { name: "Search calls by title, location or Area" }), "zzz");
    expect(screen.getByRole("heading", { name: "Nothing matches these filters" })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Clear filters" }));
    expect(screen.getAllByRole("article")).toHaveLength(2);
  });

  it("saves a call to the account and can show only the saved ones", async () => {
    serve([soon(), month()]);
    saveCall.mockImplementation(async (id: number) => ({
      data: { call_id: id, available: true, saved_at: "2026-11-16T08:00:00Z", call: month() },
    }));
    await renderBoard();
    const user = userEvent.setup();

    const save = screen.getByRole("button", { name: "Save ICACSIS 2026 paper deadline" });
    await user.click(save);
    expect(save).toHaveAttribute("aria-pressed", "true");
    expect(saveCall).toHaveBeenCalledWith(102);
    // Nothing is kept in the browser, and nothing says it is (IR-766).
    expect(localStorage.getItem("iris_saved_opportunities")).toBeNull();
    expect(screen.queryByText(/in this browser/)).toBeNull();

    await user.click(screen.getByRole("button", { name: /^Saved\s*1/ }));
    expect(screen.getAllByRole("article")).toHaveLength(1);
    expect(screen.getByRole("article", { name: "ICACSIS 2026 paper deadline" })).toBeInTheDocument();
  });
});

describe("saved calls (IR-766)", () => {
  it("counts and shows only the saved calls still on the board", async () => {
    // 101 is on the board; 999 is Over, and 7 is unavailable: both stay in My Library only.
    saved.mockResolvedValue({ data: { results: [
      { call_id: 101, available: true, saved_at: "2026-11-15T08:00:00Z", call: soon() },
      { call_id: 999, available: true, saved_at: "2026-11-14T08:00:00Z", call: call({ id: 999, title: "Over" }) },
      { call_id: 7, available: false },
    ] } });
    serve([soon(), month()]);
    await renderBoard();

    const filter = await screen.findByRole("button", { name: /^Saved\s*1$/ });
    expect(screen.getByRole("button", { name: "Save Workshop on Edge AI" })).toHaveAttribute("aria-pressed", "true");
    await userEvent.setup().click(filter);
    expect(screen.getAllByRole("article").map((a) => within(a).getByRole("heading").textContent)).toEqual(["Workshop on Edge AI"]);
  });

  it("keeps the server's saved marks when the account's list can't be read", async () => {
    saved.mockRejectedValue(new Error("Network Error"));
    serve([call({ id: 301, title: "Marked saved", is_saved: true }), call({ id: 302, title: "Not saved" })]);
    await renderBoard();

    expect(screen.getByRole("button", { name: "Save Marked saved" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "Save Not saved" })).toHaveAttribute("aria-pressed", "false");
    expect(screen.getByRole("button", { name: /^Saved\s*1$/ })).toBeInTheDocument();
  });

  it("rolls a failed save back and says so in a toast with Try again", async () => {
    serve([month()]);
    saveCall.mockRejectedValueOnce(new Error("Network Error"));
    renderScreen(<><CallsAndConferencesPage /><ToastContainer /></>);
    await screen.findByRole("article", { name: "ICACSIS 2026 paper deadline" });
    const user = userEvent.setup();

    const save = screen.getByRole("button", { name: "Save ICACSIS 2026 paper deadline" });
    await user.click(save);

    const toast = await screen.findByRole("alert");
    expect(toast).toHaveTextContent("Could not save ICACSIS 2026 paper deadline. Nothing was changed.");
    expect(save).toHaveAttribute("aria-pressed", "false");
    expect(within(toast).getByRole("button", { name: "Try again" })).toBeInTheDocument();
  });

  it("removes a save", async () => {
    saved.mockResolvedValue({ data: { results: [
      { call_id: 102, available: true, saved_at: "2026-11-15T08:00:00Z", call: month() },
    ] } });
    unsaveCall.mockResolvedValue({});
    serve([month()]);
    await renderBoard();
    const save = await screen.findByRole("button", { name: "Save ICACSIS 2026 paper deadline", pressed: true });
    await userEvent.setup().click(save);
    expect(unsaveCall).toHaveBeenCalledWith(102);
    expect(save).toHaveAttribute("aria-pressed", "false");
  });

  it("has no serious accessibility violations with a call saved", async () => {
    saved.mockResolvedValue({ data: { results: [
      { call_id: 102, available: true, saved_at: "2026-11-15T08:00:00Z", call: month() },
    ] } });
    serve([month(), soon()]);
    const { container } = await renderBoard();
    await screen.findByRole("button", { name: "Save ICACSIS 2026 paper deadline", pressed: true });
    await expectNoBlockingA11yViolations(container);
  });
});

describe("states", () => {
  it("shows no counts until there is a board to count", async () => {
    let resolve!: (b: OpportunityBoard) => void;
    board.mockReturnValueOnce(new Promise((r) => { resolve = r; }));
    renderScreen(<CallsAndConferencesPage />);

    const all = screen.getByRole("button", { name: "All" });
    expect(all).toHaveTextContent(/^All$/);

    resolve({ items: [soon()], can_post: false, can_feature: false });
    await waitFor(() => expect(all).toHaveTextContent(/^All\s*1$/));
  });

  it("says the board failed to load, and loads again on request", async () => {
    board.mockRejectedValueOnce(new Error("offline"));
    renderScreen(<CallsAndConferencesPage />);

    const alert = await screen.findByRole("alert");
    expect(within(alert).getByRole("heading", { name: "Could not load calls and conferences" })).toBeInTheDocument();
    // Nothing to filter, so nothing offers to.
    expect(screen.getByRole("button", { name: "All" })).toBeDisabled();
    expect(screen.getByRole("searchbox", { name: "Search calls by title, location or Area" })).toBeDisabled();

    serve([soon()]);
    await userEvent.setup().click(within(alert).getByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("article", { name: "Workshop on Edge AI" })).toBeInTheDocument();
  });

  it("invites a poster to post the first call on an empty board", async () => {
    serve([], true);
    await renderBoard();
    expect(screen.getByRole("heading", { name: "No calls posted yet" })).toBeInTheDocument();
    // The header's button and the empty state's own.
    expect(screen.getAllByRole("button", { name: "Post a call" })).toHaveLength(2);
  });

  // Audit US-13 (IR-1098): six zero counters and "0 open calls" over an empty
  // board are numbers with nothing to act on (PRODUCT principle 3).
  it("shows no type filters, counters or search on an empty board", async () => {
    serve([], false);
    await renderBoard();
    expect(screen.getByRole("heading", { name: "No calls posted yet" })).toBeInTheDocument();
    expect(screen.queryByRole("group", { name: "Filter by type" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^Saved/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("searchbox")).not.toBeInTheDocument();
    expect(screen.queryByText(/0 open calls/)).not.toBeInTheDocument();
  });

  it("tells a reader who posts calls, and offers no post button", async () => {
    serve([], false);
    await renderBoard();
    expect(screen.getByText(/RDCO and advisers post calls here/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Post a call" })).toBeNull();
  });

  it("reports a calendar failure in a toast with Try again, and never grows the row", async () => {
    serve([soon(), month()]);
    calendar.mockRejectedValueOnce(new Error("500"));
    renderScreen(<><CallsAndConferencesPage /><ToastContainer /></>);
    await screen.findByRole("article", { name: "Workshop on Edge AI" });
    const user = userEvent.setup();

    await user.click(screen.getByRole("button", { name: "Add the Workshop on Edge AI deadline to your calendar" }));

    const toast = await screen.findByRole("alert");
    expect(toast).toHaveTextContent("Could not build the calendar file for Workshop on Edge AI. Try again.");
    // A toast, not a line inside the row that pushes the board down.
    expect(within(screen.getByRole("article", { name: "Workshop on Edge AI" })).queryByRole("alert")).toBeNull();
    // An error stays until it is dismissed or acted on.
    expect(useUIStore.getState().toasts[0]).toMatchObject({ type: "error", persist: true });

    calendar.mockResolvedValueOnce({ data: new Blob(["BEGIN:VCALENDAR"]) });
    URL.createObjectURL = vi.fn(() => "blob:ics");
    URL.revokeObjectURL = vi.fn();
    await user.click(within(toast).getByRole("button", { name: "Try again" }));
    expect(calendar).toHaveBeenCalledTimes(2);
    await waitFor(() => expect(screen.queryByRole("alert")).toBeNull());
  });
});

describe("posting and changing calls", () => {
  it("offers Edit and Delete only on calls the server says this viewer may change", async () => {
    serve([call({ title: "Mine", can_edit: true, can_delete: true }), call({ title: "Someone else's" })], true);
    await renderBoard();

    const mine = screen.getByRole("article", { name: "Mine" });
    expect(within(mine).getByRole("button", { name: "Edit Mine" })).toBeInTheDocument();
    expect(within(mine).getByRole("button", { name: "Delete Mine" })).toBeInTheDocument();

    const theirs = screen.getByRole("article", { name: "Someone else's" });
    expect(within(theirs).queryByRole("button", { name: /^Edit/ })).toBeNull();
    expect(within(theirs).queryByRole("button", { name: /^Delete/ })).toBeNull();
  });

  it("marks the optional fields in their names and announces the required ones (IR-585, IR-760)", async () => {
    serve([month()], true);
    await renderBoard();
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Post a call" }));
    const dialog = await screen.findByRole("dialog", { name: "Post a call" });

    for (const name of ["Title", "About", "Paper deadline", "Location", "Link"]) {
      expect(within(dialog).getByLabelText(name)).toBeRequired();
    }
    expect(within(dialog).getByRole("combobox", { name: "Type" })).toBeRequired();
    expect(within(dialog).getByRole("group", { name: "Areas" })).toBeInTheDocument();
    for (const name of ["Start date (optional)", "End date (optional)", "Registration fee (optional)"]) {
      expect(within(dialog).getByLabelText(name)).not.toBeRequired();
    }
    expect(within(dialog).queryByText(/\(required\)/)).not.toBeInTheDocument();
    for (const gone of [/Posting office/, /Who can apply/, /Funding ceiling/, /Tags/, /Source/]) {
      expect(within(dialog).queryByLabelText(gone)).toBeNull();
    }
  });

  it("hides the event dates for a Journal and fills its location with Online, which stays editable", async () => {
    serve([], true);
    await renderBoard();
    const user = userEvent.setup();
    await user.click(screen.getAllByRole("button", { name: "Post a call" })[0]);
    const dialog = await screen.findByRole("dialog", { name: "Post a call" });

    await user.selectOptions(within(dialog).getByRole("combobox", { name: "Type" }), "journal");
    expect(within(dialog).queryByLabelText("Start date (optional)")).toBeNull();
    expect(within(dialog).queryByLabelText("End date (optional)")).toBeNull();
    const location = within(dialog).getByRole("textbox", { name: "Location" });
    expect(location).toHaveValue("Online");

    await user.clear(location);
    await user.type(location, "Elsevier, online submission");
    expect(location).toHaveValue("Elsevier, online submission");

    await user.selectOptions(within(dialog).getByRole("combobox", { name: "Type" }), "conference");
    expect(within(dialog).getByLabelText("Start date (optional)")).toBeInTheDocument();
  });

  it("offers Featured on a new call only to someone who may feature (ADR-050 decision 12)", async () => {
    serve([], true, false);
    const { unmount } = await renderBoard();
    await userEvent.setup().click(screen.getAllByRole("button", { name: "Post a call" })[0]);
    const adviser = await screen.findByRole("dialog", { name: "Post a call" });
    expect(within(adviser).queryByRole("checkbox", { name: /Feature this call/ })).toBeNull();
    unmount();

    serve([], true, true);
    await renderBoard();
    await userEvent.setup().click(screen.getAllByRole("button", { name: "Post a call" })[0]);
    const rdco = await screen.findByRole("dialog", { name: "Post a call" });
    expect(within(rdco).getByRole("checkbox", { name: /Feature this call/ })).not.toBeChecked();
  });

  it("offers Featured on an edit only when the server says this call may be featured", async () => {
    serve([
      call({ id: 31, title: "Featurable", can_edit: true, can_feature: true, is_featured: true }),
      call({ id: 32, title: "Not featurable", can_edit: true }),
    ], true, true);
    await renderBoard();
    const user = userEvent.setup();

    await user.click(screen.getByRole("button", { name: "Edit Featurable" }));
    const one = await screen.findByRole("dialog", { name: "Edit call" });
    expect(within(one).getByRole("checkbox", { name: /Feature this call/ })).toBeChecked();
    await user.click(within(one).getByRole("button", { name: "Cancel" }));

    await user.click(screen.getByRole("button", { name: "Edit Not featurable" }));
    const two = await screen.findByRole("dialog", { name: "Edit call" });
    expect(within(two).queryByRole("checkbox", { name: /Feature this call/ })).toBeNull();
  });

  it("keeps a posted call that waits for RDCO off the board, and says where it went", async () => {
    serve([month()], true);
    create.mockResolvedValue({
      data: call({ id: 950, title: "Waiting call", status: "pending", status_label: "Waiting for RDCO" }),
    });
    renderScreen(<><CallsAndConferencesPage /><ToastContainer /></>);
    await screen.findByRole("article", { name: "ICACSIS 2026 paper deadline" });
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Post a call" }));
    const dialog = await screen.findByRole("dialog", { name: "Post a call" });
    await user.selectOptions(within(dialog).getByRole("combobox", { name: "Type" }), "journal");
    await user.type(within(dialog).getByRole("textbox", { name: "Title" }), "Waiting call");
    await user.type(within(dialog).getByRole("textbox", { name: "About" }), "A special issue.");
    fireEvent.change(within(dialog).getByLabelText("Paper deadline"), { target: { value: "2026-11-20" } });
    await user.click(within(within(dialog).getByRole("group", { name: "Areas" })).getByRole("checkbox", { name: "Clean Energy" }));
    await user.type(within(dialog).getByRole("textbox", { name: "Link" }), "https://example.org/si");
    await user.click(within(dialog).getByRole("button", { name: "Post call" }));

    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(create).toHaveBeenCalledWith(expect.objectContaining({ location: "Online", start_date: null, end_date: null }));
    expect(screen.queryByRole("article", { name: "Waiting call" })).toBeNull();
    expect(await screen.findByText("Call sent to RDCO. It appears on the board once RDCO confirms it.")).toBeInTheDocument();
  });

  it("offers the six types of call and no other", async () => {
    serve([], true);
    await renderBoard();
    await userEvent.setup().click(screen.getAllByRole("button", { name: "Post a call" })[0]);
    const dialog = await screen.findByRole("dialog", { name: "Post a call" });
    const options = within(within(dialog).getByRole("combobox", { name: "Type" }))
      .getAllByRole("option").map((o) => o.textContent);
    expect(options).toEqual([
      "Choose a type", "Conference", "Congress", "Symposium", "Workshop", "Journal", "Book chapter",
    ]);
  });

  it("posts a call and puts it on the board where a reload would", async () => {
    serve([month()], true);
    create.mockImplementation(async (input: Record<string, unknown>) => ({
      data: call({ ...(input as Partial<Opportunity>), id: 900, days_left: 5, can_edit: true, type_display: "Symposium" }),
    }));
    await renderBoard();
    const user = userEvent.setup();

    await user.click(screen.getByRole("button", { name: "Post a call" }));
    const dialog = await screen.findByRole("dialog", { name: "Post a call" });

    // Nothing filled: the browser names what is missing, and sends nothing.
    await user.click(within(dialog).getByRole("button", { name: "Post call" }));
    for (const message of [
      "Choose what kind of call this is.", "Give the call a title.", "Say what the call is about.",
      "Set the paper deadline.", "Say where it takes place, or Online.", "Choose at least one Area.",
      "Give the link to the full call.",
    ]) {
      expect(within(dialog).getByText(message)).toBeInTheDocument();
    }
    expect(create).not.toHaveBeenCalled();

    await user.selectOptions(within(dialog).getByRole("combobox", { name: "Type" }), "symposium");
    await user.type(within(dialog).getByRole("textbox", { name: "Title" }), "Visayas Symposium on Energy");
    await user.type(within(dialog).getByRole("textbox", { name: "About" }), "Short papers on island grids.");
    fireEvent.change(within(dialog).getByLabelText("Paper deadline"), { target: { value: "2026-10-16" } });
    await user.type(within(dialog).getByRole("textbox", { name: "Location" }), "Iloilo City");
    await user.click(within(within(dialog).getByRole("group", { name: "Areas" })).getByRole("checkbox", { name: "Clean Energy" }));
    await user.type(within(dialog).getByRole("textbox", { name: "Link" }), "https://example.org/vse");
    fireEvent.change(within(dialog).getByLabelText("Start date (optional)"), { target: { value: "2027-01-20" } });
    await user.type(within(dialog).getByRole("textbox", { name: "Registration fee (optional)" }), "Free for students");
    await user.click(within(dialog).getByRole("button", { name: "Post call" }));

    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(create).toHaveBeenCalledWith({
      opportunity_type: "symposium",
      title: "Visayas Symposium on Energy",
      description: "Short papers on island grids.",
      due_date: "2026-10-16",
      location: "Iloilo City",
      areas: [2],
      external_url: "https://example.org/vse",
      start_date: "2027-01-20",
      end_date: null,
      registration_fee: "Free for students",
      is_featured: false,
    });

    const week = screen.getByRole("region", { name: /Closes within a week/ });
    expect(within(week).getByRole("article", { name: "Visayas Symposium on Energy" })).toBeInTheDocument();
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
    await user.selectOptions(within(dialog).getByRole("combobox", { name: "Type" }), "journal");
    await user.type(within(dialog).getByRole("textbox", { name: "Title" }), "A call");
    await user.type(within(dialog).getByRole("textbox", { name: "About" }), "A special issue.");
    fireEvent.change(within(dialog).getByLabelText("Paper deadline"), { target: { value: "2026-11-20" } });
    await user.type(within(dialog).getByRole("textbox", { name: "Location" }), "Online");
    await user.click(within(within(dialog).getByRole("group", { name: "Areas" })).getByRole("checkbox", { name: "Artificial Intelligence" }));
    await user.type(within(dialog).getByRole("textbox", { name: "Link" }), "ftp://example.org");
    await user.click(within(dialog).getByRole("button", { name: "Post call" }));

    const link = await within(dialog).findByRole("textbox", { name: "Link", description: "Enter a valid URL." });
    expect(link).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByRole("dialog", { name: "Post a call" })).toBeInTheDocument();
  });

  it("says when the Areas could not be loaded, rather than offering none", async () => {
    serve([], true);
    classifications.mockRejectedValueOnce(new Error("offline"));
    await renderBoard();
    await userEvent.setup().click(screen.getAllByRole("button", { name: "Post a call" })[0]);
    const dialog = await screen.findByRole("dialog", { name: "Post a call" });
    const areas = within(dialog).getByRole("group", { name: "Areas" });
    expect(await within(areas).findByText("The Areas could not be loaded. Close this and try again.")).toBeInTheDocument();
    expect(within(areas).queryByRole("checkbox")).toBeNull();
  });

  it("edits a call from its saved values", async () => {
    const mine = call({
      id: 7, title: "Old title", can_edit: true, areas: [2], area_names: ["Clean Energy"],
      start_date: "2027-02-01", end_date: "2027-02-03", registration_fee: "USD 250",
    });
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
    expect(within(dialog).getByRole("textbox", { name: "Location" })).toHaveValue("Cebu City, Philippines");
    expect(within(dialog).getByLabelText("End date (optional)")).toHaveValue("2027-02-03");
    expect(within(dialog).getByRole("textbox", { name: "Registration fee (optional)" })).toHaveValue("USD 250");
    const areas = within(dialog).getByRole("group", { name: "Areas" });
    expect(await within(areas).findByRole("checkbox", { name: "Clean Energy" })).toBeChecked();
    expect(within(areas).getByRole("checkbox", { name: "Artificial Intelligence" })).not.toBeChecked();

    await user.clear(title);
    await user.type(title, "New title");
    await user.click(within(dialog).getByRole("button", { name: "Save changes" }));

    await waitFor(() => expect(update).toHaveBeenCalledWith(7, expect.objectContaining({ title: "New title" })));
    expect(await screen.findByRole("article", { name: "New title" })).toBeInTheDocument();
  });

  it("deletes a call only after it is confirmed", async () => {
    serve([call({ id: 8, title: "Doomed call", can_edit: true, can_delete: true }), month()], true);
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

  it("offers no plain Delete where the server says a removal needs a reason", async () => {
    // RDCO on an Adviser's Call: it may edit, but removing it takes a reason
    // through `remove`, which IR-765 offers (ADR-050 amendment of 2026-11-15).
    serve([call({ title: "An Adviser's call", can_edit: true, can_delete: false, can_remove: true })], true, true);
    await renderBoard();
    const row = screen.getByRole("article", { name: "An Adviser's call" });
    expect(within(row).getByRole("button", { name: "Edit An Adviser's call" })).toBeInTheDocument();
    expect(within(row).queryByRole("button", { name: /^Delete/ })).toBeNull();
  });

  it("says before saving that an Adviser's edit sends the call back to RDCO", async () => {
    serve([call({ id: 41, title: "Confirmed call", can_edit: true, edit_returns_to_pending: true }),
      call({ id: 42, title: "RDCO's call", can_edit: true })], true);
    await renderBoard();
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Edit Confirmed call" }));
    const dialog = await screen.findByRole("dialog", { name: "Edit call" });
    expect(within(dialog).getByText(/Saving sends this call back to RDCO/)).toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: "Cancel" }));

    await user.click(screen.getByRole("button", { name: "Edit RDCO's call" }));
    expect(within(await screen.findByRole("dialog", { name: "Edit call" })).queryByText(/Saving sends this call back/)).toBeNull();
  });

  it("reports a failed save in a toast with Try again, keeps the sheet and what was typed, and grows nothing", async () => {
    const mine = call({ id: 51, title: "Kept title", can_edit: true });
    serve([mine], true);
    update.mockRejectedValueOnce(new Error("Network Error"));
    update.mockResolvedValueOnce({ data: { ...mine, title: "Kept title" } });
    renderScreen(<><CallsAndConferencesPage /><ToastContainer /></>);
    await screen.findByRole("article", { name: "Kept title" });
    const user = userEvent.setup();

    await user.click(screen.getByRole("button", { name: "Edit Kept title" }));
    const dialog = await screen.findByRole("dialog", { name: "Edit call" });
    await user.click(within(dialog).getByRole("button", { name: "Save changes" }));

    const toast = await screen.findByRole("alert");
    expect(toast).toHaveTextContent("Could not save your changes.");
    expect(toast).toHaveTextContent("Nothing has been lost.");
    expect(within(dialog).queryByRole("alert")).toBeNull();
    expect(within(dialog).getByRole("textbox", { name: "Title" })).toHaveValue("Kept title");

    await user.click(within(toast).getByRole("button", { name: "Try again" }));
    await waitFor(() => expect(update).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  });

  it("reports a failed delete in a toast with Try again, and closes the question", async () => {
    serve([call({ id: 61, title: "Stubborn call", can_edit: true, can_delete: true })], true);
    remove.mockRejectedValueOnce(new Error("Network Error"));
    remove.mockResolvedValueOnce({});
    renderScreen(<><CallsAndConferencesPage /><ToastContainer /></>);
    await screen.findByRole("article", { name: "Stubborn call" });
    const user = userEvent.setup();

    await user.click(screen.getByRole("button", { name: "Delete Stubborn call" }));
    const confirm = await screen.findByRole("dialog", { name: "Delete this call?" });
    await user.click(within(confirm).getByRole("button", { name: /Delete call/ }));

    const toast = await screen.findByRole("alert");
    expect(toast).toHaveTextContent("Could not delete Stubborn call.");
    expect(screen.queryByRole("dialog", { name: "Delete this call?" })).toBeNull();
    expect(screen.getByRole("article", { name: "Stubborn call" })).toBeInTheDocument();

    await user.click(within(toast).getByRole("button", { name: "Try again" }));
    await waitFor(() => expect(screen.queryByRole("article", { name: "Stubborn call" })).toBeNull());
    expect(remove).toHaveBeenCalledTimes(2);
  });

  it("has no serious accessibility violations with a Journal's sheet open", async () => {
    serve([], true, true);
    await renderBoard();
    const user = userEvent.setup();
    await user.click(screen.getAllByRole("button", { name: "Post a call" })[0]);
    const dialog = await screen.findByRole("dialog", { name: "Post a call" });
    await user.selectOptions(within(dialog).getByRole("combobox", { name: "Type" }), "journal");
    await expectNoBlockingA11yViolations(dialog);
  });

  it("has no serious accessibility violations with the sheet open", async () => {
    serve([], true);
    await renderBoard();
    await userEvent.setup().click(screen.getAllByRole("button", { name: "Post a call" })[0]);
    const dialog = await screen.findByRole("dialog", { name: "Post a call" });
    await expectNoBlockingA11yViolations(dialog);
  });
});

/*
 * jsdom computes no layout, so a 360 px render is the same tree as any other
 * (see reflow360.test.tsx). What would push a control off a phone is a row
 * that can't wrap or a clamp on the words, so that is what is asserted.
 */
describe("at 360 px", () => {
  it("wraps each row's tags and actions, keeps the Area filter to the width, and stays accessible", async () => {
    serve([
      call({
        title: "Busy row", is_featured: true, can_edit: true, can_delete: true, event_state: "happening", event_label: "Happening now",
        start_date: "2026-10-10", end_date: "2026-10-12", registration_fee: "PHP 5,000",
      }),
      closed(),
    ], true, true);
    const { container } = await renderBoard();
    const row = screen.getByRole("article", { name: "Busy row" });

    expect(within(row).getByText("Happening now").parentElement!.className).toMatch(/\bflex-wrap\b/);
    for (const button of within(row).getAllByRole("button")) {
      expect(button.parentElement!.className).toMatch(/\bflex-wrap\b/);
      expect(button.closest(".truncate, [class*='line-clamp']")).toBeNull();
    }
    // The filter that holds the Area select takes the full width on a phone.
    expect(screen.getByRole("combobox", { name: "Area" }).closest(".w-full")).not.toBeNull();
    await expectNoBlockingA11yViolations(container);
  });
});

describe("RDCO on the board (IR-765)", () => {
  const adviserCall = () => call({
    id: 71, title: "An Adviser's call", posted_by_name: "Ana Reyes",
    can_edit: true, can_delete: false, can_remove: true, can_feature: true,
  });

  it("removes an Adviser's call only with a reason, which the Adviser is sent", async () => {
    serve([adviserCall(), month()], true, true);
    removeWithReason.mockResolvedValue({});
    renderScreen(<><CallsAndConferencesPage /><ToastContainer /></>);
    await screen.findByRole("article", { name: "An Adviser's call" });
    const user = userEvent.setup();

    await user.click(screen.getByRole("button", { name: "Remove An Adviser's call" }));
    const dialog = await screen.findByRole("dialog", { name: "Remove this call" });
    const submit = within(dialog).getByRole("button", { name: "Remove call" });
    // No reason, no removal.
    expect(submit).toBeDisabled();

    await user.type(within(dialog).getByRole("textbox", { name: "Reason to the Adviser" }), "A duplicate of ICCE.");
    await user.click(submit);

    await waitFor(() => expect(screen.queryByRole("article", { name: "An Adviser's call" })).toBeNull());
    expect(removeWithReason).toHaveBeenCalledWith(71, "A duplicate of ICCE.");
    expect(await screen.findByText("An Adviser's call removed. Its Adviser is told why.")).toBeInTheDocument();
  });

  it("reports a failed removal in a toast and keeps the reason typed", async () => {
    serve([adviserCall()], true, true);
    removeWithReason.mockRejectedValueOnce(new Error("Network Error"));
    renderScreen(<><CallsAndConferencesPage /><ToastContainer /></>);
    await screen.findByRole("article", { name: "An Adviser's call" });
    const user = userEvent.setup();

    await user.click(screen.getByRole("button", { name: "Remove An Adviser's call" }));
    const dialog = await screen.findByRole("dialog", { name: "Remove this call" });
    await user.type(within(dialog).getByRole("textbox", { name: "Reason to the Adviser" }), "Duplicate.");
    await user.click(within(dialog).getByRole("button", { name: "Remove call" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Could not remove An Adviser's call.");
    expect(within(dialog).queryByRole("alert")).toBeNull();
    expect(within(dialog).getByRole("textbox", { name: "Reason to the Adviser" })).toHaveValue("Duplicate.");
  });

  it("sets and clears Featured on a confirmed call, without moving it", async () => {
    serve([adviserCall()], true, true);
    setFeatured.mockImplementation(async (_id: number, featured: boolean) => ({ data: { ...adviserCall(), is_featured: featured } }));
    renderScreen(<><CallsAndConferencesPage /><ToastContainer /></>);
    await screen.findByRole("article", { name: "An Adviser's call" });
    const user = userEvent.setup();

    const toggle = screen.getByRole("button", { name: "Featured: An Adviser's call" });
    expect(toggle).toHaveAttribute("aria-pressed", "false");
    await user.click(toggle);

    expect(setFeatured).toHaveBeenCalledWith(71, true);
    await waitFor(() => expect(screen.getByRole("button", { name: "Featured: An Adviser's call" })).toHaveAttribute("aria-pressed", "true"));
    expect(within(screen.getByRole("article", { name: "An Adviser's call" })).getByText("Featured", { selector: "span" })).toBeInTheDocument();
  });

  it("offers neither Remove nor Featured where the server doesn't", async () => {
    serve([call({ title: "A reader's view" })], false, false);
    await renderBoard();
    const row = screen.getByRole("article", { name: "A reader's view" });
    expect(within(row).queryByRole("button", { name: /^Remove/ })).toBeNull();
    expect(within(row).queryByRole("button", { name: /^Featured:/ })).toBeNull();
  });

  it("links a poster to their own calls", async () => {
    serve([], true);
    await renderBoard();
    expect(screen.getByRole("link", { name: "My calls" })).toHaveAttribute("href", "/opportunities/mine");
  });

  it("has no serious accessibility violations with the reason dialog open", async () => {
    serve([adviserCall()], true, true);
    await renderBoard();
    await userEvent.setup().click(screen.getByRole("button", { name: "Remove An Adviser's call" }));
    await expectNoBlockingA11yViolations(await screen.findByRole("dialog", { name: "Remove this call" }));
  });
});
