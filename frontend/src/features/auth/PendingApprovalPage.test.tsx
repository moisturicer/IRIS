/**
 * The pending-approval screen tells waiting from declined (IR-537).
 *
 * Every registration creates a role request RDCO approves or declines, and the
 * account has no role until it is approved. Before IR-537 the screen could not
 * tell the two apart, so a declined applicant read "Account Pending Approval"
 * indefinitely, under a promise of approval "within 1–2 business days" that
 * nothing backed. `role_request` on the user's own payload is what it reads now.
 *
 * Queries go through the accessible tree, as in `LoginPage.test.tsx`.
 */
import { afterEach, describe, expect, it, vi } from "vitest";

import { authApi } from "@/api/auth";
import { useAuthStore } from "@/store/auth.store";
import type { OwnRoleRequest } from "@/types/auth";

import { expectNoBlockingA11yViolations } from "@/test/axe";
import { makeUser } from "@/test/authFixtures";
import { renderScreen, screen, userEvent, waitFor } from "@/test/render";

import { PendingApprovalPage } from "./PendingApprovalPage";

function signInAs(roleRequest: OwnRoleRequest | null) {
  useAuthStore.setState({
    user: makeUser({
      email: "applicant@cit.edu",
      first_name: "Ana",
      last_name: "Reyes",
      role: null,
      role_name: null,
      role_request: roleRequest,
    }),
    accessToken: "access",
    refreshToken: "refresh-token",
    isAuthenticated: true,
  });
  return renderScreen(<PendingApprovalPage />);
}

const PENDING: OwnRoleRequest = { status: "pending", requested_role: "Adviser" };
const DECLINED: OwnRoleRequest = { status: "declined", requested_role: "Student" };

/** Any promise of how long a decision takes. Only the server could back one, and it does not. */
const TURNAROUND = /\b(?:business days?|days?|hours?|weeks?|shortly|soon|typically)\b/i;

afterEach(() => {
  vi.restoreAllMocks();
  useAuthStore.setState({ user: null, accessToken: null, refreshToken: null, isAuthenticated: false });
});

describe("a pending request", () => {
  it("says RDCO is reviewing it, for which role, and where the decision will be emailed", () => {
    signInAs(PENDING);

    expect(screen.getByRole("heading", { level: 2, name: "Waiting for approval" })).toBeInTheDocument();
    expect(
      screen.getByText(
        "RDCO is reviewing your request to join as an Adviser. You'll get an email at applicant@cit.edu when they decide.",
      ),
    ).toBeInTheDocument();
  });

  it("shows who the person registered as", () => {
    signInAs(PENDING);

    const registered = screen.getByRole("group", { name: "Registered as" });
    expect(registered).toHaveTextContent("Ana Reyes");
    expect(registered).toHaveTextContent("applicant@cit.edu");
    expect(registered).toHaveTextContent("Adviser");
  });

  it("promises no turnaround time", () => {
    const { container } = signInAs(PENDING);
    expect(container.textContent).not.toMatch(TURNAROUND);
  });

  it("has no serious or critical accessibility violations", async () => {
    const { container } = signInAs(PENDING);
    await expectNoBlockingA11yViolations(container);
  });
});

describe("a declined request", () => {
  it("says it was not approved, and who to contact", () => {
    signInAs(DECLINED);

    expect(screen.getByRole("heading", { level: 2, name: "Request not approved" })).toBeInTheDocument();
    expect(
      screen.getByText(
        "Your request to join as a Student was not approved. Contact RDCO or your department administrator if you think this is a mistake.",
      ),
    ).toBeInTheDocument();
    expect(screen.queryByText(/reviewing/i)).not.toBeInTheDocument();
  });

  it("still shows who the person registered as", () => {
    signInAs(DECLINED);

    const registered = screen.getByRole("group", { name: "Registered as" });
    expect(registered).toHaveTextContent("Ana Reyes");
    expect(registered).toHaveTextContent("Student");
  });

  it("promises no turnaround time", () => {
    const { container } = signInAs(DECLINED);
    expect(container.textContent).not.toMatch(TURNAROUND);
  });

  it("has no serious or critical accessibility violations", async () => {
    const { container } = signInAs(DECLINED);
    await expectNoBlockingA11yViolations(container);
  });
});

describe("no request at all", () => {
  // A user with no role and nothing asked for: registered without a role, or
  // approved and later had the role taken away. Neither "reviewing" nor
  // "declined" is true of them.
  it("claims neither a review nor a decline", () => {
    signInAs(null);

    expect(screen.getByRole("heading", { level: 2, name: "No role assigned" })).toBeInTheDocument();
    expect(screen.queryByText(/reviewing|not approved/i)).not.toBeInTheDocument();
    expect(screen.getByText(/Contact RDCO or your department administrator/)).toBeInTheDocument();
  });
});

describe("signing out", () => {
  it("revokes the refresh token and logs the user out", async () => {
    const logout = vi.spyOn(authApi, "logout").mockResolvedValue({ data: {} } as never);
    const user = userEvent.setup();
    signInAs(PENDING);

    await user.click(screen.getByRole("button", { name: "Sign out" }));

    expect(logout).toHaveBeenCalledWith("refresh-token");
    await waitFor(() => expect(useAuthStore.getState().isAuthenticated).toBe(false));
    expect(useAuthStore.getState().user).toBeNull();
  });

  it("logs the user out even when the revoke request fails", async () => {
    vi.spyOn(authApi, "logout").mockRejectedValue(new Error("offline"));
    const user = userEvent.setup();
    signInAs(DECLINED);

    await user.click(screen.getByRole("button", { name: "Sign out" }));

    await waitFor(() => expect(useAuthStore.getState().isAuthenticated).toBe(false));
  });
});

describe("the shared entry frame", () => {
  it("renders the screen inside it: the frame's heading, and its brand panel", () => {
    signInAs(PENDING);

    expect(screen.getByRole("heading", { level: 1, name: "IRIS · CIT-U Research Hub" })).toBeInTheDocument();
    expect(screen.getByRole("complementary", { name: "About IRIS" })).toBeInTheDocument();
  });
});

describe("role_request", () => {
  // Read by nothing but this screen (IR-537 acceptance criteria): it is an
  // applicant's own state, and nothing else should start branching on it.
  const SOURCES = import.meta.glob<string>("/src/**/*.{ts,tsx}", {
    query: "?raw",
    import: "default",
    eager: true,
  });

  it("is read only by the pending screen and declared only in the auth types", () => {
    const readers = Object.entries(SOURCES)
      .filter(([path]) => !/\.test\.tsx?$/.test(path) && !path.startsWith("/src/test/"))
      .filter(([, text]) => text.includes("role_request"))
      .map(([path]) => path)
      .sort();

    expect(readers).toEqual(["/src/features/auth/PendingApprovalPage.tsx", "/src/types/auth.ts"]);
  });
});
