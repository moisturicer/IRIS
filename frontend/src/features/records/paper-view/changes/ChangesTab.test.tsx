/**
 * The Changes tab (ADR-058 §3 as amended 2026-11-08, IR-873): what it shows
 * for each state the server sends, how it marks a change, where *Show in
 * paper* goes, and the threads it lists under a section. Every query goes
 * through the accessible tree; no wording names how a text was read.
 */
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { expectNoBlockingA11yViolations } from "@/test/axe";
import { act, renderScreen, screen, waitFor, within } from "@/test/render";
import type { RecordVersion, SectionComparison, VersionChange, VersionComparisonPayload } from "@/types/records";

import { comment } from "../threads/threadFixtures";
import { groupThreads } from "../threads/threadModel";
import { ChangesTab } from "./ChangesTab";
import { PREPARING_POLL_MS } from "./useVersionComparison";

const api = vi.hoisted(() => ({ compareVersions: vi.fn(), markSectionViewed: vi.fn() }));
vi.mock("@/api/records", () => ({ recordsApi: api }));

const VERSIONS = [1, 2, 3].map((number) => ({
  number, cause: number === 1 ? "submission" : "revision", cause_label: number === 1 ? "Submitted" : "Revised",
  created_at: "2026-11-01T00:00:00Z", created_by_name: null, manuscript_url: `/m/${number}`,
})) as RecordVersion[];

const REGION = { page: 2, left: 0.1, top: 0.4, right: 0.9, bottom: 0.45 };
const side = (section: string, text: string, page = 2) => ({ section, text, page, regions: [{ ...REGION, page }] });

const NUMBER: VersionChange = {
  kind: "changed", certainty: "established",
  from: side("background", "Metro Cebu generates about 2,000 tonnes of waste a day."),
  to: side("background", "Metro Cebu generates about 2,500 tonnes of waste a day."),
  words: [
    { op: "equal", text: "Metro Cebu generates about" }, { op: "delete", text: "2,000" },
    { op: "insert", text: "2,500" }, { op: "equal", text: "tonnes of waste a day." },
  ],
};

const section = (key: string, heading: string, over: Partial<SectionComparison> = {}): SectionComparison => ({
  status: "unchanged", renamed: false, moved: false,
  from: { key, heading, page: 2 }, to: { key, heading, page: 2 },
  changes: [], counts: { changed: 0, added: 0, removed: 0, moved: 0 }, ...over,
});

function ready(over: Partial<VersionComparisonPayload> = {}): VersionComparisonPayload {
  return {
    state: "ready", message: null, from: 2, to: 3, mode: "sections", changes: [], notices: [],
    documents: [{ slot: "Manuscript", status: "replaced", from: 1, to: 2 }],
    counts: { changed: 1, added: 0, removed: 0, moved: 0, sections_renamed: 0, sections_moved: 0 },
    sections: [
      section("title", "Title page"),
      section("background", "1.1 Background of the Study", {
        status: "changed", changes: [NUMBER], counts: { changed: 1, added: 0, removed: 0, moved: 0 },
      }),
    ],
    threads: [],
    ...over,
  };
}

const THREADS = groupThreads([
  comment({ id: 41, party: "itso", party_label: "ITSO", severity: "must_fix", state: "open" }),
]).sent;

function open(over: Partial<Parameters<typeof ChangesTab>[0]> = {}) {
  const onShowInPaper = vi.fn();
  const onOpenThread = vi.fn();
  const view = renderScreen(
    <ChangesTab recordId={7} versions={VERSIONS} threads={THREADS}
      onShowInPaper={onShowInPaper} onOpenThread={onOpenThread} {...over} />,
  );
  return { ...view, onShowInPaper, onOpenThread };
}

/** The line that sums a ready comparison up. */
const summary = async () => (await screen.findByText("v2 → v3:")).parentElement;

beforeEach(() => {
  api.markSectionViewed.mockReset().mockResolvedValue({ data: { viewed: true } });
  api.compareVersions.mockReset().mockResolvedValue({ data: ready() });
});

afterEach(() => {
  vi.useRealTimers();
});

