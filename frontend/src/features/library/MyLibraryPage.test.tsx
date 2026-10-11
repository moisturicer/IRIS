import { beforeEach, describe, expect, it, vi } from "vitest";
import { recordsApi } from "@/api/records";
import { useAuthStore } from "@/store/auth.store";
import { expectNoBlockingA11yViolations } from "@/test/axe";
import { renderScreen, screen, userEvent, waitFor, within } from "@/test/render";
import type { MyResearchItem } from "@/types/records";
import MyLibraryPage from "./MyLibraryPage";

vi.mock("@/api/records", () => ({
  recordsApi: {
    mine: vi.fn(),
    list: vi.fn().mockResolvedValue({ data: { results: [] } }),
  },
}));

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
  vi.clearAllMocks();
  mine([]);
  useAuthStore.setState({ user: { role_name: "Student" } as NonNullable<ReturnType<typeof useAuthStore.getState>["user"]> });
});

describe("My Library: an author's research", () => {
  it("opens on the author's research, with the server's status and Continue into Publish for a draft", async () => {
    mine([ownRecord({})]);
    const { container } = renderScreen(<MyLibraryPage />);

    expect(await screen.findByRole("link", { name: "Community Water Monitoring" })).toHaveAttribute("href", "/records/12");
    expect(within(section("Drafts")).getByText("Draft")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Continue" })).toHaveAttribute("href", "/?publish=12");
    expect(recordsApi.mine).toHaveBeenCalledOnce();
    await expectNoBlockingA11yViolations(container);
  });

  it("puts what waits on the author first, with the next step and Respond into the right Paper View section", async () => {
    mine([
      ownRecord({ id: 13, title: "Still with the offices", pipeline_status: "in_review", workflow_state: "in_review", workflow_state_label: "In review", holders: [{ party: "ierc", label: "IERC" }] }),
      ownRecord({ id: 14, title: "Asked to revise", pipeline_status: "in_review", workflow_state: "awaiting_resubmission", workflow_state_label: "Revision requested", holders: [{ party: "ierc", label: "IERC" }] }),
      ownRecord({ id: 15, title: "Asked for a form", pipeline_status: "in_review", workflow_state: "awaiting_document", workflow_state_label: "Document requested", holders: [{ party: "adviser", label: "Adviser" }] }),
    ]);
    renderScreen(<MyLibraryPage />);

    await screen.findByRole("link", { name: "Asked to revise" });
    const headings = screen.getAllByRole("heading", { level: 2 }).map((h) => h.textContent);
    expect(headings.indexOf("Waiting on you")).toBeLessThan(headings.indexOf("With the offices"));

    const waiting = section("Waiting on you");
    expect(within(waiting).getByText(/submit a new version/i)).toBeInTheDocument();
    const [revise, form] = within(waiting).getAllByRole("link", { name: "Respond" });
    expect(revise).toHaveAttribute("href", "/records/14?section=review");
    expect(form).toHaveAttribute("href", "/records/15?section=files");
    expect(within(waiting).queryByRole("link", { name: "Still with the offices" })).not.toBeInTheDocument();
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
    expect(within(offices).getByText("IERC reviewing")).toBeInTheDocument();
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
  it("keeps the reading panel beside the research, says it is this browser only, and opens a folder", async () => {
    mine([ownRecord({})]);
    renderScreen(<MyLibraryPage />);

    await screen.findByRole("link", { name: "Community Water Monitoring" });
    const reading = screen.getByRole("region", { name: "Your reading" });
    expect(within(reading).getByText("Saved in this browser only.")).toBeInTheDocument();

    await userEvent.click(within(reading).getByRole("button", { name: "Want to read" }));
    expect(screen.getByRole("heading", { name: "Nothing in Want to read yet" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Back to your research" }));
    expect(screen.getByRole("link", { name: "Community Water Monitoring" })).toBeInTheDocument();
  });

  it("defaults a non-author to Want to read and never fetches owned research", async () => {
    useAuthStore.setState({ user: { role_name: "RDCO" } as NonNullable<ReturnType<typeof useAuthStore.getState>["user"]> });
    const { container } = renderScreen(<MyLibraryPage />);

    expect(await screen.findByRole("heading", { name: "Nothing in Want to read yet" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Back to your research" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Publish" })).not.toBeInTheDocument();
    await waitFor(() => expect(recordsApi.mine).not.toHaveBeenCalled());
    await expectNoBlockingA11yViolations(container);
  });

  it("opens Saved directly from ?section=saved", async () => {
    renderScreen(<MyLibraryPage />, { route: "/records/mine?section=saved" });

    expect(await screen.findByRole("heading", { name: "Nothing in Want to read yet" })).toBeInTheDocument();
  });
});
