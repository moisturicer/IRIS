/**
 * The signed-in account updates live (ADR-073, IR-1289): an `account` hint, or
 * the tab shown again, reads `/auth/me` into the store, and a changed role
 * reopens the stream so the new role's channel is heard.
 */
import { act, render, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const me = vi.hoisted(() => vi.fn());
vi.mock("@/api/auth", () => ({ authApi: { me } }));
vi.mock("@/lib/live", async (actual) => ({
  ...(await actual<typeof import("@/lib/live")>()),
  startLive: vi.fn(),
  stopLive: vi.fn(),
  restartLive: vi.fn(),
}));

import { LIVE_COALESCE_MS } from "@/hooks/useLiveRefresh";
import { emitLiveHint, restartLive } from "@/lib/live";
import { useAuthStore } from "@/store/auth.store";
import type { User } from "@/types/auth";

import { AuthBootstrap } from "./AuthBootstrap";

const pending = { id: 7, role_name: null, role_request: { status: "pending" } } as unknown as User;
const student = { id: 7, role_name: "Student", role_request: null } as unknown as User;

function signedInAs(user: User) {
  useAuthStore.setState({
    authReady: true, isAuthenticated: true, accessToken: "access", user,
    hydrateAuth: async () => {}, remembered: true,
  });
}

async function hint(topics: string[]) {
  act(() => { emitLiveHint(topics); });
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, LIVE_COALESCE_MS + 50)); });
}

beforeEach(() => {
  me.mockReset();
  vi.mocked(restartLive).mockClear();
});

describe("AuthBootstrap, live account (IR-1289)", () => {
  it("takes the new role from an account hint and reopens the stream", async () => {
    signedInAs(pending);
    me.mockResolvedValue({ data: student });
    render(<AuthBootstrap><p>App</p></AuthBootstrap>);

    await hint(["reviews"]);
    expect(me).not.toHaveBeenCalled();

    await hint(["account"]);
    await waitFor(() => expect(useAuthStore.getState().user?.role_name).toBe("Student"));
    expect(restartLive).toHaveBeenCalledTimes(1);
  });

  it("keeps the stream when the role is unchanged", async () => {
    signedInAs(student);
    me.mockResolvedValue({ data: { ...student, first_name: "Ana" } });
    render(<AuthBootstrap><p>App</p></AuthBootstrap>);

    await hint(["account"]);
    await waitFor(() => expect(me).toHaveBeenCalledTimes(1));
    expect(restartLive).not.toHaveBeenCalled();
  });

  it("keeps the account shown when the read fails", async () => {
    signedInAs(pending);
    me.mockRejectedValue(new Error("offline"));
    render(<AuthBootstrap><p>App</p></AuthBootstrap>);

    await hint(["account"]);
    await waitFor(() => expect(me).toHaveBeenCalledTimes(1));
    expect(useAuthStore.getState().user).toBe(pending);
    expect(useAuthStore.getState().isAuthenticated).toBe(true);
  });
});
