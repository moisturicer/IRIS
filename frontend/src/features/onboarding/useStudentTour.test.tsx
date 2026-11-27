/**
 * The student tours' rules (IR-1342), on a stand-in page so each rule is
 * driven alone: who is offered a tour (AC 4), when it starts and when it is
 * marked seen (AC 1, 6), taking one again from Settings (AC 5), one tour at a
 * time, and a failed request. The real pages and Publish are in their own
 * tests; this holds the hook every one of them shares.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useLocation, useNavigate } from "react-router-dom";

import type { TourStep } from "@/components/tour/types";
import { ROLES, type RoleName } from "@/lib/constants";
import { useAuthStore } from "@/store/auth.store";
import { expectNoBlockingA11yViolations } from "@/test/axe";
import { makeUser } from "@/test/authFixtures";
import { act, renderScreen, screen, userEvent, waitFor } from "@/test/render";

import { discoverTourSteps, MENU_BUTTON_ID, SIDEBAR_ID } from "./studentTours";
import { TOUR_KEYS, TOUR_KEYS_JSON, type TourKey } from "./tourKeys";
import { useTourSession } from "./tourSession";
import { useStudentTour } from "./useStudentTour";

vi.mock("@/api/accounts", () => ({
  accountsApi: { markTourSeen: vi.fn() },
}));
const { accountsApi } = await import("@/api/accounts");

const STEPS: TourStep[] = [
  { id: "first", target: "stand-in-first", title: "First area", body: "What the first area is for." },
  { id: "second", target: "stand-in-second", title: "Second area", body: "What the second area is for." },
];

function Address() {
  const { pathname, search } = useLocation();
  return <output aria-label="Address">{pathname}{search}</output>;
}

/** Opens Publish over the page, as its button does. */
function OpenPublish() {
  const navigate = useNavigate();
  return <button type="button" onClick={() => navigate("/?publish=new")}>Open Publish</button>;
}

function StandIn({ ready = true, drawn = true, tourKey = "discover" as TourKey }) {
  const tour = useStudentTour(tourKey, { ready, steps: STEPS });
  return (
    <>
      <main id="main-content" tabIndex={-1}>
        {drawn && <div id="stand-in-first">First</div>}
        {drawn && <div id="stand-in-second">Second</div>}
        <OpenPublish />
      </main>
      <Address />
      {tour}
    </>
  );
}

function signIn(role: RoleName | null, toursSeen: string[] | "absent" = []) {
  const user = makeUser({ role_name: role });
  useAuthStore.setState({ user: toursSeen === "absent" ? user : { ...user, tours_seen: toursSeen } });
}

const tour = () => screen.queryByRole("dialog", { name: "Discover tour" });

beforeEach(() => {
  useTourSession.getState().reset();
  // The server's answer: the account's keys, the new one once.
  vi.mocked(accountsApi.markTourSeen).mockImplementation(async (key: string) => ({
    data: { tours_seen: [...new Set([...(useAuthStore.getState().user?.tours_seen ?? []), key])] },
  }) as never);
});

afterEach(() => {
  vi.clearAllMocks();
  useAuthStore.setState({ user: null });
});

describe("the keys", () => {
  it("are the list the server checks", () => {
    expect([...TOUR_KEYS]).toEqual(TOUR_KEYS_JSON);
  });
});

describe("Discover's steps", () => {
  it("point at the sidebar on a wide screen and at Open menu on a phone", () => {
    const targets = (phone: boolean) => discoverTourSteps({ canPublish: true, phone }).map((s) => s.target);
    expect(targets(false)).toContain(SIDEBAR_ID);
    expect(targets(false)).not.toContain(MENU_BUTTON_ID);
    expect(targets(true)).toContain(MENU_BUTTON_ID);
    expect(targets(true)).not.toContain(SIDEBAR_ID);
  });

  it("say where to take a tour again on the last step", () => {
    for (const canPublish of [true, false]) {
      const steps = discoverTourSteps({ canPublish, phone: false });
      expect(steps[steps.length - 1].body).toMatch(/Settings › Help/);
    }
  });
});

