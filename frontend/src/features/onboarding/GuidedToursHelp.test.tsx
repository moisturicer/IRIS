/**
 * Settings › Help's "Don't show tours again" (IR-1349, AC 4): the same account
 * setting as each tour card's tickbox, saved as soon as it changes.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ROLES } from "@/lib/constants";
import { useAuthStore } from "@/store/auth.store";
import { expectNoBlockingA11yViolations } from "@/test/axe";
import { makeUser } from "@/test/authFixtures";
import { renderScreen, screen, userEvent, waitFor } from "@/test/render";

import { GuidedToursHelp } from "./GuidedToursHelp";

vi.mock("@/api/accounts", () => ({
  accountsApi: { setToursOff: vi.fn() },
}));
const { accountsApi } = await import("@/api/accounts");

function signIn(toursOff: boolean) {
  useAuthStore.setState({ user: { ...makeUser({ role_name: ROLES.STUDENT }), tours_off: toursOff } });
}

const tickbox = () => screen.getByRole("checkbox", { name: "Don't show tours again" });

beforeEach(() => {
  vi.mocked(accountsApi.setToursOff).mockImplementation(async (off: boolean) => ({ data: { tours_off: off } }) as never);
});

afterEach(() => {
  vi.clearAllMocks();
  useAuthStore.setState({ user: null });
});

describe("Don't show tours again in Settings › Help", () => {
  it("ticking it saves it to the account and says so", async () => {
    signIn(false);
    const { container } = renderScreen(<GuidedToursHelp />);
    expect(tickbox()).not.toBeChecked();
    await userEvent.click(tickbox());

    expect(accountsApi.setToursOff).toHaveBeenCalledWith(true);
    expect(useAuthStore.getState().user?.tours_off).toBe(true);
    expect(await screen.findByText("Saved. Tours won't start by themselves.")).toBeInTheDocument();
    expect(tickbox()).toBeChecked();
    await expectNoBlockingA11yViolations(container);
  });

  it("unticking it turns tours back on", async () => {
    signIn(true);
    renderScreen(<GuidedToursHelp />);
    expect(tickbox()).toBeChecked();
    await userEvent.click(tickbox());

    expect(accountsApi.setToursOff).toHaveBeenCalledWith(false);
    expect(await screen.findByText("Saved. Tours start again on the pages you haven't toured.")).toBeInTheDocument();
    expect(tickbox()).not.toBeChecked();
  });

  it("a failed save puts it back and says so", async () => {
    vi.mocked(accountsApi.setToursOff).mockRejectedValue(new Error("offline"));
    signIn(false);
    renderScreen(<GuidedToursHelp />);
    await userEvent.click(tickbox());

    expect(await screen.findByText("Could not save Don't show tours again. Try again.")).toBeInTheDocument();
    await waitFor(() => expect(tickbox()).not.toBeChecked());
    expect(useAuthStore.getState().user?.tours_off).toBe(false);
  });
});
