/**
 * The Users page: coordinator controls (IR-478; ADR-032 §4) and row actions in a
 * "⋯" menu with Lock behind a dialog that names the person (IR-1077). Every
 * query goes through the accessible tree.
 */
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useAuthStore } from "@/store/auth.store";

import { expectNoBlockingA11yViolations } from "@/test/axe";
import { renderScreen, screen, waitFor, within } from "@/test/render";
import type { UserListItem } from "@/types/auth";

import UserListPage from "./UserListPage";

const userList = vi.fn();
const setCoordinator = vi.fn();
const setRole = vi.fn();
const setLocked = vi.fn();

vi.mock("@/api/accounts", () => ({
  accountsApi: {
    userList: (params: unknown) => userList(params),
    setCoordinator: (id: number, value: boolean) => setCoordinator(id, value),
    setRole: (id: number, role: string) => setRole(id, role),
    setLocked: (id: number, value: boolean) => setLocked(id, value),
  },
}));

function user(overrides: Partial<UserListItem>): UserListItem {
  return {
    id: 1, email: "someone@cit.edu", first_name: "Some", last_name: "One",
    role_name: "Student", is_active: true, is_locked: false, is_verified: true,
    is_office_coordinator: false, date_joined: "2026-01-01",
    ...overrides,
  };
}

const MEMBER      = user({ id: 2, email: "itso@cit.edu", first_name: "Ida", last_name: "Tso", role_name: "ITSO" });
const COORDINATOR = user({ id: 3, email: "ierc.coordinator@cit.edu", first_name: "Ian", last_name: "Ierc", role_name: "IERC", is_office_coordinator: true });
const STUDENT     = user({ id: 4, email: "student@cit.edu", first_name: "Stu", last_name: "Dent", role_name: "Student" });
const ADVISER     = user({ id: 5, email: "adviser@cit.edu", first_name: "Ada", last_name: "Viser", role_name: "Adviser" });

function listing(rows: UserListItem[]) {
  return { data: { count: rows.length, results: rows } };
}

async function rowFor(email: string) {
  return (await screen.findByRole("row", { name: new RegExp(email) }));
}

const actionsTrigger = (row: HTMLElement) => within(row).getByRole("button", { name: /^Actions for / });

/** Opens a row's "⋯" menu and returns it. */
async function openMenu(email: string) {
  await userEvent.click(actionsTrigger(await rowFor(email)));
  return screen.getByRole("menu");
}

/** Opens a row's menu and chooses an item by its name. */
async function choose(email: string, item: string) {
  await userEvent.click(within(await openMenu(email)).getByRole("menuitem", { name: item }));
}

/** The names of a row's menu items, closing the menu again; none when the row has no menu. */
async function offered(email: string): Promise<string[]> {
  const row = await rowFor(email);
  if (!within(row).queryByRole("button", { name: /^Actions for / })) return [];
  const names = within(await openMenu(email)).getAllByRole("menuitem").map((i) => i.textContent ?? "");
  await userEvent.keyboard("{Escape}");
  return names;
}

/** The viewer the page is opened by. The System Admin gives office roles and the
 * coordinator flag, so most tests open it as one (IR-781, deliberately). */
function signInAs(role_name: string) {
  useAuthStore.setState({ user: { id: 99, email: "viewer@cit.edu", role_name } as never, isAuthenticated: true });
}

beforeEach(() => {
  signInAs("System Admin");
  userList.mockResolvedValue(listing([MEMBER, COORDINATOR, STUDENT, ADVISER]));
});

afterEach(() => {
  vi.clearAllMocks();
});

