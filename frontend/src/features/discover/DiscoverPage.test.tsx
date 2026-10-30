/**
 * Discover, redesigned for the settled workflow (IR-407, F2; spec §4.3).
 *
 * The page finds published research, and lets an author start a submission.
 * Every query goes through the accessible tree, by role and accessible name,
 * and every assertion is something a reader would observe: what is on the
 * screen, and what the page asked the API for.
 *
 * Two older guards are kept from IR-264: Discover offers no Proposal filter,
 * and never calls a Proposal "ongoing research" -- Proposals are not in the
 * public catalogue (ADR-021 §13).
 */
import { afterEach, beforeEach, describe, expect, it, vi, type MockInstance } from "vitest";
import { Route, Routes, useLocation, useNavigate } from "react-router-dom";

import { expectNoBlockingA11yViolations } from "@/test/axe";
import { importedReference } from "@/test/fixtures/importedReference";
import { renderScreen, screen, userEvent, waitFor, within } from "@/test/render";
import { recordsApi } from "@/api/records";
import { useAuthStore } from "@/store/auth.store";
import { getCollections, isStarred } from "@/lib/recordLibrary";
import type { RecordListItem } from "@/types/records";
import type { User } from "@/types/auth";

import DiscoverPage from "./DiscoverPage";

function listItem(overrides: Partial<RecordListItem>): RecordListItem {
  return {
    id: 1,
    title: "Untitled",
    abstract: "An abstract.",
    year_accomplished: 2026,
    classification_name: "Applied Research",
    record_type_name: "Thesis/Research",
    pipeline_status: "published",
    is_ip: false,
    ip_type: "",
    for_commercialization: false,
    community_extension: false,
    access_count: 0,
    file_count: 0,
    created_at: "2026-09-01T08:00:00Z",
    authors: [{ id: 1, name: "Mateo Villanueva", role: null }],
    ...overrides,
  };
}

const publishedThesis = listItem({ id: 1, title: "Assistive Navigation for Low-Vision Commuters" });

/**
 * Not something the API returns any more. Fed in deliberately, to prove the
 * card itself no longer calls an approved Proposal "ongoing research".
 */
const approvedProposal = listItem({
  id: 2,
  title: "Low-Cost Soil Moisture Sensing for Upland Farms",
  record_type_name: "Proposal",
  pipeline_status: "approved",
});

let listed: RecordListItem[] = [publishedThesis];
let total: number | null = null;
let recommended: { mode: "for_you" | "latest"; results: (RecordListItem & { reason: { kind: "selected_area" | "latest"; area?: string } })[]; next_cursor: string | null; count: number } = {
  mode: "latest", results: [{ ...publishedThesis, reason: { kind: "latest" } }], next_cursor: null, count: 1,
};

const page = <T,>(results: T[], count = results.length) =>
  Promise.resolve({ data: { results, count } });

const feedPage = (data: Awaited<ReturnType<typeof recordsApi.forYou>>["data"]) =>
  Promise.resolve({ data } as Awaited<ReturnType<typeof recordsApi.forYou>>);

vi.mock("@/api/records", () => ({
  recordsApi: {
    list: vi.fn(() => page(listed, total ?? listed.length)),
    forYou: vi.fn(() => Promise.resolve({ data: recommended })),
    interests: vi.fn(() => Promise.resolve({ data: { classifications: [], psced: [] } })),
    updateInterests: vi.fn((body: { classification_ids: number[]; psced_ids: number[] }) => Promise.resolve({ data: {
      classifications: body.classification_ids.map((id) => ({ id, name: "Applied Research" })),
      psced: body.psced_ids.map((id) => ({ id, name: "Engineering" })),
    } })),
    notInterested: vi.fn(() => Promise.resolve({ data: undefined })),
    undoNotInterested: vi.fn(() => Promise.resolve({ data: undefined })),
    resetInterests: vi.fn(() => Promise.resolve({ data: { classifications: [], psced: [] } })),
    facets: vi.fn(() => Promise.resolve({ data: { years: [2026, 2009] } })),
    classifications: vi.fn(() => page([{ id: 7, name: "Applied Research" }])),
    pscedList: vi.fn(() => page([{ id: 3, name: "Engineering" }])),
    recordTypes: vi.fn(() =>
      page([
        { id: 1, name: "Thesis/Research" },
        { id: 2, name: "Project" },
        { id: 3, name: "Proposal" },
      ]),
    ),
  },
}));

vi.mock("@/api/accounts", () => ({
  accountsApi: { colleges: vi.fn(() => page([{ id: 4, name: "College of Engineering" }])) },
}));

vi.mock("@/api/notifications", () => ({
  notificationsApi: {
    list: vi.fn(() => page([])),
    unreadCount: vi.fn(() => Promise.resolve({ data: { count: 0 } })),
    markRead: vi.fn(),
    markAllRead: vi.fn(),
  },
}));

function signInAs(roleName: string) {
  useAuthStore.setState({
    user: { id: 9, email: "reader@cit.edu", role_name: roleName } as unknown as User,
    isAuthenticated: true,
    authReady: true,
  });
}

/** Shows where the router is, so a test can see the Publish dialog's URL. */
function LocationProbe() {
  const { search } = useLocation();
  return <output aria-label="Current query">{search}</output>;
}

