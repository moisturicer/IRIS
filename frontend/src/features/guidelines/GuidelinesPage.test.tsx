/**
 * Guidelines (ADR-063 decision 7, IR-974): what each record type needs, for
 * anyone signed in. The server decides what is listed and hidden; these pin
 * what a reader sees and which download each button asks for.
 *
 * The page shows one record type at a time (redesign, 2026-11-23): it used to
 * stack every type, which readers found overwhelming, so these tests changed
 * with it. What they protect is unchanged: RDCO's order, the right download,
 * the address Publish links to, Advisers' Templates and load failures.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { guidelinesApi, type GuidelineRecordType, type SharedTemplate } from "@/api/guidelines";
import { ROLES } from "@/lib/constants";
import { useAuthStore } from "@/store/auth.store";
import { expectNoBlockingA11yViolations } from "@/test/axe";
import { makeUser } from "@/test/authFixtures";
import { renderScreen, screen, userEvent, within } from "@/test/render";
import GuidelinesPage from "./GuidelinesPage";

const save = vi.fn();
vi.mock("@/lib/utils", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/utils")>()),
  downloadBlob: (...args: unknown[]) => save(...args),
}));

const PROPOSAL: GuidelineRecordType = {
  id: 1, name: "Proposal", description: "Comes before a Thesis.",
  manuscript: { description: "The proposal itself.", template_name: "proposal-format.docx" },
  requirements: [
    { id: 11, name: "Thesis Revision Form", is_required: true, description: "", template_name: "revision.pdf" },
  ],
};
const THESIS: GuidelineRecordType = {
  id: 2, name: "Thesis / Research", description: "Needs an approved Proposal first.\nSee https://cit.edu/forms",
  manuscript: { description: "", template_name: "" },
  requirements: [
    { id: 21, name: "Community Extension", is_required: false, description: "If the work reached a community.", template_name: "" },
    { id: 22, name: "Release Form", is_required: true, description: "Signed by every author.", template_name: "release.pdf" },
    { id: 23, name: "Ethics Clearance", is_required: true, description: "", template_name: "" },
  ],
};
const ADA: SharedTemplate = {
  id: 7, title: "Ada's format", description: "For AI proposals.", file_name: "ada.docx", position: 1,
  updated_at: "2026-11-19T08:00:00Z", shared_by: { id: 40, name: "Ada Lovelace" },
};
const ADA_2: SharedTemplate = { ...ADA, id: 8, title: "Ada's budget", description: "", file_name: "budget.xlsx", position: 2 };
const ALAN: SharedTemplate = {
  ...ADA, id: 9, title: "Alan's outline", description: "", file_name: "outline.pdf", shared_by: { id: 41, name: "Alan Turing" },
};

function load(types = [PROPOSAL, THESIS], shared = [ADA, ADA_2, ALAN]) {
  vi.spyOn(guidelinesApi, "list").mockResolvedValue({ data: types } as never);
  vi.spyOn(guidelinesApi, "advisersTemplates").mockResolvedValue({ data: shared } as never);
}

async function openPage(route = "/guidelines") {
  const user = userEvent.setup();
  const view = renderScreen(<GuidelinesPage />, { route });
  await screen.findByRole("tablist", { name: "Record types" });
  return { user, ...view };
}

/** The open record type's panel. */
const panel = (name: string) => screen.getByRole("tabpanel", { name });
const tab = (name: string) => within(screen.getByRole("tablist", { name: "Record types" })).getByRole("tab", { name });
const rowNames = (list: HTMLElement) =>
  within(list).getAllByRole("listitem").map((r) => within(r).getByRole("heading", { level: 4 }).textContent);

beforeEach(() => {
  useAuthStore.setState({
    user: makeUser({ role_name: ROLES.STUDENT }), accessToken: "t", isAuthenticated: true, authReady: true,
  });
});
afterEach(() => {
  vi.restoreAllMocks();
  save.mockReset();
});