describe("a ready comparison", () => {
  it("summarises the pair and lists only the changed sections", async () => {
    open();
    expect(await summary()).toHaveTextContent("v2 → v3: 1 changed");
    const outline = screen.getByRole("navigation", { name: "Changed sections" });
    expect(within(outline).getAllByRole("button").map((b) => b.textContent))
      .toEqual(["1.1 Background of the Study1 changed"]);
    expect(screen.queryByRole("heading", { name: "Title page" })).toBeNull();
    expect(api.compareVersions).toHaveBeenCalledWith(7, undefined, expect.anything());
  });

  it("marks the changed words in words, not by colour alone", async () => {
    open();
    const change = await screen.findByRole("article", { name: "Changed, page 2" });
    expect(within(change).getByText("Changed")).toBeInTheDocument();
    expect(change.querySelector("del")).toHaveTextContent("Removed: 2,000");
    expect(change.querySelector("ins")).toHaveTextContent("Added: 2,500");
  });

  it("shows each side apart in the side-by-side view", async () => {
    const user = userEvent.setup();
    open();
    await screen.findByRole("article", { name: "Changed, page 2" });
    await user.click(screen.getByRole("radio", { name: "Side by side" }));
    const change = screen.getByRole("article", { name: "Changed, page 2" });
    expect(within(change).getByText("v2")).toBeInTheDocument();
    expect(within(change).getByText("v3")).toBeInTheDocument();
    expect(change.querySelectorAll("del")).toHaveLength(1);
    expect(change.querySelectorAll("ins")).toHaveLength(1);
  });

  it("opens either Version at the change's page", async () => {
    const user = userEvent.setup();
    const { onShowInPaper } = open();
    await user.click(await screen.findByRole("button", { name: "Show in v3, p. 2" }));
    expect(onShowInPaper).toHaveBeenLastCalledWith({ version: 3, page: 2, regions: [REGION] });
    await user.click(screen.getByRole("button", { name: "Show in v2, p. 2" }));
    expect(onShowInPaper).toHaveBeenLastCalledWith({ version: 2, page: 2, regions: [REGION] });
  });

  it("shows the unchanged sections on request", async () => {
    const user = userEvent.setup();
    open();
    await user.click(await screen.findByRole("button", { name: "Show 1 unchanged section" }));
    expect(screen.getByRole("heading", { name: "Title page" })).toBeInTheDocument();
    expect(screen.getByText("Same as v2")).toBeInTheDocument();
  });

  it("says what happened to a section that was renamed or moved", async () => {
    api.compareVersions.mockResolvedValue({ data: ready({ sections: [
      section("problem", "1.2 Research Questions", {
        renamed: true, moved: true, from: { key: "problem", heading: "1.2 Statement of the Problem", page: 2 },
      }),
    ] }) });
    open();
    expect(await screen.findByText('Renamed from "1.2 Statement of the Problem"')).toBeInTheDocument();
    expect(screen.getByText("Moved")).toBeInTheDocument();
  });

  it("lists a section's earlier threads and opens one", async () => {
    const user = userEvent.setup();
    api.compareVersions.mockResolvedValue({ data: ready({ threads: [{ thread: 41, side: "from", page: 2, section: 1 }] }) });
    const { onOpenThread } = open();
    const list = await screen.findByRole("list", { name: "Threads in this section" });
    await user.click(within(list).getByRole("button", { name: "Thread 1 · ITSO, Must fix, open" }));
    expect(onOpenThread).toHaveBeenCalledWith(THREADS[0]);
  });

  it("asks for the pair chosen", async () => {
    const user = userEvent.setup();
    open();
    await summary();
    await user.selectOptions(screen.getByRole("combobox", { name: "Compare" }), "1");
    await waitFor(() => expect(api.compareVersions).toHaveBeenLastCalledWith(7, { from: 1, to: 3 }, expect.anything()));
  });
});