function renderDiscover(route = "/") {
  return renderScreen(
    <>
      <DiscoverPage />
      <LocationProbe />
    </>,
    { route },
  );
}

/** The params of the most recent list request. */
function lastListParams(): Record<string, unknown> {
  const calls = vi.mocked(recordsApi.list).mock.calls;
  return (calls[calls.length - 1]?.[0] ?? {}) as Record<string, unknown>;
}

async function filterSheet() {
  const open = screen.queryByRole("dialog", { name: "Filters" });
  if (open) return open;
  await userEvent.click(screen.getByRole("button", { name: /^Filters/ }));
  return screen.findByRole("dialog", { name: "Filters" });
}

async function choose(control: RegExp, option: RegExp, scope?: HTMLElement) {
  scope ??= await filterSheet();
  await userEvent.click(within(scope).getByRole("button", { name: control }));
  const list = await screen.findByRole("listbox");
  await userEvent.click(within(list).getByRole("option", { name: option }));
}

beforeEach(() => {
  vi.clearAllMocks();
  sessionStorage.clear();
  localStorage.clear();
  listed = [publishedThesis];
  total = null;
  recommended = { mode: "latest", results: [{ ...publishedThesis, reason: { kind: "latest" } }], next_cursor: null, count: 1 };
  signInAs("Student");
});

describe("the page head", () => {
  it("is titled Discover, and shows an author a Publish action that opens the dialog", async () => {
    const { container } = renderDiscover();

    expect(screen.getByRole("heading", { level: 1, name: "Discover" })).toBeInTheDocument();
    await screen.findByText(publishedThesis.title);

    await userEvent.click(screen.getByRole("button", { name: "Publish" }));
    expect(screen.getByRole("status", { name: "Current query" })).toHaveTextContent("publish=new");

    await expectNoBlockingA11yViolations(container);
  });

  // IR-554: the search box's debounce timer, armed on load and on every
  // keystroke, used to write back the URL it saw when armed -- so a Publish
  // click inside its 300ms was erased when it fired.
  it("keeps the Publish dialog open when the search debounce fires after the click", async () => {
    renderDiscover();

    await userEvent.click(screen.getByRole("button", { name: "Publish" }));
    await new Promise((resolve) => setTimeout(resolve, 400));

    expect(screen.getByRole("status", { name: "Current query" })).toHaveTextContent("publish=new");
  });

  it("keeps both a just-typed search and the Publish dialog in the URL", async () => {
    renderDiscover();

    await userEvent.type(screen.getByRole("textbox", { name: "Search records" }), "rainfall");
    await userEvent.click(screen.getByRole("button", { name: "Publish" }));
    await new Promise((resolve) => setTimeout(resolve, 400));

    const query = screen.getByRole("status", { name: "Current query" });
    expect(query).toHaveTextContent("publish=new");
    expect(query).toHaveTextContent("q=rainfall");
  });

  it("shows an Adviser the Publish action too, because an Adviser authors", async () => {
    signInAs("Adviser");
    renderDiscover();
    expect(await screen.findByRole("button", { name: "Publish" })).toBeInTheDocument();
  });

  it("shows an office reviewer no Publish action", async () => {
    signInAs("RDCO");
    renderDiscover();
    await screen.findByText(publishedThesis.title);
    expect(screen.queryByRole("button", { name: "Publish" })).not.toBeInTheDocument();
  });
});