describe("a new student's first visit (AC 1)", () => {
  it("starts the tour once the page is ready, and Done marks it seen once", async () => {
    signIn(ROLES.STUDENT);
    renderScreen(<StandIn />);

    const card = await screen.findByRole("dialog", { name: "Discover tour" });
    expect(card).toHaveTextContent("Step 1 of 2");
    await userEvent.click(screen.getByRole("button", { name: "Next" }));
    await userEvent.click(screen.getByRole("button", { name: "Done" }));

    expect(tour()).not.toBeInTheDocument();
    expect(accountsApi.markTourSeen).toHaveBeenCalledTimes(1);
    expect(accountsApi.markTourSeen).toHaveBeenCalledWith("discover");
    await waitFor(() => expect(useAuthStore.getState().user?.tours_seen).toEqual(["discover"]));
  });

  it("Escape closes it, marks it seen, and focus goes back to the page", async () => {
    signIn(ROLES.STUDENT);
    renderScreen(<StandIn />);
    await screen.findByRole("dialog", { name: "Discover tour" });
    await userEvent.keyboard("{Escape}");
    expect(tour()).not.toBeInTheDocument();
    expect(accountsApi.markTourSeen).toHaveBeenCalledWith("discover");
    expect(document.activeElement).toBe(document.getElementById("main-content"));
  });

  it("Skip tour marks it seen", async () => {
    signIn(ROLES.STUDENT);
    renderScreen(<StandIn tourKey="library" />);
    await screen.findByRole("dialog", { name: "My Library tour" });
    await userEvent.click(screen.getByRole("button", { name: "Skip tour" }));
    expect(screen.queryByRole("dialog", { name: "My Library tour" })).not.toBeInTheDocument();
    expect(accountsApi.markTourSeen).toHaveBeenCalledTimes(1);
    expect(accountsApi.markTourSeen).toHaveBeenCalledWith("library");
  });

  it("does not start again once seen", async () => {
    signIn(ROLES.STUDENT, ["discover"]);
    renderScreen(<StandIn />);
    await act(async () => {});
    expect(tour()).not.toBeInTheDocument();
    expect(accountsApi.markTourSeen).not.toHaveBeenCalled();
  });

  it("has no blocking accessibility problem while open", async () => {
    signIn(ROLES.STUDENT);
    const { container } = renderScreen(<StandIn />);
    await screen.findByRole("dialog", { name: "Discover tour" });
    await expectNoBlockingA11yViolations(container.ownerDocument.body);
  });
});

describe("a page still loading does not use the tour up (AC 6)", () => {
  it("waits for ready, posts nothing before, then starts", async () => {
    signIn(ROLES.STUDENT);
    const { rerender } = renderScreen(<StandIn ready={false} />);
    await act(async () => {});
    expect(tour()).not.toBeInTheDocument();
    expect(accountsApi.markTourSeen).not.toHaveBeenCalled();

    rerender(<StandIn ready />);
    expect(await screen.findByRole("dialog", { name: "Discover tour" })).toBeInTheDocument();
  });

  it("waits for a step's target to be drawn", async () => {
    signIn(ROLES.STUDENT);
    const { rerender } = renderScreen(<StandIn drawn={false} />);
    await act(async () => {});
    expect(tour()).not.toBeInTheDocument();
    expect(accountsApi.markTourSeen).not.toHaveBeenCalled();

    rerender(<StandIn drawn />);
    expect(await screen.findByRole("dialog", { name: "Discover tour" })).toBeInTheDocument();
  });

  it("leaving the page before any step showed marks nothing", async () => {
    signIn(ROLES.STUDENT);
    const { unmount } = renderScreen(<StandIn drawn={false} />);
    await act(async () => {});
    unmount();
    expect(accountsApi.markTourSeen).not.toHaveBeenCalled();
  });

  it("leaving the page with the tour open counts as seen", async () => {
    signIn(ROLES.STUDENT);
    const { unmount } = renderScreen(<StandIn />);
    await screen.findByRole("dialog", { name: "Discover tour" });
    unmount();
    expect(accountsApi.markTourSeen).toHaveBeenCalledWith("discover");
  });
});