describe("what each record type needs", () => {
  it("shows one record type at a time, chosen at the top and kept in the address", async () => {
    load();
    const { user, container } = await openPage();

    expect(within(screen.getByRole("tablist", { name: "Record types" })).getAllByRole("tab").map((t) => t.textContent))
      .toEqual(["Proposal", "Thesis / Research"]);
    expect(tab("Proposal")).toHaveAttribute("aria-selected", "true");
    expect(panel("Proposal")).toBeInTheDocument();
    expect(screen.queryByRole("tabpanel", { name: "Thesis / Research" })).toBeNull();

    await user.click(tab("Thesis / Research"));
    expect(tab("Thesis / Research")).toHaveAttribute("aria-selected", "true");
    expect(panel("Thesis / Research")).toHaveAttribute("id", "thesis-research");
    await expectNoBlockingA11yViolations(container);
  });

  it("opens on the type an address names, as Publish's link asks", async () => {
    load();
    await openPage("/guidelines#thesis-research");
    expect(tab("Thesis / Research")).toHaveAttribute("aria-selected", "true");
    expect(panel("Thesis / Research")).toBeInTheDocument();
  });

  it("moves between types with the arrow keys", async () => {
    load();
    const { user } = await openPage();
    tab("Proposal").focus();
    await user.keyboard("{ArrowRight}");
    expect(tab("Thesis / Research")).toHaveFocus();
    expect(panel("Thesis / Research")).toBeInTheDocument();
  });

  it("starts with the type's description, then the Manuscript alone as what you submit", async () => {
    load();
    await openPage("/guidelines#thesis-research");

    const thesis = panel("Thesis / Research");
    expect(within(thesis).getByText(/Needs an approved Proposal first/)).toBeInTheDocument();
    expect(within(thesis).getByRole("link", { name: "https://cit.edu/forms" }))
      .toHaveAttribute("href", "https://cit.edu/forms");
    const submit = within(thesis).getByRole("region", { name: "What you submit" });
    expect(within(submit).getByRole("group", { name: "Manuscript" })).toBeInTheDocument();
    expect(screen.getByText(/only the manuscript is needed to submit/i)).toBeInTheDocument();
  });

  it("lists Required requirements to have ready in RDCO's order, and folds the Optional ones away", async () => {
    load();
    const { user } = await openPage("/guidelines#thesis-research");

    const thesis = panel("Thesis / Research");
    expect(rowNames(within(thesis).getByRole("list", { name: "Thesis / Research: have these ready" })))
      .toEqual(["Release Form", "Ethics Clearance"]);
    expect(within(thesis).getByText("Signed by every author.")).toBeInTheDocument();
    expect(within(thesis).queryByRole("group", { name: "Community Extension" })).toBeNull();

    await user.click(within(thesis).getByRole("button", { name: "Show 1 optional document" }));
    expect(rowNames(within(thesis).getByRole("list", { name: "Thesis / Research: only if they apply" })))
      .toEqual(["Community Extension"]);
    await user.click(within(thesis).getByRole("button", { name: "Hide 1 optional document" }));
    expect(within(thesis).queryByRole("group", { name: "Community Extension" })).toBeNull();
  });

  it("offers a download only where there is a Template, and asks for that one", async () => {
    load();
    const manuscript = vi.spyOn(guidelinesApi, "downloadManuscriptTemplate").mockResolvedValue({ data: new Blob() } as never);
    const requirement = vi.spyOn(guidelinesApi, "downloadRequirementTemplate").mockResolvedValue({ data: new Blob() } as never);
    const { user } = await openPage("/guidelines#thesis-research");

    const thesis = panel("Thesis / Research");
    expect(within(within(thesis).getByRole("group", { name: "Manuscript" })).queryByRole("button")).toBeNull();
    await user.click(within(thesis).getByRole("button", { name: "Show 1 optional document" }));
    expect(within(within(thesis).getByRole("group", { name: "Community Extension" })).queryByRole("button")).toBeNull();

    await user.click(within(thesis).getByRole("button", { name: "Download the Release Form Template, release.pdf" }));
    expect(requirement).toHaveBeenCalledWith(22);
    expect(save).toHaveBeenLastCalledWith(expect.any(Blob), "release.pdf");

    await user.click(tab("Proposal"));
    await user.click(within(panel("Proposal"))
      .getByRole("button", { name: "Download the Manuscript Template, proposal-format.docx" }));
    expect(manuscript).toHaveBeenCalledWith(1);
    expect(save).toHaveBeenLastCalledWith(expect.any(Blob), "proposal-format.docx");
  });

  it("says why a download failed, beside it", async () => {
    load();
    vi.spyOn(guidelinesApi, "downloadRequirementTemplate").mockRejectedValue(new Error("boom"));
    const { user } = await openPage("/guidelines#thesis-research");

    const row = within(panel("Thesis / Research")).getByRole("group", { name: "Release Form" });
    await user.click(within(row).getByRole("button", { name: /Download the Release Form Template/ }));
    expect(await within(row).findByRole("alert")).toHaveTextContent("didn't download");
  });

  it("changes nothing: its only buttons download, or show and hide", async () => {
    load();
    await openPage("/guidelines#thesis-research");

    const buttons = screen.getAllByRole("button").map((b) => b.getAttribute("aria-label") ?? b.textContent);
    expect(buttons.every((name) => /^(Download|Show|Hide)/.test(name ?? ""))).toBe(true);
  });
});

