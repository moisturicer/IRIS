import { act } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useSearchParams } from "react-router-dom";
import { libraryApi, type FolderEntry, type ReadingHistoryEntry, type ReadingStatus, type SavedRecordEntry } from "@/api/library";
import { recordsApi } from "@/api/records";
import { RequestTimeoutError } from "@/api/requestPolicy";
import { useAuthStore } from "@/store/auth.store";
import { useHistoryStore } from "@/store/history.store";
import { useLibraryStore } from "@/store/library.store";
import type { User } from "@/types/auth";
import { expectNoBlockingA11yViolations } from "@/test/axe";
import { renderScreen, screen, userEvent, waitFor, within } from "@/test/render";
import type { ClearanceStripEntry, MyResearchItem, ReaderDownloadRequest, RecordListItem } from "@/types/records";
import MyLibraryPage from "./MyLibraryPage";

/** Stands in for closing the Publish form, which removes only `publish` (IR-1258). */
function ClosePublish() {
  const [, setParams] = useSearchParams();
  return (
    <button type="button" onClick={() => setParams((prev) => { const next = new URLSearchParams(prev); next.delete("publish"); return next; }, { replace: true })}>
      Close Publish
    </button>
  );
}

vi.mock("@/api/records", () => ({
  recordsApi: {
    mine: vi.fn(),
    list: vi.fn().mockResolvedValue({ data: { results: [] } }),
    myDownloadRequests: vi.fn(),
    cancelDownloadRequest: vi.fn(),
    requestDownload: vi.fn(),
    downloadCopy: vi.fn(),
    delete: vi.fn(),
  },
}));

// Saved calls (IR-766) read their own endpoint.
const savedCalls = vi.fn();
vi.mock("@/api/opportunities", () => ({
  opportunitiesApi: { saved: () => savedCalls(), save: vi.fn(), unsave: vi.fn() },
}));

const downloadBlob = vi.fn();
vi.mock("@/lib/utils", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/utils")>()),
  downloadBlob: (...args: unknown[]) => downloadBlob(...args),
}));

vi.mock("@/api/library", () => ({
  libraryApi: {
    saves: vi.fn(),
    save: vi.fn(),
    unsave: vi.fn(),
    history: vi.fn(),
    clearHistory: vi.fn(),
    preferences: vi.fn(),
    updatePreferences: vi.fn(),
    // IR-572: folders are read with the saves, and written one call at a time.
    folders: vi.fn(),
    createFolder: vi.fn(),
    renameFolder: vi.fn(),
    deleteFolder: vi.fn(),
    fileInFolder: vi.fn(),
    removeFromFolder: vi.fn(),
  },
}));

type SavesResponse = Awaited<ReturnType<typeof libraryApi.saves>>;
type FoldersResponse = Awaited<ReturnType<typeof libraryApi.folders>>;

const folderEntry = (id: number, name: string, record_ids: number[] = []): FolderEntry => ({
  id, name, record_ids, created_at: "2026-11-01T08:00:00Z", updated_at: "2026-11-01T08:00:00Z",
});

const folders = (entries: FolderEntry[], limit = 10) =>
  vi.mocked(libraryApi.folders).mockResolvedValue({ data: { results: entries, limit } } as FoldersResponse);

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

/** What the account's history answers (IR-756). */
const history = (entries: ReadingHistoryEntry[], keep_history = true) => {
  vi.mocked(libraryApi.history).mockResolvedValue({ data: { results: entries } } as Awaited<ReturnType<typeof libraryApi.history>>);
  vi.mocked(libraryApi.preferences).mockResolvedValue({ data: { keep_history } } as Awaited<ReturnType<typeof libraryApi.preferences>>);
};

const visitEntry = (record: RecordListItem, viewed_at = "2026-11-02T08:00:00Z"): ReadingHistoryEntry => ({
  record_id: record.id, available: true, viewed_at, record,
});

/** A sign-in as `login` does it: a new session, so a new epoch. */
function signIn(id: number, role = "Student", canAuthor = role === "Student" || role === "Adviser") {
  // `can_author` is the server's flag (IR-1096); a test says what the server said.
  useAuthStore.getState().login(
    { id, email: `reader${id}@cit.edu`, role_name: role, can_author: canAuthor } as unknown as User, "access",
  );
}

/** What a resubmission left on a record: ITSO's clearance kept, IERC's reset (IR-1083). */
const KEPT: ClearanceStripEntry = {
  party: "itso", label: "ITSO", kind: "kept", text: "Cleared", note: "Kept from v1", version: 1,
};
const RESET: ClearanceStripEntry = {
  party: "ierc", label: "IERC", kind: "reviewing", text: "Reviewing v2", note: "Reset by v2", version: 2,
};

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
  clearance_strip: [],
  submitter_status: { line: "Draft: not yet submitted", waiting_on_you: [] },
  created_at: "2026-10-01T00:00:00Z",
  updated_at: "2026-10-02T00:00:00Z",
  ...overrides,
});

const mine = (records: MyResearchItem[]) =>
  vi.mocked(recordsApi.mine).mockResolvedValue({ data: records } as MineResponse);

const SUBMISSIONS = { route: "/records/mine?section=research" };
const DOWNLOADS = { route: "/records/mine?section=downloads" };

type MyDownloadsResponse = Awaited<ReturnType<typeof recordsApi.myDownloadRequests>>;

const downloadRequest = (overrides: Partial<ReaderDownloadRequest>): ReaderDownloadRequest => ({
  id: 1,
  record: 41,
  record_title: "Rainwater Harvesting Survey",
  note: "Citing its survey method.",
  created_at: "2026-10-28T08:00:00Z",
  state: "pending",
  grant_expires_at: null,
  rdco_note: "",
  actions: ["cancel"],
  ...overrides,
});

const myDownloads = (rows: ReaderDownloadRequest[]) =>
  vi.mocked(recordsApi.myDownloadRequests).mockResolvedValue({ data: rows } as MyDownloadsResponse);

const section = (name: string) =>
  screen.getByRole("heading", { name, level: 2 }).closest("section, details") as HTMLElement;

/* Saved Papers' folder tiles (IR-1324), named "<folder>, <n> papers". */
const folderShelf = () => screen.getByRole("region", { name: "Folders" });
const tileName = (name: string) => new RegExp(`^${name.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}, \\d+ papers?$`);
const folderTile = (name: string) => within(folderShelf()).getByRole("button", { name: tileName(name) });
const queryFolderTile = (name: string) => within(folderShelf()).queryByRole("button", { name: tileName(name) });
/** Open a tile, going back to All saved first when inside a folder. */
async function openTile(name: string) {
  if (!screen.queryByRole("region", { name: "Folders" })) await userEvent.click(screen.getByRole("button", { name: "All saved papers" }));
  await userEvent.click(folderTile(name));
}
/** + Folder names the folder in a dialog (IR-1324). */
async function newFolder(name: string) {
  await userEvent.click(within(folderShelf()).getByRole("button", { name: "Folder" }));
  const dialog = await screen.findByRole("dialog", { name: "New folder" });
  await userEvent.type(within(dialog).getByRole("textbox", { name: "Folder name" }), name);
  await userEvent.click(within(dialog).getByRole("button", { name: "Create folder" }));
}
/** A folder tile's "⋯" menu (IR-1324). */
async function folderAction(folder: string, action: string) {
  await userEvent.click(within(folderShelf()).getByRole("button", { name: `Actions for ${folder}` }));
  await userEvent.click(await screen.findByRole("menuitem", { name: action }));
}

beforeEach(() => {
  localStorage.clear();
  sessionStorage.clear();
  vi.clearAllMocks();
  mine([]);
  saves([]);
  history([]);
  folders([]);
  myDownloads([]);
  savedCalls.mockResolvedValue({ data: { results: [] } });
  vi.mocked(libraryApi.unsave).mockResolvedValue({ status: 204 } as Awaited<ReturnType<typeof libraryApi.unsave>>);
  signIn(9);
});