describe("how far a comparison can be trusted", () => {
  it("shows the server's notice and marks a change that may be missed text", async () => {
    const message = "Parts of this comparison may be unreliable. Some text in v3 may not have been read. Check removed passages against the PDF before relying on them.";
    api.compareVersions.mockResolvedValue({ data: ready({
      notices: [{ code: "may_be_unreliable", side: "to", message }],
      counts: { changed: 0, added: 0, removed: 1, moved: 0, sections_renamed: 0, sections_moved: 0 },
      sections: [section("background", "1.1 Background of the Study", {
        status: "changed", counts: { changed: 0, added: 0, removed: 1, moved: 0 },
        changes: [{ kind: "removed", certainty: "tentative", from: side("background", "A paragraph."), to: null }],
      })],
    }) });
    open();
    expect(await screen.findByRole("note")).toHaveTextContent(message);
    const change = screen.getByRole("article", { name: "Removed, page 2" });
    expect(within(change).getByText("Check against the PDF")).toBeInTheDocument();
  });

  it("lists changes by page when sections couldn't be identified", async () => {
    api.compareVersions.mockResolvedValue({ data: ready({
      mode: "pages", sections: [],
      notices: [{ code: "sections_unidentified", side: "to", message: "Sections couldn't be identified in v3, so changes are listed by page." }],
      changes: [NUMBER, { ...NUMBER, from: side("document", "x", 5), to: side("document", "y", 5) }],
      counts: { changed: 2, added: 0, removed: 0, moved: 0, sections_renamed: 0, sections_moved: 0 },
    }) });
    open();
    const outline = await screen.findByRole("navigation", { name: "Changed pages" });
    expect(within(outline).getAllByRole("button").map((b) => b.textContent)).toEqual(["Page 21 changed", "Page 51 changed"]);
    expect(screen.getByRole("heading", { name: "Page 5" })).toBeInTheDocument();
  });
});

describe("when there is nothing to show yet", () => {
  it("says it is preparing, then shows the comparison once ready", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    api.compareVersions
      .mockResolvedValueOnce({ data: { state: "preparing", message: "Preparing the comparison…", from: 2, to: 3, documents: [] } })
      .mockResolvedValue({ data: ready() });
    open();
    expect(await screen.findByText("Preparing the comparison…")).toBeInTheDocument();
    await act(async () => { await vi.advanceTimersByTimeAsync(PREPARING_POLL_MS); });
    expect(await summary()).toHaveTextContent("v2 → v3: 1 changed");
  });

  it("offers a retry when the comparison isn't available", async () => {
    const user = userEvent.setup();
    api.compareVersions
      .mockResolvedValueOnce({ data: { state: "unavailable", message: "This comparison isn't available right now.", from: 2, to: 3, documents: [] } })
      .mockResolvedValue({ data: ready() });
    open();
    await user.click(await screen.findByRole("button", { name: "Try again" }));
    expect(await summary()).toHaveTextContent("v2 → v3: 1 changed");
  });

  it("says a Version has no text and still lists the documents", async () => {
    api.compareVersions.mockResolvedValue({ data: {
      state: "no_text", message: "No text for v2, so it can't be compared.", from: 2, to: 3,
      documents: [{ slot: "Manuscript", status: "replaced", from: 1, to: 2 }],
    } });
    open();
    expect(await screen.findByText("No text for v2, so it can't be compared.")).toBeInTheDocument();
    expect(screen.getByText("Replaced in v3")).toBeInTheDocument();
  });

  it("shows a failed request, and a wrong shape, as a failure it can retry", async () => {
    api.compareVersions.mockResolvedValue({ data: { results: [] } });
    open();
    expect(await screen.findByRole("alert")).toHaveTextContent("Couldn't load the comparison.");
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
  });

  it("shows the server's reason for a pair it refuses", async () => {
    api.compareVersions.mockRejectedValue({ response: { status: 400, data: { detail: "Choose two different Versions." } } });
    open();
    expect(await screen.findByRole("alert")).toHaveTextContent("Choose two different Versions.");
  });
});