describe("the users table", () => {
  it("names the table and every column for assistive technology", async () => {
    renderScreen(<UserListPage />);

    const table = await screen.findByRole("table", { name: "User accounts" });
    const headers = within(table).getAllByRole("columnheader");
    expect(headers).toHaveLength(4);
    for (const header of headers) expect(header).toHaveAttribute("scope", "col");
    expect(within(table).getByRole("columnheader", { name: "Actions" })).toBeInTheDocument();
  });

  it("shows the name first and the email under it, in one cell", async () => {
    renderScreen(<UserListPage />);

    const table = await screen.findByRole("table", { name: "User accounts" });
    expect(within(table).getByRole("columnheader", { name: "User" })).toBeInTheDocument();
    const cell = within(await rowFor("student@cit.edu")).getByRole("cell", { name: /Stu Dent/ });
    expect(cell.textContent).toBe("Stu Dentstudent@cit.edu");
    expect(within(table).queryByRole("columnheader", { name: "Email" })).not.toBeInTheDocument();
  });

  it("announces loading and the new page when pagination changes", async () => {
    const firstPage = Array.from({ length: 20 }, (_, index) =>
      user({ id: 100 + index, email: `person${index + 1}@cit.edu` }),
    );
    userList.mockResolvedValueOnce({ data: { count: 25, results: firstPage } });

    renderScreen(<UserListPage />);

    const status = screen.getByRole("status", { name: "User accounts status" });
    await waitFor(() => {
      expect(status).toHaveTextContent("User accounts: showing 1–20 of 25. Page 1 of 2.");
    });

    let resolvePageTwo!: (value: ReturnType<typeof listing>) => void;
    userList.mockImplementationOnce(() => new Promise((resolve) => {
      resolvePageTwo = resolve;
    }));

    await userEvent.click(screen.getByRole("button", { name: "Next page" }));
    await waitFor(() => expect(status).toHaveTextContent("Loading User accounts."));

    resolvePageTwo({ data: { count: 25, results: [STUDENT, ADVISER] } });
    await waitFor(() => {
      expect(status).toHaveTextContent("User accounts: showing 21–25 of 25. Page 2 of 2.");
    });
    expect(userList).toHaveBeenLastCalledWith({ page: 2, search: "" });
  });
});

describe("the Coordinator badge", () => {
  it("is shown on coordinators and on nobody else", async () => {
    renderScreen(<UserListPage />);

    expect(within(await rowFor("ierc.coordinator@cit.edu")).getByText("Coordinator")).toBeInTheDocument();
    for (const email of ["itso@cit.edu", "student@cit.edu", "adviser@cit.edu"]) {
      expect(within(await rowFor(email)).queryByText("Coordinator")).not.toBeInTheDocument();
    }
  });
});

describe("who is offered the action", () => {
  it("offers it on office rows, by their current state", async () => {
    renderScreen(<UserListPage />);

    expect(await offered("itso@cit.edu")).toContain("Make coordinator");
    expect(await offered("ierc.coordinator@cit.edu")).toContain("Remove coordinator");
  });

  it("never offers it on a Student or Adviser row", async () => {
    renderScreen(<UserListPage />);

    for (const email of ["student@cit.edu", "adviser@cit.edu"]) {
      expect((await offered(email)).join()).not.toMatch(/coordinator/i);
    }
  });
});

describe("granting", () => {
  it("states what a coordinator may do, and confirming updates the row", async () => {
    setCoordinator.mockResolvedValue({ data: { ...MEMBER, is_office_coordinator: true } });
    renderScreen(<UserListPage />);

    await choose("itso@cit.edu", "Make coordinator");
    const dialog = screen.getByRole("dialog", { name: "Make coordinator?" });
    expect(dialog).toHaveTextContent("can assign, reassign and withdraw reviewers in ITSO");

    await userEvent.click(within(dialog).getByRole("button", { name: "Make coordinator" }));

    expect(setCoordinator).toHaveBeenCalledWith(2, true);
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    const row = await rowFor("itso@cit.edu");
    expect(within(row).getByText("Coordinator")).toBeInTheDocument();
    expect(await offered("itso@cit.edu")).toContain("Remove coordinator");
  });

  it("changes nothing when cancelled", async () => {
    renderScreen(<UserListPage />);

    await choose("itso@cit.edu", "Make coordinator");
    await userEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Cancel" }));

    expect(setCoordinator).not.toHaveBeenCalled();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(within(await rowFor("itso@cit.edu")).queryByText("Coordinator")).not.toBeInTheDocument();
  });

  it("shows a refusal in the dialog and leaves the row as it was", async () => {
    setCoordinator.mockRejectedValue({
      response: { status: 400, data: { detail: "Only a member of ITSO, IERC, KTTO or RDCO can coordinate an office." } },
    });
    renderScreen(<UserListPage />);

    await choose("itso@cit.edu", "Make coordinator");
    const dialog = screen.getByRole("dialog", { name: "Make coordinator?" });
    await userEvent.click(within(dialog).getByRole("button", { name: "Make coordinator" }));

    expect(await within(dialog).findByRole("alert")).toHaveTextContent(
      "Only a member of ITSO, IERC, KTTO or RDCO can coordinate an office.",
    );
    expect(screen.getByRole("dialog", { name: "Make coordinator?" })).toBeInTheDocument();
    expect(within(await rowFor("itso@cit.edu")).queryByText("Coordinator")).not.toBeInTheDocument();
  });
});

