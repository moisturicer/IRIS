/**
 * Guidelines (ADR-063 decision 7, IR-974): what each record type needs, for
 * anyone signed in. The server decides what is listed and hidden; these pin
 * what a reader sees and which download each button asks for.
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

async function openPage() {
  const user = userEvent.setup();
  const view = renderScreen(<GuidelinesPage />, { route: "/guidelines" });
  await screen.findByRole("heading", { level: 2, name: "Proposal" });
  return { user, ...view };
}

const section = (name: string) => screen.getByRole("region", { name });
const rowNames = (list: HTMLElement) =>
  within(list).getAllByRole("listitem").map((r) => within(r).getByRole("heading", { level: 3 }).textContent);

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
  it("shows every record type in its own section, with jump links to each", async () => {
    load();
    const { container } = await openPage();

    const jump = screen.getByRole("navigation", { name: "Record types" });
    expect(within(jump).getAllByRole("link").map((a) => a.textContent)).toEqual(["Proposal", "Thesis / Research"]);
    expect(within(jump).getByRole("link", { name: "Thesis / Research" }))
      .toHaveAttribute("href", "#thesis-research");
    expect(section("Thesis / Research")).toHaveAttribute("id", "thesis-research");
    await expectNoBlockingA11yViolations(container);
  });

  it("scrolls to the section an address names once the sections have loaded, as Publish's link asks", async () => {
    load();
    const scrolled: Element[] = [];
    const original = Element.prototype.scrollIntoView;
    Element.prototype.scrollIntoView = function (this: Element) { scrolled.push(this); };
    try {
      renderScreen(<GuidelinesPage />, { route: "/guidelines#thesis-research" });
      await screen.findByRole("heading", { level: 2, name: "Thesis / Research" });
      expect(scrolled).toContain(section("Thesis / Research"));
    } finally {
      Element.prototype.scrollIntoView = original;
    }
  });

  it("starts with the type's description, then the Manuscript, then RDCO's requirements in order", async () => {
    load();
    await openPage();

    const thesis = section("Thesis / Research");
    expect(within(thesis).getByText(/Needs an approved Proposal first/)).toBeInTheDocument();
    expect(within(thesis).getByRole("link", { name: "https://cit.edu/forms" }))
      .toHaveAttribute("href", "https://cit.edu/forms");
    const list = within(thesis).getByRole("list", { name: "Thesis / Research requirements" });
    expect(rowNames(list)).toEqual(["Manuscript", "Community Extension", "Release Form"]);
  });

  it("labels each requirement Required or Optional, and says only the manuscript is needed to submit", async () => {
    load();
    await openPage();

    const thesis = section("Thesis / Research");
    const row = (name: string) => within(thesis).getByRole("group", { name });
    expect(within(row("Manuscript")).getByText("Required")).toBeInTheDocument();
    expect(within(row("Community Extension")).getByText("Optional")).toBeInTheDocument();
    expect(within(row("Release Form")).getByText("Required")).toBeInTheDocument();
    expect(within(row("Release Form")).getByText("Signed by every author.")).toBeInTheDocument();
    expect(screen.getByText(/only the manuscript is needed to submit/i)).toBeInTheDocument();
  });

  it("offers a download only where there is a Template, and asks for that one", async () => {
    load();
    const manuscript = vi.spyOn(guidelinesApi, "downloadManuscriptTemplate").mockResolvedValue({ data: new Blob() } as never);
    const requirement = vi.spyOn(guidelinesApi, "downloadRequirementTemplate").mockResolvedValue({ data: new Blob() } as never);
    const { user } = await openPage();

    const thesis = section("Thesis / Research");
    expect(within(within(thesis).getByRole("group", { name: "Manuscript" })).queryByRole("button")).toBeNull();
    expect(within(within(thesis).getByRole("group", { name: "Community Extension" })).queryByRole("button")).toBeNull();

    await user.click(within(thesis).getByRole("button", { name: "Download the Release Form Template, release.pdf" }));
    expect(requirement).toHaveBeenCalledWith(22);
    expect(save).toHaveBeenLastCalledWith(expect.any(Blob), "release.pdf");

    await user.click(within(section("Proposal"))
      .getByRole("button", { name: "Download the Manuscript Template, proposal-format.docx" }));
    expect(manuscript).toHaveBeenCalledWith(1);
    expect(save).toHaveBeenLastCalledWith(expect.any(Blob), "proposal-format.docx");
  });

  it("says why a download failed, beside it", async () => {
    load();
    vi.spyOn(guidelinesApi, "downloadRequirementTemplate").mockRejectedValue(new Error("boom"));
    const { user } = await openPage();

    const row = within(section("Thesis / Research")).getByRole("group", { name: "Release Form" });
    await user.click(within(row).getByRole("button", { name: /Download the Release Form Template/ }));
    expect(await within(row).findByRole("alert")).toHaveTextContent("didn't download");
  });

  it("changes nothing: there is no control but a download", async () => {
    load();
    await openPage();

    const buttons = screen.getAllByRole("button").map((b) => b.getAttribute("aria-label") ?? b.textContent);
    expect(buttons.every((name) => name?.startsWith("Download"))).toBe(true);
  });
});

describe("Advisers' Templates, in the Proposal section", () => {
  it("lists each Adviser's Templates under their name, only for Proposals", async () => {
    load();
    await openPage();

    const proposal = section("Proposal");
    const shared = within(proposal).getByRole("region", { name: "Advisers' Templates" });
    expect(within(shared).getAllByRole("heading", { level: 4 }).map((h) => h.textContent))
      .toEqual(["Ada Lovelace", "Alan Turing"]);
    expect(within(within(shared).getByRole("list", { name: "Ada Lovelace's Templates" }))
      .getAllByRole("listitem").map((r) => within(r).getByRole("heading", { level: 5 }).textContent))
      .toEqual(["Ada's format", "Ada's budget"]);
    expect(within(shared).getByText("For AI proposals.")).toBeInTheDocument();
    expect(within(section("Thesis / Research")).queryByRole("region", { name: "Advisers' Templates" })).toBeNull();
  });

  it("downloads an Adviser's Template", async () => {
    load();
    const file = vi.spyOn(guidelinesApi, "downloadAdviserTemplate").mockResolvedValue({ data: new Blob() } as never);
    const { user } = await openPage();

    await user.click(screen.getByRole("button", { name: "Download Ada's format by Ada Lovelace, ada.docx" }));
    expect(file).toHaveBeenCalledWith(7);
    expect(save).toHaveBeenLastCalledWith(expect.any(Blob), "ada.docx");
  });

  it("narrows to the Advisers whose name matches the search", async () => {
    load();
    const { user } = await openPage();

    const shared = within(section("Proposal")).getByRole("region", { name: "Advisers' Templates" });
    await user.type(within(shared).getByRole("searchbox", { name: "Search by Adviser" }), "tur");
    expect(within(shared).getAllByRole("heading", { level: 4 }).map((h) => h.textContent)).toEqual(["Alan Turing"]);

    await user.clear(within(shared).getByRole("searchbox", { name: "Search by Adviser" }));
    await user.type(within(shared).getByRole("searchbox", { name: "Search by Adviser" }), "Grace");
    expect(within(shared).queryAllByRole("heading", { level: 4 })).toHaveLength(0);
    expect(within(shared).getByText("No Adviser's name matches “Grace”.")).toBeInTheDocument();
  });

  it("says so when no Adviser shares a Template yet, with no search to make", async () => {
    load([PROPOSAL, THESIS], []);
    await openPage();

    const shared = within(section("Proposal")).getByRole("region", { name: "Advisers' Templates" });
    expect(within(shared).getByText("No Adviser shares a Template yet.")).toBeInTheDocument();
    expect(within(shared).queryByRole("searchbox")).toBeNull();
  });

  it("keeps the requirements on screen when Advisers' Templates don't load", async () => {
    vi.spyOn(guidelinesApi, "list").mockResolvedValue({ data: [PROPOSAL, THESIS] } as never);
    vi.spyOn(guidelinesApi, "advisersTemplates").mockRejectedValue(new Error("boom"));
    await openPage();

    const shared = within(section("Proposal")).getByRole("region", { name: "Advisers' Templates" });
    expect(await within(shared).findByRole("alert")).toHaveTextContent("Advisers' Templates didn't load");
    expect(within(section("Proposal")).getByRole("group", { name: "Thesis Revision Form" })).toBeInTheDocument();
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