describe("My Library: an author's research", () => {
  it("offers continuation only when the server permits it", async () => {
    mine([ownRecord({ pipeline_status: "approved", workflow_state: "approved", can_continue: true })]);
    renderScreen(<MyLibraryPage />, SUBMISSIONS);
    expect(await screen.findByRole("button", { name: "Continue as Thesis" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Continue as Project" })).toBeInTheDocument();
  });
  it("opens My submissions from ?section=research, with the server's status, and a draft's row reopens Publish", async () => {
    mine([ownRecord({})]);
    const { container } = renderScreen(<MyLibraryPage />, SUBMISSIONS);

    // The whole row is the link: a draft's opens Publish over this tab
    // (IR-1258), so it has no separate "Continue draft" button (IR-1279).
    expect(await screen.findByRole("link", { name: "Community Water Monitoring" }))
      .toHaveAttribute("href", "/records/mine?section=research&publish=12");
    expect(within(section("Drafts")).getByText("Draft: not yet submitted")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /^Continue draft/ })).not.toBeInTheDocument();
    expect(recordsApi.mine).toHaveBeenCalledOnce();
    await expectNoBlockingA11yViolations(container);
  });

  it("deletes a draft after one confirmation and drops its row", async () => {
    mine([ownRecord({}), ownRecord({ id: 13, title: "Still with the offices", pipeline_status: "in_review", workflow_state: "in_review", workflow_state_label: "In review", submitter_status: { line: "In review", waiting_on_you: [] } })]);
    vi.mocked(recordsApi.delete).mockResolvedValue({} as Awaited<ReturnType<typeof recordsApi.delete>>);
    const user = userEvent.setup();
    renderScreen(<MyLibraryPage />, SUBMISSIONS);

    await user.click(await screen.findByRole("button", { name: "Delete draft “Community Water Monitoring”" }));
    const dialog = screen.getByRole("dialog", { name: "Delete this draft?" });
    expect(within(dialog).getByRole("button", { name: "Cancel" })).toHaveFocus();
    expect(recordsApi.delete).not.toHaveBeenCalled();

    await user.click(within(dialog).getByRole("button", { name: "Delete draft" }));
    await waitFor(() => expect(screen.queryByRole("link", { name: "Community Water Monitoring" })).not.toBeInTheDocument());
    expect(recordsApi.delete).toHaveBeenCalledWith(12);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    // Only a draft offers it.
    expect(screen.getByRole("link", { name: "Still with the offices" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^Delete draft/ })).not.toBeInTheDocument();
  });

  it("keeps the draft and says why when the delete fails", async () => {
    mine([ownRecord({})]);
    vi.mocked(recordsApi.delete).mockRejectedValue({ response: { status: 400, data: { detail: "A delete decision is already pending for this record." } } });
    const user = userEvent.setup();
    renderScreen(<MyLibraryPage />, SUBMISSIONS);

    await user.click(await screen.findByRole("button", { name: "Delete draft “Community Water Monitoring”" }));
    await user.click(screen.getByRole("button", { name: "Delete draft" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("A delete decision is already pending for this record.");
    expect(screen.getByRole("dialog", { name: "Delete this draft?" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Community Water Monitoring" })).toBeInTheDocument();
  });

  it("puts what waits on the author first, each request linking straight to the act that answers it", async () => {
    const revision = { kind: "revision", party: "ierc", label: "Changes requested by IERC", action_label: "Submit a new version" } as const;
    const document = { kind: "document", party: "adviser", label: "Changes requested by Adviser", action_label: "Upload the documents" } as const;
    mine([
      ownRecord({ id: 13, title: "Still with the offices", pipeline_status: "in_review", workflow_state: "in_review", workflow_state_label: "In review", holders: [{ party: "ierc", label: "IERC" }], submitter_status: { line: "In specialist review: IERC", waiting_on_you: [] } }),
      ownRecord({ id: 14, title: "Asked to revise", pipeline_status: "in_review", workflow_state: "awaiting_resubmission", workflow_state_label: "Awaiting resubmission", holders: [{ party: "ierc", label: "IERC" }], submitter_status: { line: "Revision requested by IERC: action needed", waiting_on_you: [revision, document] } }),
      ownRecord({ id: 15, title: "Asked for a form", pipeline_status: "in_review", workflow_state: "awaiting_document", workflow_state_label: "Awaiting document", holders: [{ party: "adviser", label: "Adviser" }], submitter_status: { line: "Documents requested by Adviser: action needed", waiting_on_you: [document] } }),
    ]);
    const { container } = renderScreen(<MyLibraryPage />, SUBMISSIONS);

    await screen.findByRole("link", { name: "Asked to revise" });
    const headings = screen.getAllByRole("heading", { level: 2 }).map((h) => h.textContent);
    expect(headings.indexOf("Needs your action")).toBeLessThan(headings.indexOf("In review"));

    const waiting = section("Needs your action");
    expect(within(waiting).getByText("Revision requested by IERC: action needed")).toBeInTheDocument();
    // The row itself opens Review's Documents tab, where both are answered
    // (IR-1318); it carries no per-request button (IR-1321).
    expect(within(waiting).getByRole("link", { name: "Asked to revise" }))
      .toHaveAttribute("href", "/records/14?section=review&documents=open");
    expect(within(waiting).getByRole("link", { name: "Asked for a form" }))
      .toHaveAttribute("href", "/records/15?section=review&documents=open");
    expect(within(waiting).queryByRole("link", { name: /^Submit a new version|^Upload the documents/ })).not.toBeInTheDocument();
    expect(within(waiting).queryByRole("link", { name: "Still with the offices" })).not.toBeInTheDocument();
    expect(within(section("In review")).getByRole("link", { name: "Still with the offices" })).toHaveAttribute("href", "/records/13");
    expect(within(section("In review")).getByText("In specialist review: IERC")).toBeInTheDocument();
    await expectNoBlockingA11yViolations(container);
  });

  it("files every reviewer's records under In review and shows each office's clearance, kept ones marked", async () => {
    mine([
      ownRecord({
        id: 20, title: "Parallel review", pipeline_status: "in_review", workflow_state: "in_review", workflow_state_label: "In review",
        holders: [{ party: "ierc", label: "IERC" }],
        cleared_offices: [{ office: "itso", label: "ITSO", preserved: true }],
        clearance_strip: [KEPT, RESET],
      }),
      ownRecord({ id: 21, title: "First reading", pipeline_status: "in_review", workflow_state: "submitted", workflow_state_label: "Submitted", holders: [{ party: "adviser", label: "Adviser" }] }),
    ]);
    renderScreen(<MyLibraryPage />, SUBMISSIONS);

    await screen.findByRole("link", { name: "Parallel review" });
    const review = section("In review");
    // The strip is the server's words (IR-1083): kept says which version it was kept from.
    const strip = within(review).getByRole("list", { name: "Clearances" });
    expect(strip).toHaveTextContent("ITSO: Cleared · Kept from v1");
    expect(strip).toHaveTextContent("IERC: Reviewing v2 · Reset by v2");
    expect(within(review).getByRole("link", { name: "First reading" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: /With your Adviser|With the offices|With RDCO/ })).not.toBeInTheDocument();
  });

  it("renders no numeric counters", async () => {
    mine([ownRecord({ id: 31, title: "Draft one" }), ownRecord({ id: 32, title: "Draft two" })]);
    renderScreen(<MyLibraryPage />, SUBMISSIONS);

    await screen.findByRole("link", { name: "Draft one" });
    for (const heading of screen.getAllByRole("heading", { level: 2 })) {
      expect(heading.textContent).not.toMatch(/\d/);
    }
  });

  // IR-1324 replaces "folds every group": nothing folds, and every filter always shows.
  it("shows every group under a plain heading, offers all five filters, and says when a picked one is empty", async () => {
    mine([
      ownRecord({ id: 22, title: "Rejected paper", pipeline_status: "rejected", workflow_state: "rejected", workflow_state_label: "Archived" }),
      ownRecord({ id: 23, title: "Draft paper" }),
    ]);
    const { container } = renderScreen(<MyLibraryPage />, SUBMISSIONS);

    await screen.findByRole("heading", { name: "Drafts", level: 2 });
    expect(within(section("Finished")).getByRole("link", { name: "Rejected paper" })).toBeVisible();
    expect(container.querySelector("details")).toBeNull();
    const filters = screen.getByRole("group", { name: "Show" });
    expect(within(filters).getAllByRole("button").map((b) => b.textContent))
      .toEqual(["All", "Needs your action", "In review", "Drafts", "Finished"]);

    await userEvent.click(within(filters).getByRole("button", { name: "Finished" }));
    expect(screen.getByRole("link", { name: "Rejected paper" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Drafts", level: 2 })).not.toBeInTheDocument();

    await userEvent.click(within(filters).getByRole("button", { name: "In review" }));
    expect(screen.getByRole("heading", { name: "Nothing in review" })).toBeInTheDocument();
    await expectNoBlockingA11yViolations(container);
  });

  it("searches titles and authors, and says when nothing matches", async () => {
    mine([ownRecord({ id: 1, title: "Water quality" }), ownRecord({ id: 2, title: "Soil sensors" })]);
    renderScreen(<MyLibraryPage />, SUBMISSIONS);

    await screen.findByRole("link", { name: "Water quality" });
    await userEvent.type(screen.getByRole("searchbox", { name: "Search your research" }), "soil");
    expect(screen.queryByRole("link", { name: "Water quality" })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Soil sensors" })).toBeInTheDocument();

    await userEvent.type(screen.getByRole("searchbox", { name: "Search your research" }), "zzz");
    expect(screen.getByRole("heading", { name: "Nothing matches “soilzzz”" })).toBeInTheDocument();
  });

  it("says nothing is waiting on an author only once their research has loaded, with no counter (IR-1321)", async () => {
    mine([ownRecord({ id: 12 })]);
    const { container } = renderScreen(<MyLibraryPage />, { route: "/records/mine" });

    const waiting = await screen.findByRole("region", { name: "Waiting on you" });
    expect(await within(waiting).findByText(/^Nothing needs your action\./)).toBeInTheDocument();
    expect(within(waiting).queryByText(/^\d+$/)).not.toBeInTheDocument();
    await expectNoBlockingA11yViolations(container);
  });

  // IR-1323: each side card is a fixed rectangle whose list scrolls, so none is cut short.
  it("lists every paper waiting on the author in a card that scrolls, and an empty Recently opened says so", async () => {
    const document = { kind: "document", party: "adviser", label: "Changes requested by Adviser", action_label: "Upload the documents" } as const;
    mine(Array.from({ length: 7 }, (_, i) => ownRecord({
      id: 40 + i, title: `Waiting paper ${i + 1}`, pipeline_status: "in_review", workflow_state: "awaiting_document",
      workflow_state_label: "Awaiting document", holders: [{ party: "adviser", label: "Adviser" }],
      submitter_status: { line: "Documents requested by Adviser: action needed", waiting_on_you: [document] },
    })));
    const { container } = renderScreen(<MyLibraryPage />, { route: "/records/mine" });

    const waiting = await screen.findByRole("region", { name: "Waiting on you" });
    expect(await within(waiting).findByRole("link", { name: "Waiting paper 7" })).toBeInTheDocument();
    expect(within(waiting).getAllByRole("link", { name: /^Waiting paper/ })).toHaveLength(7);
    expect(within(waiting).queryByRole("button", { name: /Show all/ })).not.toBeInTheDocument();
    expect(within(screen.getByRole("region", { name: "Recently opened" })).getByText("Papers you open appear here.")).toBeInTheDocument();
    await expectNoBlockingA11yViolations(container);
  });

  it("opens an author on Overview: what waits on them, counted, in the right column, and a tab to every submission", async () => {
    const document = { kind: "document", party: "adviser", label: "Changes requested by Adviser", action_label: "Upload the documents" } as const;
    mine([
      ownRecord({ id: 15, title: "Asked for a form", pipeline_status: "in_review", workflow_state: "awaiting_document", workflow_state_label: "Awaiting document", holders: [{ party: "adviser", label: "Adviser" }], submitter_status: { line: "Documents requested by Adviser: action needed", waiting_on_you: [document] } }),
      ownRecord({ id: 12 }),
    ]);
    const { container } = renderScreen(<MyLibraryPage />, { route: "/records/mine" });

    expect(await screen.findByRole("tab", { name: "Overview" })).toHaveAttribute("aria-selected", "true");
    const waiting = screen.getByRole("region", { name: "Waiting on you" });
    expect(within(waiting).getByText("1")).toBeInTheDocument();
    // One short link per paper (IR-1324); the request's words stay for a screen reader.
    expect(within(waiting).getByRole("link", { name: /^Submit documents/ }))
      .toHaveAttribute("href", "/records/15?section=review&documents=open");
    expect(within(waiting).getByRole("link", { name: /^Submit documents/ })).toHaveAccessibleName(/Changes requested by Adviser.*Asked for a form/);
    // The draft's title opens Publish over My Library (IR-1258).
    expect(within(screen.getByRole("region", { name: "Recent submissions" })).getByRole("link", { name: "Community Water Monitoring" }))
      .toHaveAttribute("href", "/records/mine?publish=12");
    // The Reading shelf is gone (IR-1321), and Continue reading with it (IR-1324).
    expect(screen.queryByRole("region", { name: "Reading shelf" })).not.toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Continue reading" })).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Your folders" })).not.toBeInTheDocument();
    // The side cards in order, first on a phone, then the author's records (IR-1323, IR-1324).
    expect(screen.getAllByRole("heading", { level: 2 }).slice(0, 3).map((h) => h.textContent))
      .toEqual(["Waiting on you", "Recently opened", "Recent submissions"]);
    // A brief row carries no per-request button either.
    expect(within(screen.getByRole("region", { name: "Recent submissions" })).queryByRole("link", { name: /^Submit documents/ })).not.toBeInTheDocument();
    await expectNoBlockingA11yViolations(container);

    await userEvent.click(screen.getByRole("tab", { name: "My Submissions" }));
    expect(screen.getByRole("tab", { name: "My Submissions" })).toHaveAttribute("aria-selected", "true");
    expect(within(section("Drafts")).getByRole("link", { name: "Community Water Monitoring" })).toBeInTheDocument();
  });

  it("offers Publish when the author has nothing yet", async () => {
    const { container } = renderScreen(<MyLibraryPage />);

    expect(await screen.findByRole("heading", { name: "You haven’t published anything yet" })).toBeInTheDocument();
    for (const link of screen.getAllByRole("link", { name: "Publish" })) {
      expect(link).toHaveAttribute("href", "/?publish=new");
    }
    await expectNoBlockingA11yViolations(container);
  });

  it("opens Publish over the tab it is on, never over Discover (IR-1258)", async () => {
    renderScreen(<MyLibraryPage />, SUBMISSIONS);

    expect(await screen.findByRole("heading", { name: "You haven’t published anything yet" })).toBeInTheDocument();
    for (const link of screen.getAllByRole("link", { name: "Publish" })) {
      expect(link).toHaveAttribute("href", "/records/mine?section=research&publish=new");
    }
  });

  it("reads its papers again, without a spinner, when Publish closes over it (IR-1258)", async () => {
    vi.mocked(recordsApi.mine)
      .mockResolvedValueOnce({ data: [ownRecord({})] } as unknown as MineResponse)
      // Deleted in the form: the server no longer lists it.
      .mockResolvedValueOnce({ data: [] } as unknown as MineResponse);
    const user = userEvent.setup();
    renderScreen(<><MyLibraryPage /><ClosePublish /></>, { route: "/records/mine?section=research&publish=12" });

    expect(await screen.findByRole("link", { name: "Community Water Monitoring" })).toBeInTheDocument();
    expect(recordsApi.mine).toHaveBeenCalledOnce();

    await user.click(screen.getByRole("button", { name: "Close Publish" }));

    await waitFor(() => expect(recordsApi.mine).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(screen.queryByRole("link", { name: "Community Water Monitoring" })).not.toBeInTheDocument());
    expect(screen.getByRole("tab", { name: "My Submissions" })).toHaveAttribute("aria-selected", "true");
  });

  it("offers a retry when the research list fails to load", async () => {
    vi.mocked(recordsApi.mine).mockRejectedValueOnce(new Error("offline"));
    renderScreen(<MyLibraryPage />);

    await userEvent.click(await screen.findByRole("button", { name: "Try again" }));
    expect(recordsApi.mine).toHaveBeenCalledTimes(2);
  });
});

// IR-1306 removed the sentence under each title (IR-1084's "… Nothing to do yet."): the status label,
// the clearance strip and the one action carry it.
describe("My Library: what each paper waits on (IR-1084, IR-1306)", () => {
  const inReview = (overrides: Partial<MyResearchItem> = {}) => ownRecord({
    id: 13, title: "Still with the offices", pipeline_status: "in_review", workflow_state: "in_review",
    workflow_state_label: "In review", holders: [{ party: "ierc", label: "IERC" }],
    clearance_strip: [KEPT, RESET],
    submitter_status: { line: "In specialist review: IERC", waiting_on_you: [] },
    ...overrides,
  });

  it("shows each Overview row's status without a sentence about it, and offers one action", async () => {
    mine([ownRecord({}), inReview()]);
    renderScreen(<MyLibraryPage />);

    const recent = await screen.findByRole("region", { name: "Recent submissions" });
    const review = within(recent).getByRole("link", { name: "Still with the offices" }).closest("li") as HTMLElement;
    expect(within(review).queryByText(/Nothing to do yet/)).not.toBeInTheDocument();
    // The row itself opens the review; there is no "Open review" button to add.
    expect(within(recent).getByRole("link", { name: "Still with the offices" })).toHaveAttribute("href", "/records/13");
    expect(within(review).queryByRole("link", { name: /^Open review/ })).not.toBeInTheDocument();
    expect(within(review).queryByRole("button")).not.toBeInTheDocument();

    const draft = within(recent).getByRole("link", { name: "Community Water Monitoring" }).closest("li") as HTMLElement;
    expect(within(draft).queryByText(/waits on you/)).not.toBeInTheDocument();
    // The row reopens Publish; the trash can is its one button.
    expect(within(recent).getByRole("link", { name: "Community Water Monitoring" })).toHaveAttribute("href", "/?publish=12");
    expect(within(draft).queryByRole("link", { name: /^Continue draft/ })).not.toBeInTheDocument();
    expect(within(draft).getByRole("button", { name: "Delete draft “Community Water Monitoring”" })).toBeInTheDocument();
  });

  it("deletes a draft from the Overview after the same question, and drops its row (IR-1256)", async () => {
    mine([ownRecord({})]);
    vi.mocked(recordsApi.delete).mockResolvedValue({} as Awaited<ReturnType<typeof recordsApi.delete>>);
    const user = userEvent.setup();
    renderScreen(<MyLibraryPage />);

    const recent = await screen.findByRole("region", { name: "Recent submissions" });
    await user.click(within(recent).getByRole("button", { name: "Delete draft “Community Water Monitoring”" }));
    const dialog = screen.getByRole("dialog", { name: "Delete this draft?" });
    expect(recordsApi.delete).not.toHaveBeenCalled();
    await user.click(within(dialog).getByRole("button", { name: "Delete draft" }));

    await waitFor(() => expect(screen.queryByRole("link", { name: "Community Water Monitoring" })).not.toBeInTheDocument());
    expect(recordsApi.delete).toHaveBeenCalledWith(12);
  });

  it("labels each row by the server's status alone, with no sentence about who holds it", async () => {
    mine([
      inReview({ id: 21, title: "Two offices", holders: [{ party: "ierc", label: "IERC" }, { party: "ktto", label: "KTTO" }],
        clearance_strip: [{ ...RESET }, { ...RESET, party: "ktto", label: "KTTO" }] }),
      inReview({ id: 22, title: "With the Adviser", holders: [{ party: "adviser", label: "Adviser" }], clearance_strip: [] }),
      inReview({ id: 23, title: "Final decision", workflow_state: "final_review", holders: [{ party: "rdco", label: "RDCO Final" }], clearance_strip: [] }),
      inReview({ id: 24, title: "Already published", pipeline_status: "published", workflow_state: "published", holders: [], clearance_strip: [] }),
    ]);
    renderScreen(<MyLibraryPage />, SUBMISSIONS);

    await screen.findByRole("link", { name: "Two offices" });
    expect(screen.getAllByText("In specialist review: IERC").length).toBeGreaterThan(0);
    expect(screen.queryByText(/Nothing to do yet|Nothing is waiting/)).not.toBeInTheDocument();
  });

  it("opens a paper with an open request straight on its Documents tab, with no button of its own (IR-1321)", async () => {
    const revision = { kind: "revision", party: "ierc", label: "Changes requested by IERC", action_label: "Submit a new version" } as const;
    mine([inReview({ id: 14, title: "Asked to revise", workflow_state: "awaiting_resubmission",
      submitter_status: { line: "Revision requested by IERC: action needed", waiting_on_you: [revision] } })]);
    renderScreen(<MyLibraryPage />, SUBMISSIONS);

    await screen.findByRole("link", { name: "Asked to revise" });
    expect(screen.getByText("Revision requested by IERC: action needed")).toBeInTheDocument();
    expect(screen.queryByText(/^Waiting on you:/)).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Asked to revise" })).toHaveAttribute("href", "/records/14?section=review&documents=open");
    expect(screen.queryByRole("link", { name: /^Submit a new version/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /^Open review/ })).not.toBeInTheDocument();
  });

  it("puts a red trash can alone under the draft's Updated date, and it asks once (IR-1279)", async () => {
    mine([ownRecord({})]);
    const user = userEvent.setup();
    renderScreen(<MyLibraryPage />, SUBMISSIONS);

    const row = (await screen.findByRole("link", { name: "Community Water Monitoring" })).closest("li") as HTMLElement;
    const updated = within(row).getByText(/^Updated /);
    const remove = within(row).getByRole("button", { name: "Delete draft “Community Water Monitoring”" });
    // After the date, in the same column, and the row's only button.
    expect(updated.compareDocumentPosition(remove) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(updated.parentElement?.contains(remove)).toBe(true);
    expect(within(row).getAllByRole("button")).toEqual([remove]);
    expect(within(row).queryByRole("link", { name: /^Continue draft/ })).not.toBeInTheDocument();
    // A red trash can, not a menu.
    expect(remove).toHaveClass("text-brand");
    expect(remove).not.toHaveAttribute("aria-haspopup");
    expect(within(row).queryByRole("button", { name: /^Actions for/ })).not.toBeInTheDocument();

    // One press, then the one question.
    await user.click(remove);
    const dialog = screen.getByRole("dialog", { name: "Delete this draft?" });
    expect(dialog).toHaveTextContent("“Community Water Monitoring” and its files will be removed.");
    expect(recordsApi.delete).not.toHaveBeenCalled();
  });
});

describe("My Library: withdrawing a paper in review (IR-1282)", () => {
  const inReview = (overrides: Partial<MyResearchItem> = {}) => ownRecord({
    id: 13, title: "Still with the offices", pipeline_status: "in_review", workflow_state: "in_review",
    workflow_state_label: "In review", holders: [{ party: "ierc", label: "IERC" }],
    submitter_status: { line: "In specialist review: IERC", waiting_on_you: [] },
    delete_act: "withdraw_submission",
    ...overrides,
  });

  it("puts the same red trash can on a paper in review, asks once in withdrawal's words, then drops the row", async () => {
    mine([inReview()]);
    vi.mocked(recordsApi.delete).mockResolvedValue({} as Awaited<ReturnType<typeof recordsApi.delete>>);
    const user = userEvent.setup();
    renderScreen(<MyLibraryPage />, SUBMISSIONS);

    const row = (await screen.findByRole("link", { name: "Still with the offices" })).closest("li") as HTMLElement;
    const remove = within(row).getByRole("button", { name: "Withdraw and delete “Still with the offices”" });
    expect(within(row).getByText(/^Updated /).parentElement?.contains(remove)).toBe(true);
    expect(remove).toHaveClass("text-brand");

    await user.click(remove);
    const dialog = screen.getByRole("dialog", { name: "Withdraw and delete this paper?" });
    expect(dialog).toHaveTextContent("“Still with the offices” leaves review and is removed with its files.");
    expect(dialog).toHaveTextContent("Your Adviser and any office reviewing it stop, and are told.");
    expect(within(dialog).getByRole("button", { name: "Cancel" })).toHaveFocus();
    expect(recordsApi.delete).not.toHaveBeenCalled();

    await user.click(within(dialog).getByRole("button", { name: "Withdraw and delete" }));
    await waitFor(() => expect(screen.queryByRole("link", { name: "Still with the offices" })).not.toBeInTheDocument());
    expect(recordsApi.delete).toHaveBeenCalledWith(13);
  });

  it("keeps the paper and says why when the withdrawal fails", async () => {
    mine([inReview()]);
    vi.mocked(recordsApi.delete).mockRejectedValue({ response: { status: 403, data: { detail: "Only an owner can delete this record." } } });
    const user = userEvent.setup();
    renderScreen(<MyLibraryPage />, SUBMISSIONS);

    await user.click(await screen.findByRole("button", { name: "Withdraw and delete “Still with the offices”" }));
    await user.click(screen.getByRole("button", { name: "Withdraw and delete" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Only an owner can delete this record.");
    expect(screen.getByRole("dialog", { name: "Withdraw and delete this paper?" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Still with the offices" })).toBeInTheDocument();
  });

  it("offers no trash can on accepted work, a rejected paper, or one awaiting RDCO's delete decision", async () => {
    mine([
      inReview({ id: 31, title: "Published work", pipeline_status: "published", workflow_state: "published", holders: [], delete_act: "request_deletion" }),
      inReview({ id: 32, title: "Rejected work", pipeline_status: "rejected", workflow_state: "rejected", holders: [], delete_act: "delete_record" }),
      inReview({ id: 33, title: "Awaiting RDCO", pipeline_status: "pending_delete", workflow_state: "pending_delete", holders: [], delete_act: null }),
    ]);
    renderScreen(<MyLibraryPage />, SUBMISSIONS);

    for (const title of ["Published work", "Rejected work", "Awaiting RDCO"]) {
      const row = (await screen.findByRole("link", { name: title })).closest("li") as HTMLElement;
      expect(within(row).queryByRole("button", { name: /^(Withdraw and delete|Delete draft)/ })).not.toBeInTheDocument();
    }
  });
});

describe("My Library: interrupted reads (IR-906)", () => {
  const timeout = () => new RequestTimeoutError(30_000, "get", "/x/");

  it("shows a research list that timed out as interrupted, and Retry reads again", async () => {
    vi.mocked(recordsApi.mine).mockRejectedValueOnce(timeout());
    renderScreen(<MyLibraryPage />);

    expect(await screen.findByRole("heading", { name: "This took too long" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Could not load your research" })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(recordsApi.mine).toHaveBeenCalledTimes(2);
  });

  it("shows download requests that timed out as interrupted", async () => {
    vi.mocked(recordsApi.myDownloadRequests).mockRejectedValueOnce(timeout());
    renderScreen(<MyLibraryPage />, DOWNLOADS);

    expect(await screen.findByRole("heading", { name: "This took too long" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(recordsApi.myDownloadRequests).toHaveBeenCalledTimes(2);
  });

  it("shows saved papers that timed out as interrupted, and Retry reads the account's saves again", async () => {
    vi.mocked(libraryApi.saves).mockRejectedValueOnce(timeout());
    renderScreen(<MyLibraryPage />, { route: "/records/mine?section=saved" });

    expect(await screen.findByRole("heading", { name: "This took too long" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Retry" }));
    await waitFor(() => expect(libraryApi.saves).toHaveBeenCalledTimes(2));
  });
});

describe("My Library: reading", () => {
  // IR-1324 replaces the Folder picker (IR-1313) with folder tiles: History
  // is a tile, + Folder makes a folder in place and the new tile appears.
  it("keeps search and sort on one line, folders as tiles with + Folder, and says saves and folders follow the account", async () => {
    mine([ownRecord({})]);
    vi.mocked(libraryApi.createFolder).mockResolvedValue({ data: folderEntry(3, "Methods") } as Awaited<ReturnType<typeof libraryApi.createFolder>>);
    const { container } = renderScreen(<MyLibraryPage />);

    await userEvent.click(await screen.findByRole("tab", { name: "Saved Papers" }));
    expect(screen.getByText("Saves and folders follow your account.")).toBeInTheDocument();
    expect(screen.queryByRole("combobox", { name: "Folder" })).not.toBeInTheDocument();
    expect(screen.getByRole("searchbox", { name: "Search saved papers" })).toBeInTheDocument();
    expect(folderTile("History")).toBeInTheDocument();
    expect(within(folderShelf()).getByText(/No folders yet/)).toBeInTheDocument();
    await newFolder("Methods");
    expect(await within(folderShelf()).findByRole("button", { name: "Methods, 0 papers" })).toBeInTheDocument();
    expect(libraryApi.createFolder).toHaveBeenCalledWith("Methods");
    expect(screen.queryByRole("button", { name: /liked/i })).not.toBeInTheDocument();

    await userEvent.click(within(screen.getByRole("group", { name: "Reading status" })).getByRole("button", { name: "Want to read" }));
    expect(await screen.findByRole("heading", { name: "Nothing in Want to read yet" })).toBeInTheDocument();
    await expectNoBlockingA11yViolations(container);
    await userEvent.click(screen.getByRole("tab", { name: "My Submissions" }));
    expect(screen.getByRole("link", { name: "Community Water Monitoring" })).toBeInTheDocument();
  });

  // IR-743 replaces "no tablist" for a non-author: every reader has a
  // Download requests tab beside Saved papers, and nothing an author has.
  it("defaults a non-author to All saved, with Download requests beside it, and never fetches owned research", async () => {
    signIn(10, "RDCO");
    const { container } = renderScreen(<MyLibraryPage />);

    expect(await screen.findByRole("heading", { name: "No saved papers yet" })).toBeInTheDocument();
    expect(screen.getAllByRole("tab").map((t) => t.textContent)).toEqual(["Saved Papers", "Saved Calls", "Download Requests"]);
    expect(screen.getByRole("tab", { name: "Saved Papers" })).toHaveAttribute("aria-selected", "true");
    expect(screen.queryByRole("link", { name: "Publish" })).not.toBeInTheDocument();
    await waitFor(() => expect(recordsApi.mine).not.toHaveBeenCalled());
    await expectNoBlockingA11yViolations(container);
  });

  it("opens Saved directly from ?section=saved", async () => {
    renderScreen(<MyLibraryPage />, { route: "/records/mine?section=saved" });

    expect(await screen.findByRole("heading", { name: "No saved papers yet" })).toBeInTheDocument();
    // Audit LAY-06 (IR-1098): an empty page names the next useful step.
    expect(screen.getByRole("link", { name: "Browse Discover" })).toHaveAttribute("href", "/");
  });
});

// IR-1314: an empty library used to draw research and saved cards for a moment,
// then swap them for its empty state. A load answered inside 400 ms now goes
// straight to the empty state.
/**
 * Records whether a loader ever put a placeholder shape on the page, however
 * briefly: anything inside a `role="status"` region's `aria-hidden` wrapper.
 * The shapes are decoration with no role or name, so this reads the mutation
 * records, which keep a node's subtree even after React has removed it.
 */
function watchForPlaceholders() {
  let seen = false;
  const SHAPES = "[role='status'] > [aria-hidden='true'] > *";
  const check = (records: MutationRecord[]) => {
    for (const record of records) {
      const target = record.target as Element;
      for (const node of Array.from(record.addedNodes)) {
        if (!(node instanceof Element)) continue;
        const wrapperFilled = target.getAttribute("role") === "status"
          && node.getAttribute("aria-hidden") === "true" && node.childElementCount > 0;
        const regionWithShapes = node.getAttribute("role") === "status"
          && node.querySelector(":scope > [aria-hidden='true'] > *") !== null;
        if (wrapperFilled || regionWithShapes || node.querySelector(SHAPES)) seen = true;
      }
    }
  };
  const observer = new MutationObserver(check);
  observer.observe(document.body, { childList: true, subtree: true });
  return { seen: () => { check(observer.takeRecords()); return seen; }, stop: () => observer.disconnect() };
}

describe("My Library: an empty library that answers at once", () => {
  afterEach(() => vi.useRealTimers());

  it.each([
    ["Overview", undefined, "You haven’t published anything yet"],
    ["Saved", { route: "/records/mine?section=saved" }, "No saved papers yet"],
  ] as const)("never draws a placeholder on %s", async (_tab, route, empty) => {
    vi.useFakeTimers();
    const placeholders = watchForPlaceholders();
    renderScreen(<MyLibraryPage />, route);
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });

    expect(screen.getByRole("heading", { name: empty })).toBeInTheDocument();
    await act(async () => { await vi.advanceTimersByTimeAsync(5_000); });
    expect(placeholders.seen()).toBe(false);
    placeholders.stop();
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

    await userEvent.click(within(screen.getByRole("group", { name: "Reading status" })).getByRole("button", { name: "Reading" }));
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
    history([visitEntry(water)]);
    // What an older build kept in this browser is wiped, never read (IR-756).
    localStorage.setItem("iris_reading_history", JSON.stringify([{ recordId: water.id, title: water.title, viewedAt: "2026-10-31T08:00:00Z" }]));
    const first = renderScreen(<MyLibraryPage />, { route: "/records/mine?section=saved" });
    expect(await screen.findByRole("link", { name: water.title })).toBeInTheDocument();
    first.unmount();

    useAuthStore.getState().logout();
    expect(useLibraryStore.getState().items).toEqual({});
    expect(useHistoryStore.getState().items).toEqual([]);
    expect(localStorage.getItem("iris_reading_history")).toBeNull();

    saves([savedEntry(rice)]);
    history([]);
    signIn(11);
    renderScreen(<MyLibraryPage />, { route: "/records/mine?section=saved" });

    expect(await screen.findByRole("link", { name: rice.title })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: water.title })).not.toBeInTheDocument();
    await openTile("History");
    expect(await screen.findByRole("heading", { name: "No reading history yet" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: water.title })).not.toBeInTheDocument();
  });

  // IR-579 changes this test on purpose: the old browser saves, folders and
  // stars were left untouched for an import, and IRIS had no readers before
  // the account library, so they are now deleted instead (ADR-044 amendment
  // 2026-11-16). They are still never shown, and signing out removes them.
  it("never shows the old browser saves, folders and stars, and signing out deletes them (IR-579)", async () => {
    const legacy = JSON.stringify([
      { id: "want-to-read", name: "Want to read", recordIds: [water.id] },
      { id: "1730000000000", name: "Old browser folder", recordIds: [rice.id] },
    ]);
    localStorage.setItem("iris_record_collections", legacy);
    localStorage.setItem("iris_starred_records", JSON.stringify([rice.id]));
    renderScreen(<MyLibraryPage />, { route: "/records/mine?section=saved" });

    expect(await screen.findByRole("heading", { name: "No saved papers yet" })).toBeInTheDocument();
    await userEvent.click(within(screen.getByRole("group", { name: "Reading status" })).getByRole("button", { name: "Want to read" }));

    expect(await screen.findByRole("heading", { name: "Nothing in Want to read yet" })).toBeInTheDocument();
    expect(queryFolderTile("Old browser folder")).not.toBeInTheDocument();
    expect(libraryApi.save).not.toHaveBeenCalled();
    expect(libraryApi.createFolder).not.toHaveBeenCalled();

    useAuthStore.getState().logout();
    expect(localStorage.getItem("iris_record_collections")).toBeNull();
    expect(localStorage.getItem("iris_starred_records")).toBeNull();
  });
});

describe("My Library: reading history follows the account (IR-756)", () => {
  const water = paper(41, "Rainwater Harvesting Survey");
  const rice = paper(42, "Rice Husk Insulation Panels");

  async function openHistory() {
    renderScreen(<MyLibraryPage />, { route: "/records/mine?section=saved" });
    await screen.findByRole("region", { name: "Folders" });
    await openTile("History");
    return screen.findByRole("heading", { name: "History", level: 2 });
  }

  it("lists what the reader opened on another device, newest first, and says only they can see it", async () => {
    history([visitEntry(rice, "2026-11-02T08:00:00Z"), visitEntry(water, "2026-11-01T08:00:00Z")]);
    await openHistory();

    const links = await screen.findAllByRole("link", { name: /Rainwater|Rice Husk/ });
    expect(links.map((l) => l.textContent)).toEqual([rice.title, water.title]);
    expect(recordsApi.list).not.toHaveBeenCalled();
    expect(screen.getByText(/stored on your account.*only you can see it/i)).toBeInTheDocument();
    expect(localStorage.getItem("iris_reading_history")).toBeNull();
  });

  it("shows a paper the reader can no longer read as unavailable and discloses nothing", async () => {
    history([visitEntry(water), { record_id: 77, available: false }]);
    await openHistory();

    expect(await screen.findByText(/1 paper in your history is no longer available to you/)).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: /Rainwater/ })).toHaveLength(1);
    expect(recordsApi.list).not.toHaveBeenCalled();
  });

  it("clears the history on the account", async () => {
    history([visitEntry(water)]);
    vi.mocked(libraryApi.clearHistory).mockResolvedValue({} as Awaited<ReturnType<typeof libraryApi.clearHistory>>);
    await openHistory();

    await userEvent.click(await screen.findByRole("button", { name: "Clear history" }));

    expect(libraryApi.clearHistory).toHaveBeenCalledTimes(1);
    expect(await screen.findByRole("heading", { name: "No reading history yet" })).toBeInTheDocument();
  });

  it("keeps the history and says so when clearing fails", async () => {
    history([visitEntry(water)]);
    vi.mocked(libraryApi.clearHistory).mockRejectedValue(new Error("offline"));
    await openHistory();

    await userEvent.click(await screen.findByRole("button", { name: "Clear history" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/could not clear your history/i);
    expect(screen.getByRole("link", { name: water.title })).toBeInTheDocument();
  });

  it("pauses history on the account, keeping what is listed", async () => {
    history([visitEntry(water)]);
    vi.mocked(libraryApi.updatePreferences).mockImplementation(async (body) => ({ data: body }) as Awaited<ReturnType<typeof libraryApi.updatePreferences>>);
    await openHistory();

    const keep = await screen.findByRole("checkbox", { name: "Keep reading history" });
    expect(keep).toBeChecked();
    await userEvent.click(keep);

    expect(libraryApi.updatePreferences).toHaveBeenCalledWith({ keep_history: false });
    expect(keep).not.toBeChecked();
    expect(screen.getByText(/history is paused/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: water.title })).toBeInTheDocument();
  });

  it("opens with history paused when the account says so", async () => {
    history([], false);
    await openHistory();

    expect(await screen.findByRole("checkbox", { name: "Keep reading history" })).not.toBeChecked();
    expect(screen.getByRole("heading", { name: "History is paused" })).toBeInTheDocument();
  });

  it("says the history is safe when loading it fails, and Try again reads it again", async () => {
    vi.mocked(libraryApi.history).mockRejectedValueOnce(new Error("offline"));
    await openHistory();

    expect(await screen.findByText("Your history is safe in your account; only loading it failed.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));

    await waitFor(() => expect(libraryApi.history).toHaveBeenCalledTimes(2));
    expect(await screen.findByRole("heading", { name: "No reading history yet" })).toBeInTheDocument();
  });

  it("shows the most recent papers on an author's Overview, from the account", async () => {
    history([visitEntry(rice), { record_id: 77, available: false }, visitEntry(water, "2026-11-01T08:00:00Z")]);
    renderScreen(<MyLibraryPage />);

    const block = await screen.findByRole("region", { name: "Recently opened" });
    expect(within(block).getAllByRole("link").map((l) => l.textContent)).toEqual([rice.title, water.title]);
  });

  it("has no blocking accessibility violations in the History view", async () => {
    history([visitEntry(water)]);
    await openHistory();
    await screen.findByRole("link", { name: water.title });

    await expectNoBlockingA11yViolations(document.body);
  });
});

describe("My Library: folders follow the account (IR-572)", () => {
  const water = paper(41, "Rainwater Harvesting Survey");
  const rice = paper(42, "Rice Husk Insulation Panels");
  const SAVED = { route: "/records/mine?section=saved" };
  const pick = (name: string) => name === "All saved papers"
    ? userEvent.click(screen.getByRole("button", { name: "All saved papers" }))
    : openTile(name);
  const failed = () => Promise.reject(new Error("offline"));

  it("reads the account's folders from the server and shows a folder's saves in filing order", async () => {
    saves([savedEntry(water, "reading"), savedEntry(rice), { record_id: 77, available: false }]);
    folders([folderEntry(3, "Methods", [rice.id, 77, water.id]), folderEntry(4, "Results")]);
    const { container } = renderScreen(<MyLibraryPage />, SAVED);

    await screen.findByRole("link", { name: water.title });
    await pick("Methods");

    expect(await screen.findByRole("heading", { name: "Methods" })).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: /Rainwater|Rice Husk/ }).map((l) => l.textContent)).toEqual([rice.title, water.title]);
    expect(screen.getByText(/1 saved paper is no longer available to you/)).toBeInTheDocument();
    expect(recordsApi.list).not.toHaveBeenCalled();
    await expectNoBlockingA11yViolations(container);

    await pick("Results");
    expect(await screen.findByRole("heading", { name: "Nothing in Results yet" })).toBeInTheDocument();
  });

  // IR-1324: a new folder appears as a tile rather than opening.
  it("creates a folder on the server and shows its tile; a refusal says why and adds nothing", async () => {
    folders([folderEntry(3, "Methods")]);
    vi.mocked(libraryApi.createFolder)
      .mockResolvedValueOnce({ data: folderEntry(5, "Field work") } as Awaited<ReturnType<typeof libraryApi.createFolder>>)
      .mockRejectedValueOnce({ response: { status: 400, data: { code: "folder_limit", detail: "You have 10 folders. Delete one to make another." } } });
    renderScreen(<MyLibraryPage />, SAVED);
    await screen.findByRole("heading", { name: "No saved papers yet" });

    await newFolder("Field work");
    expect(await within(folderShelf()).findByRole("button", { name: "Field work, 0 papers" })).toBeInTheDocument();

    await newFolder("One more");
    expect(await screen.findByRole("alert")).toHaveTextContent("You have 10 folders. Delete one to make another.");
    expect(queryFolderTile("One more")).not.toBeInTheDocument();
  });

  it("does not offer a new folder once the account holds the most it may", async () => {
    folders([folderEntry(3, "Methods"), folderEntry(4, "Results")], 2);
    renderScreen(<MyLibraryPage />, SAVED);
    await screen.findByRole("heading", { name: "No saved papers yet" });

    expect(within(folderShelf()).getByRole("button", { name: "Folder" })).toBeDisabled();
    expect(within(folderShelf()).getByText("You have 2 folders, the most an account can hold.")).toBeInTheDocument();
  });

  it("takes a paper out of a folder without unsaving it", async () => {
    saves([savedEntry(water, "reading")]);
    folders([folderEntry(3, "Methods", [water.id])]);
    vi.mocked(libraryApi.removeFromFolder).mockResolvedValue({ status: 204 } as Awaited<ReturnType<typeof libraryApi.removeFromFolder>>);
    renderScreen(<MyLibraryPage />, SAVED);
    await screen.findByRole("link", { name: water.title });
    await pick("Methods");

    await userEvent.click(await screen.findByRole("button", { name: `Remove from folder: ${water.title}` }));

    expect(libraryApi.removeFromFolder).toHaveBeenCalledWith(3, water.id);
    expect(libraryApi.unsave).not.toHaveBeenCalled();
    expect(await screen.findByRole("heading", { name: "Nothing in Methods yet" })).toBeInTheDocument();
    await pick("All saved papers");
    expect(await screen.findByRole("link", { name: water.title })).toBeInTheDocument();
  });

  it("rolls a failed removal from a folder back where the reader can see it", async () => {
    saves([savedEntry(water)]);
    folders([folderEntry(3, "Methods", [water.id])]);
    vi.mocked(libraryApi.removeFromFolder).mockImplementation(failed);
    renderScreen(<MyLibraryPage />, SAVED);
    await screen.findByRole("link", { name: water.title });
    await pick("Methods");

    await userEvent.click(await screen.findByRole("button", { name: `Remove from folder: ${water.title}` }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/could not take this paper out of the folder/i);
    expect(screen.getByRole("link", { name: water.title })).toBeInTheDocument();
  });

  // IR-1324: rename and delete live on the tile's "⋯" menu, and renaming is a dialog.
  it("renames a folder on the server, and a failed delete brings the folder back visibly", async () => {
    saves([savedEntry(water)]);
    folders([folderEntry(3, "Methods", [water.id])]);
    vi.mocked(libraryApi.renameFolder).mockResolvedValue({ data: folderEntry(3, "Method papers", [water.id]) } as Awaited<ReturnType<typeof libraryApi.renameFolder>>);
    vi.mocked(libraryApi.deleteFolder).mockImplementationOnce(failed);
    const { container } = renderScreen(<MyLibraryPage />, SAVED);
    await screen.findByRole("link", { name: water.title });

    await folderAction("Methods", "Rename");
    const dialog = await screen.findByRole("dialog", { name: "Rename folder" });
    const field = within(dialog).getByRole("textbox", { name: "Folder name" });
    expect(field).toHaveValue("Methods");
    await userEvent.clear(field);
    await userEvent.type(field, "Method papers");
    await expectNoBlockingA11yViolations(container);
    await userEvent.click(within(dialog).getByRole("button", { name: "Rename" }));
    expect(await within(folderShelf()).findByRole("button", { name: "Method papers, 1 paper" })).toBeInTheDocument();
    expect(libraryApi.renameFolder).toHaveBeenCalledWith(3, "Method papers");

    await folderAction("Method papers", "Delete folder");
    expect(await screen.findByRole("alert")).toHaveTextContent(/could not delete this folder/i);
    expect(await within(folderShelf()).findByRole("button", { name: "Method papers, 1 paper" })).toBeInTheDocument();
    // The paper was never at risk: deleting a folder never deletes a save.
    expect(screen.getByRole("link", { name: water.title })).toBeInTheDocument();
    expect(libraryApi.unsave).not.toHaveBeenCalled();
  });

  // IR-1324: leaving a folder dialog just closes it, with no warning, and saves nothing.
  it("closes a folder dialog without asking, and saves nothing", async () => {
    folders([folderEntry(3, "Methods")]);
    renderScreen(<MyLibraryPage />, SAVED);
    await screen.findByRole("heading", { name: "No saved papers yet" });

    await userEvent.click(within(folderShelf()).getByRole("button", { name: "Folder" }));
    await userEvent.type(within(await screen.findByRole("dialog", { name: "New folder" })).getByRole("textbox", { name: "Folder name" }), "Half typed");
    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();

    await folderAction("Methods", "Rename");
    const rename = await screen.findByRole("dialog", { name: "Rename folder" });
    await userEvent.type(within(rename).getByRole("textbox", { name: "Folder name" }), " changed");
    await userEvent.click(within(rename).getByRole("button", { name: "Cancel" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
    expect(libraryApi.createFolder).not.toHaveBeenCalled();
    expect(libraryApi.renameFolder).not.toHaveBeenCalled();
    expect(folderTile("Methods")).toBeInTheDocument();
  });

  it("never shows one account's folders to the next account on the same browser", async () => {
    saves([savedEntry(water)]);
    folders([folderEntry(3, "First reader's folder", [water.id])]);
    const first = renderScreen(<MyLibraryPage />, SAVED);
    await screen.findByRole("link", { name: water.title });
    expect(folderTile("First reader's folder")).toBeInTheDocument();
    first.unmount();

    useAuthStore.getState().logout();
    expect(useLibraryStore.getState().folders).toEqual([]);

    saves([savedEntry(rice)]);
    folders([folderEntry(9, "Second reader's folder", [rice.id])]);
    signIn(11);
    renderScreen(<MyLibraryPage />, SAVED);

    await screen.findByRole("link", { name: rice.title });
    expect(folderTile("Second reader's folder")).toBeInTheDocument();
    expect(queryFolderTile("First reader's folder")).not.toBeInTheDocument();
    expect(localStorage.getItem("iris_record_collections")).toBeNull();
  });
});

describe("My Library: download requests (IR-743)", () => {
  const row = (name: string) => screen.getByRole("link", { name }).closest("li") as HTMLElement;

  it("lists the reader's requests in the server's order, each with its state, note and what fits", async () => {
    myDownloads([
      downloadRequest({ id: 5, record: 45, record_title: "Pending paper", created_at: "2026-10-30T08:00:00Z" }),
      downloadRequest({ id: 4, record: 44, record_title: "Granted paper", state: "granted", grant_expires_at: "2026-11-30T08:00:00Z", actions: ["download"] }),
      downloadRequest({ id: 3, record: 43, record_title: "Declined paper", state: "declined", rdco_note: "Not for commercial use.", actions: ["request_again"] }),
      downloadRequest({ id: 2, record: 42, record_title: "Revoked paper", state: "revoked", rdco_note: "", actions: ["request_again"] }),
      downloadRequest({ id: 1, record: 41, record_title: "Expired paper", state: "expired", actions: [] }),
    ]);
    const { container } = renderScreen(<MyLibraryPage />, DOWNLOADS);

    expect(await screen.findByRole("link", { name: "Pending paper" })).toHaveAttribute("href", "/records/45");
    expect(screen.getByRole("tab", { name: "Download Requests" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getAllByRole("listitem").map((li) => within(li).getByRole("link").textContent))
      .toEqual(["Pending paper", "Granted paper", "Declined paper", "Revoked paper", "Expired paper"]);

    const pending = row("Pending paper");
    expect(pending).toHaveTextContent("Asked 30 Oct 2026");
    expect(pending).toHaveTextContent("Citing its survey method.");
    expect(within(pending).getByText("Pending")).toBeInTheDocument();
    expect(within(pending).getByRole("button", { name: "Cancel request" })).toBeInTheDocument();

    const granted = row("Granted paper");
    expect(within(granted).getByText("Granted until 30 Nov 2026")).toBeInTheDocument();
    expect(within(granted).getByRole("button", { name: "Download" })).toBeInTheDocument();

    const declined = row("Declined paper");
    expect(within(declined).getByText("Declined")).toBeInTheDocument();
    expect(declined).toHaveTextContent("RDCO's note: Not for commercial use.");
    expect(within(declined).getByRole("button", { name: "Request again" })).toBeInTheDocument();

    const revoked = row("Revoked paper");
    expect(within(revoked).getByText("Revoked")).toBeInTheDocument();
    expect(revoked).toHaveTextContent("RDCO's note: No note recorded");

    // The server offered nothing on this row (a newer request counts), so nothing shows.
    const expired = row("Expired paper");
    expect(within(expired).getByText("Expired")).toBeInTheDocument();
    expect(within(expired).queryByRole("button")).not.toBeInTheDocument();

    await expectNoBlockingA11yViolations(container);
  });

  it("is offered to an author as a fourth tab, and fetched only when opened", async () => {
    renderScreen(<MyLibraryPage />);

    expect(await screen.findByRole("tab", { name: "Overview" })).toHaveAttribute("aria-selected", "true");
    expect(recordsApi.myDownloadRequests).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("tab", { name: "Download Requests" }));
    expect(await screen.findByRole("heading", { name: "No download requests yet" })).toBeInTheDocument();
    expect(recordsApi.myDownloadRequests).toHaveBeenCalledOnce();
  });

  it("cancels a pending request and re-reads the list", async () => {
    myDownloads([downloadRequest({ id: 5 })]);
    vi.mocked(recordsApi.cancelDownloadRequest).mockResolvedValue({} as Awaited<ReturnType<typeof recordsApi.cancelDownloadRequest>>);
    renderScreen(<MyLibraryPage />, DOWNLOADS);

    await userEvent.click(await screen.findByRole("button", { name: "Cancel request" }));

    expect(recordsApi.cancelDownloadRequest).toHaveBeenCalledWith(5);
    await waitFor(() => expect(recordsApi.myDownloadRequests).toHaveBeenCalledTimes(2));
  });

  it("asks again from the dialog, for that paper", async () => {
    myDownloads([downloadRequest({ id: 3, record: 43, record_title: "Declined paper", state: "declined", rdco_note: "No.", actions: ["request_again"] })]);
    vi.mocked(recordsApi.requestDownload).mockResolvedValue({} as Awaited<ReturnType<typeof recordsApi.requestDownload>>);
    renderScreen(<MyLibraryPage />, DOWNLOADS);

    await userEvent.click(await screen.findByRole("button", { name: "Request again" }));
    const dialog = await screen.findByRole("dialog", { name: "Request download access" });
    expect(dialog).toHaveTextContent("Declined paper");
    await userEvent.type(within(dialog).getByRole("textbox", { name: "Why do you need a copy?" }), "For my defence.");
    await userEvent.click(within(dialog).getByRole("button", { name: "Submit request" }));

    await waitFor(() => expect(recordsApi.requestDownload).toHaveBeenCalledWith(43, "For my defence."));
    await waitFor(() => expect(recordsApi.myDownloadRequests).toHaveBeenCalledTimes(2));
  });

  it("saves a marked copy through the download route on a granted request", async () => {
    const pdf = new Blob(["%PDF-"], { type: "application/pdf" });
    vi.mocked(recordsApi.downloadCopy).mockResolvedValue({
      data: pdf, headers: { "content-disposition": 'attachment; filename="Granted paper.pdf"' },
    } as unknown as Awaited<ReturnType<typeof recordsApi.downloadCopy>>);
    myDownloads([downloadRequest({ id: 4, record: 44, record_title: "Granted paper", state: "granted", grant_expires_at: "2026-11-30T08:00:00Z", actions: ["download"] })]);
    renderScreen(<MyLibraryPage />, DOWNLOADS);

    await userEvent.click(await screen.findByRole("button", { name: "Download" }));

    expect(recordsApi.downloadCopy).toHaveBeenCalledWith(44);
    await waitFor(() => expect(downloadBlob).toHaveBeenCalledWith(pdf, "Granted paper.pdf"));
  });

  it("says when there are none, and offers a retry when the list fails to load", async () => {
    vi.mocked(recordsApi.myDownloadRequests).mockRejectedValueOnce(new Error("offline"));
    renderScreen(<MyLibraryPage />, DOWNLOADS);

    await userEvent.click(await screen.findByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("heading", { name: "No download requests yet" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Browse Discover" })).toHaveAttribute("href", "/");
    expect(recordsApi.myDownloadRequests).toHaveBeenCalledTimes(2);
  });
});

describe("My Library follows the server's can_author (IR-1096)", () => {
  it("gives a Student the server refuses only Saved papers, Saved calls and Download requests, and no Publish", async () => {
    signIn(12, "Student", false);
    renderScreen(<MyLibraryPage />);

    expect(await screen.findByRole("heading", { name: "No saved papers yet" })).toBeInTheDocument();
    expect(screen.getAllByRole("tab").map((t) => t.textContent)).toEqual(["Saved Papers", "Saved Calls", "Download Requests"]);
    expect(screen.queryByRole("link", { name: "Publish" })).not.toBeInTheDocument();
    await waitFor(() => expect(recordsApi.mine).not.toHaveBeenCalled());
  });

  it("gives anyone the server says can author the research tabs and Publish, whatever their role", async () => {
    signIn(13, "RDCO", true);
    renderScreen(<MyLibraryPage />);

    expect(screen.getAllByRole("tab").map((t) => t.textContent)).toEqual(["Overview", "My Submissions", "Saved Papers", "Saved Calls", "Download Requests"]);
    expect(screen.getByRole("link", { name: "Publish" })).toBeInTheDocument();
  });
});

describe("Saved calls (IR-766)", () => {
  it("has its own tab, apart from saved papers, at ?section=calls", async () => {
    savedCalls.mockResolvedValue({ data: { results: [{
      call_id: 5, available: true, saved_at: "2026-11-15T08:00:00Z",
      call: {
        id: 5, opportunity_type: "journal", type_display: "Journal", title: "Energy Letters special issue",
        description: "", external_url: "https://example.org/si", due_date: "2026-12-01", location: "Online",
        areas: [], area_names: [], start_date: null, end_date: null, registration_fee: "", is_featured: false,
        posted_by: 2, posted_by_name: "RDCO", created_at: "2026-11-01T00:00:00Z", updated_at: "2026-11-01T00:00:00Z",
        days_left: 15, is_closed: false, papers_state: "accepting", papers_label: "Accepting papers",
        event_state: null, event_label: null, status: "confirmed", status_label: "Confirmed", review_reason: "",
        reviewed_at: null, can_edit: false, can_delete: false, can_remove: false, can_confirm: false,
        can_reject: false, can_feature: false, edit_returns_to_pending: false,
      },
    }] } });
    renderScreen(<MyLibraryPage />, { route: "/records/mine?section=calls" });

    expect(await screen.findByRole("article", { name: "Energy Letters special issue" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Saved Calls" })).toHaveAttribute("aria-selected", "true");
    expect(screen.queryByRole("heading", { name: "No saved papers yet" })).toBeNull();
  });
});
