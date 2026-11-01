import { beforeEach, describe, expect, it, vi } from "vitest";
import { libraryApi, type ReadingStatus, type SavedRecordEntry } from "@/api/library";
import { recordsApi } from "@/api/records";
import { useAuthStore } from "@/store/auth.store";
import { useLibraryStore } from "@/store/library.store";
import type { User } from "@/types/auth";
import { expectNoBlockingA11yViolations } from "@/test/axe";
import { renderScreen, screen, userEvent, waitFor, within } from "@/test/render";
import type { MyResearchItem, RecordListItem } from "@/types/records";
import MyLibraryPage from "./MyLibraryPage";

vi.mock("@/api/records", () => ({
  recordsApi: {
    mine: vi.fn(),
    list: vi.fn().mockResolvedValue({ data: { results: [] } }),
  },
}));

vi.mock("@/api/library", () => ({
  libraryApi: {
    saves: vi.fn(),
    save: vi.fn(),
    unsave: vi.fn(),
  },
}));

type SavesResponse = Awaited<ReturnType<typeof libraryApi.saves>>;

const paper = (id: number, title: string): RecordListItem => ({
  id, title, abstract: "An abstract.", year_accomplished: 2026, classification_name: "Applied Research",
  record_type_name: "Thesis/Research", pipeline_status: "published", is_ip: false, ip_type: "",
  for_commercialization: false, community_extension: false, access_count: 0, file_count: 0,
  created_at: "2026-09-01T08:00:00Z", authors: [{ id: 1, name: "Mateo Villanueva", role: null }],
});

const savedEntry = (record: RecordListItem, reading_status: ReadingStatus | null = null, saved_at = "2026-10-30T08:00:00Z"): SavedRecordEntry => ({
  record_id: record.id, available: true, reading_status, saved_at, updated_at: saved_at, record,
});

const saves = (entries: SavedRecordEntry[]) =>
  vi.mocked(libraryApi.saves).mockResolvedValue({ data: { results: entries } } as SavesResponse);

/** A sign-in as `login` does it: a new session, so a new epoch. */
function signIn(id: number, role = "Student") {
  useAuthStore.getState().login({ id, email: `reader${id}@cit.edu`, role_name: role } as unknown as User, "access", "refresh");
}

type MineResponse = Awaited<ReturnType<typeof recordsApi.mine>>;

const ownRecord = (overrides: Partial<MyResearchItem>): MyResearchItem => ({
  id: 12,
  title: "Community Water Monitoring",
  authors: [{ id: 1, name: "Lee Cruz", role: null }],
  adviser_name: "Dr Santos",
  record_type_name: "Thesis / Research",
  pipeline_status: "draft",
  workflow_state: "draft",
  workflow_state_label: "Draft",
  holders: [],
  cleared_offices: [],
  submitter_status: { line: "Draft: not yet submitted", waiting_on_you: [] },
  created_at: "2026-10-01T00:00:00Z",
  updated_at: "2026-10-02T00:00:00Z",
  ...overrides,
});

const mine = (records: MyResearchItem[]) =>
  vi.mocked(recordsApi.mine).mockResolvedValue({ data: records } as MineResponse);

const section = (name: string) =>
  screen.getByRole("heading", { name, level: 2 }).closest("section, details") as HTMLElement;

beforeEach(() => {
  localStorage.clear();
  sessionStorage.clear();
  vi.clearAllMocks();
  mine([]);
  saves([]);
  vi.mocked(libraryApi.unsave).mockResolvedValue({ status: 204 } as Awaited<ReturnType<typeof libraryApi.unsave>>);
  signIn(9);
});