describe("only students (AC 4)", () => {
  it.each([
    ["an Adviser", ROLES.ADVISER],
    ["an office role", ROLES.KTTO],
    ["RDCO", ROLES.RDCO],
    ["an account still waiting for a role", null],
  ])("%s sees no tour, even when asked for one", async (_who, role) => {
    signIn(role as RoleName | null);
    renderScreen(<StandIn />, { route: "/?tour=discover" });
    await act(async () => {});
    expect(tour()).not.toBeInTheDocument();
    expect(accountsApi.markTourSeen).not.toHaveBeenCalled();
  });

  it("an account whose payload has no tours_seen starts none", async () => {
    signIn(ROLES.STUDENT, "absent");
    renderScreen(<StandIn />);
    await act(async () => {});
    expect(tour()).not.toBeInTheDocument();
  });
});

describe("taking a tour again from Settings (AC 5)", () => {
  it("?tour= starts it although it was seen, and leaves the address", async () => {
    signIn(ROLES.STUDENT, [...TOUR_KEYS]);
    renderScreen(<StandIn />, { route: "/?tour=discover" });
    expect(await screen.findByRole("dialog", { name: "Discover tour" })).toBeInTheDocument();
    expect(screen.getByRole("status", { name: "Address" })).toHaveTextContent(/^\/$/);
    await userEvent.click(screen.getByRole("button", { name: "Skip tour" }));
    // Already seen on the account: nothing to tell the server.
    expect(accountsApi.markTourSeen).not.toHaveBeenCalled();
  });

  it("another page's key starts nothing here", async () => {
    signIn(ROLES.STUDENT, [...TOUR_KEYS]);
    renderScreen(<StandIn />, { route: "/?tour=library" });
    await act(async () => {});
    expect(tour()).not.toBeInTheDocument();
  });
});

describe("a failed request", () => {
  it("does not replay the tour in the same session", async () => {
    vi.mocked(accountsApi.markTourSeen).mockRejectedValue(new Error("offline"));
    signIn(ROLES.STUDENT);
    const first = renderScreen(<StandIn />);
    await screen.findByRole("dialog", { name: "Discover tour" });
    await userEvent.click(screen.getByRole("button", { name: "Skip tour" }));
    first.unmount();

    // A fresh read of /users/me/ that never heard the mark.
    signIn(ROLES.STUDENT, []);
    renderScreen(<StandIn />);
    await act(async () => {});
    expect(tour()).not.toBeInTheDocument();
  });
});

describe("one tour at a time", () => {
  it("a page's tour waits while Publish is open", async () => {
    signIn(ROLES.STUDENT);
    renderScreen(<StandIn />, { route: "/?publish=new" });
    await act(async () => {});
    expect(tour()).not.toBeInTheDocument();
  });

  it("Publish opening closes the page's tour without marking it", async () => {
    signIn(ROLES.STUDENT);
    renderScreen(<StandIn />);
    await screen.findByRole("dialog", { name: "Discover tour" });
    await userEvent.click(screen.getByRole("button", { name: "Open Publish" }));

    expect(tour()).not.toBeInTheDocument();
    expect(useTourSession.getState().active).toBeNull();
    expect(accountsApi.markTourSeen).not.toHaveBeenCalled();
  });

  it("a second tour does not start while one runs", async () => {
    signIn(ROLES.STUDENT);
    renderScreen(<><StandIn /><StandIn tourKey="library" /></>);
    await screen.findByRole("dialog", { name: "Discover tour" });
    expect(screen.queryByRole("dialog", { name: "My Library tour" })).not.toBeInTheDocument();
  });
});
