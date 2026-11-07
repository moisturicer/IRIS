/**
 * Discover's "My feeds" menu (IR-577): a reader's private saved feeds, opened,
 * saved from the filters on screen, renamed and deleted.
 *
 * Every query goes through the accessible tree, by role and accessible name.
 * The API is mocked at its own boundary; the store is the real one.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";

import { libraryApi, type SavedFeed } from "@/api/library";
import { useAuthStore } from "@/store/auth.store";
import { useFeedsStore } from "@/store/feeds.store";
import { expectNoBlockingA11yViolations } from "@/test/axe";
import { renderScreen, screen, userEvent, waitFor, within } from "@/test/render";
import type { User } from "@/types/auth";

import { parseDiscoverQuery } from "./discoverQuery";
import { MyFeeds } from "./MyFeeds";

vi.mock("@/api/library", () => ({
  libraryApi: { feeds: vi.fn(), createFeed: vi.fn(), updateFeed: vi.fn(), deleteFeed: vi.fn() },
}));

const feed = (id: number, name: string, extra: Partial<SavedFeed> = {}): SavedFeed => ({
  id, name, query: { q: "flood" }, stale: {},
  created_at: "2026-11-07T00:00:00Z", updated_at: "2026-11-07T00:00:00Z", ...extra,
});
const answer = <T,>(data: T) => ({ data }) as never;
const refused = (data: unknown) => Object.assign(new Error("refused"), { response: { status: 400, data } });
const query = (search: string) => parseDiscoverQuery(new URLSearchParams(search));

const OPTIONS = {
  classifications: [{ value: "4", label: "Civil Engineering" }, { value: "7", label: "Environmental Science" }],
  colleges: [{ value: "5", label: "College of Engineering" }],
  recordTypes: [{ value: "2", label: "Thesis" }],
};

function show(props: Partial<React.ComponentProps<typeof MyFeeds>> = {}) {
  const onOpen = vi.fn();
  const onDeleted = vi.fn();
  const view = renderScreen(
    <MyFeeds
      query={query("q=flood&classification=4,7")}
      matchCount={12}
      options={OPTIONS}
      activeFeedId={null}
      onOpen={onOpen}
      onDeleted={onDeleted}
      {...props}
    />,
  );
  return { ...view, onOpen, onDeleted };
}

async function openMenu() {
  await userEvent.click(await screen.findByRole("button", { name: /My feeds/ }));
}

beforeEach(() => {
  vi.clearAllMocks();
  useAuthStore.getState().login({ id: 1, email: "r1@cit.edu", role_name: "Student" } as unknown as User, "a", "r");
  useFeedsStore.setState({ load: "idle", feeds: [], limit: 10, interrupted: false });
  vi.mocked(libraryApi.feeds).mockResolvedValue(answer({ results: [], limit: 10 }));
});

describe("My feeds menu", () => {
  it("says there are no saved feeds yet, and offers to save the filters on screen", async () => {
    show();
    await openMenu();

    expect(await screen.findByText("No saved feeds yet.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Save these filters as a feed/ })).toBeInTheDocument();
  });

  it("lists the reader's feeds and opens the one chosen", async () => {
    vi.mocked(libraryApi.feeds).mockResolvedValue(answer({ results: [feed(1, "Coastal hazards"), feed(2, "Aquaculture")], limit: 10 }));
    const { onOpen } = show();
    await openMenu();

    await userEvent.click(await screen.findByRole("button", { name: "Open Aquaculture" }));

    expect(onOpen).toHaveBeenCalledWith(expect.objectContaining({ id: 2, name: "Aquaculture" }));
  });

  it("marks the open feed and says which feeds need attention", async () => {
    vi.mocked(libraryApi.feeds).mockResolvedValue(answer({
      results: [feed(1, "Coastal hazards"), feed(2, "Old Area", { stale: { classification: [9] } })], limit: 10,
    }));
    show({ activeFeedId: 1 });
    await openMenu();

    expect(await screen.findByRole("button", { name: "Open Coastal hazards" })).toHaveAttribute("aria-current", "true");
    expect(within(screen.getByRole("listitem", { name: "Old Area" })).getByText("Needs attention")).toBeInTheDocument();
  });

  it("says the feeds could not load, and tries again on request", async () => {
    vi.mocked(libraryApi.feeds).mockRejectedValueOnce(new Error("offline"));
    show();
    await openMenu();

    expect(await screen.findByRole("alert")).toHaveTextContent(/could not be loaded/i);
    vi.mocked(libraryApi.feeds).mockResolvedValueOnce(answer({ results: [feed(1, "Coastal hazards")], limit: 10 }));
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));

    expect(await screen.findByRole("button", { name: "Open Coastal hazards" })).toBeInTheDocument();
  });

  it("reads the next account's feeds after the account changes", async () => {
    show();
    await waitFor(() => expect(libraryApi.feeds).toHaveBeenCalledTimes(1));

    useAuthStore.getState().login({ id: 2, email: "r2@cit.edu", role_name: "Student" } as unknown as User, "a", "r");

    await waitFor(() => expect(libraryApi.feeds).toHaveBeenCalledTimes(2));
  });

  it("closes on Escape", async () => {
    show();
    await openMenu();
    await screen.findByText("No saved feeds yet.");

    await userEvent.keyboard("{Escape}");

    expect(screen.queryByText("No saved feeds yet.")).not.toBeInTheDocument();
  });

  it("has no blocking accessibility violations, closed or open", async () => {
    const { container } = show();
    await expectNoBlockingA11yViolations(container);
    await openMenu();
    await screen.findByText("No saved feeds yet.");
    await expectNoBlockingA11yViolations(container);
  });
});

describe("saving the filters on screen", () => {
  async function openSaveForm() {
    await openMenu();
    await userEvent.click(await screen.findByRole("button", { name: /Save these filters as a feed/ }));
    return screen.findByRole("dialog");
  }

  it("shows the criteria in words and how many papers match, then saves under the name given", async () => {
    vi.mocked(libraryApi.createFeed).mockResolvedValue(answer(feed(7, "Coastal hazards", { query: { q: "flood", classification: "4,7" } })));
    const { onOpen } = show();
    const dialog = await openSaveForm();

    expect(within(dialog).getByText("Keywords: flood")).toBeInTheDocument();
    expect(within(dialog).getByText("Areas: Civil Engineering, Environmental Science")).toBeInTheDocument();
    expect(within(dialog).getByText(/12 papers match right now/)).toBeInTheDocument();
    expect(within(dialog).getByText(/any one of the Areas.*every other filter/is)).toBeInTheDocument();

    await userEvent.type(within(dialog).getByRole("textbox", { name: /Feed name/ }), "Coastal hazards");
    await userEvent.click(within(dialog).getByRole("button", { name: "Save feed" }));

    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(libraryApi.createFeed).toHaveBeenCalledWith({ name: "Coastal hazards", query: { q: "flood", classification: "4,7" } });
    expect(screen.getByRole("status")).toHaveTextContent("Saved “Coastal hazards”");
    // The page then shows the new feed, which is the visible confirmation.
    expect(onOpen).toHaveBeenCalledWith(expect.objectContaining({ id: 7 }));
  });

  it("saves Trending as most viewed", async () => {
    vi.mocked(libraryApi.createFeed).mockResolvedValue(answer(feed(7, "Popular")));
    show({ query: query("q=flood&feed=trending") });
    const dialog = await openSaveForm();

    await userEvent.type(within(dialog).getByRole("textbox", { name: /Feed name/ }), "Popular");
    await userEvent.click(within(dialog).getByRole("button", { name: "Save feed" }));

    await waitFor(() => expect(libraryApi.createFeed).toHaveBeenCalledWith({ name: "Popular", query: { q: "flood", sort: "viewed" } }));
  });

  it("keeps what was typed and says why when the server refuses", async () => {
    vi.mocked(libraryApi.createFeed).mockRejectedValue(refused({ name: ["You already have a saved feed with that name."] }));
    show();
    const dialog = await openSaveForm();
    await userEvent.type(within(dialog).getByRole("textbox", { name: /Feed name/ }), "Coastal hazards");

    await userEvent.click(within(dialog).getByRole("button", { name: "Save feed" }));

    expect(await within(dialog).findByRole("alert")).toHaveTextContent("You already have a saved feed with that name.");
    expect(within(dialog).getByRole("textbox", { name: /Feed name/ })).toHaveValue("Coastal hazards");
    expect(within(dialog).getByText("Keywords: flood")).toBeInTheDocument();
  });

  it("needs a name before it asks the server", async () => {
    show();
    const dialog = await openSaveForm();

    expect(within(dialog).getByRole("button", { name: "Save feed" })).toBeDisabled();
    expect(libraryApi.createFeed).not.toHaveBeenCalled();
  });

  it("cannot save a feed with no filters, and says so", async () => {
    show({ query: query("") });
    const dialog = await openSaveForm();
    await userEvent.type(within(dialog).getByRole("textbox", { name: /Feed name/ }), "Everything");

    expect(within(dialog).getByText(/Choose at least one filter or keyword/)).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "Save feed" })).toBeDisabled();
  });

  it("is not offered on For you, and says how to save its filters", async () => {
    show({ query: query("classification=4&feed=for_you") });
    await openMenu();

    expect(await screen.findByText(/switch to Latest or Trending/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Save these filters as a feed/ })).not.toBeInTheDocument();
  });

  it("says the account is full instead of offering a save that would be refused", async () => {
    vi.mocked(libraryApi.feeds).mockResolvedValue(answer({
      results: [feed(1, "A"), feed(2, "B")], limit: 2,
    }));
    show();
    await openMenu();

    expect(await screen.findByText("You have 2 saved feeds. Delete one to save another.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Save these filters as a feed/ })).not.toBeInTheDocument();
  });

  it("has no blocking accessibility violations in the save form", async () => {
    const { baseElement } = show();
    await openSaveForm();

    await expectNoBlockingA11yViolations(baseElement);
  });
});

describe("renaming and deleting", () => {
  beforeEach(() => {
    vi.mocked(libraryApi.feeds).mockResolvedValue(answer({ results: [feed(1, "Coastal hazards")], limit: 10 }));
  });

  it("renames a feed without touching its criteria", async () => {
    vi.mocked(libraryApi.updateFeed).mockResolvedValue(answer(feed(1, "Floods")));
    show();
    await openMenu();
    await userEvent.click(await screen.findByRole("button", { name: "Rename Coastal hazards" }));
    const dialog = await screen.findByRole("dialog");
    const input = within(dialog).getByRole("textbox", { name: /Feed name/ });
    expect(input).toHaveValue("Coastal hazards");

    await userEvent.clear(input);
    await userEvent.type(input, "Floods");
    await userEvent.click(within(dialog).getByRole("button", { name: "Save name" }));

    await waitFor(() => expect(libraryApi.updateFeed).toHaveBeenCalledWith(1, { name: "Floods" }));
    // The menu closed when the dialog opened; the new name is there on reopening.
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    await openMenu();
    expect(await screen.findByRole("button", { name: "Open Floods" })).toBeInTheDocument();
  });

  it("shows a refused rename and keeps the old name", async () => {
    vi.mocked(libraryApi.updateFeed).mockRejectedValue(refused({ name: ["You already have a saved feed with that name."] }));
    show();
    await openMenu();
    await userEvent.click(await screen.findByRole("button", { name: "Rename Coastal hazards" }));
    const dialog = await screen.findByRole("dialog");
    await userEvent.type(within(dialog).getByRole("textbox", { name: /Feed name/ }), "2");

    await userEvent.click(within(dialog).getByRole("button", { name: "Save name" }));

    expect(await within(dialog).findByRole("alert")).toHaveTextContent("already have a saved feed");
    expect(useFeedsStore.getState().feeds[0].name).toBe("Coastal hazards");
  });

  it("asks before deleting, says papers are untouched, and tells the page", async () => {
    vi.mocked(libraryApi.deleteFeed).mockResolvedValue(answer(undefined));
    const { onDeleted } = show();
    await openMenu();
    await userEvent.click(await screen.findByRole("button", { name: "Delete Coastal hazards" }));
    const dialog = await screen.findByRole("dialog");

    expect(within(dialog).getByText(/removes the feed only/i)).toBeInTheDocument();
    expect(libraryApi.deleteFeed).not.toHaveBeenCalled();
    await userEvent.click(within(dialog).getByRole("button", { name: "Delete feed" }));

    await waitFor(() => expect(libraryApi.deleteFeed).toHaveBeenCalledWith(1));
    expect(onDeleted).toHaveBeenCalledWith(1);
    await waitFor(() => expect(useFeedsStore.getState().feeds).toEqual([]));
  });

  it("keeps the feed when the delete is cancelled or fails", async () => {
    vi.mocked(libraryApi.deleteFeed).mockRejectedValue(new Error("offline"));
    const { onDeleted } = show();
    await openMenu();
    await userEvent.click(await screen.findByRole("button", { name: "Delete Coastal hazards" }));
    let dialog = await screen.findByRole("dialog");
    await userEvent.click(within(dialog).getByRole("button", { name: "Keep feed" }));
    expect(libraryApi.deleteFeed).not.toHaveBeenCalled();

    await openMenu();
    await userEvent.click(await screen.findByRole("button", { name: "Delete Coastal hazards" }));
    dialog = await screen.findByRole("dialog");
    await userEvent.click(within(dialog).getByRole("button", { name: "Delete feed" }));

    expect(await within(dialog).findByRole("alert")).toHaveTextContent(/still saved/i);
    expect(onDeleted).not.toHaveBeenCalled();
    expect(useFeedsStore.getState().feeds).toHaveLength(1);
  });
});