describe("My Library: an author's research", () => {
  it("offers continuation only when the server permits it", async () => {
    mine([ownRecord({ pipeline_status: "approved", workflow_state: "approved", can_continue: true })]);
    renderScreen(<MyLibraryPage />);
    expect(await screen.findByRole("button", { name: "Continue as Thesis" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Continue as Project" })).toBeInTheDocument();
  });
  it("opens on the author's research, with the server's status and Continue into Publish for a draft", async () => {
    mine([ownRecord({})]);
    const { container } = renderScreen(<MyLibraryPage />);

    expect(await screen.findByRole("link", { name: "Community Water Monitoring" })).toHaveAttribute("href", "/records/12");
    expect(within(section("Drafts")).getByText("Draft: not yet submitted")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Continue" })).toHaveAttribute("href", "/?publish=12");
    expect(recordsApi.mine).toHaveBeenCalledOnce();
    await expectNoBlockingA11yViolations(container);
  });

  it("puts what waits on the author first, each request linking straight to the act that answers it", async () => {
    const revision = { kind: "revision", party: "ierc", label: "Revision requested by IERC", action_label: "Submit a new version" } as const;
    const document = { kind: "document", party: "adviser", label: "Documents requested by Adviser", action_label: "Upload the documents" } as const;
    mine([
      ownRecord({ id: 13, title: "Still with the offices", pipeline_status: "in_review", workflow_state: "in_review", workflow_state_label: "In review", holders: [{ party: "ierc", label: "IERC" }], submitter_status: { line: "In specialist review: IERC", waiting_on_you: [] } }),
      ownRecord({ id: 14, title: "Asked to revise", pipeline_status: "in_review", workflow_state: "awaiting_resubmission", workflow_state_label: "Awaiting resubmission", holders: [{ party: "ierc", label: "IERC" }], submitter_status: { line: "Revision requested by IERC: action needed", waiting_on_you: [revision, document] } }),
      ownRecord({ id: 15, title: "Asked for a form", pipeline_status: "in_review", workflow_state: "awaiting_document", workflow_state_label: "Awaiting document", holders: [{ party: "adviser", label: "Adviser" }], submitter_status: { line: "Documents requested by Adviser: action needed", waiting_on_you: [document] } }),
    ]);
    const { container } = renderScreen(<MyLibraryPage />);

    await screen.findByRole("link", { name: "Asked to revise" });
    const headings = screen.getAllByRole("heading", { level: 2 }).map((h) => h.textContent);
    expect(headings.indexOf("Waiting on you")).toBeLessThan(headings.indexOf("With the offices"));

    const waiting = section("Waiting on you");
    expect(within(waiting).getByText("Revision requested by IERC: action needed")).toBeInTheDocument();
    expect(within(waiting).getByRole("link", { name: "Submit a new version (Revision requested by IERC)" }))
      .toHaveAttribute("href", "/records/14?section=overview#revision-requested");
    const uploads = within(waiting).getAllByRole("link", { name: "Upload the documents (Documents requested by Adviser)" });
    expect(uploads.map((link) => link.getAttribute("href"))).toEqual([
      "/records/14?section=overview#documents-requested",
      "/records/15?section=overview#documents-requested",
    ]);
    expect(within(waiting).queryByRole("link", { name: "Still with the offices" })).not.toBeInTheDocument();
    expect(within(section("With the offices")).getByText("In specialist review: IERC")).toBeInTheDocument();
    await expectNoBlockingA11yViolations(container);
  });

  it("groups review by who holds it and shows each office's clearance, kept ones marked", async () => {
    mine([
      ownRecord({
        id: 20, title: "Parallel review", pipeline_status: "in_review", workflow_state: "in_review", workflow_state_label: "In review",
        holders: [{ party: "ierc", label: "IERC" }],
        cleared_offices: [{ office: "itso", label: "ITSO", preserved: true }],
      }),
      ownRecord({ id: 21, title: "First reading", pipeline_status: "in_review", workflow_state: "submitted", workflow_state_label: "Submitted", holders: [{ party: "adviser", label: "Adviser" }] }),
    ]);
    renderScreen(<MyLibraryPage />);

    await screen.findByRole("link", { name: "Parallel review" });
    const offices = section("With the offices");
    expect(within(offices).getByText("ITSO cleared")).toBeInTheDocument();
    expect(within(offices).getByText("· kept")).toBeInTheDocument();
    expect(within(section("With your Adviser")).getByRole("link", { name: "First reading" })).toBeInTheDocument();
  });

  it("renders no numeric counters", async () => {
    mine([ownRecord({ id: 31, title: "Draft one" }), ownRecord({ id: 32, title: "Draft two" })]);
    renderScreen(<MyLibraryPage />);

    await screen.findByRole("link", { name: "Draft one" });
    for (const heading of screen.getAllByRole("heading", { level: 2 })) {
      expect(heading.textContent).not.toMatch(/\d/);
    }
  });

  it("keeps Archived collapsed until asked for", async () => {
    mine([ownRecord({ id: 22, title: "Rejected paper", pipeline_status: "rejected", workflow_state: "rejected", workflow_state_label: "Archived" })]);
    renderScreen(<MyLibraryPage />);

    const archived = (await screen.findByText("Rejected records, kept for your reference.")).closest("details") as HTMLDetailsElement;
    expect(archived.open).toBe(false);
  });

  it("searches titles and authors, and says when nothing matches", async () => {
    mine([ownRecord({ id: 1, title: "Water quality" }), ownRecord({ id: 2, title: "Soil sensors" })]);
    renderScreen(<MyLibraryPage />);

    await screen.findByRole("link", { name: "Water quality" });
    await userEvent.type(screen.getByRole("searchbox", { name: "Search your research" }), "soil");
    expect(screen.queryByRole("link", { name: "Water quality" })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Soil sensors" })).toBeInTheDocument();

    await userEvent.type(screen.getByRole("searchbox", { name: "Search your research" }), "zzz");
    expect(screen.getByRole("heading", { name: "Nothing matches “soilzzz”" })).toBeInTheDocument();
  });

  it("offers Publish when the author has nothing yet", async () => {
    const { container } = renderScreen(<MyLibraryPage />);

    expect(await screen.findByRole("heading", { name: "You haven’t published anything yet" })).toBeInTheDocument();
    for (const link of screen.getAllByRole("link", { name: "Publish" })) {
      expect(link).toHaveAttribute("href", "/?publish=new");
    }
    await expectNoBlockingA11yViolations(container);
  });

  it("offers a retry when the research list fails to load", async () => {
    vi.mocked(recordsApi.mine).mockRejectedValueOnce(new Error("offline"));
    renderScreen(<MyLibraryPage />);

    await userEvent.click(await screen.findByRole("button", { name: "Try again" }));
    expect(recordsApi.mine).toHaveBeenCalledTimes(2);
  });
});

describe("My Library: reading", () => {
  it("keeps the reading panel beside the research, says what follows the account, and opens a status", async () => {
    mine([ownRecord({})]);
    renderScreen(<MyLibraryPage />);

    await screen.findByRole("link", { name: "Community Water Monitoring" });
    const reading = screen.getByRole("region", { name: "Your reading" });
    expect(within(reading).getByText("Saved papers follow your account.")).toBeInTheDocument();
    expect(within(reading).getByRole("heading", { name: "In this browser only" })).toBeInTheDocument();
    expect(within(reading).queryByText(/saved in this browser only/i)).not.toBeInTheDocument();
    expect(within(reading).queryByRole("button", { name: /liked/i })).not.toBeInTheDocument();

    await userEvent.click(within(reading).getByRole("button", { name: "Want to read" }));
    expect(await screen.findByRole("heading", { name: "Nothing in Want to read yet" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Back to your research" }));
    expect(screen.getByRole("link", { name: "Community Water Monitoring" })).toBeInTheDocument();
  });

  it("defaults a non-author to All saved and never fetches owned research", async () => {
    signIn(10, "RDCO");
    const { container } = renderScreen(<MyLibraryPage />);

    expect(await screen.findByRole("heading", { name: "No saved papers yet" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Back to your research" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Publish" })).not.toBeInTheDocument();
    await waitFor(() => expect(recordsApi.mine).not.toHaveBeenCalled());
    await expectNoBlockingA11yViolations(container);
  });

  it("opens Saved directly from ?section=saved", async () => {
    renderScreen(<MyLibraryPage />, { route: "/records/mine?section=saved" });

    expect(await screen.findByRole("heading", { name: "No saved papers yet" })).toBeInTheDocument();
  });
});

describe("My Library: saves follow the account (IR-566)", () => {
  const water = paper(41, "Rainwater Harvesting Survey");
  const rice = paper(42, "Rice Husk Insulation Panels");

  it("lists the account's saves, newest first, and files each under its Reading status", async () => {
    saves([savedEntry(rice, "reading", "2026-10-31T08:00:00Z"), savedEntry(water, null, "2026-10-30T08:00:00Z")]);
    renderScreen(<MyLibraryPage />, { route: "/records/mine?section=saved" });

    const links = await screen.findAllByRole("link", { name: /Rainwater|Rice Husk/ });
    expect(links.map((l) => l.textContent)).toEqual([rice.title, water.title]);
    expect(recordsApi.list).not.toHaveBeenCalled();

    await userEvent.click(within(screen.getByRole("region", { name: "Your reading" })).getByRole("button", { name: "Reading" }));
    expect(await screen.findByRole("link", { name: rice.title })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: water.title })).not.toBeInTheDocument();
  });

  it("shows a save the reader can no longer read as unavailable, discloses nothing, and lets them remove it", async () => {
    saves([savedEntry(water), { record_id: 77, available: false }]);
    renderScreen(<MyLibraryPage />, { route: "/records/mine?section=saved" });

    expect(await screen.findByText(/1 saved paper is no longer available to you/)).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: /Rainwater/ })).toHaveLength(1);

    await userEvent.click(screen.getByRole("button", { name: "Remove it" }));

    expect(libraryApi.unsave).toHaveBeenCalledWith(77);
    await waitFor(() => expect(screen.queryByText(/no longer available/)).not.toBeInTheDocument());
  });

  it("rolls a failed removal back where the reader can see it", async () => {
    saves([savedEntry(water)]);
    vi.mocked(libraryApi.unsave).mockRejectedValueOnce(new Error("offline"));
    renderScreen(<MyLibraryPage />, { route: "/records/mine?section=saved" });

    await userEvent.click(await screen.findByRole("button", { name: `Remove from library: ${water.title}` }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/could not remove this paper/i);
    expect(screen.getByRole("link", { name: water.title })).toBeInTheDocument();
  });

  it("never shows one account's saves or history to the next account on the same browser", async () => {
    saves([savedEntry(water, "want_to_read")]);
    localStorage.setItem("iris_reading_history", JSON.stringify([{ recordId: water.id, title: water.title, viewedAt: "2026-10-31T08:00:00Z" }]));
    const first = renderScreen(<MyLibraryPage />, { route: "/records/mine?section=saved" });
    expect(await screen.findByRole("link", { name: water.title })).toBeInTheDocument();
    first.unmount();

    useAuthStore.getState().logout();
    expect(useLibraryStore.getState().items).toEqual({});
    expect(localStorage.getItem("iris_reading_history")).toBeNull();

    saves([savedEntry(rice)]);
    signIn(11);
    renderScreen(<MyLibraryPage />, { route: "/records/mine?section=saved" });

    expect(await screen.findByRole("link", { name: rice.title })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: water.title })).not.toBeInTheDocument();
    expect(screen.queryByText("Recently opened")).not.toBeInTheDocument();
  });

  it("leaves the old browser saves and stars untouched for the import (IR-579)", async () => {
    const legacy = JSON.stringify([{ id: "want-to-read", name: "Want to read", recordIds: [water.id] }]);
    localStorage.setItem("iris_record_collections", legacy);
    localStorage.setItem("iris_starred_records", JSON.stringify([rice.id]));
    renderScreen(<MyLibraryPage />, { route: "/records/mine?section=saved" });

    expect(await screen.findByRole("heading", { name: "No saved papers yet" })).toBeInTheDocument();
    await userEvent.click(within(screen.getByRole("region", { name: "Your reading" })).getByRole("button", { name: "Want to read" }));

    expect(await screen.findByRole("heading", { name: "Nothing in Want to read yet" })).toBeInTheDocument();
    expect(localStorage.getItem("iris_record_collections")).toBe(legacy);
    expect(localStorage.getItem("iris_starred_records")).toBe(JSON.stringify([rice.id]));
  });
});