describe("browsing", () => {
  it("offers For you, Latest, and Trending, opening on the latest catalogue", async () => {
    renderDiscover();
    await screen.findByText(publishedThesis.title);

    expect(screen.getByRole("button", { name: "For you" })).toHaveAttribute("aria-pressed", "false");
    expect(screen.getByRole("button", { name: "Latest" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "Trending" })).toHaveAttribute("aria-pressed", "false");
    expect(lastListParams()).toMatchObject({ ordering: "-created_at" });
  });

  it("shows most viewed research in Trending and retains catalogue filters", async () => {
    renderDiscover("/?type=2");
    await screen.findByText(publishedThesis.title);
    await userEvent.click(screen.getByRole("button", { name: "Trending" }));
    await waitFor(() => expect(lastListParams()).toMatchObject({ ordering: "-access_count", record_type: "2" }));
    expect(screen.getByRole("button", { name: "Trending" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("status", { name: "Current query" })).toHaveTextContent("feed=trending");
    await userEvent.click(screen.getByRole("button", { name: "Latest" }));
    await waitFor(() => expect(lastListParams()).toMatchObject({ ordering: "-created_at", record_type: "2" }));
  });

  it("defaults to one column and cycles through two and three", async () => {
    renderDiscover();
    const card = await screen.findByRole("article", { name: publishedThesis.title });
    expect(screen.getByRole("button", { name: "1 column; switch to 2" })).toBeInTheDocument();
    expect(card.parentElement).toHaveClass("grid-cols-1");
    expect(card.parentElement).not.toHaveClass("md:grid-cols-2");
    const preview = within(card).getByRole("complementary", { name: "Manuscript and abstract preview" });
    expect(preview).toHaveTextContent("From the abstract");
    expect(preview).toHaveTextContent("An abstract.");

    await userEvent.click(screen.getByRole("button", { name: "1 column; switch to 2" }));
    expect(card.parentElement).toHaveClass("md:grid-cols-2");
    expect(localStorage.getItem("iris.discover.columns")).toBe("2");
    expect(within(card).queryByRole("complementary", { name: "Manuscript and abstract preview" })).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "2 columns; switch to 3" }));
    expect(card.parentElement).toHaveClass("xl:grid-cols-3");

    await userEvent.click(screen.getByRole("button", { name: "3 columns; switch to 1" }));
    expect(card.parentElement).not.toHaveClass("md:grid-cols-2");
  });

  it("keeps filters across feeds, applies them to recommendations, and hides recommendation sorting", async () => {
    renderDiscover("/?type=1&college=4&year=2026");
    await screen.findByText(publishedThesis.title);
    await userEvent.click(screen.getByRole("button", { name: "For you" }));
    await waitFor(() => expect(recordsApi.forYou).toHaveBeenLastCalledWith(undefined, expect.objectContaining({
      record_type: "1", college: "4", year_from: "2026", year_to: "2026",
    })));
    const forYouFilters = await filterSheet();
    expect(screen.queryByRole("button", { name: /Sort:/ })).not.toBeInTheDocument();
    await choose(/^Year/, /^2009$/, forYouFilters);
    await waitFor(() => expect(recordsApi.forYou).toHaveBeenLastCalledWith(undefined, expect.objectContaining({ year_from: "2009", year_to: "2009" })));
    expect(screen.getByRole("button", { name: "For you" })).toHaveAttribute("aria-pressed", "true");
    await userEvent.click(screen.getByRole("button", { name: "Latest" }));
    await waitFor(() => expect(lastListParams()).toMatchObject({ record_type: "1", college: "4", year_from: "2009" }));
    expect(within(await filterSheet()).getByRole("button", { name: /^Sort/ })).toBeInTheDocument();
  });

  it("offers clearing active For you filters when they match no research", async () => {
    recommended = { mode: "for_you", results: [], next_cursor: null, count: 0 };
    renderDiscover("/?feed=for_you&year=2009");
    expect(await screen.findByRole("heading", { name: "No research matches these filters" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Clear filters" }));
    await waitFor(() => expect(recordsApi.forYou).toHaveBeenLastCalledWith(undefined, { ordering: "-created_at" }));
    expect(screen.getByRole("button", { name: "For you" })).toHaveAttribute("aria-pressed", "true");
  });

  it("offers personalized results with the API explanation", async () => {
    recommended = { mode: "for_you", results: [{ ...publishedThesis, reason: { kind: "selected_area", area: "Applied Research" } }], next_cursor: null, count: 1 };
    renderDiscover();
    await screen.findByText(publishedThesis.title);
    await userEvent.click(screen.getByRole("button", { name: "For you" }));
    expect(await screen.findByText("Because you chose Applied Research")).toBeInTheDocument();
    expect(vi.mocked(recordsApi.forYou)).toHaveBeenCalled();

  });

  it("keeps a direct For you link selected after the search debounce", async () => {
    renderDiscover("/?feed=for_you");
    await screen.findByText(publishedThesis.title);
    await new Promise((resolve) => setTimeout(resolve, 400));

    expect(screen.getByRole("button", { name: "For you" })).toHaveAttribute("aria-pressed", "true");
    expect(recordsApi.forYou).toHaveBeenCalledTimes(1);
  });

  it("truthfully explains that For you is showing Latest until Areas are chosen", async () => {
    renderDiscover();
    await screen.findByText(publishedThesis.title);
    await userEvent.click(screen.getByRole("button", { name: "For you" }));
    expect(await screen.findByText(/Choose an Area to get recommendations/)).toBeInTheDocument();
    expect(await screen.findByText("Latest research")).toBeInTheDocument();
  });

  it("saves optional classification and PSCED Areas, then opens For you", async () => {
    renderDiscover();
    await screen.findByText(publishedThesis.title);
    await userEvent.click(screen.getByRole("button", { name: "Choose Areas" }));
    const dialog = await screen.findByRole("dialog");
    await userEvent.click(within(dialog).getByLabelText("Applied Research"));
    await userEvent.click(within(dialog).getByLabelText("Engineering"));
    await userEvent.click(within(dialog).getByRole("button", { name: "Save Areas" }));
    await waitFor(() => expect(recordsApi.updateInterests).toHaveBeenCalledWith({ classification_ids: [7], psced_ids: [3] }));
    expect(await screen.findByRole("button", { name: "For you" })).toHaveAttribute("aria-pressed", "true");
  });

  it("loads another For you page with the cursor", async () => {
    recommended = { mode: "for_you", results: [{ ...publishedThesis, reason: { kind: "selected_area", area: "Applied Research" } }], next_cursor: "next", count: 2 };
    vi.mocked(recordsApi.forYou).mockImplementationOnce(() => feedPage(recommended))
      .mockImplementationOnce(() => feedPage({ ...recommended, results: [{ ...publishedThesis, id: 2, title: "Next result", reason: { kind: "selected_area", area: "Applied Research" } }], next_cursor: null }));
    renderDiscover("/?feed=for_you");
    await screen.findByText(publishedThesis.title);
    await userEvent.click(screen.getByRole("button", { name: /Load more/ }));
    expect(await screen.findByText("Next result")).toBeInTheDocument();
    expect(recordsApi.forYou).toHaveBeenLastCalledWith("next", { ordering: "-created_at" });
  });

  it("refreshes the personalized list when its cursor has gone stale", async () => {
    recommended = { mode: "for_you", results: [{ ...publishedThesis, reason: { kind: "selected_area", area: "Applied Research" } }], next_cursor: "stale", count: 2 };
    vi.mocked(recordsApi.forYou).mockImplementationOnce(() => feedPage(recommended))
      .mockImplementationOnce(() => Promise.reject({ response: { status: 409, data: { code: "stale_cursor" } } }))
      .mockImplementationOnce(() => feedPage({ ...recommended, results: [{ ...publishedThesis, reason: { kind: "selected_area", area: "Applied Research" } }], next_cursor: null, count: 1 }));
    renderDiscover("/?feed=for_you");
    await screen.findByText(publishedThesis.title);
    await userEvent.click(screen.getByRole("button", { name: /Load more/ }));
    await waitFor(() => expect(recordsApi.forYou).toHaveBeenCalledTimes(3));
    expect(await screen.findByText(/recommendation list changed/)).toBeInTheDocument();
  });

  it("shows no tabs while Research is the only content, so there is no empty Proposals tab", async () => {
    renderDiscover();
    await screen.findByText(publishedThesis.title);
    expect(screen.queryByRole("tablist")).not.toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: /proposals/i })).not.toBeInTheDocument();
  });

  it("sorts by most viewed through ordering, and back to newest", async () => {
    renderDiscover();
    await screen.findByText(publishedThesis.title);

    const sheet = await filterSheet();
    await userEvent.click(within(sheet).getByRole("button", { name: /^sort/i }));
    await userEvent.click(within(await screen.findByRole("listbox")).getByRole("option", { name: "Most viewed" }));
    await waitFor(() => expect(lastListParams()).toMatchObject({ ordering: "-access_count" }));

    await userEvent.click(within(sheet).getByRole("button", { name: /^sort/i }));
    await userEvent.click(within(await screen.findByRole("listbox")).getByRole("option", { name: "Newest" }));
    await waitFor(() => expect(lastListParams()).toMatchObject({ ordering: "-created_at" }));
  });

  it("shows each result's type, title, authors, year and IP, and lets a reader cite it", async () => {
    listed = [listItem({ id: 5, title: "Rice Husk Insulation Panels", is_ip: true, ip_type: "patent" })];
    localStorage.setItem("iris.discover.columns", "2");
    renderDiscover();

    const card = await screen.findByRole("article", { name: "Rice Husk Insulation Panels" });
    expect(within(card).getByText(/thesis\/research/i)).toBeInTheDocument();
    expect(within(card).getByText("Mateo Villanueva")).toBeInTheDocument();
    expect(within(card).getByText(/2026/)).toBeInTheDocument();
    expect(within(card).getByText("Patent")).toBeInTheDocument();
    expect(within(card).getByRole("link", { name: "Rice Husk Insulation Panels" })).toHaveAttribute(
      "href",
      "/records/5",
    );

    await userEvent.click(within(card).getByRole("button", { name: "Cite this paper" }));
    expect(await screen.findByRole("dialog")).toBeInTheDocument();
  });

  it("states missing authors and external origin without claiming institutional authorship", async () => {
    listed = [listItem({ title: "An imported reference", authors: [], origin: "imported_reference", publication_year: null })];
    localStorage.setItem("iris.discover.columns", "2");
    renderDiscover();
    const card = await screen.findByRole("article", { name: "An imported reference" });
    expect(within(card).getByText("Authors not recorded")).toHaveClass("italic", "text-stone-500");
    expect(within(card).getByText("Imported reference")).toBeInTheDocument();
    expect(within(card).queryByText("Institutional Author")).not.toBeInTheDocument();
  });

  it("shows verified imported author metadata and publication year", async () => {
    listed = [listItem({ ...importedReference, year_accomplished: 2020 })];
    localStorage.setItem("iris.discover.columns", "2");
    renderDiscover();
    const card = await screen.findByRole("article", { name: importedReference.title });
    expect(within(card).getByText(/Ashish Vaswani, Noam Shazeer, Niki Parmar, Jakob Uszkoreit/)).toBeInTheDocument();
    expect(within(card).getByText("Published 2017")).toBeInTheDocument();
    expect(within(card).getByText("Imported reference")).toBeInTheDocument();
  });

  it("loads more results, saying honestly how many remain", async () => {
    listed = [publishedThesis];
    total = 3;
    renderDiscover();

    await userEvent.click(await screen.findByRole("button", { name: "Load more (2 left)" }));
    await waitFor(() => expect(lastListParams()).toMatchObject({ page: 2 }));
  });
});