describe("Advisers' Templates, in the Proposal section", () => {
  it("lists each Adviser's Templates under their name, only for Proposals", async () => {
    load();
    const { user } = await openPage();

    const shared = within(panel("Proposal")).getByRole("region", { name: "Advisers' Templates" });
    await within(shared).findByRole("heading", { level: 4, name: "Ada Lovelace" });
    expect(within(shared).getAllByRole("heading", { level: 4 }).map((h) => h.textContent))
      .toEqual(["Ada Lovelace", "Alan Turing"]);
    expect(within(within(shared).getByRole("list", { name: "Ada Lovelace's Templates" }))
      .getAllByRole("listitem").map((r) => within(r).getByRole("heading", { level: 5 }).textContent))
      .toEqual(["Ada's format", "Ada's budget"]);
    expect(within(shared).getByText("For AI proposals.")).toBeInTheDocument();

    await user.click(tab("Thesis / Research"));
    expect(within(panel("Thesis / Research")).queryByRole("region", { name: "Advisers' Templates" })).toBeNull();
  });

  it("downloads an Adviser's Template", async () => {
    load();
    const file = vi.spyOn(guidelinesApi, "downloadAdviserTemplate").mockResolvedValue({ data: new Blob() } as never);
    const { user } = await openPage();

    await user.click(await screen.findByRole("button", { name: "Download Ada's format by Ada Lovelace, ada.docx" }));
    expect(file).toHaveBeenCalledWith(7);
    expect(save).toHaveBeenLastCalledWith(expect.any(Blob), "ada.docx");
  });

  it("narrows to the Advisers whose name matches the search", async () => {
    load();
    const { user } = await openPage();

    const shared = within(panel("Proposal")).getByRole("region", { name: "Advisers' Templates" });
    await user.type(await within(shared).findByRole("searchbox", { name: "Search by Adviser" }), "tur");
    expect(within(shared).getAllByRole("heading", { level: 4 }).map((h) => h.textContent)).toEqual(["Alan Turing"]);

    await user.clear(within(shared).getByRole("searchbox", { name: "Search by Adviser" }));
    await user.type(within(shared).getByRole("searchbox", { name: "Search by Adviser" }), "Grace");
    expect(within(shared).queryAllByRole("heading", { level: 4 })).toHaveLength(0);
    expect(within(shared).getByText("No Adviser's name matches “Grace”.")).toBeInTheDocument();
  });

  it("says so when no Adviser shares a Template yet, with no search to make", async () => {
    load([PROPOSAL, THESIS], []);
    await openPage();

    const shared = within(panel("Proposal")).getByRole("region", { name: "Advisers' Templates" });
    expect(await within(shared).findByText("No Adviser shares a Template yet.")).toBeInTheDocument();
    expect(within(shared).queryByRole("searchbox")).toBeNull();
  });

  it("keeps the requirements on screen when Advisers' Templates don't load", async () => {
    vi.spyOn(guidelinesApi, "list").mockResolvedValue({ data: [PROPOSAL, THESIS] } as never);
    vi.spyOn(guidelinesApi, "advisersTemplates").mockRejectedValue(new Error("boom"));
    await openPage();

    const shared = within(panel("Proposal")).getByRole("region", { name: "Advisers' Templates" });
    expect(await within(shared).findByRole("alert")).toHaveTextContent("Advisers' Templates didn't load");
    expect(within(panel("Proposal")).getByRole("group", { name: "Thesis Revision Form" })).toBeInTheDocument();
  });
});

describe("when the guidelines don't load", () => {
  it("says so and offers to try again, instead of loading for ever", async () => {
    const list = vi.spyOn(guidelinesApi, "list").mockRejectedValueOnce(new Error("boom"))
      .mockResolvedValue({ data: [PROPOSAL] } as never);
    vi.spyOn(guidelinesApi, "advisersTemplates").mockResolvedValue({ data: [] } as never);
    const user = userEvent.setup();
    renderScreen(<GuidelinesPage />, { route: "/guidelines" });

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("The guidelines didn't load.");
    await user.click(within(alert).getByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("heading", { level: 2, name: "Proposal" })).toBeInTheDocument();
    expect(list).toHaveBeenCalledTimes(2);
  });

  it("refuses an answer it can't read", async () => {
    vi.spyOn(guidelinesApi, "list").mockResolvedValue({ data: { detail: "odd" } } as never);
    vi.spyOn(guidelinesApi, "advisersTemplates").mockResolvedValue({ data: [] } as never);
    renderScreen(<GuidelinesPage />, { route: "/guidelines" });

    expect(await screen.findByRole("alert")).toHaveTextContent("can't read");
  });
});
