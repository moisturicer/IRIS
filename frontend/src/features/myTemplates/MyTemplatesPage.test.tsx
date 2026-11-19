/**
 * My Templates: an Adviser's own proposal Templates (ADR-063 decision 8, IR-975).
 * The server enforces who may call each route and the file rules; these pin
 * what the Adviser sees and sends.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { myTemplatesApi, type MyTemplate } from "@/api/myTemplates";
import { ROLES } from "@/lib/constants";
import { useAuthStore } from "@/store/auth.store";
import { expectNoBlockingA11yViolations } from "@/test/axe";
import { makeUser } from "@/test/authFixtures";
import { renderScreen, screen, userEvent, waitFor, within } from "@/test/render";
import MyTemplatesPage from "./MyTemplatesPage";

const CHAPTER_1: MyTemplate = {
  id: 7, title: "Chapter 1 format", description: "Use this for Chapter 1.\nSee https://cit.edu/forms.",
  file_name: "chapter-1.docx", position: 1, updated_at: "2026-11-19T08:00:00Z",
};
const BUDGET: MyTemplate = {
  id: 8, title: "Budget sheet", description: "", file_name: "budget.xlsx", position: 2,
  updated_at: "2026-11-19T08:00:00Z",
};

function load(list: MyTemplate[] = [CHAPTER_1, BUDGET]) {
  return vi.spyOn(myTemplatesApi, "list").mockResolvedValue({ data: list } as never);
}

async function openPage() {
  const user = userEvent.setup();
  const view = renderScreen(<MyTemplatesPage />, { route: "/my-templates" });
  await screen.findByRole("heading", { level: 1, name: "My Templates" });
  return { user, ...view };
}

const template = (title: string) => screen.getByRole("group", { name: title });
const pdf = (name = "format.pdf") => new File(["%PDF-1.4"], name, { type: "application/pdf" });

beforeEach(() => {
  useAuthStore.setState({
    user: makeUser({ role_name: ROLES.ADVISER }), accessToken: "t", isAuthenticated: true, authReady: true,
  });
});
afterEach(() => vi.restoreAllMocks());

describe("the list an Adviser keeps", () => {
  it("shows each Template in the Adviser's order, with its description and file", async () => {
    load();
    const { container } = await openPage();

    const rows = within(await screen.findByRole("list", { name: "Your Templates" })).getAllByRole("listitem");
    expect(rows.map((r) => within(r).getByRole("heading", { level: 3 }).textContent))
      .toEqual(["Chapter 1 format", "Budget sheet"]);
    expect(within(template("Chapter 1 format")).getByRole("link", { name: "https://cit.edu/forms" }))
      .toHaveAttribute("href", "https://cit.edu/forms");
    expect(within(template("Chapter 1 format"))
      .getByRole("button", { name: "Download Chapter 1 format, chapter-1.docx" })).toBeInTheDocument();
    await expectNoBlockingA11yViolations(container);
  });

  it("says so when there are none yet, and offers to add one", async () => {
    load([]);
    await openPage();

    expect(await screen.findByText(/haven.t shared any Templates yet/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Add a Template" })).toBeInTheDocument();
  });
});

describe("adding a Template", () => {
  it("sends the title, description and file, then shows the new list", async () => {
    const list = load([]);
    const add = vi.spyOn(myTemplatesApi, "add").mockResolvedValue({ data: CHAPTER_1 } as never);
    const { user } = await openPage();

    await user.click(screen.getByRole("button", { name: "Add a Template" }));
    const form = screen.getByRole("form", { name: "Add a Template" });
    await user.type(within(form).getByLabelText("Title"), "Chapter 1 format");
    await user.type(within(form).getByLabelText("Description"), "Use this for Chapter 1.");
    await user.upload(within(form).getByLabelText("File"), pdf("chapter-1.pdf"));
    list.mockResolvedValue({ data: [CHAPTER_1] } as never);
    await user.click(within(form).getByRole("button", { name: "Add Template" }));

    await waitFor(() => expect(add).toHaveBeenCalledTimes(1));
    const [fields, file] = add.mock.calls[0];
    expect(fields).toEqual({ title: "Chapter 1 format", description: "Use this for Chapter 1." });
    expect(file.name).toBe("chapter-1.pdf");
    expect(await screen.findByRole("status")).toHaveTextContent("Chapter 1 format is added.");
    expect(within(screen.getByRole("list", { name: "Your Templates" })).getAllByRole("listitem")).toHaveLength(1);
  });

  it("asks for a title and a file before sending anything", async () => {
    load([]);
    const add = vi.spyOn(myTemplatesApi, "add");
    const { user } = await openPage();

    await user.click(screen.getByRole("button", { name: "Add a Template" }));
    const form = screen.getByRole("form", { name: "Add a Template" });
    await user.click(within(form).getByRole("button", { name: "Add Template" }));

    expect(within(form).getByLabelText("Title")).toHaveAccessibleDescription("Give the Template a title.");
    expect(within(form).getByLabelText("File")).toHaveAccessibleDescription("Choose a file.");
    expect(add).not.toHaveBeenCalled();
  });

  it("shows why the server refused a file", async () => {
    load([]);
    vi.spyOn(myTemplatesApi, "add").mockRejectedValue({
      isAxiosError: true, response: { status: 400, data: { detail: "This file was flagged as unsafe and was not uploaded." } },
    });
    const { user } = await openPage();

    await user.click(screen.getByRole("button", { name: "Add a Template" }));
    const form = screen.getByRole("form", { name: "Add a Template" });
    await user.type(within(form).getByLabelText("Title"), "Chapter 1 format");
    await user.upload(within(form).getByLabelText("File"), pdf());
    await user.click(within(form).getByRole("button", { name: "Add Template" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("flagged as unsafe");
  });
});

describe("changing a Template", () => {
  it("saves an edited title and description", async () => {
    load();
    const edit = vi.spyOn(myTemplatesApi, "edit").mockResolvedValue({ data: CHAPTER_1 } as never);
    const { user } = await openPage();

    await user.click(within(template("Budget sheet")).getByRole("button", { name: "Edit Budget sheet" }));
    const form = screen.getByRole("form", { name: "Edit Budget sheet" });
    await user.clear(within(form).getByLabelText("Title"));
    await user.type(within(form).getByLabelText("Title"), "Budget");
    await user.click(within(form).getByRole("button", { name: "Save" }));

    await waitFor(() => expect(edit).toHaveBeenCalledWith(8, { title: "Budget", description: "" }));
  });

  it("replaces the file", async () => {
    load();
    const replace = vi.spyOn(myTemplatesApi, "replaceFile").mockResolvedValue({ data: BUDGET } as never);
    const { user } = await openPage();

    await user.upload(within(template("Budget sheet")).getByLabelText("New file for Budget sheet"), pdf("budget-v2.pdf"));

    await waitFor(() => expect(replace).toHaveBeenCalledTimes(1));
    expect(replace.mock.calls[0][0]).toBe(8);
    expect(replace.mock.calls[0][1].name).toBe("budget-v2.pdf");
  });

  it("moves a Template, the first unable to go up and the last unable to go down", async () => {
    load();
    const reorder = vi.spyOn(myTemplatesApi, "reorder").mockResolvedValue({ data: { order: [8, 7] } } as never);
    const { user } = await openPage();

    expect(within(template("Chapter 1 format")).getByRole("button", { name: "Move up Chapter 1 format" })).toBeDisabled();
    expect(within(template("Budget sheet")).getByRole("button", { name: "Move down Budget sheet" })).toBeDisabled();
    await user.click(within(template("Budget sheet")).getByRole("button", { name: "Move up Budget sheet" }));

    await waitFor(() => expect(reorder).toHaveBeenCalledWith([8, 7]));
  });

  it("removes a Template only once the Adviser confirms", async () => {
    load();
    const remove = vi.spyOn(myTemplatesApi, "remove").mockResolvedValue({ data: null } as never);
    const { user } = await openPage();

    await user.click(within(template("Budget sheet")).getByRole("button", { name: "Remove Budget sheet" }));
    const dialog = await screen.findByRole("dialog", { name: "Remove Budget sheet?" });
    expect(remove).not.toHaveBeenCalled();
    await user.click(within(dialog).getByRole("button", { name: "Remove" }));

    await waitFor(() => expect(remove).toHaveBeenCalledWith(8));
  });
});
