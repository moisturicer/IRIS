/**
 * RDCO's Setup page, Requirements & Templates (ADR-063, IR-971). The server
 * enforces who may call each route; these pin what RDCO sees and sends.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useLocation } from "react-router-dom";
import { noticeApi } from "@/api/notice";
import { setupApi, type SetupRecordType } from "@/api/setup";
import { linkParts } from "@/components/shared/PlainTextWithLinks";
import { ROLES } from "@/lib/constants";
import { useAuthStore } from "@/store/auth.store";
import { expectNoBlockingA11yViolations } from "@/test/axe";
import { makeUser } from "@/test/authFixtures";
import { renderScreen, screen, userEvent, waitFor, within } from "@/test/render";
import SetupPage from "./SetupPage";

function thesis(overrides: Partial<SetupRecordType> = {}): SetupRecordType {
  return {
    id: 2,
    name: "Thesis / Research",
    description: "Needs a Proposal first.",
    manuscript: { description: "Use the CIT-U format.", template_name: "" },
    requirements: [
      { id: 11, name: "Release Form", is_required: true, description: "Signed by every author.\nSee https://cit.edu/forms.",
        position: 1, template_name: "release-form.pdf", in_use: true },
      { id: 12, name: "Ethics Clearance", is_required: false, description: "", position: 2, template_name: "",
        in_use: false },
    ],
    ...overrides,
  };
}

const PROPOSAL: SetupRecordType = {
  id: 1, name: "Proposal", description: "", manuscript: { description: "", template_name: "" },
  requirements: [{ id: 21, name: "Thesis Revision Form", is_required: true, description: "", position: 1,
                   template_name: "", in_use: false }],
};

function load(list: SetupRecordType[] = [thesis(), PROPOSAL]) {
  return vi.spyOn(setupApi, "recordTypes").mockResolvedValue({ data: list } as never);
}

async function openPage() {
  const user = userEvent.setup();
  const view = renderScreen(<SetupPage />, { route: "/rdco/setup" });
  await screen.findByRole("heading", { level: 2, name: "Requirements & Templates" });
  return { user, ...view };
}

const requirement = (name: string) => screen.getByRole("group", { name });

beforeEach(() => {
  useAuthStore.setState({
    user: makeUser({ role_name: ROLES.RDCO }), accessToken: "t", isAuthenticated: true, authReady: true,
  });
});
afterEach(() => vi.restoreAllMocks());

describe("the list RDCO keeps", () => {
  it("opens on the first record type, the Manuscript first and fixed, each requirement labelled", async () => {
    load();
    const { container } = await openPage();

    expect(screen.getByRole("tab", { name: "Thesis / Research" })).toHaveAttribute("aria-selected", "true");
    const rows = within(screen.getByRole("list", { name: "Thesis / Research requirements" })).getAllByRole("listitem");
    expect(rows.map((r) => within(r).getByRole("heading", { level: 3 }).textContent))
      .toEqual(["Manuscript", "Release Form", "Ethics Clearance"]);
    const manuscript = requirement("Manuscript");
    expect(manuscript).toHaveTextContent("Required");
    expect(manuscript).toHaveTextContent("can't be removed or made Optional");
    expect(within(manuscript).queryByRole("button", { name: /^Remove Manuscript/ })).not.toBeInTheDocument();
    expect(requirement("Release Form")).toHaveTextContent("Required");
    expect(requirement("Ethics Clearance")).toHaveTextContent("Optional");
    expect(screen.getByText(/never stop anyone submitting/)).toBeInTheDocument();
    await expectNoBlockingA11yViolations(container);
  });

  it("shows a description as plain text, line breaks kept and web links clickable", async () => {
    load();
    await openPage();

    const link = within(requirement("Release Form")).getByRole("link", { name: "https://cit.edu/forms" });
    expect(link).toHaveAttribute("href", "https://cit.edu/forms");
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", "noopener noreferrer");
  });

  it("switches record type", async () => {
    load();
    const { user } = await openPage();

    await user.click(screen.getByRole("tab", { name: "Proposal" }));

    expect(screen.getByRole("list", { name: "Proposal requirements" })).toBeInTheDocument();
    expect(requirement("Thesis Revision Form")).toBeInTheDocument();
  });

  it("edits a requirement's label in place, not in a popup", async () => {
    load();
    const edit = vi.spyOn(setupApi, "editRequirement").mockResolvedValue({ data: {} } as never);
    const { user } = await openPage();

    await user.click(within(requirement("Ethics Clearance")).getByRole("button", { name: "Edit" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    const form = screen.getByRole("form", { name: "Edit Ethics Clearance" });
    await user.click(within(form).getByRole("radio", { name: "Required" }));
    await user.click(within(form).getByRole("button", { name: "Save" }));

    expect(edit).toHaveBeenCalledWith(12, { name: "Ethics Clearance", is_required: true, description: "" });
  });

  it("moves a requirement, sending the whole new order", async () => {
    load();
    const reorder = vi.spyOn(setupApi, "reorder").mockResolvedValue({ data: thesis() } as never);
    const { user } = await openPage();

    expect(screen.getByRole("button", { name: "Move up Release Form" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Move down Ethics Clearance" })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "Move up Ethics Clearance" }));

    expect(reorder).toHaveBeenCalledWith(2, [12, 11]);
  });
});

describe("adding a requirement (IR-1315)", () => {
  const ADD_DIALOG = "Add a requirement to Thesis / Research";
  const openAdd = async (user: ReturnType<typeof userEvent.setup>) => {
    await user.click(screen.getByRole("button", { name: "Add a requirement" }));
    return screen.getByRole("dialog", { name: ADD_DIALOG });
  };

  it("starts from the section's heading, above the list, and nothing is left below it", async () => {
    load();
    await openPage();

    const heading = screen.getByRole("heading", { level: 2, name: "Requirements & Templates" });
    const button = screen.getByRole("button", { name: "Add a requirement" });
    const list = screen.getByRole("list", { name: "Thesis / Research requirements" });
    expect(heading.parentElement).toContainElement(button);
    expect(button.compareDocumentPosition(list) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(screen.getAllByRole("button", { name: "Add a requirement" })).toHaveLength(1);
  });

  it("opens a popup named for the record type, with Name focused and the actions in it", async () => {
    load();
    const { user } = await openPage();

    const dialog = await openAdd(user);
    await waitFor(() => expect(within(dialog).getByRole("textbox", { name: "Name" })).toHaveFocus());
    expect(within(dialog).getByRole("radio", { name: "Optional" })).toBeChecked();
    expect(within(dialog).getByRole("textbox", { name: "Description" })).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "Add requirement" })).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "Cancel" })).toBeInTheDocument();
    await expectNoBlockingA11yViolations(document.body);
  });

  it("throws away what was typed on Cancel or Escape, with no question, and focus goes back", async () => {
    load();
    const add = vi.spyOn(setupApi, "addRequirement");
    const { user } = await openPage();
    const trigger = screen.getByRole("button", { name: "Add a requirement" });

    let dialog = await openAdd(user);
    await user.type(within(dialog).getByRole("textbox", { name: "Name" }), "Half typed");
    await user.click(within(dialog).getByRole("button", { name: "Cancel" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();

    dialog = await openAdd(user);
    expect(within(dialog).getByRole("textbox", { name: "Name" })).toHaveValue("");
    await user.type(within(dialog).getByRole("textbox", { name: "Description" }), "Also half typed");
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();

    dialog = await openAdd(user);
    expect(within(dialog).getByRole("textbox", { name: "Description" })).toHaveValue("");
    await user.click(within(dialog).getByRole("button", { name: "Close" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(add).not.toHaveBeenCalled();
  });

  it("adds a requirement with its label and description, closes, and shows the saved list with it last", async () => {
    const saved = thesis({
      requirements: [
        ...thesis().requirements,
        { id: 13, name: "Adviser's Endorsement", is_required: true, description: "Signed by the Adviser.",
          position: 3, template_name: "", in_use: false },
      ],
    });
    const read = load();
    read.mockResolvedValueOnce({ data: [thesis(), PROPOSAL] } as never)
      .mockResolvedValueOnce({ data: [saved, PROPOSAL] } as never);
    const add = vi.spyOn(setupApi, "addRequirement").mockResolvedValue({ data: {} } as never);
    const { user } = await openPage();

    const dialog = await openAdd(user);
    await user.type(within(dialog).getByRole("textbox", { name: "Name" }), "Adviser's Endorsement");
    await user.click(within(dialog).getByRole("radio", { name: "Required" }));
    await user.type(within(dialog).getByRole("textbox", { name: "Description" }), "Signed by the Adviser.");
    await user.click(within(dialog).getByRole("button", { name: "Add requirement" }));

    expect(add).toHaveBeenCalledWith(2, {
      name: "Adviser's Endorsement", is_required: true, description: "Signed by the Adviser.",
    });
    expect(await screen.findByRole("status")).toHaveTextContent("Adviser's Endorsement is added to Thesis / Research.");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(read).toHaveBeenCalledTimes(2);
    const rows = within(screen.getByRole("list", { name: "Thesis / Research requirements" })).getAllByRole("listitem");
    expect(rows.map((r) => within(r).getByRole("heading", { level: 3 }).textContent))
      .toEqual(["Manuscript", "Release Form", "Ethics Clearance", "Adviser's Endorsement"]);
  });

  it("stays open with the fields kept and says why when the server refuses", async () => {
    load();
    vi.spyOn(setupApi, "addRequirement").mockRejectedValue(new Error("network"));
    const { user } = await openPage();

    const dialog = await openAdd(user);
    await user.type(within(dialog).getByRole("textbox", { name: "Name" }), "Adviser's Endorsement");
    await user.type(within(dialog).getByRole("textbox", { name: "Description" }), "Signed by the Adviser.");
    await user.click(within(dialog).getByRole("button", { name: "Add requirement" }));

    expect(await within(dialog).findByRole("alert")).toHaveTextContent("The requirement wasn't added. Try again.");
    expect(screen.getByRole("dialog", { name: ADD_DIALOG })).toBe(dialog);
    expect(within(dialog).getByRole("textbox", { name: "Name" })).toHaveValue("Adviser's Endorsement");
    expect(within(dialog).getByRole("textbox", { name: "Description" })).toHaveValue("Signed by the Adviser.");
    await expectNoBlockingA11yViolations(document.body);

    // Closing after a refusal leaves no stale warning on the page behind it.
    await user.click(within(dialog).getByRole("button", { name: "Cancel" }));
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("refuses a requirement named Manuscript or after one it already has, before sending", async () => {
    load();
    const add = vi.spyOn(setupApi, "addRequirement");
    const { user } = await openPage();

    const dialog = await openAdd(user);
    const name = within(dialog).getByRole("textbox", { name: "Name" });
    await user.click(within(dialog).getByRole("button", { name: "Add requirement" }));
    expect(within(dialog).getByText("Give the requirement a name.")).toBeInTheDocument();

    await user.type(name, "manuscript");
    await user.click(within(dialog).getByRole("button", { name: "Add requirement" }));
    expect(within(dialog).getByText("The Manuscript is always the first requirement.")).toBeInTheDocument();
    expect(name).toHaveAttribute("aria-invalid", "true");

    await user.clear(name);
    await user.type(name, "release form");
    await user.click(within(dialog).getByRole("button", { name: "Add requirement" }));
    expect(within(dialog).getByText("This record type already has a requirement with that name.")).toBeInTheDocument();
    expect(add).not.toHaveBeenCalled();
  });
});

describe("removing a requirement", () => {
  it("says a used requirement is hidden and its files stay", async () => {
    load();
    const remove = vi.spyOn(setupApi, "removeRequirement").mockResolvedValue({ data: { outcome: "hidden" } } as never);
    const { user } = await openPage();

    await user.click(screen.getByRole("button", { name: "Remove Release Form" }));
    const dialog = await screen.findByRole("dialog", { name: "Remove Release Form?" });
    expect(dialog).toHaveTextContent("files stay on their papers");
    await user.click(within(dialog).getByRole("button", { name: "Remove" }));

    expect(remove).toHaveBeenCalledWith(11);
    expect(await screen.findByRole("status")).toHaveTextContent("Release Form is hidden. Papers that have files in it keep them.");
  });

  it("says an unused requirement is deleted", async () => {
    load();
    const { user } = await openPage();

    await user.click(screen.getByRole("button", { name: "Remove Ethics Clearance" }));

    expect(await screen.findByRole("dialog", { name: "Remove Ethics Clearance?" }))
      .toHaveTextContent("Nobody has used it yet, so it will be deleted.");
  });
});

describe("Templates", () => {
  it("uploads a Template for a requirement, offering only the accepted types", async () => {
    load();
    const upload = vi.spyOn(setupApi, "setTemplate").mockResolvedValue({ data: {} } as never);
    const { user } = await openPage();

    const input = screen.getByLabelText("Template file for Ethics Clearance");
    expect(input).toHaveAttribute("accept", ".pdf,.doc,.docx,.odt,.xls,.xlsx,.ods,.png,.jpg,.jpeg");
    const file = new File(["%PDF-1.4"], "ethics.pdf", { type: "application/pdf" });
    await user.upload(input, file);

    expect(upload).toHaveBeenCalledWith(12, file);
    expect(await screen.findByRole("status")).toHaveTextContent("ethics.pdf is now the Template for Ethics Clearance.");
  });

  it("refuses a file over 50 MB before sending it", async () => {
    load();
    const upload = vi.spyOn(setupApi, "setTemplate");
    const { user } = await openPage();

    const big = new File(["x"], "huge.pdf", { type: "application/pdf" });
    Object.defineProperty(big, "size", { value: 50 * 1024 * 1024 + 1 });
    await user.upload(screen.getByLabelText("Template file for Ethics Clearance"), big);

    expect(within(requirement("Ethics Clearance")).getByRole("alert")).toHaveTextContent("over the 50 MB limit");
    expect(upload).not.toHaveBeenCalled();
  });

  it("shows the server's refusal of a file type", async () => {
    load();
    vi.spyOn(setupApi, "setTemplate").mockRejectedValue({
      response: { status: 400, data: { detail: "Templates must be a PDF, Word (.doc, .docx, .odt), spreadsheet (.xls, .xlsx, .ods) or image (.png, .jpg) file." } },
    });
    const { user } = await openPage();

    await user.upload(screen.getByLabelText("Template file for Ethics Clearance"),
                      new File(["x"], "notes.pdf", { type: "application/pdf" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Templates must be a PDF, Word");
  });

  it("downloads the current Template, and replaces or removes it", async () => {
    load();
    const download = vi.spyOn(setupApi, "downloadTemplate").mockResolvedValue({ data: new Blob(["%PDF"]) } as never);
    const remove = vi.spyOn(setupApi, "removeTemplate").mockResolvedValue({ data: {} } as never);
    URL.createObjectURL = vi.fn(() => "blob:x");
    URL.revokeObjectURL = vi.fn();
    const { user } = await openPage();

    const row = requirement("Release Form");
    expect(within(row).getByRole("button", { name: "Replace the Template for Release Form" })).toBeInTheDocument();
    await user.click(within(row).getByRole("button", { name: "Download the Template for Release Form, release-form.pdf" }));
    await waitFor(() => expect(download).toHaveBeenCalledWith(11));

    await user.click(within(row).getByRole("button", { name: "Remove the Template for Release Form" }));
    expect(remove).toHaveBeenCalledWith(11);
  });

  it("gives the Manuscript its own Template and description", async () => {
    load();
    const upload = vi.spyOn(setupApi, "setManuscriptTemplate").mockResolvedValue({ data: thesis() } as never);
    const describe_ = vi.spyOn(setupApi, "describe").mockResolvedValue({ data: thesis() } as never);
    const { user } = await openPage();

    const file = new File(["PK"], "Thesis format.docx");
    await user.upload(screen.getByLabelText("Template file for the Manuscript"), file);
    expect(upload).toHaveBeenCalledWith(2, file);

    await user.click(within(requirement("Manuscript")).getByRole("button", { name: "Edit description" }));
    const field = screen.getByRole("textbox", { name: "Manuscript description" });
    await user.clear(field);
    await user.type(field, "Follow the 2026 format.");
    await user.click(within(requirement("Manuscript")).getByRole("button", { name: "Save" }));
    expect(describe_).toHaveBeenCalledWith(2, { manuscript_description: "Follow the 2026 format." });
  });
});

describe("the record type's description", () => {
  it("saves only once it changed", async () => {
    load();
    const describe_ = vi.spyOn(setupApi, "describe").mockResolvedValue({ data: thesis() } as never);
    const { user } = await openPage();

    const save = screen.getByRole("button", { name: "Save description" });
    expect(save).toBeDisabled();
    const field = screen.getByRole("textbox", { name: "What a Thesis / Research is" });
    await user.type(field, " It covers research outputs.");
    await user.click(save);

    expect(describe_).toHaveBeenCalledWith(2, { description: "Needs a Proposal first. It covers research outputs." });
  });
});

describe("a failed read", () => {
  it("offers to try again", async () => {
    vi.spyOn(setupApi, "recordTypes").mockResolvedValue({ data: { not: "a list" } } as never);
    renderScreen(<SetupPage />, { route: "/rdco/setup" });

    expect(await screen.findByRole("alert")).toHaveTextContent("Setup didn't load");
  });

  it("says so when the server answers with an error, instead of loading for ever (IR-974)", async () => {
    const read = vi.spyOn(setupApi, "recordTypes")
      .mockRejectedValueOnce({ isAxiosError: true, response: { status: 500, data: {} } })
      .mockResolvedValue({ data: [thesis(), PROPOSAL] } as never);
    const user = userEvent.setup();
    renderScreen(<SetupPage />, { route: "/rdco/setup" });

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Setup didn't load.");
    await user.click(within(alert).getByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("heading", { level: 2, name: "Requirements & Templates" })).toBeInTheDocument();
    expect(read).toHaveBeenCalledTimes(2);
  });
});

describe("linkParts", () => {
  it("links only web addresses, leaving trailing punctuation and markup as text", () => {
    expect(linkParts("See https://cit.edu/forms. Or <b>http://x.y</b>")).toEqual([
      { text: "See " },
      { text: "https://cit.edu/forms", href: "https://cit.edu/forms" },
      { text: ". Or <b>" },
      { text: "http://x.y", href: "http://x.y" },
      { text: "</b>" },
    ]);
    expect(linkParts("javascript:alert(1) ftp://a")).toEqual([{ text: "javascript:alert(1) ftp://a" }]);
  });
});

/* -------------------------------------------------------------------------- */
/* Setup's two sections (ADR-063 decision 9, IR-972)                          */
/* -------------------------------------------------------------------------- */