describe("Not interested, Undo and reset (IR-576)", () => {
  const second = listItem({ id: 2, title: "Rice Husk Insulation Panels" });

  beforeEach(() => {
    recommended = {
      mode: "for_you",
      results: [
        { ...publishedThesis, reason: { kind: "selected_area", area: "Applied Research" } },
        { ...second, reason: { kind: "latest" } },
      ],
      next_cursor: null,
      count: 2,
    };
    // One column draws each card's actions twice (phone and wide footers).
    localStorage.setItem("iris.discover.columns", "2");
  });

  /** Everything this browser keeps for the reader: saves, folders and stars live here. */
  const browserLibrary = () => JSON.stringify(Object.entries({ ...localStorage }).sort());

  it("removes a recommendation at once and offers Undo, which restores it in a fresh feed", async () => {
    renderDiscover("/?feed=for_you");
    const card = await screen.findByRole("article", { name: publishedThesis.title });

    await userEvent.click(within(card).getByRole("button", { name: "Not interested" }));

    expect(screen.queryByRole("article", { name: publishedThesis.title })).not.toBeInTheDocument();
    expect(screen.getByRole("article", { name: second.title })).toBeInTheDocument();
    expect(recordsApi.notInterested).toHaveBeenCalledWith(publishedThesis.id);
    expect(await screen.findByText(/won.t be recommended/)).toBeInTheDocument();
    expect(recordsApi.forYou).toHaveBeenCalledTimes(1);

    await userEvent.click(screen.getByRole("button", { name: "Undo" }));

    await waitFor(() => expect(recordsApi.undoNotInterested).toHaveBeenCalledWith(publishedThesis.id));
    await waitFor(() => expect(recordsApi.forYou).toHaveBeenCalledTimes(2));
    expect(recordsApi.forYou).toHaveBeenLastCalledWith(undefined, expect.anything());
    expect(await screen.findByRole("article", { name: publishedThesis.title })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Undo" })).not.toBeInTheDocument();
  });

  it("waits for the dismissal to land before Undo, so a fast Undo is not lost", async () => {
    let land!: () => void;
    vi.mocked(recordsApi.notInterested).mockImplementationOnce(
      () => new Promise((resolve) => { land = () => resolve({ data: undefined } as never); }),
    );
    renderDiscover("/?feed=for_you");
    const card = await screen.findByRole("article", { name: publishedThesis.title });
    await userEvent.click(within(card).getByRole("button", { name: "Not interested" }));

    await userEvent.click(screen.getByRole("button", { name: "Undo" }));
    expect(recordsApi.undoNotInterested).not.toHaveBeenCalled();

    land();
    await waitFor(() => expect(recordsApi.undoNotInterested).toHaveBeenCalledWith(publishedThesis.id));
  });

  it("keeps a dismissed card out of a page loaded before the server stored the dismissal", async () => {
    recommended = { ...recommended, next_cursor: "next", count: 3 };
    vi.mocked(recordsApi.notInterested).mockImplementationOnce(() => new Promise(() => {}));
    vi.mocked(recordsApi.forYou)
      .mockImplementationOnce(() => feedPage(recommended))
      .mockImplementationOnce(() => feedPage({
        mode: "for_you", next_cursor: null, count: 3,
        results: [
          { ...publishedThesis, reason: { kind: "latest" } },
          { ...listItem({ id: 3, title: "Third paper" }), reason: { kind: "latest" } },
        ],
      }));
    renderDiscover("/?feed=for_you");
    const card = await screen.findByRole("article", { name: publishedThesis.title });
    await userEvent.click(within(card).getByRole("button", { name: "Not interested" }));

    await userEvent.click(screen.getByRole("button", { name: /Load more/ }));

    expect(await screen.findByRole("article", { name: "Third paper" })).toBeInTheDocument();
    expect(screen.queryByRole("article", { name: publishedThesis.title })).not.toBeInTheDocument();
  });

  it("puts the recommendation back and says so when Not interested fails", async () => {
    vi.mocked(recordsApi.notInterested).mockRejectedValueOnce(new Error("offline"));
    renderDiscover("/?feed=for_you");
    const card = await screen.findByRole("article", { name: publishedThesis.title });

    await userEvent.click(within(card).getByRole("button", { name: "Not interested" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/couldn.t be hidden/i);
    expect(await screen.findByRole("article", { name: publishedThesis.title })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Undo" })).not.toBeInTheDocument();
  });

  it("offers Not interested only on For you, not on Latest", async () => {
    renderDiscover();
    const card = await screen.findByRole("article", { name: publishedThesis.title });
    expect(within(card).queryByRole("button", { name: "Not interested" })).not.toBeInTheDocument();
  });

  it("leaves saves and folders alone when dismissing, and keeps feedback off this browser", async () => {
    renderDiscover("/?feed=for_you");
    const card = await screen.findByRole("article", { name: publishedThesis.title });
    await userEvent.click(within(card).getByRole("button", { name: "Save to collection" }));
    await userEvent.click(within(card).getByRole("button", { name: "Want to read" }));
    await userEvent.click(within(card).getByRole("button", { name: "Star paper" }));
    const saved = browserLibrary();

    await userEvent.click(within(card).getByRole("button", { name: "Not interested" }));

    // The folder and star are untouched, and the feedback went to the account, not storage.
    expect(browserLibrary()).toBe(saved);
    expect(getCollections().find((c) => c.id === "want-to-read")?.recordIds).toEqual([publishedThesis.id]);
    expect(isStarred(publishedThesis.id)).toBe(true);
    expect(recordsApi.notInterested).toHaveBeenCalledWith(publishedThesis.id);
  });

  it("does not count unstarring a paper as Not interested", async () => {
    renderDiscover("/?feed=for_you");
    const card = await screen.findByRole("article", { name: second.title });
    await userEvent.click(within(card).getByRole("button", { name: "Star paper" }));
    await userEvent.click(within(card).getByRole("button", { name: "Starred" }));

    expect(isStarred(second.id)).toBe(false);
    expect(screen.getByRole("article", { name: second.title })).toBeInTheDocument();
    expect(recordsApi.notInterested).not.toHaveBeenCalled();
  });

  it("does not count removing a paper from a folder as Not interested", async () => {
    renderDiscover("/?feed=for_you");
    const card = await screen.findByRole("article", { name: second.title });
    await userEvent.click(within(card).getByRole("button", { name: "Save to collection" }));
    await userEvent.click(within(card).getByRole("button", { name: "Want to read" }));
    expect(getCollections().find((c) => c.id === "want-to-read")?.recordIds).toEqual([second.id]);
    await userEvent.click(within(card).getByRole("button", { name: "Want to read" }));

    expect(getCollections().find((c) => c.id === "want-to-read")?.recordIds).toEqual([]);
    expect(screen.getByRole("article", { name: second.title })).toBeInTheDocument();
    expect(recordsApi.notInterested).not.toHaveBeenCalled();
  });

  it("resets Areas and Not interested after a confirmation, then refreshes For you", async () => {
    vi.mocked(recordsApi.interests).mockResolvedValueOnce({
      data: { classifications: [{ id: 7, name: "Applied Research" }], psced: [] },
    } as unknown as Awaited<ReturnType<typeof recordsApi.interests>>);
    renderDiscover("/?feed=for_you");
    const card = await screen.findByRole("article", { name: publishedThesis.title });
    await userEvent.click(within(card).getByRole("button", { name: "Save to collection" }));
    await userEvent.click(within(card).getByRole("button", { name: "Want to read" }));
    const saved = browserLibrary();
    await userEvent.click(await screen.findByRole("button", { name: "Edit Areas" }));
    const dialog = await screen.findByRole("dialog");

    await userEvent.click(within(dialog).getByRole("button", { name: "Reset my interests" }));
    expect(recordsApi.resetInterests).not.toHaveBeenCalled();
    expect(within(dialog).getByText(/saved papers and folders stay/i)).toBeInTheDocument();
    await userEvent.click(within(dialog).getByRole("button", { name: "Reset" }));

    await waitFor(() => expect(recordsApi.resetInterests).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    await waitFor(() => expect(recordsApi.forYou).toHaveBeenCalledTimes(2));
    expect(await screen.findByText(/interests were reset/i)).toBeInTheDocument();
    expect(browserLibrary()).toBe(saved);
    expect(await screen.findByRole("button", { name: "Choose Areas" })).toBeInTheDocument();
  });

  it("keeps the dialog open with a message when the reset fails", async () => {
    vi.mocked(recordsApi.resetInterests).mockRejectedValueOnce(new Error("offline"));
    renderDiscover("/?feed=for_you");
    await screen.findByRole("article", { name: publishedThesis.title });
    await userEvent.click(screen.getByRole("button", { name: "Choose Areas" }));
    const dialog = await screen.findByRole("dialog");

    await userEvent.click(within(dialog).getByRole("button", { name: "Reset my interests" }));
    await userEvent.click(within(dialog).getByRole("button", { name: "Reset" }));

    expect(await within(dialog).findByRole("alert")).toHaveTextContent(/couldn.t be reset/i);
    expect(recordsApi.forYou).toHaveBeenCalledTimes(1);
  });
});

describe("filtering", () => {
  it("maps each filter to its query param and counts active choices in one control", async () => {
    renderDiscover();
    await screen.findByText(publishedThesis.title);

    await choose(/^type/i, /^project$/i);
    await waitFor(() => expect(lastListParams()).toMatchObject({ record_type: "2" }));

    await choose(/^college/i, /college of engineering/i);
    await userEvent.keyboard("{Escape}");
    await waitFor(() => expect(lastListParams()).toMatchObject({ college: "4" }));

    await choose(/^classification/i, /applied research/i);
    await userEvent.keyboard("{Escape}");
    await waitFor(() => expect(lastListParams()).toMatchObject({ classification: "7" }));

    await choose(/^ip & patents/i, /^has ip$/i);
    await waitFor(() => expect(lastListParams()).toMatchObject({ is_ip: true }));

    expect(screen.getByRole("button", { name: "Filters, 4 active" })).toBeInTheDocument();
    await choose(/^type/i, /^any type$/i);
    await waitFor(() => expect(lastListParams()).not.toHaveProperty("record_type"));
    expect(lastListParams()).toMatchObject({ college: "4", classification: "7", is_ip: true });
  });

  it("filters by one IP type through ip_type", async () => {
    renderDiscover();
    await screen.findByText(publishedThesis.title);

    await choose(/^ip & patents/i, /^patent$/i);
    await waitFor(() => expect(lastListParams()).toMatchObject({ ip_type: "patent" }));
    expect(lastListParams()).not.toHaveProperty("is_ip");
  });

  it("filters by year through year_from and year_to", async () => {
    renderDiscover();
    await screen.findByText(publishedThesis.title);

    await choose(/^year/i, /^2026$/);
    await waitFor(() => expect(lastListParams()).toMatchObject({ year_from: "2026", year_to: "2026" }));
  });

  it("does not offer a Proposal type, because Proposals are not in the catalogue", async () => {
    renderDiscover();
    await screen.findByText(publishedThesis.title);

    await userEvent.click(within(await filterSheet()).getByRole("button", { name: /^type/i }));
    const options = await screen.findByRole("listbox");
    expect(within(options).getByRole("option", { name: /thesis\/research/i })).toBeInTheDocument();
    expect(within(options).queryByRole("option", { name: /proposal/i })).not.toBeInTheDocument();
  });

  it("clears every filter at once", async () => {
    renderDiscover();
    await screen.findByText(publishedThesis.title);
    await choose(/^type/i, /^project$/i);

    await userEvent.click(within(await filterSheet()).getByRole("button", { name: "Clear all" }));
    await waitFor(() => expect(lastListParams()).not.toHaveProperty("record_type"));
    expect(screen.getByRole("button", { name: "Filters" })).toBeInTheDocument();
  });

  it("opens every filter in one compact panel", async () => {
    const { container } = renderDiscover();
    await screen.findByText(publishedThesis.title);

    const sheet = await filterSheet();

    expect(screen.getByRole("button", { name: "Filters" })).toHaveAttribute("aria-expanded", "true");
    expect(within(sheet).getByRole("button", { name: "Close filters" })).toBeInTheDocument();

    await choose(/^type/i, /^project$/i, sheet);
    await waitFor(() => expect(lastListParams()).toMatchObject({ record_type: "2" }));
    await expectNoBlockingA11yViolations(container);

    await userEvent.click(within(sheet).getByRole("button", { name: /^show/i }));
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "Filters" })).not.toBeInTheDocument());
  });
});

describe("states", () => {
  it("says nothing has been published yet, and offers an author Publish", async () => {
    listed = [];
    const { container } = renderDiscover();

    expect(await screen.findByRole("heading", { name: "Nothing has been published yet." })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Clear filters" })).not.toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "Publish" }).length).toBeGreaterThanOrEqual(2);
    await expectNoBlockingA11yViolations(container);
  });

  it("offers no Publish in an empty catalogue to someone who cannot publish", async () => {
    signInAs("RDCO");
    listed = [];
    renderDiscover();

    await screen.findByRole("heading", { name: "Nothing has been published yet." });
    expect(screen.queryByRole("button", { name: "Publish" })).not.toBeInTheDocument();
  });

  it("says no research matches, and clears the filters", async () => {
    listed = [];
    renderDiscover("/?q=flood");

    expect(await screen.findByRole("heading", { name: "No research matches these filters" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Clear filters" }));

    expect(await screen.findByRole("heading", { name: "Nothing has been published yet." })).toBeInTheDocument();
    expect(lastListParams()).not.toHaveProperty("search");
  });

  it("announces a feed that failed to load, and tries again", async () => {
    vi.mocked(recordsApi.list).mockImplementationOnce(() => Promise.reject(new Error("down")));
    renderDiscover();

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("We couldn't load research");

    await userEvent.click(within(alert).getByRole("button", { name: "Try again" }));
    expect(await screen.findByText(publishedThesis.title)).toBeInTheDocument();
  });

  it("does not present an approved Proposal as ongoing research", async () => {
    listed = [publishedThesis, approvedProposal];
    renderDiscover();

    await screen.findByText(approvedProposal.title);
    expect(screen.queryByText(/research ongoing/i)).not.toBeInTheDocument();
  });
});

/* ── IR-560: the query survives Back, reload and Load more ─────────────── */

/** A Record page that only offers Back, so a test can leave Discover and return. */
function RecordStub() {
  const navigate = useNavigate();
  return (
    <button type="button" onClick={() => navigate(-1)}>
      Back to Discover
    </button>
  );
}

function renderDiscoverWithRecords(route = "/") {
  return renderScreen(
    <Routes>
      <Route
        path="/"
        element={
          <>
            <DiscoverPage />
            <LocationProbe />
          </>
        }
      />
      <Route path="/records/:id" element={<RecordStub />} />
    </Routes>,
    { route },
  );
}

/** The list mock, typed loosely: these fixtures return `{ data }`, not a full response. */
const listMock = () =>
  vi.mocked(recordsApi.list) as unknown as MockInstance<(params?: Record<string, unknown>) => Promise<unknown>>;

const secondPagePaper = listItem({ id: 3, title: "Bamboo Truss Load Testing" });

/** page 1 is `listed`; page 2 is the second-page paper. */
function twoPages() {
  total = 2;
  listMock().mockImplementation((params) => {
    const { page: n, page_size: size } = (params ?? {}) as { page?: number; page_size?: number };
    if (n === 2) return page([secondPagePaper], 2);
    // A restored depth asks for both pages at once.
    return page(size && size > 12 ? [publishedThesis, secondPagePaper] : [publishedThesis], 2);
  });
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((r) => {
    resolve = r;
  });
  return { promise, resolve };
}

describe("continuity", () => {
  afterEach(() => {
    listMock().mockImplementation(() => page(listed, total ?? listed.length));
  });

  it("restores the search, filters and sort from the URL", async () => {
    renderDiscover("/?q=rain&type=2&year=2019&sort=viewed");

    await waitFor(() =>
      expect(lastListParams()).toMatchObject({
        search: "rain",
        record_type: "2",
        year_from: "2019",
        year_to: "2019",
        ordering: "-access_count",
      }),
    );
    expect(screen.getByRole("textbox", { name: "Search records" })).toHaveValue("rain");
    expect(screen.getByRole("button", { name: "Filters, 2 active" })).toBeInTheDocument();
  });

  it("writes each filter and sort change into the URL", async () => {
    renderDiscover();
    await screen.findByText(publishedThesis.title);

    await choose(/^type/i, /^project$/i);
    await userEvent.click(within(await filterSheet()).getByRole("button", { name: /^sort/i }));
    await userEvent.click(within(await screen.findByRole("listbox")).getByRole("option", { name: "Most viewed" }));

    const query = screen.getByRole("status", { name: "Current query" });
    await waitFor(() => expect(query).toHaveTextContent("type=2"));
    expect(query).toHaveTextContent("sort=viewed");
  });

  it("falls back to safe defaults for values it does not recognise, and corrects the URL", async () => {
    renderDiscover("/?sort=bogus&year=19&type=thesis&college=4,x");

    await waitFor(() => expect(lastListParams()).toMatchObject({ ordering: "-created_at", college: "4" }));
    expect(lastListParams()).not.toHaveProperty("year_from");
    expect(lastListParams()).not.toHaveProperty("record_type");
    await waitFor(() =>
      expect(screen.getByRole("status", { name: "Current query" })).toHaveTextContent(/^\?college=4$/),
    );
  });

  it("brings back the query and every loaded result after opening a Record and going Back", async () => {
    twoPages();
    renderDiscoverWithRecords("/?type=2");

    await userEvent.click(await screen.findByRole("button", { name: "Load more (1 left)" }));
    await screen.findByText(secondPagePaper.title);

    await userEvent.click(screen.getByRole("link", { name: publishedThesis.title }));
    await userEvent.click(await screen.findByRole("button", { name: "Back to Discover" }));

    expect(await screen.findByText(secondPagePaper.title)).toBeInTheDocument();
    expect(screen.getByText(publishedThesis.title)).toBeInTheDocument();
    expect(lastListParams()).toMatchObject({ record_type: "2", page: 1, page_size: 24 });
    expect(screen.queryByRole("button", { name: /load more/i })).not.toBeInTheDocument();
  });

  it("never appends an older page after the filters change", async () => {
    total = 2;
    const oldPageTwo = deferred<{ data: { results: RecordListItem[]; count: number } }>();
    renderDiscover();
    await screen.findByText(publishedThesis.title);

    listMock().mockImplementationOnce(() => oldPageTwo.promise);
    await userEvent.click(screen.getByRole("button", { name: "Load more (1 left)" }));

    const projectPaper = listItem({ id: 8, title: "Solar Dryer for Copra" });
    listed = [projectPaper];
    total = 1;
    await choose(/^type/i, /^project$/i);
    await screen.findByText(projectPaper.title);

    oldPageTwo.resolve({ data: { results: [listItem({ id: 9, title: "Stale Second Page" })], count: 2 } });
    await new Promise((resolve) => setTimeout(resolve, 0));

    expect(screen.queryByText("Stale Second Page")).not.toBeInTheDocument();
    expect(screen.getByText(projectPaper.title)).toBeInTheDocument();
  });

  it("offers every year in the catalogue, not only the years of the loaded cards", async () => {
    renderDiscover();
    await screen.findByText(publishedThesis.title);

    await userEvent.click(within(await filterSheet()).getByRole("button", { name: /^year/i }));
    const options = await screen.findByRole("listbox");
    expect(within(options).getByRole("option", { name: "2009" })).toBeInTheDocument();
  });

  it("recovers the filter choices on their own when they fail to load", async () => {
    vi.mocked(recordsApi.facets).mockImplementationOnce(() => Promise.reject(new Error("down")));
    renderDiscover();

    // The results still load: only the filter choices failed.
    expect(await screen.findByText(publishedThesis.title)).toBeInTheDocument();
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Some filters couldn't load");

    await userEvent.click(within(alert).getByRole("button", { name: "Retry filters" }));
    await waitFor(() => expect(screen.queryByRole("alert")).not.toBeInTheDocument());
    expect(recordsApi.facets).toHaveBeenCalledTimes(2);
  });

  it("recovers a failed Load more on its own, keeping the first page", async () => {
    total = 2;
    renderDiscover();
    await screen.findByText(publishedThesis.title);

    listMock().mockImplementationOnce(() => Promise.reject(new Error("down")));
    await userEvent.click(screen.getByRole("button", { name: "Load more (1 left)" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("More results didn't load.");
    expect(screen.getByText(publishedThesis.title)).toBeInTheDocument();

    listMock().mockImplementationOnce(() => page([secondPagePaper], 2));
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByText(secondPagePaper.title)).toBeInTheDocument();
  });
});

describe("continuity: the search box follows the URL", () => {
  /** What the sidebar's Discover link does: go to "/" while Discover is open. */
  function DiscoverLink() {
    const navigate = useNavigate();
    return (
      <button type="button" onClick={() => navigate("/")}>
        Discover home
      </button>
    );
  }

  it("empties the search box when the URL drops the search", async () => {
    renderScreen(
      <>
        <DiscoverPage />
        <DiscoverLink />
      </>,
      { route: "/?q=robotics" },
    );
    const box = screen.getByRole("textbox", { name: "Search records" });
    expect(box).toHaveValue("robotics");

    await userEvent.click(screen.getByRole("button", { name: "Discover home" }));

    await waitFor(() => expect(box).toHaveValue(""));
    await new Promise((resolve) => setTimeout(resolve, 400));
    expect(lastListParams()).not.toHaveProperty("search");
  });
});
