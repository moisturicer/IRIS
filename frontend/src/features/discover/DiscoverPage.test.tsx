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
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useLocation } from "react-router-dom";

import { expectNoBlockingA11yViolations } from "@/test/axe";
import { renderScreen, screen, userEvent, waitFor, within } from "@/test/render";
import { recordsApi } from "@/api/records";
import { useAuthStore } from "@/store/auth.store";
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

const page = <T,>(results: T[], count = results.length) =>
  Promise.resolve({ data: { results, count } });

vi.mock("@/api/records", () => ({
  recordsApi: {
    list: vi.fn(() => page(listed, total ?? listed.length)),
    classifications: vi.fn(() => page([{ id: 7, name: "Applied Research" }])),
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

/** The desktop filter row: filters are buttons named by what they filter. */
function filterRow() {
  return screen.getByRole("group", { name: "Filter research" });
}

async function choose(control: RegExp, option: RegExp, scope = filterRow()) {
  await userEvent.click(within(scope).getByRole("button", { name: control }));
  const list = await screen.findByRole("listbox");
  await userEvent.click(within(list).getByRole("option", { name: option }));
}

beforeEach(() => {
  vi.clearAllMocks();
  listed = [publishedThesis];
  total = null;
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
  it("has no saved views, and opens on the newest research", async () => {
    renderDiscover();
    await screen.findByText(publishedThesis.title);

    for (const view of ["For you", "Latest", "Theses"]) {
      expect(screen.queryByRole("tab", { name: view })).not.toBeInTheDocument();
    }
    expect(lastListParams()).toMatchObject({ ordering: "-created_at" });
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

    await userEvent.click(screen.getByRole("button", { name: /^sort/i }));
    await userEvent.click(within(await screen.findByRole("listbox")).getByRole("option", { name: "Most viewed" }));
    await waitFor(() => expect(lastListParams()).toMatchObject({ ordering: "-access_count" }));

    await userEvent.click(screen.getByRole("button", { name: /^sort/i }));
    await userEvent.click(within(await screen.findByRole("listbox")).getByRole("option", { name: "Newest" }));
    await waitFor(() => expect(lastListParams()).toMatchObject({ ordering: "-created_at" }));
  });

  it("shows each result's type, title, authors, year and IP, and lets a reader cite it", async () => {
    listed = [listItem({ id: 5, title: "Rice Husk Insulation Panels", is_ip: true, ip_type: "patent" })];
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

  it("loads more results, saying honestly how many remain", async () => {
    listed = [publishedThesis];
    total = 3;
    renderDiscover();

    await userEvent.click(await screen.findByRole("button", { name: "Load more (2 left)" }));
    await waitFor(() => expect(lastListParams()).toMatchObject({ page: 2 }));
  });
});

describe("filtering", () => {
  it("maps each filter to its query param and shows it as a removable chip", async () => {
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

    const chips = screen.getByRole("list", { name: "Active filters" });
    for (const chip of ["Project", "College of Engineering", "Applied Research", "Has IP"]) {
      expect(within(chips).getByRole("button", { name: `Remove filter: ${chip}` })).toBeInTheDocument();
    }

    await userEvent.click(within(chips).getByRole("button", { name: "Remove filter: Project" }));
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

    await userEvent.click(within(filterRow()).getByRole("button", { name: /^type/i }));
    const options = await screen.findByRole("listbox");
    expect(within(options).getByRole("option", { name: /thesis\/research/i })).toBeInTheDocument();
    expect(within(options).queryByRole("option", { name: /proposal/i })).not.toBeInTheDocument();
  });

  it("clears every filter at once", async () => {
    renderDiscover();
    await screen.findByText(publishedThesis.title);
    await choose(/^type/i, /^project$/i);

    await userEvent.click(await screen.findByRole("button", { name: "Clear all filters" }));
    await waitFor(() => expect(lastListParams()).not.toHaveProperty("record_type"));
    expect(screen.queryByRole("list", { name: "Active filters" })).not.toBeInTheDocument();
  });

  it("opens the filters in a sheet that holds focus, for a phone", async () => {
    const { container } = renderDiscover();
    await screen.findByText(publishedThesis.title);

    await userEvent.click(screen.getByRole("button", { name: "Filters" }));
    const sheet = await screen.findByRole("dialog", { name: "Filters" });

    // The sheet is modal and takes focus as it opens. Tab cycling itself is
    // `Modal`'s trap, which jsdom cannot drive: with no layout,
    // `tabbableWithin` finds nothing to cycle through. It is verified in a
    // browser instead (see the PR).
    expect(sheet).toHaveAttribute("aria-modal", "true");
    expect(sheet).toContainElement(document.activeElement as HTMLElement);

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
