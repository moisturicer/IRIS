import { beforeEach, describe, expect, it, vi } from "vitest";
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

/** The rail (IR-1311): every list, named once. */
const rail = () => screen.getByRole("navigation", { name: "My Library" });
const railItem = (name: string) => within(rail()).getByRole("button", { name: new RegExp(`^${name}`) });
const open = (name: string) => userEvent.click(railItem(name));
const railNames = () => within(rail()).getAllByRole("button").map((b) => b.textContent);

/** A group of All research, folded like a chapter. */
const group = (name: string) =>
  screen.getByRole("heading", { name, level: 3 }).closest("details") as HTMLDetailsElement;

/** Open a row's or a view's ⋯ menu and choose an item. */
async function choose(menu: string, item: string) {
  await userEvent.click(screen.getByRole("button", { name: menu }));
  await userEvent.click(screen.getByRole("menuitem", { name: item }));
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

  it("opens All research from ?section=research, with the server's status, and a draft's row reopens Publish", async () => {
    mine([ownRecord({})]);
    const { container } = renderScreen(<MyLibraryPage />, SUBMISSIONS);

    // The whole row is the link: a draft's opens Publish over this list
    // (IR-1258), so it has no separate "Continue draft" button (IR-1279).
    expect(await screen.findByRole("link", { name: "Community Water Monitoring" }))
      .toHaveAttribute("href", "/records/mine?section=research&publish=12");
    expect(within(group("Drafts")).getByText("Draft: not yet submitted")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /^Continue draft/ })).not.toBeInTheDocument();
    expect(railItem("All research")).toHaveAttribute("aria-current", "page");
    expect(recordsApi.mine).toHaveBeenCalledOnce();
    await expectNoBlockingA11yViolations(container);
  });

  it("deletes a draft from its ⋯ menu after one confirmation and drops its row", async () => {
    mine([ownRecord({}), ownRecord({ id: 13, title: "Still with the offices", pipeline_status: "in_review", workflow_state: "in_review", workflow_state_label: "In review", submitter_status: { line: "In review", waiting_on_you: [] } })]);
    vi.mocked(recordsApi.delete).mockResolvedValue({} as Awaited<ReturnType<typeof recordsApi.delete>>);
    const user = userEvent.setup();
    renderScreen(<MyLibraryPage />, SUBMISSIONS);

    await user.click(await screen.findByRole("button", { name: "Actions for Community Water Monitoring" }));
    await user.click(screen.getByRole("menuitem", { name: "Delete draft" }));
    const dialog = screen.getByRole("dialog", { name: "Delete this draft?" });
    expect(within(dialog).getByRole("button", { name: "Cancel" })).toHaveFocus();
    expect(recordsApi.delete).not.toHaveBeenCalled();

    await user.click(within(dialog).getByRole("button", { name: "Delete draft" }));
    await waitFor(() => expect(screen.queryByRole("link", { name: "Community Water Monitoring" })).not.toBeInTheDocument());
    expect(recordsApi.delete).toHaveBeenCalledWith(12);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    // Only a draft offers it: a row in review has nothing for its menu, so it has none.
    expect(screen.getByRole("link", { name: "Still with the offices" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Actions for Still with the offices" })).not.toBeInTheDocument();
  });

  it("keeps the draft and says why when the delete fails", async () => {
    mine([ownRecord({})]);
    vi.mocked(recordsApi.delete).mockRejectedValue({ response: { status: 400, data: { detail: "A delete decision is already pending for this record." } } });
    renderScreen(<MyLibraryPage />, SUBMISSIONS);

    await screen.findByRole("link", { name: "Community Water Monitoring" });
    await choose("Actions for Community Water Monitoring", "Delete draft");
    await userEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Delete draft" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("A delete decision is already pending for this record.");
    expect(screen.getByRole("dialog", { name: "Delete this draft?" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Community Water Monitoring" })).toBeInTheDocument();
  });

  it("puts what waits on the author first, with no button for a request: it is answered on the paper's Overview", async () => {
    const revision = { kind: "revision", party: "ierc", label: "Revision requested by IERC", action_label: "Submit a new version" } as const;
    const document = { kind: "document", party: "adviser", label: "Documents requested by Adviser", action_label: "Upload the documents" } as const;
    mine([
      ownRecord({ id: 13, title: "Still with the offices", pipeline_status: "in_review", workflow_state: "in_review", workflow_state_label: "In review", holders: [{ party: "ierc", label: "IERC" }], submitter_status: { line: "In specialist review: IERC", waiting_on_you: [] } }),
      ownRecord({ id: 14, title: "Asked to revise", pipeline_status: "in_review", workflow_state: "awaiting_resubmission", workflow_state_label: "Awaiting resubmission", holders: [{ party: "ierc", label: "IERC" }], submitter_status: { line: "Revision requested by IERC: action needed", waiting_on_you: [revision, document] } }),
      ownRecord({ id: 15, title: "Asked for a form", pipeline_status: "in_review", workflow_state: "awaiting_document", workflow_state_label: "Awaiting document", holders: [{ party: "adviser", label: "Adviser" }], submitter_status: { line: "Documents requested by Adviser: action needed", waiting_on_you: [document] } }),
    ]);
    const { container } = renderScreen(<MyLibraryPage />, SUBMISSIONS);

    await screen.findByRole("link", { name: "Asked to revise" });
    const headings = screen.getAllByRole("heading", { level: 3 }).map((h) => h.textContent);
    expect(headings.indexOf("Needs your action")).toBeLessThan(headings.indexOf("In review"));

    const waiting = group("Needs your action");
    expect(within(waiting).getByText("Revision requested by IERC: action needed")).toBeInTheDocument();
    // The requests are answered on the paper's Overview, which the title opens: no button, no menu.
    expect(within(waiting).queryByRole("link", { name: /^Submit a new version/ })).not.toBeInTheDocument();
    expect(within(waiting).queryByRole("link", { name: /^Upload the documents/ })).not.toBeInTheDocument();
    expect(within(waiting).queryByRole("button", { name: "Actions for Asked to revise" })).not.toBeInTheDocument();
    expect(within(waiting).getByRole("link", { name: "Asked to revise" })).toHaveAttribute("href", "/records/14");

    expect(within(waiting).queryByRole("link", { name: "Still with the offices" })).not.toBeInTheDocument();
    expect(within(group("In review")).getByText("In specialist review: IERC")).toBeInTheDocument();
    // The rail counts what waits on the author, and nothing else.
    expect(railItem("Needs your action")).toHaveTextContent("2");
    expect(railItem("In review")).not.toHaveTextContent(/\d/);
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
    const review = group("In review");
    // The strip is the server's words (IR-1083): kept says which version it was kept from.
    const strip = within(review).getByRole("list", { name: "Clearances" });
    expect(strip).toHaveTextContent("ITSO: Cleared · Kept from v1");
    expect(strip).toHaveTextContent("IERC: Reviewing v2 · Reset by v2");
    expect(within(review).getByRole("link", { name: "First reading" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: /With your Adviser|With the offices|With RDCO/ })).not.toBeInTheDocument();
  });

  it("renders no numeric counters in its headings", async () => {
    mine([ownRecord({ id: 31, title: "Draft one" }), ownRecord({ id: 32, title: "Draft two" })]);
    renderScreen(<MyLibraryPage />, SUBMISSIONS);

    await screen.findByRole("link", { name: "Draft one" });
    for (const heading of screen.getAllByRole("heading")) {
      expect(heading.textContent).not.toMatch(/\d/);
    }
  });

  it("folds every group, keeps Finished folded, and shows one group's rows alone when the rail picks it", async () => {
    mine([
      ownRecord({ id: 22, title: "Rejected paper", pipeline_status: "rejected", workflow_state: "rejected", workflow_state_label: "Archived" }),
      ownRecord({ id: 23, title: "Draft paper" }),
    ]);
    renderScreen(<MyLibraryPage />, SUBMISSIONS);

    await screen.findByRole("heading", { name: "Drafts", level: 3 });
    expect(group("Drafts").open).toBe(true);
    expect(group("Finished").open).toBe(false);

    await open("Finished");
    expect(railItem("Finished")).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("heading", { name: "Finished", level: 2 })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Rejected paper" })).toBeVisible();
    expect(screen.queryByRole("link", { name: "Draft paper" })).not.toBeInTheDocument();

    await open("Needs your action");
    expect(screen.getByRole("heading", { name: "Nothing is waiting on you" })).toBeInTheDocument();
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

  // IR-1311 replaces the Overview tab: an author lands on All research, which
  // already puts what waits on them first, and the rail names every list once.
  it("opens an author on All research, with one rail in place of tabs, and keeps the list in the address", async () => {
    const document = { kind: "document", party: "adviser", label: "Documents requested by Adviser", action_label: "Upload the documents" } as const;
    mine([
      ownRecord({ id: 15, title: "Asked for a form", pipeline_status: "in_review", workflow_state: "awaiting_document", workflow_state_label: "Awaiting document", holders: [{ party: "adviser", label: "Adviser" }], submitter_status: { line: "Documents requested by Adviser: action needed", waiting_on_you: [document] } }),
      ownRecord({ id: 12 }),
    ]);
    const { container } = renderScreen(<MyLibraryPage />, { route: "/records/mine" });

    expect(await screen.findByRole("link", { name: "Asked for a form" })).toHaveAttribute("href", "/records/15");
    expect(screen.queryByRole("link", { name: /^Upload the documents/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("tablist")).not.toBeInTheDocument();
    expect(railItem("All research")).toHaveAttribute("aria-current", "page");
    expect(railItem("Needs your action")).toHaveTextContent("1");
    expect(railNames()).toEqual([
      "All research", "Needs your action1 waiting", "In review", "Drafts", "Finished",
      "All saved", "Want to read", "Reading", "Completed", "History",
      "New folder", "Saved calls", "Download requests",
    ]);
    // The draft's title opens Publish over My Library (IR-1258).
    expect(screen.getByRole("link", { name: "Community Water Monitoring" })).toHaveAttribute("href", "/records/mine?publish=12");
    await expectNoBlockingA11yViolations(container);

    await open("Drafts");
    expect(railItem("Drafts")).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: "Community Water Monitoring" })).toHaveAttribute("href", "/records/mine?section=drafts&publish=12");
  });

  it("offers the same lists in one picker for a narrow page", async () => {
    mine([ownRecord({})]);
    renderScreen(<MyLibraryPage />, SUBMISSIONS);
    await screen.findByRole("link", { name: "Community Water Monitoring" });

    const picker = screen.getByRole("combobox", { name: "Show" });
    expect(picker).toHaveValue("research:all");
    await userEvent.selectOptions(picker, "Drafts");
    expect(railItem("Drafts")).toHaveAttribute("aria-current", "page");
    await userEvent.selectOptions(screen.getByRole("combobox", { name: "Show" }), "Download requests");
    expect(await screen.findByRole("heading", { name: "No download requests yet" })).toBeInTheDocument();
  });

  it("offers Publish when the author has nothing yet", async () => {
    const { container } = renderScreen(<MyLibraryPage />);

    expect(await screen.findByRole("heading", { name: "You haven’t published anything yet" })).toBeInTheDocument();
    for (const link of screen.getAllByRole("link", { name: "Publish" })) {
      expect(link).toHaveAttribute("href", "/?publish=new");
    }
    await expectNoBlockingA11yViolations(container);
  });

  it("opens Publish over the list it is on, never over Discover (IR-1258)", async () => {
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
    expect(railItem("All research")).toHaveAttribute("aria-current", "page");
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

  it("gives a row in review no button: its link opens the review", async () => {
    mine([inReview()]);
    renderScreen(<MyLibraryPage />, SUBMISSIONS);

    const link = await screen.findByRole("link", { name: "Still with the offices" });
    const row = link.closest("li") as HTMLElement;
    expect(link).toHaveAttribute("href", "/records/13");
    expect(within(row).queryByText(/Nothing to do yet/)).not.toBeInTheDocument();
    expect(within(row).queryByRole("link", { name: /^Open review/ })).not.toBeInTheDocument();
    expect(within(row).queryByRole("button")).not.toBeInTheDocument();
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

  it("folds its pane to icons that keep their names, and remembers it in this browser", async () => {
    localStorage.removeItem("iris-library-pane");
    mine([inReview({ id: 14, title: "Folding" })]);
    const { container, unmount } = renderScreen(<MyLibraryPage />, SUBMISSIONS);
    await screen.findByRole("link", { name: "Folding" });

    const toggle = screen.getByRole("button", { name: "Hide My Library lists" });
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    await userEvent.click(toggle);
    expect(screen.getByRole("button", { name: "Show My Library lists" })).toHaveAttribute("aria-expanded", "false");
    expect(railItem("In review")).toBeInTheDocument();
    await expectNoBlockingA11yViolations(container);
    unmount();

    renderScreen(<MyLibraryPage />, SUBMISSIONS);
    await screen.findByRole("link", { name: "Folding" });
    // New folder needs the width, so it opens the pane and asks for the name there.
    await userEvent.click(screen.getByRole("button", { name: "New folder" }));
    expect(screen.getByRole("textbox", { name: "New folder name" })).toHaveFocus();
    expect(screen.getByRole("button", { name: "Hide My Library lists" })).toBeInTheDocument();
    localStorage.removeItem("iris-library-pane");
  });

  it("says what the author owes in the server's words, with no button for it", async () => {
    const revision = { kind: "revision", party: "ierc", label: "Revision requested by IERC", action_label: "Submit a new version" } as const;
    mine([inReview({ id: 14, title: "Asked to revise", workflow_state: "awaiting_resubmission",
      submitter_status: { line: "Revision requested by IERC: action needed", waiting_on_you: [revision] } })]);
    renderScreen(<MyLibraryPage />, SUBMISSIONS);

    await screen.findByRole("link", { name: "Asked to revise" });
    expect(screen.getByText("Revision requested by IERC: action needed")).toBeInTheDocument();
    expect(screen.queryByText(/^Waiting on you:/)).not.toBeInTheDocument();
    // The act is on the paper's Overview, so the row has no button for it, no "Open review" and no menu.
    expect(screen.queryByRole("link", { name: /^Submit a new version/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /^Open review/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Actions for Asked to revise" })).not.toBeInTheDocument();
  });

  // IR-1311 replaces IR-1279's trash can, at the project owner's request: a
  // row's acts live in its ⋯ menu, and the row itself still continues the draft.
  it("keeps a draft's Delete in its ⋯ menu, marked as destructive, and it asks once (IR-1311)", async () => {
    mine([ownRecord({})]);
    const user = userEvent.setup();
    renderScreen(<MyLibraryPage />, SUBMISSIONS);

    const row = (await screen.findByRole("link", { name: "Community Water Monitoring" })).closest("li") as HTMLElement;
    const menu = within(row).getByRole("button", { name: "Actions for Community Water Monitoring" });
    expect(within(row).getAllByRole("button")).toEqual([menu]);
    expect(menu).toHaveAttribute("aria-haspopup", "menu");
    expect(within(row).queryByRole("link", { name: /^Continue draft/ })).not.toBeInTheDocument();

    await user.click(menu);
    const remove = screen.getByRole("menuitem", { name: "Delete draft" });
    expect(remove).toHaveClass("text-brand-dark");
    await user.click(remove);
    const dialog = screen.getByRole("dialog", { name: "Delete this draft?" });
    expect(dialog).toHaveTextContent("“Community Water Monitoring” and its files will be removed.");
    expect(recordsApi.delete).not.toHaveBeenCalled();
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
  // IR-1311 changes this test on purpose: the Folder picker and the Reading
  // status chips are gone, and the rail names each of those lists once.
  it("names every reading list in the rail, says saves follow the account, and makes a folder there", async () => {
    mine([ownRecord({})]);
    vi.mocked(libraryApi.createFolder).mockResolvedValue({ data: folderEntry(3, "Methods") } as Awaited<ReturnType<typeof libraryApi.createFolder>>);
    renderScreen(<MyLibraryPage />);
    await screen.findByRole("link", { name: "Community Water Monitoring" });

    await open("All saved");
    expect(screen.getByRole("heading", { name: "All saved", level: 2 })).toBeInTheDocument();
    expect(screen.getByText("Saves, reading status and folders follow your account.")).toBeInTheDocument();
    expect(screen.queryByRole("combobox", { name: "Folder" })).not.toBeInTheDocument();
    expect(screen.queryByRole("group", { name: "Reading status" })).not.toBeInTheDocument();
    // No grid of cards to toggle to: one ruled list.
    expect(screen.queryByRole("button", { name: /Grid view|List view/ })).not.toBeInTheDocument();

    await open("New folder");
    await userEvent.type(screen.getByRole("textbox", { name: "New folder name" }), "Methods{Enter}");
    expect(await screen.findByRole("heading", { name: "Methods", level: 2 })).toBeInTheDocument();
    expect(libraryApi.createFolder).toHaveBeenCalledWith("Methods");
    expect(railItem("Methods")).toHaveAttribute("aria-current", "page");
    expect(screen.queryByRole("button", { name: /liked/i })).not.toBeInTheDocument();

    await open("Want to read");
    expect(await screen.findByRole("heading", { name: "Nothing in Want to read yet" })).toBeInTheDocument();
    await open("All research");
    expect(screen.getByRole("link", { name: "Community Water Monitoring" })).toBeInTheDocument();
  });

  // IR-743, IR-1311: every reader has the reading, folder and request lists,
  // and nothing an author has.
  it("defaults a non-author to All saved, with no research lists, and never fetches owned research", async () => {
    signIn(10, "RDCO");
    const { container } = renderScreen(<MyLibraryPage />);

    expect(await screen.findByRole("heading", { name: "No saved papers yet" })).toBeInTheDocument();
    expect(railNames()).toEqual(["All saved", "Want to read", "Reading", "Completed", "History", "New folder", "Saved calls", "Download requests"]);
    expect(railItem("All saved")).toHaveAttribute("aria-current", "page");
    expect(screen.queryByRole("link", { name: "Publish" })).not.toBeInTheDocument();
    await waitFor(() => expect(recordsApi.mine).not.toHaveBeenCalled());
    await expectNoBlockingA11yViolations(container);
  });

  it("sends a non-author's old research link to All saved", async () => {
    signIn(10, "RDCO");
    renderScreen(<MyLibraryPage />, SUBMISSIONS);

    expect(await screen.findByRole("heading", { name: "No saved papers yet" })).toBeInTheDocument();
    expect(recordsApi.mine).not.toHaveBeenCalled();
  });

  it("opens Saved directly from ?section=saved", async () => {
    renderScreen(<MyLibraryPage />, { route: "/records/mine?section=saved" });

    expect(await screen.findByRole("heading", { name: "No saved papers yet" })).toBeInTheDocument();
    // Audit LAY-06 (IR-1098): an empty page names the next useful step.
    expect(screen.getByRole("link", { name: "Browse Discover" })).toHaveAttribute("href", "/");
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

    await open("Reading");
    expect(await screen.findByRole("link", { name: rice.title })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: water.title })).not.toBeInTheDocument();
  });

  it("sets a saved paper's Reading status from its ⋯ menu, and choosing the checked one clears it", async () => {
    saves([savedEntry(water, "want_to_read")]);
    vi.mocked(libraryApi.save).mockImplementation(async (id, body) => ({
      data: { ...savedEntry(water, (body as { reading_status?: ReadingStatus | null }).reading_status ?? null), record_id: id },
    }) as Awaited<ReturnType<typeof libraryApi.save>>);
    renderScreen(<MyLibraryPage />, { route: "/records/mine?section=saved" });
    await screen.findByRole("link", { name: water.title });

    await userEvent.click(screen.getByRole("button", { name: `Actions for ${water.title}` }));
    // Reading status opens as a flyout beside its item.
    await userEvent.click(screen.getByRole("menuitem", { name: "Reading status" }));
    expect(screen.getByRole("menuitemradio", { name: "Want to read" })).toHaveAttribute("aria-checked", "true");
    expect(screen.getByRole("menuitemradio", { name: "Reading" })).toHaveAttribute("aria-checked", "false");
    await userEvent.click(screen.getByRole("menuitemradio", { name: "Reading" }));
    expect(libraryApi.save).toHaveBeenLastCalledWith(water.id, { reading_status: "reading" });

    await userEvent.click(screen.getByRole("button", { name: `Actions for ${water.title}` }));
    await userEvent.click(screen.getByRole("menuitem", { name: "Reading status" }));
    await userEvent.click(screen.getByRole("menuitemradio", { name: "Reading" }));
    expect(libraryApi.save).toHaveBeenLastCalledWith(water.id, { reading_status: null });
    // Clearing a status never unsaves.
    expect(libraryApi.unsave).not.toHaveBeenCalled();
  });

  it("offers Cite in a paper's menu only when it is published (IR-1305)", async () => {
    const proposal = { ...paper(43, "Soil moisture sensing for upland farms"), record_type_name: "Proposal", pipeline_status: "approved" } as RecordListItem;
    saves([savedEntry(water), savedEntry(proposal)]);
    renderScreen(<MyLibraryPage />, { route: "/records/mine?section=saved" });
    await screen.findByRole("link", { name: water.title });

    await userEvent.click(screen.getByRole("button", { name: `Actions for ${water.title}` }));
    expect(screen.getByRole("menuitem", { name: "Cite" })).toBeInTheDocument();
    await userEvent.keyboard("{Escape}");

    await userEvent.click(screen.getByRole("button", { name: `Actions for ${proposal.title}` }));
    expect(screen.queryByRole("menuitem", { name: "Cite" })).not.toBeInTheDocument();
    // Removing a saved Proposal from the Library still works.
    expect(screen.getByRole("menuitem", { name: "Remove from library" })).toBeInTheDocument();
  });

  it("removes papers together after Select papers in the view's menu", async () => {
    saves([savedEntry(water), savedEntry(rice)]);
    renderScreen(<MyLibraryPage />, { route: "/records/mine?section=saved" });
    await screen.findByRole("link", { name: water.title });
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();

    await choose("All saved options", "Select papers");
    const bar = screen.getByRole("region", { name: "Selected papers" });
    expect(within(bar).getByRole("button", { name: "Remove from library" })).toBeDisabled();
    await userEvent.click(screen.getByRole("checkbox", { name: `Select ${water.title}` }));
    await userEvent.click(screen.getByRole("checkbox", { name: `Select ${rice.title}` }));
    expect(bar).toHaveTextContent("2 papers chosen");
    await userEvent.click(within(bar).getByRole("button", { name: "Remove from library" }));

    expect(libraryApi.unsave).toHaveBeenCalledWith(water.id);
    expect(libraryApi.unsave).toHaveBeenCalledWith(rice.id);
    expect(screen.queryByRole("region", { name: "Selected papers" })).not.toBeInTheDocument();
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
    await screen.findByRole("link", { name: water.title });

    await choose(`Actions for ${water.title}`, "Remove from library");

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
    await open("History");
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
    await open("Want to read");

    expect(await screen.findByRole("heading", { name: "Nothing in Want to read yet" })).toBeInTheDocument();
    expect(within(rail()).queryByRole("button", { name: "Old browser folder" })).not.toBeInTheDocument();
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
    await screen.findByRole("heading", { name: "All saved", level: 2 });
    await open("History");
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

  it("opens History directly from ?section=history", async () => {
    history([visitEntry(water)]);
    renderScreen(<MyLibraryPage />, { route: "/records/mine?section=history" });

    expect(await screen.findByRole("link", { name: water.title })).toBeInTheDocument();
    expect(railItem("History")).toHaveAttribute("aria-current", "page");
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
    await screen.findByRole("link", { name: water.title });

    await choose("History options", "Clear history");

    expect(libraryApi.clearHistory).toHaveBeenCalledTimes(1);
    expect(await screen.findByRole("heading", { name: "No reading history yet" })).toBeInTheDocument();
  });

  it("keeps the history and says so when clearing fails", async () => {
    history([visitEntry(water)]);
    vi.mocked(libraryApi.clearHistory).mockRejectedValue(new Error("offline"));
    await openHistory();
    await screen.findByRole("link", { name: water.title });

    await choose("History options", "Clear history");

    expect(await screen.findByRole("alert")).toHaveTextContent(/could not clear your history/i);
    expect(screen.getByRole("link", { name: water.title })).toBeInTheDocument();
  });

  it("pauses history on the account, keeping what is listed, and can resume it", async () => {
    history([visitEntry(water)]);
    vi.mocked(libraryApi.updatePreferences).mockImplementation(async (body) => ({ data: body }) as Awaited<ReturnType<typeof libraryApi.updatePreferences>>);
    await openHistory();
    await screen.findByRole("link", { name: water.title });

    await choose("History options", "Pause history");

    expect(libraryApi.updatePreferences).toHaveBeenCalledWith({ keep_history: false });
    expect(await screen.findByText(/history is paused/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: water.title })).toBeInTheDocument();

    await choose("History options", "Resume history");
    expect(libraryApi.updatePreferences).toHaveBeenLastCalledWith({ keep_history: true });
  });

  it("opens with history paused when the account says so", async () => {
    history([], false);
    await openHistory();

    expect(await screen.findByRole("heading", { name: "History is paused" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "History options" }));
    expect(screen.getByRole("menuitem", { name: "Resume history" })).toBeInTheDocument();
  });

  it("says the history is safe when loading it fails, and Try again reads it again", async () => {
    vi.mocked(libraryApi.history).mockRejectedValueOnce(new Error("offline"));
    await openHistory();

    expect(await screen.findByText("Your history is safe in your account; only loading it failed.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));

    await waitFor(() => expect(libraryApi.history).toHaveBeenCalledTimes(2));
    expect(await screen.findByRole("heading", { name: "No reading history yet" })).toBeInTheDocument();
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
  const failed = () => Promise.reject(new Error("offline"));

  it("reads the account's folders from the server and shows a folder's saves in filing order", async () => {
    saves([savedEntry(water, "reading"), savedEntry(rice), { record_id: 77, available: false }]);
    folders([folderEntry(3, "Methods", [rice.id, 77, water.id]), folderEntry(4, "Results")]);
    const { container } = renderScreen(<MyLibraryPage />, SAVED);

    await screen.findByRole("link", { name: water.title });
    await open("Methods");

    expect(await screen.findByRole("heading", { name: "Methods", level: 2 })).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: /Rainwater|Rice Husk/ }).map((l) => l.textContent)).toEqual([rice.title, water.title]);
    expect(screen.getByText(/1 saved paper is no longer available to you/)).toBeInTheDocument();
    expect(recordsApi.list).not.toHaveBeenCalled();
    await expectNoBlockingA11yViolations(container);

    await open("Results");
    expect(await screen.findByRole("heading", { name: "Nothing in Results yet" })).toBeInTheDocument();
  });

  it("opens a folder directly from its address", async () => {
    saves([savedEntry(water)]);
    folders([folderEntry(3, "Methods", [water.id])]);
    renderScreen(<MyLibraryPage />, { route: "/records/mine?section=folder&folder=3" });

    expect(await screen.findByRole("heading", { name: "Methods", level: 2 })).toBeInTheDocument();
    expect(railItem("Methods")).toHaveAttribute("aria-current", "page");
  });

  it("creates a folder on the server and opens it; a refusal says why and adds nothing", async () => {
    folders([folderEntry(3, "Methods")]);
    vi.mocked(libraryApi.createFolder)
      .mockResolvedValueOnce({ data: folderEntry(5, "Field work") } as Awaited<ReturnType<typeof libraryApi.createFolder>>)
      .mockRejectedValueOnce({ response: { status: 400, data: { code: "folder_limit", detail: "You have 10 folders. Delete one to make another." } } });
    renderScreen(<MyLibraryPage />, SAVED);
    await screen.findByRole("heading", { name: "No saved papers yet" });

    await open("New folder");
    await userEvent.type(screen.getByRole("textbox", { name: "New folder name" }), "Field work{Enter}");
    expect(await screen.findByRole("heading", { name: "Field work", level: 2 })).toBeInTheDocument();

    await open("New folder");
    await userEvent.type(screen.getByRole("textbox", { name: "New folder name" }), "One more{Enter}");
    expect(await screen.findByRole("alert")).toHaveTextContent("You have 10 folders. Delete one to make another.");
    expect(within(rail()).queryByRole("button", { name: "One more" })).not.toBeInTheDocument();
  });

  it("does not offer a new folder once the account holds the most it may, and says so", async () => {
    folders([folderEntry(3, "Methods"), folderEntry(4, "Results")], 2);
    renderScreen(<MyLibraryPage />, SAVED);
    await screen.findByRole("heading", { name: "No saved papers yet" });

    expect(within(rail()).queryByRole("button", { name: "New folder" })).not.toBeInTheDocument();
    expect(within(rail()).getByText("No room for a new folder (2 is the most)")).toBeInTheDocument();
    const picker = screen.getByRole("combobox", { name: "Show" });
    expect(within(picker).queryByRole("option", { name: "+ New folder…" })).not.toBeInTheDocument();
    expect(within(picker).getByRole("option", { name: "No room for a new folder (2 is the most)" })).toBeDisabled();
  });

  it("takes a paper out of a folder without unsaving it", async () => {
    saves([savedEntry(water, "reading")]);
    folders([folderEntry(3, "Methods", [water.id])]);
    vi.mocked(libraryApi.removeFromFolder).mockResolvedValue({ status: 204 } as Awaited<ReturnType<typeof libraryApi.removeFromFolder>>);
    renderScreen(<MyLibraryPage />, SAVED);
    await screen.findByRole("link", { name: water.title });
    await open("Methods");
    await screen.findByRole("heading", { name: "Methods", level: 2 });

    await choose(`Actions for ${water.title}`, "Remove from folder");

    expect(libraryApi.removeFromFolder).toHaveBeenCalledWith(3, water.id);
    expect(libraryApi.unsave).not.toHaveBeenCalled();
    expect(await screen.findByRole("heading", { name: "Nothing in Methods yet" })).toBeInTheDocument();
    await open("All saved");
    expect(await screen.findByRole("link", { name: water.title })).toBeInTheDocument();
  });

  it("rolls a failed removal from a folder back where the reader can see it", async () => {
    saves([savedEntry(water)]);
    folders([folderEntry(3, "Methods", [water.id])]);
    vi.mocked(libraryApi.removeFromFolder).mockImplementation(failed);
    renderScreen(<MyLibraryPage />, SAVED);
    await screen.findByRole("link", { name: water.title });
    await open("Methods");
    await screen.findByRole("heading", { name: "Methods", level: 2 });

    await choose(`Actions for ${water.title}`, "Remove from folder");

    expect(await screen.findByRole("alert")).toHaveTextContent(/could not take this paper out of the folder/i);
    expect(screen.getByRole("link", { name: water.title })).toBeInTheDocument();
  });

  it("renames a folder from its menu, and a failed delete brings the folder back visibly", async () => {
    saves([savedEntry(water)]);
    folders([folderEntry(3, "Methods", [water.id])]);
    vi.mocked(libraryApi.renameFolder).mockResolvedValue({ data: folderEntry(3, "Method papers", [water.id]) } as Awaited<ReturnType<typeof libraryApi.renameFolder>>);
    vi.mocked(libraryApi.deleteFolder).mockImplementationOnce(failed);
    renderScreen(<MyLibraryPage />, SAVED);
    await screen.findByRole("link", { name: water.title });
    await open("Methods");
    await screen.findByRole("heading", { name: "Methods", level: 2 });

    await choose("Methods options", "Rename folder");
    const field = screen.getByRole("textbox", { name: "Rename Methods" });
    await userEvent.clear(field);
    await userEvent.type(field, "Method papers{Enter}");
    expect(await screen.findByRole("heading", { name: "Method papers", level: 2 })).toBeInTheDocument();
    expect(libraryApi.renameFolder).toHaveBeenCalledWith(3, "Method papers");

    await choose("Method papers options", "Delete folder");
    expect(await screen.findByRole("alert")).toHaveTextContent(/could not delete this folder/i);
    expect(railItem("Method papers")).toBeInTheDocument();
    // The paper was never at risk: deleting a folder never deletes a save.
    expect(screen.getByRole("link", { name: water.title })).toBeInTheDocument();
    expect(libraryApi.unsave).not.toHaveBeenCalled();
  });

  it("never shows one account's folders to the next account on the same browser", async () => {
    saves([savedEntry(water)]);
    folders([folderEntry(3, "First reader's folder", [water.id])]);
    const first = renderScreen(<MyLibraryPage />, SAVED);
    await screen.findByRole("link", { name: water.title });
    expect(railItem("First reader's folder")).toBeInTheDocument();
    first.unmount();

    useAuthStore.getState().logout();
    expect(useLibraryStore.getState().folders).toEqual([]);

    saves([savedEntry(rice)]);
    folders([folderEntry(9, "Second reader's folder", [rice.id])]);
    signIn(11);
    renderScreen(<MyLibraryPage />, SAVED);

    await screen.findByRole("link", { name: rice.title });
    expect(railItem("Second reader's folder")).toBeInTheDocument();
    expect(within(rail()).queryByRole("button", { name: "First reader's folder" })).not.toBeInTheDocument();
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
    expect(railItem("Download requests")).toHaveAttribute("aria-current", "page");
    const list = screen.getByRole("link", { name: "Pending paper" }).closest("ul") as HTMLElement;
    expect(within(list).getAllByRole("listitem").map((li) => within(li).getByRole("link").textContent))
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

  it("is offered to an author in the rail, and fetched only when opened", async () => {
    renderScreen(<MyLibraryPage />);

    expect(await screen.findByRole("heading", { name: "You haven’t published anything yet" })).toBeInTheDocument();
    expect(recordsApi.myDownloadRequests).not.toHaveBeenCalled();
    await open("Download requests");
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
  it("gives a Student the server refuses only the reading, folder and request lists, and no Publish", async () => {
    signIn(12, "Student", false);
    renderScreen(<MyLibraryPage />);

    expect(await screen.findByRole("heading", { name: "No saved papers yet" })).toBeInTheDocument();
    expect(within(rail()).queryByRole("button", { name: "All research" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Publish" })).not.toBeInTheDocument();
    await waitFor(() => expect(recordsApi.mine).not.toHaveBeenCalled());
  });

  it("gives anyone the server says can author the research lists and Publish, whatever their role", async () => {
    signIn(13, "RDCO", true);
    renderScreen(<MyLibraryPage />);

    expect(railItem("All research")).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: "Publish" })).toBeInTheDocument();
  });
});

describe("Saved calls (IR-766)", () => {
  it("has its own list, apart from saved papers, at ?section=calls", async () => {
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
    expect(railItem("Saved calls")).toHaveAttribute("aria-current", "page");
    expect(screen.queryByRole("heading", { name: "No saved papers yet" })).toBeNull();
  });
});