describe("Viewed marks (IR-877)", () => {
  const viewedBox = (name: string) => screen.findByRole("checkbox", { name: `Viewed: ${name}` });

  it("ticks a section viewed, tells the server which, and folds its changes away", async () => {
    const user = userEvent.setup();
    open();
    const box = await viewedBox("1.1 Background of the Study");
    expect(box).not.toBeChecked();
    expect(screen.getByRole("article", { name: "Changed, page 2" })).toBeInTheDocument();

    await user.click(box);

    expect(api.markSectionViewed).toHaveBeenCalledWith(7, { from: 2, to: 3, side: "to", key: "background", viewed: true });
    expect(box).toBeChecked();
    expect(screen.queryByRole("article", { name: "Changed, page 2" })).not.toBeInTheDocument();
    // The list of changed sections says so too.
    expect(within(screen.getByRole("navigation", { name: "Changed sections" })).getByText(/Viewed/)).toBeInTheDocument();
  });

  it("shows a section the server says is viewed as ticked, and unticking it sends that", async () => {
    api.compareVersions.mockResolvedValue({ data: ready({ sections: [
      section("background", "1.1 Background of the Study", {
        status: "changed", changes: [NUMBER], counts: { changed: 1, added: 0, removed: 0, moved: 0 }, viewed: true,
      }),
    ] }) });
    api.markSectionViewed.mockResolvedValue({ data: { viewed: false } });
    const user = userEvent.setup();
    open();
    const box = await viewedBox("1.1 Background of the Study");
    expect(box).toBeChecked();

    await user.click(box);

    expect(api.markSectionViewed).toHaveBeenCalledWith(7, expect.objectContaining({ key: "background", viewed: false }));
    expect(box).not.toBeChecked();
    expect(screen.getByRole("article", { name: "Changed, page 2" })).toBeInTheDocument();
  });

  it("marks a removed section on its earlier side", async () => {
    api.compareVersions.mockResolvedValue({ data: ready({ sections: [
      section("methods", "Methods", { status: "removed", to: null }),
    ] }) });
    const user = userEvent.setup();
    open();

    await user.click(await viewedBox("Methods"));

    expect(api.markSectionViewed).toHaveBeenCalledWith(7, expect.objectContaining({ side: "from", key: "methods" }));
  });

  it("waits for one answer before the box can be clicked again", async () => {
    let answer: (value: unknown) => void = () => {};
    api.markSectionViewed.mockReturnValue(new Promise((resolve) => { answer = resolve; }));
    const user = userEvent.setup();
    open();
    const box = await viewedBox("1.1 Background of the Study");

    await user.click(box);
    expect(box).toBeDisabled();
    await act(async () => answer({ data: { viewed: true } }));

    expect(box).toBeEnabled();
    expect(box).toBeChecked();
    expect(api.markSectionViewed).toHaveBeenCalledTimes(1);
  });

  it("puts the box back and says so when the server refuses", async () => {
    api.markSectionViewed.mockRejectedValue({ response: { status: 400, data: { detail: "That section isn't in this comparison." } } });
    const user = userEvent.setup();
    open();
    const box = await viewedBox("1.1 Background of the Study");

    await user.click(box);

    expect(await screen.findByText("That section isn't in this comparison.")).toBeInTheDocument();
    expect(box).not.toBeChecked();
  });

  it("reads an answer of the wrong shape as a failure", async () => {
    api.markSectionViewed.mockResolvedValue({ data: { ok: 1 } });
    const user = userEvent.setup();
    open();
    const box = await viewedBox("1.1 Background of the Study");

    await user.click(box);

    expect(await screen.findByText("Couldn't save that. Please try again.")).toBeInTheDocument();
    expect(box).not.toBeChecked();
  });

  it("treats a `viewed` of the wrong shape as not viewed", async () => {
    api.compareVersions.mockResolvedValue({ data: ready({ sections: [
      { ...section("background", "1.1 Background of the Study", {
        status: "changed", changes: [NUMBER], counts: { changed: 1, added: 0, removed: 0, moved: 0 },
      }), viewed: "yes" as unknown as boolean },
    ] }) });
    open();
    expect(await viewedBox("1.1 Background of the Study")).not.toBeChecked();
  });

  it("offers no Viewed box when the comparison is listed by page", async () => {
    api.compareVersions.mockResolvedValue({ data: ready({ mode: "pages", sections: [], changes: [NUMBER] }) });
    open();
    await screen.findByText("v2 → v3:");
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
  });
});

describe("accessibility and wording", () => {
  it("has no blocking violations and never mentions a reader", async () => {
    const { container } = open();
    await screen.findByRole("article", { name: "Changed, page 2" });
    await expectNoBlockingA11yViolations(container);
    expect(container.textContent?.toLowerCase()).not.toContain("reader");
  });
});
