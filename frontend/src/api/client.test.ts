import axios from "axios";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { refreshSession } from "./client";
import { useAuthStore } from "@/store/auth.store";

const { redirect } = vi.hoisted(() => ({ redirect: vi.fn() }));
vi.mock("@/lib/authSession", () => ({ redirectToLoginSessionExpired: redirect }));

// The refresh shared by apiClient and the Ask IRIS streams (IR-634).
describe("refreshSession", () => {
  let post: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    useAuthStore.setState({ accessToken: "old", refreshToken: "r1", isAuthenticated: true });
    post = vi.spyOn(axios, "post");
  });
  afterEach(() => { vi.restoreAllMocks(); redirect.mockClear(); });

  it("stores and returns the new tokens", async () => {
    post.mockResolvedValue({ data: { access: "a2", refresh: "r2" } });

    expect(await refreshSession()).toBe("a2");
    expect(useAuthStore.getState()).toMatchObject({ accessToken: "a2", refreshToken: "r2" });
    expect(post.mock.calls[0][2]).toMatchObject({ headers: { "X-IRIS-Idle-Seconds": expect.any(String) } });
  });

  it("logs out and redirects when the refresh is refused, as an idle session's is", async () => {
    post.mockRejectedValue(new Error("401 session_idle"));

    expect(await refreshSession()).toBeNull();
    expect(useAuthStore.getState().isAuthenticated).toBe(false);
    expect(redirect).toHaveBeenCalledTimes(1);
  });

  it("logs out and redirects with no refresh token to spend", async () => {
    useAuthStore.setState({ refreshToken: null });

    expect(await refreshSession()).toBeNull();
    expect(post).not.toHaveBeenCalled();
    expect(redirect).toHaveBeenCalledTimes(1);
  });

  it("discards a refresh that finishes after the user logged out", async () => {
    post.mockImplementation(async () => {
      useAuthStore.getState().logout();
      return { data: { access: "a2", refresh: "r2" } };
    });

    expect(await refreshSession()).toBeNull();
    expect(useAuthStore.getState().accessToken).toBeNull();
  });
});