describe("removing", () => {
  it("says existing assignments stay, and confirming updates the row", async () => {
    setCoordinator.mockResolvedValue({ data: { ...COORDINATOR, is_office_coordinator: false } });
    renderScreen(<UserListPage />);

    await choose("ierc.coordinator@cit.edu", "Remove coordinator");
    const dialog = screen.getByRole("dialog", { name: "Remove coordinator?" });
    expect(dialog).toHaveTextContent("their existing assignments stay");

    await userEvent.click(within(dialog).getByRole("button", { name: "Remove coordinator" }));

    expect(setCoordinator).toHaveBeenCalledWith(3, false);
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    const row = await rowFor("ierc.coordinator@cit.edu");
    expect(within(row).queryByText("Coordinator")).not.toBeInTheDocument();
    expect(await offered("ierc.coordinator@cit.edu")).toContain("Make coordinator");
  });

  it("shows a refusal in the dialog and leaves the row as it was", async () => {
    setCoordinator.mockRejectedValue({ response: { status: 403, data: { detail: "You do not have permission to perform this action." } } });
    renderScreen(<UserListPage />);

    await choose("ierc.coordinator@cit.edu", "Remove coordinator");
    const dialog = screen.getByRole("dialog", { name: "Remove coordinator?" });
    await userEvent.click(within(dialog).getByRole("button", { name: "Remove coordinator" }));

    expect(await within(dialog).findByRole("alert")).toHaveTextContent("You do not have permission");
    expect(within(await rowFor("ierc.coordinator@cit.edu")).getByText("Coordinator")).toBeInTheDocument();
  });
});

describe("the Change role dialog", () => {
  it("warns that a coordinator loses coordinator status", async () => {
    renderScreen(<UserListPage />);

    await choose("ierc.coordinator@cit.edu", "Change role");
    const dialog = screen.getByRole("dialog", { name: "Change Role" });

    expect(within(dialog).getByRole("combobox", { name: "New role" })).toHaveValue("IERC");
    expect(dialog).toHaveTextContent("removes their coordinator status");
  });

  it("gives no such warning for a member who does not coordinate", async () => {
    renderScreen(<UserListPage />);

    await choose("itso@cit.edu", "Change role");

    expect(screen.getByRole("dialog", { name: "Change Role" })).not.toHaveTextContent(/coordinator/i);
  });
});

describe("unverified registrations (IR-804)", () => {
  // Only the System Admin's list holds them: RDCO's leaves them out (IR-705).
  it("marks an account whose email is not verified, and no other", async () => {
    const pending = user({ id: 7, email: "newcomer@cit.edu", is_verified: false });
    userList.mockResolvedValue(listing([STUDENT, pending]));
    const { container } = renderScreen(<UserListPage />);

    expect(within(await rowFor("newcomer@cit.edu")).getByText("Unverified")).toBeInTheDocument();
    expect(within(await rowFor("student@cit.edu")).queryByText("Unverified")).not.toBeInTheDocument();
    await expectNoBlockingA11yViolations(container);
  });
});

describe("accessibility", () => {
  it("has no blocking axe violations on the table or either dialog", async () => {
    const { container } = renderScreen(<UserListPage />);
    await rowFor("itso@cit.edu");
    await expectNoBlockingA11yViolations(container);

    await choose("itso@cit.edu", "Make coordinator");
    await expectNoBlockingA11yViolations(document.body);
    await userEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Cancel" }));

    await choose("ierc.coordinator@cit.edu", "Change role");
    await expectNoBlockingA11yViolations(document.body);
  });
});

describe("a list that fails to load (IR-745)", () => {
  it("says so and tries again, rather than showing an empty table", async () => {
    userList.mockRejectedValueOnce(new Error("Network Error"));
    renderScreen(<UserListPage />);

    expect(await screen.findByRole("heading", { name: "Couldn't load users" })).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await rowFor(STUDENT.email)).toBeInTheDocument();
  });
});


// Who gives which role, and who locks, is the server's (ADR-051 §4-5, amended,
// IR-781). The page offers each viewer only what the server will let them do.
describe("what each viewer is offered (IR-781)", () => {
  const ADMIN = user({ id: 6, email: "sysadmin@cit.edu", first_name: "Sys", last_name: "Admin", role_name: "System Admin" });

  beforeEach(() => {
    userList.mockResolvedValue(listing([MEMBER, STUDENT, ADMIN]));
  });

  it("offers RDCO Student and Adviser for someone outside the offices, and Lock", async () => {
    signInAs("RDCO");
    renderScreen(<UserListPage />);

    expect(await offered("student@cit.edu")).toEqual(["Change role", "Lock"]);
    await choose("student@cit.edu", "Change role");
    const options = within(screen.getByRole("dialog")).getAllByRole("option").map((o) => o.textContent);
    expect(options).toEqual(["Student", "Adviser"]);
  });

  it("offers RDCO no role change or coordinator on an office row, only Lock", async () => {
    signInAs("RDCO");
    renderScreen(<UserListPage />);

    expect(await offered("itso@cit.edu")).toEqual(["Lock"]);
  });

  it("offers nobody anything on a System Admin's row", async () => {
    for (const role of ["RDCO", "System Admin"]) {
      signInAs(role);
      const view = renderScreen(<UserListPage />);
      expect(await offered("sysadmin@cit.edu")).toEqual([]);
      view.unmount();
    }
  });

  it("offers the System Admin every role but its own, and the coordinator flag, and no Lock", async () => {
    renderScreen(<UserListPage />);

    expect(await offered("itso@cit.edu")).toEqual(["Change role", "Make coordinator"]);
    await choose("itso@cit.edu", "Change role");
    const options = within(screen.getByRole("dialog")).getAllByRole("option").map((o) => o.textContent);
    expect(options).toContain("ITSO");
    expect(options).toContain("RDCO");
    expect(options).not.toContain("System Admin");
  });
});

