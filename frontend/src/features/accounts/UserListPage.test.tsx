/**
 * The Users page's coordinator controls (IR-478; ADR-032 §4). Every query goes
 * through the accessible tree.
 */
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { expectNoBlockingA11yViolations } from "@/test/axe";
import { renderScreen, screen, waitFor, within } from "@/test/render";
import type { UserListItem } from "@/types/auth";

import UserListPage from "./UserListPage";

const userList = vi.fn();
const setCoordinator = vi.fn();
const setRole = vi.fn();

vi.mock("@/api/accounts", () => ({
  accountsApi: {
    userList: (params: unknown) => userList(params),
    setCoordinator: (id: number, value: boolean) => setCoordinator(id, value),
    setRole: (id: number, role: string) => setRole(id, role),
    setLocked: vi.fn(),
  },
}));

function user(overrides: Partial<UserListItem>): UserListItem {
  return {
    id: 1, email: "someone@cit.edu", first_name: "Some", last_name: "One",
    role_name: "Student", is_active: true, is_locked: false,
    is_office_coordinator: false, date_joined: "2026-01-01",
    ...overrides,
  };
}

const MEMBER      = user({ id: 2, email: "itso@cit.edu", role_name: "ITSO" });
const COORDINATOR = user({ id: 3, email: "ierc.coordinator@cit.edu", role_name: "IERC", is_office_coordinator: true });
const STUDENT     = user({ id: 4, email: "student@cit.edu", role_name: "Student" });
const ADVISER     = user({ id: 5, email: "adviser@cit.edu", role_name: "Adviser" });

function listing(rows: UserListItem[]) {
  return { data: { count: rows.length, results: rows } };
}

async function rowFor(email: string) {
  return (await screen.findByRole("row", { name: new RegExp(email) }));
}

beforeEach(() => {
  userList.mockResolvedValue(listing([MEMBER, COORDINATOR, STUDENT, ADVISER]));
});

afterEach(() => {
  vi.clearAllMocks();
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

    expect(within(await rowFor("itso@cit.edu")).getByRole("button", { name: "Make coordinator" })).toBeInTheDocument();
    expect(within(await rowFor("ierc.coordinator@cit.edu")).getByRole("button", { name: "Remove coordinator" })).toBeInTheDocument();
  });

  it("never offers it on a Student or Adviser row", async () => {
    renderScreen(<UserListPage />);

    for (const email of ["student@cit.edu", "adviser@cit.edu"]) {
      const row = await rowFor(email);
      expect(within(row).queryByRole("button", { name: /coordinator/i })).not.toBeInTheDocument();
    }
  });
});

describe("granting", () => {
  it("states what a coordinator may do, and confirming updates the row", async () => {
    setCoordinator.mockResolvedValue({ data: { ...MEMBER, is_office_coordinator: true } });
    renderScreen(<UserListPage />);

    await userEvent.click(within(await rowFor("itso@cit.edu")).getByRole("button", { name: "Make coordinator" }));
    const dialog = screen.getByRole("dialog", { name: "Make coordinator?" });
    expect(dialog).toHaveTextContent("can assign, reassign and withdraw reviewers in ITSO");

    await userEvent.click(within(dialog).getByRole("button", { name: "Make coordinator" }));

    expect(setCoordinator).toHaveBeenCalledWith(2, true);
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    const row = await rowFor("itso@cit.edu");
    expect(within(row).getByText("Coordinator")).toBeInTheDocument();
    expect(within(row).getByRole("button", { name: "Remove coordinator" })).toBeInTheDocument();
  });

  it("changes nothing when cancelled", async () => {
    renderScreen(<UserListPage />);

    await userEvent.click(within(await rowFor("itso@cit.edu")).getByRole("button", { name: "Make coordinator" }));
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

    await userEvent.click(within(await rowFor("itso@cit.edu")).getByRole("button", { name: "Make coordinator" }));
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

    await userEvent.click(within(await rowFor("ierc.coordinator@cit.edu")).getByRole("button", { name: "Remove coordinator" }));
    const dialog = screen.getByRole("dialog", { name: "Remove coordinator?" });
    expect(dialog).toHaveTextContent("their existing assignments stay");

    await userEvent.click(within(dialog).getByRole("button", { name: "Remove coordinator" }));

    expect(setCoordinator).toHaveBeenCalledWith(3, false);
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    const row = await rowFor("ierc.coordinator@cit.edu");
    expect(within(row).queryByText("Coordinator")).not.toBeInTheDocument();
    expect(within(row).getByRole("button", { name: "Make coordinator" })).toBeInTheDocument();
  });

  it("shows a refusal in the dialog and leaves the row as it was", async () => {
    setCoordinator.mockRejectedValue({ response: { status: 403, data: { detail: "You do not have permission to perform this action." } } });
    renderScreen(<UserListPage />);

    await userEvent.click(within(await rowFor("ierc.coordinator@cit.edu")).getByRole("button", { name: "Remove coordinator" }));
    const dialog = screen.getByRole("dialog", { name: "Remove coordinator?" });
    await userEvent.click(within(dialog).getByRole("button", { name: "Remove coordinator" }));

    expect(await within(dialog).findByRole("alert")).toHaveTextContent("You do not have permission");
    expect(within(await rowFor("ierc.coordinator@cit.edu")).getByText("Coordinator")).toBeInTheDocument();
  });
});

describe("the Change role dialog", () => {
  it("warns that a coordinator loses coordinator status", async () => {
    renderScreen(<UserListPage />);

    await userEvent.click(within(await rowFor("ierc.coordinator@cit.edu")).getByRole("button", { name: "Change role" }));
    const dialog = screen.getByRole("dialog", { name: "Change Role" });

    expect(within(dialog).getByRole("combobox", { name: "New role" })).toHaveValue("IERC");
    expect(dialog).toHaveTextContent("removes their coordinator status");
  });

  it("gives no such warning for a member who does not coordinate", async () => {
    renderScreen(<UserListPage />);

    await userEvent.click(within(await rowFor("itso@cit.edu")).getByRole("button", { name: "Change role" }));

    expect(screen.getByRole("dialog", { name: "Change Role" })).not.toHaveTextContent(/coordinator/i);
  });
});

describe("accessibility", () => {
  it("has no blocking axe violations on the table or either dialog", async () => {
    const { container } = renderScreen(<UserListPage />);
    await rowFor("itso@cit.edu");
    await expectNoBlockingA11yViolations(container);

    await userEvent.click(within(await rowFor("itso@cit.edu")).getByRole("button", { name: "Make coordinator" }));
    await expectNoBlockingA11yViolations(document.body);
    await userEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Cancel" }));

    await userEvent.click(within(await rowFor("ierc.coordinator@cit.edu")).getByRole("button", { name: "Change role" }));
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
