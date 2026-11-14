import { beforeEach, describe, expect, it, vi } from "vitest";
import { libraryApi, type ReadingStatus, type SavedRecordEntry } from "@/api/library";
import { recordsApi } from "@/api/records";
import { RequestTimeoutError } from "@/api/requestPolicy";
import { useAuthStore } from "@/store/auth.store";
import { useLibraryStore } from "@/store/library.store";
import type { User } from "@/types/auth";
import { expectNoBlockingA11yViolations } from "@/test/axe";
import { renderScreen, screen, userEvent, waitFor, within } from "@/test/render";
import type { ClearanceStripEntry, MyResearchItem, ReaderDownloadRequest, RecordListItem } from "@/types/records";
import MyLibraryPage from "./MyLibraryPage";

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

beforeEach(() => {
  localStorage.clear();
  sessionStorage.clear();
  vi.clearAllMocks();
  mine([]);
  saves([]);
  myDownloads([]);
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
  it("opens My submissions from ?section=research, with the server's status and Continue into Publish for a draft", async () => {
    mine([ownRecord({})]);
    const { container } = renderScreen(<MyLibraryPage />, SUBMISSIONS);

    expect(await screen.findByRole("link", { name: "Community Water Monitoring" })).toHaveAttribute("href", "/records/12");
    expect(within(section("Drafts")).getByText("Draft: not yet submitted")).toBeInTheDocument();
    // Renamed from "Continue" by IR-1084, which asks for "Continue draft".
    expect(screen.getByRole("link", { name: /^Continue draft/ })).toHaveAttribute("href", "/?publish=12");
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
    expect(screen.queryByRole("button", { name: /^Delete/ })).not.toBeInTheDocument();
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
    const revision = { kind: "revision", party: "ierc", label: "Revision requested by IERC", action_label: "Submit a new version" } as const;
    const document = { kind: "document", party: "adviser", label: "Documents requested by Adviser", action_label: "Upload the documents" } as const;
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
    expect(within(waiting).getByRole("link", { name: "Submit a new version (Revision requested by IERC)" }))
      .toHaveAttribute("href", "/records/14?section=overview#revision-requested");
    const uploads = within(waiting).getAllByRole("link", { name: "Upload the documents (Documents requested by Adviser)" });
    expect(uploads.map((link) => link.getAttribute("href"))).toEqual([
      "/records/14?section=overview#documents-requested",
      "/records/15?section=overview#documents-requested",
    ]);
    expect(within(waiting).queryByRole("link", { name: "Still with the offices" })).not.toBeInTheDocument();
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

  it("folds every group, keeps Finished folded until asked for, and opens a group picked as a filter", async () => {
    mine([
      ownRecord({ id: 22, title: "Rejected paper", pipeline_status: "rejected", workflow_state: "rejected", workflow_state_label: "Archived" }),
      ownRecord({ id: 23, title: "Draft paper" }),
    ]);
    renderScreen(<MyLibraryPage />, SUBMISSIONS);

    await screen.findByRole("heading", { name: "Drafts", level: 2 });
    expect((section("Drafts") as HTMLDetailsElement).open).toBe(true);
    expect((section("Finished") as HTMLDetailsElement).open).toBe(false);

    await userEvent.click(within(screen.getByRole("group", { name: "Show" })).getByRole("button", { name: "Finished" }));
    expect((section("Finished") as HTMLDetailsElement).open).toBe(true);
    expect(screen.queryByRole("heading", { name: "Drafts", level: 2 })).not.toBeInTheDocument();
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

  it("opens an author on Overview: what waits on them, counted, and a tab to every submission", async () => {
    const document = { kind: "document", party: "adviser", label: "Documents requested by Adviser", action_label: "Upload the documents" } as const;
    mine([
      ownRecord({ id: 15, title: "Asked for a form", pipeline_status: "in_review", workflow_state: "awaiting_document", workflow_state_label: "Awaiting document", holders: [{ party: "adviser", label: "Adviser" }], submitter_status: { line: "Documents requested by Adviser: action needed", waiting_on_you: [document] } }),
      ownRecord({ id: 12 }),
    ]);
    const { container } = renderScreen(<MyLibraryPage />);

    expect(await screen.findByRole("tab", { name: "Overview" })).toHaveAttribute("aria-selected", "true");
    const waiting = screen.getByRole("region", { name: "Waiting on you" });
    expect(within(waiting).getByText("1")).toBeInTheDocument();
    expect(within(waiting).getByRole("link", { name: /^Upload the documents/ }))
      .toHaveAttribute("href", "/records/15?section=overview#documents-requested");
    expect(within(screen.getByRole("region", { name: "Recent submissions" })).getByRole("link", { name: "Community Water Monitoring" }))
      .toHaveAttribute("href", "/records/12");
    expect(screen.getByRole("region", { name: "Reading shelf" })).toHaveTextContent("Saved papers follow your account.");
    await expectNoBlockingA11yViolations(container);

    await userEvent.click(screen.getByRole("tab", { name: "My submissions" }));
    expect(screen.getByRole("tab", { name: "My submissions" })).toHaveAttribute("aria-selected", "true");
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

  it("offers a retry when the research list fails to load", async () => {
    vi.mocked(recordsApi.mine).mockRejectedValueOnce(new Error("offline"));
    renderScreen(<MyLibraryPage />);

    await userEvent.click(await screen.findByRole("button", { name: "Try again" }));
    expect(recordsApi.mine).toHaveBeenCalledTimes(2);
  });
});

describe("My Library: what each paper waits on (IR-1084)", () => {
  const inReview = (overrides: Partial<MyResearchItem> = {}) => ownRecord({
    id: 13, title: "Still with the offices", pipeline_status: "in_review", workflow_state: "in_review",
    workflow_state_label: "In review", holders: [{ party: "ierc", label: "IERC" }],
    clearance_strip: [KEPT, RESET],
    submitter_status: { line: "In specialist review: IERC", waiting_on_you: [] },
    ...overrides,
  });

  it("says on each Overview row what the paper waits on, and offers one action", async () => {
    mine([ownRecord({}), inReview()]);
    renderScreen(<MyLibraryPage />);

    const recent = await screen.findByRole("region", { name: "Recent submissions" });
    const review = within(recent).getByRole("link", { name: "Still with the offices" }).closest("li") as HTMLElement;
    expect(within(review).getByText("IERC is reviewing your version 2. Nothing to do yet.")).toBeInTheDocument();
    expect(within(review).getByRole("link", { name: /^Open review/ })).toHaveAttribute("href", "/records/13");
    expect(within(review).queryByRole("button")).not.toBeInTheDocument();

    const draft = within(recent).getByRole("link", { name: "Community Water Monitoring" }).closest("li") as HTMLElement;
    expect(within(draft).getByText("Not submitted yet. It waits on you to finish and send it.")).toBeInTheDocument();
    // The one action reopens Publish; Delete is not offered on the Overview.
    expect(within(draft).getByRole("link", { name: /^Continue draft/ })).toHaveAttribute("href", "/?publish=12");
    expect(within(draft).queryByRole("button", { name: /Delete/ })).not.toBeInTheDocument();
  });

  it("names every office still reviewing, and the Adviser or RDCO when they hold it", async () => {
    mine([
      inReview({ id: 21, title: "Two offices", holders: [{ party: "ierc", label: "IERC" }, { party: "ktto", label: "KTTO" }],
        clearance_strip: [{ ...RESET }, { ...RESET, party: "ktto", label: "KTTO" }] }),
      inReview({ id: 22, title: "With the Adviser", holders: [{ party: "adviser", label: "Adviser" }], clearance_strip: [] }),
      inReview({ id: 23, title: "Final decision", workflow_state: "final_review", holders: [{ party: "rdco", label: "RDCO Final" }], clearance_strip: [] }),
      inReview({ id: 24, title: "Already published", pipeline_status: "published", workflow_state: "published", holders: [], clearance_strip: [] }),
    ]);
    renderScreen(<MyLibraryPage />, SUBMISSIONS);

    await screen.findByRole("link", { name: "Two offices" });
    expect(screen.getByText("IERC and KTTO are reviewing your version 2. Nothing to do yet.")).toBeInTheDocument();
    expect(screen.getByText("Your Adviser is reviewing this. Nothing to do yet.")).toBeInTheDocument();
    expect(screen.getByText("RDCO is making the final decision. Nothing to do yet.")).toBeInTheDocument();
    expect(screen.getByText("Nothing is waiting on this paper.")).toBeInTheDocument();
  });

  it("says what the author owes, in the server's words, where a request is open", async () => {
    const revision = { kind: "revision", party: "ierc", label: "Revision requested by IERC", action_label: "Submit a new version" } as const;
    mine([inReview({ id: 14, title: "Asked to revise", workflow_state: "awaiting_resubmission",
      submitter_status: { line: "Revision requested by IERC: action needed", waiting_on_you: [revision] } })]);
    renderScreen(<MyLibraryPage />, SUBMISSIONS);

    await screen.findByRole("link", { name: "Asked to revise" });
    expect(screen.getByText("Waiting on you: Revision requested by IERC.")).toBeInTheDocument();
    // Its own act stays the one action; "Open review" is not added beside it.
    expect(screen.getByRole("link", { name: "Submit a new version (Revision requested by IERC)" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /^Open review/ })).not.toBeInTheDocument();
  });

  it("offers Delete draft as a quiet button that names the draft before it asks", async () => {
    mine([ownRecord({})]);
    const user = userEvent.setup();
    renderScreen(<MyLibraryPage />, SUBMISSIONS);

    const row = (await screen.findByRole("link", { name: "Community Water Monitoring" })).closest("li") as HTMLElement;
    expect(within(row).getByRole("link", { name: /^Continue draft/ })).toHaveAttribute("href", "/?publish=12");
    const remove = within(row).getByRole("button", { name: "Delete draft “Community Water Monitoring”" });
    // A ghost: no resting fill and no outline ring (a hover tint is fine).
    expect(remove.className).not.toMatch(/(^|\s)bg-/);
    expect(remove.className).not.toMatch(/(^|\s)ring-/);

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
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(recordsApi.mine).toHaveBeenCalledTimes(2);
  });

  it("shows download requests that timed out as interrupted", async () => {
    vi.mocked(recordsApi.myDownloadRequests).mockRejectedValueOnce(timeout());
    renderScreen(<MyLibraryPage />, DOWNLOADS);

    expect(await screen.findByRole("heading", { name: "This took too long" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(recordsApi.myDownloadRequests).toHaveBeenCalledTimes(2);
  });

  it("shows saved papers that timed out as interrupted, and Retry reads the account's saves again", async () => {
    vi.mocked(libraryApi.saves).mockRejectedValueOnce(timeout());
    renderScreen(<MyLibraryPage />, { route: "/records/mine?section=saved" });

    expect(await screen.findByRole("heading", { name: "This took too long" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    await waitFor(() => expect(libraryApi.saves).toHaveBeenCalledTimes(2));
  });
});

describe("My Library: reading", () => {
  it("keeps search, sort, Folder and Reading status in one toolbar, and says what stays in this browser", async () => {
    mine([ownRecord({})]);
    renderScreen(<MyLibraryPage />);

    await userEvent.click(await screen.findByRole("tab", { name: "Saved papers" }));
    expect(screen.getByText("Saves follow your account. Folders stay in this browser.")).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Folders" })).not.toBeInTheDocument();

    expect(within(screen.getByRole("combobox", { name: "Folder" })).queryByRole("option", { name: "History" })).not.toBeInTheDocument();
    await userEvent.selectOptions(screen.getByRole("combobox", { name: "Folder" }), "+ New folder…");
    await userEvent.type(screen.getByRole("textbox", { name: "New folder name" }), "Methods{Enter}");
    expect(await screen.findByRole("heading", { name: "Methods" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /liked/i })).not.toBeInTheDocument();

    await userEvent.click(within(screen.getByRole("group", { name: "Reading status" })).getByRole("button", { name: "Want to read" }));
    expect(await screen.findByRole("heading", { name: "Nothing in Want to read yet" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("tab", { name: "My submissions" }));
    expect(screen.getByRole("link", { name: "Community Water Monitoring" })).toBeInTheDocument();
  });

  // IR-743 replaces "no tablist" for a non-author: every reader has a
  // Download requests tab beside Saved papers, and nothing an author has.
  it("defaults a non-author to All saved, with Download requests beside it, and never fetches owned research", async () => {
    signIn(10, "RDCO");
    const { container } = renderScreen(<MyLibraryPage />);

    expect(await screen.findByRole("heading", { name: "No saved papers yet" })).toBeInTheDocument();
    expect(screen.getAllByRole("tab").map((t) => t.textContent)).toEqual(["Saved papers", "Download requests"]);
    expect(screen.getByRole("tab", { name: "Saved papers" })).toHaveAttribute("aria-selected", "true");
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
    await userEvent.click(within(screen.getByRole("group", { name: "Reading status" })).getByRole("button", { name: "Want to read" }));

    expect(await screen.findByRole("heading", { name: "Nothing in Want to read yet" })).toBeInTheDocument();
    expect(localStorage.getItem("iris_record_collections")).toBe(legacy);
    expect(localStorage.getItem("iris_starred_records")).toBe(JSON.stringify([rice.id]));
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
    expect(screen.getByRole("tab", { name: "Download requests" })).toHaveAttribute("aria-selected", "true");
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
    await userEvent.click(screen.getByRole("tab", { name: "Download requests" }));
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
    expect(recordsApi.myDownloadRequests).toHaveBeenCalledTimes(2);
  });
});
