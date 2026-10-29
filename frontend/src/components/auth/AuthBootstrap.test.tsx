/**
 * AuthBootstrap signs an idle user out (IR-166, NFR-S2).
 */
import { act, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/authSession", () => ({ redirectToLoginSessionExpired: vi.fn() }));

import { AuthBootstrap } from "./AuthBootstrap";
import { IDLE_TIMEOUT_MS, __resetActivity } from "@/lib/activity";
import { redirectToLoginSessionExpired } from "@/lib/authSession";
import { useAuthStore } from "@/store/auth.store";

function signedIn() {
  useAuthStore.setState({
    authReady: true,
    isAuthenticated: true,
    accessToken: "access",
    refreshToken: "refresh",
    hydrateAuth: async () => {},
  });
}

beforeEach(() => {
  vi.useFakeTimers();
  __resetActivity();
  vi.mocked(redirectToLoginSessionExpired).mockClear();
});

afterEach(() => {
  vi.useRealTimers();
});

describe("AuthBootstrap inactivity sign-out", () => {
  it("signs out and sends the user to sign in after 30 idle minutes", () => {
    signedIn();
    render(<AuthBootstrap><p>Private page</p></AuthBootstrap>);
    expect(screen.getByText("Private page")).toBeInTheDocument();

    act(() => { vi.advanceTimersByTime(IDLE_TIMEOUT_MS + 30_000); });

    expect(useAuthStore.getState().isAuthenticated).toBe(false);
    expect(useAuthStore.getState().accessToken).toBeNull();
    expect(redirectToLoginSessionExpired).toHaveBeenCalledTimes(1);
  });

  it("keeps a user who types now and then signed in", () => {
    signedIn();
    render(<AuthBootstrap><p>Private page</p></AuthBootstrap>);

    for (let i = 0; i < 6; i++) {
      act(() => {
        vi.advanceTimersByTime(20 * 60_000);
        window.dispatchEvent(new KeyboardEvent("keydown", { key: "a" }));
      });
    }

    expect(useAuthStore.getState().isAuthenticated).toBe(true);
    expect(redirectToLoginSessionExpired).not.toHaveBeenCalled();
  });

  it("does nothing for someone who is not signed in", () => {
    useAuthStore.setState({ authReady: true, isAuthenticated: false, hydrateAuth: async () => {} });
    render(<AuthBootstrap><p>Public page</p></AuthBootstrap>);
    act(() => { vi.advanceTimersByTime(IDLE_TIMEOUT_MS * 2); });
    expect(redirectToLoginSessionExpired).not.toHaveBeenCalled();
  });
});