// A filled, destructive Lock on every row, your own included, was audit CMP-01.
describe("row actions in a menu (IR-1077)", () => {
  beforeEach(() => {
    signInAs("RDCO");
    userList.mockResolvedValue(listing([MEMBER, STUDENT]));
  });

  it("gives each row a menu named for its person, and no row a loose Lock button", async () => {
    renderScreen(<UserListPage />);

    await rowFor("student@cit.edu");
    expect(screen.getByRole("button", { name: "Actions for Stu Dent" })).toHaveAttribute("aria-haspopup", "menu");
    expect(screen.getByRole("button", { name: "Actions for Ida Tso" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^(Lock|Unlock|Change role)$/ })).not.toBeInTheDocument();
  });

  it("names the person in the Lock confirmation, and Lock is a menu item, not a button", async () => {
    renderScreen(<UserListPage />);

    await choose("student@cit.edu", "Lock");

    const dialog = screen.getByRole("dialog", { name: "Lock Stu Dent's account?" });
    expect(dialog).toHaveTextContent("Stu Dent (student@cit.edu) will be prevented from logging in");
    expect(setLocked).not.toHaveBeenCalled();
  });

  it("changes nothing when the Lock confirmation is cancelled, and returns focus to the row's menu", async () => {
    renderScreen(<UserListPage />);

    await choose("student@cit.edu", "Lock");
    await userEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Cancel" }));

    expect(setLocked).not.toHaveBeenCalled();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Actions for Stu Dent" })).toHaveFocus();
  });

  it("locks once on confirm, says so, and reloads the list", async () => {
    setLocked.mockResolvedValue({ data: {} });
    renderScreen(<UserListPage />);

    await choose("student@cit.edu", "Lock");
    await userEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Lock" }));

    await waitFor(() => expect(setLocked).toHaveBeenCalledTimes(1));
    expect(setLocked).toHaveBeenCalledWith(4, true);
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    await waitFor(() => expect(userList).toHaveBeenCalledTimes(2));
  });

  it("names the person when unlocking too", async () => {
    userList.mockResolvedValue(listing([user({ ...STUDENT, is_locked: true })]));
    renderScreen(<UserListPage />);

    expect(await offered("student@cit.edu")).toEqual(["Change role", "Unlock"]);
    await choose("student@cit.edu", "Unlock");

    const dialog = screen.getByRole("dialog", { name: "Unlock Stu Dent's account?" });
    expect(dialog).toHaveTextContent("Stu Dent (student@cit.edu) will be able to log in again");
  });

  it("falls back to the email when a person has no name", async () => {
    userList.mockResolvedValue(listing([user({ id: 8, email: "noname@cit.edu", first_name: "", last_name: "" })]));
    renderScreen(<UserListPage />);

    await choose("noname@cit.edu", "Lock");

    expect(screen.getByRole("dialog", { name: "Lock noname@cit.edu's account?" })).toBeInTheDocument();
  });

  it("gives the viewer's own row no actions at all", async () => {
    const own = user({ id: 99, email: "viewer@cit.edu", first_name: "Vi", last_name: "Ewer", role_name: "Student" });
    userList.mockResolvedValue(listing([own, STUDENT]));
    renderScreen(<UserListPage />);

    const row = await rowFor("viewer@cit.edu");
    expect(within(row).queryByRole("button")).not.toBeInTheDocument();
    expect(await offered("student@cit.edu")).toEqual(["Change role", "Lock"]);
  });

  it("has no blocking axe violations with a menu open and on the Lock dialog", async () => {
    renderScreen(<UserListPage />);

    await openMenu("student@cit.edu");
    await expectNoBlockingA11yViolations(document.body);
    await userEvent.click(screen.getByRole("menuitem", { name: "Lock" }));
    await expectNoBlockingA11yViolations(document.body);
  });
});