function Address() {
  const { pathname, search } = useLocation();
  return <p>Address: {`${pathname}${search}`}</p>;
}

const address = () => screen.getByText(/^Address: /).textContent?.replace("Address: ", "");
const sections = () => screen.getByRole("tablist", { name: "Setup sections" });

function notices() {
  return vi.spyOn(noticeApi, "versions").mockResolvedValue({
    data: [{ version: 1, text: "IRIS data notice", published_at: "2026-11-01T02:00:00Z", published_by: null }],
  } as never);
}

describe("Setup's sections", () => {
  it("opens on Requirements & Templates, and choosing Notice opens it and says so in the address", async () => {
    load();
    const versions = notices();
    const user = userEvent.setup();
    const { container } = renderScreen(<><SetupPage /><Address /></>, { route: "/rdco/setup" });
    await screen.findByRole("heading", { level: 2, name: "Requirements & Templates" });

    expect(within(sections()).getByRole("tab", { name: "Requirements & Templates" })).toHaveAttribute("aria-selected", "true");
    expect(versions).not.toHaveBeenCalled();

    await user.click(within(sections()).getByRole("tab", { name: "Notice" }));

    expect(within(sections()).getByRole("tab", { name: "Notice" })).toHaveAttribute("aria-selected", "true");
    expect(await screen.findByRole("heading", { level: 2, name: "Version history" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { level: 2, name: "Requirements & Templates" })).not.toBeInTheDocument();
    expect(address()).toBe("/rdco/setup?section=notice");
    await expectNoBlockingA11yViolations(container);
  });

  it("opens on the Notice when the address says so, which is where an old /notices link lands", async () => {
    notices();
    const records = load();
    renderScreen(<SetupPage />, { route: "/rdco/setup?section=notice" });

    expect(await screen.findByRole("heading", { level: 2, name: "Version history" })).toBeInTheDocument();
    expect(within(sections()).getByRole("tab", { name: "Notice" })).toHaveAttribute("aria-selected", "true");
    expect(records).not.toHaveBeenCalled();
  });

  it("moves between sections with the arrow keys, and back to Requirements & Templates clears the address", async () => {
    load();
    notices();
    const user = userEvent.setup();
    renderScreen(<><SetupPage /><Address /></>, { route: "/rdco/setup?section=notice" });
    await screen.findByRole("heading", { level: 2, name: "Version history" });

    within(sections()).getByRole("tab", { name: "Notice" }).focus();
    await user.keyboard("{ArrowLeft}");

    const requirements = within(sections()).getByRole("tab", { name: "Requirements & Templates" });
    expect(requirements).toHaveAttribute("aria-selected", "true");
    expect(requirements).toHaveFocus();
    expect(await screen.findByRole("heading", { level: 2, name: "Requirements & Templates" })).toBeInTheDocument();
    expect(address()).toBe("/rdco/setup");
  });
});
