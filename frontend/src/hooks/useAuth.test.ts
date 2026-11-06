/**
 * `useAuth` is a window onto the auth store (IR-916). The store's own rules are
 * tested in `store/auth.store.test.ts` and `lib/authStorage.test.ts`; this pins
 * what a component sees through the hook, and that it re-renders when the
 * session changes under it.
 */
import { beforeEach, describe, expect, it } from "vitest";
import { act, renderHook } from "@testing-library/react";

import { useAuth } from "./useAuth";
import { useAuthStore } from "@/store/auth.store";
import { makeUser } from "@/test/authFixtures";

beforeEach(() => {
  sessionStorage.clear();
  useAuthStore.setState({
    user: null, accessToken: null, refreshToken: null, isAuthenticated: false,
  });
});

describe("useAuth", () => {
  it("is signed out with no user and no refresh token to begin with", () => {
    const { result } = renderHook(() => useAuth());

    expect(result.current.user).toBeNull();
    expect(result.current.isAuthenticated).toBe(false);
    expect(result.current.refreshToken).toBeNull();
  });

  it("reflects a sign-in made through the hook's own login", () => {
    const { result } = renderHook(() => useAuth());
    const user = makeUser();

    act(() => result.current.login(user, "access-1", "refresh-1"));

    expect(result.current.user).toEqual(user);
    expect(result.current.isAuthenticated).toBe(true);
    expect(result.current.refreshToken).toBe("refresh-1");
  });

  it("reflects a sign-out", () => {
    useAuthStore.getState().login(makeUser(), "access-1", "refresh-1");
    const { result } = renderHook(() => useAuth());

    act(() => result.current.logout());

    expect(result.current.user).toBeNull();
    expect(result.current.isAuthenticated).toBe(false);
    expect(result.current.refreshToken).toBeNull();
  });

  it("re-renders when the session ends somewhere else, such as the 401 handler", () => {
    useAuthStore.getState().login(makeUser(), "access-1", "refresh-1");
    const { result } = renderHook(() => useAuth());
    expect(result.current.isAuthenticated).toBe(true);

    act(() => useAuthStore.getState().logout());

    expect(result.current.isAuthenticated).toBe(false);
  });

  it("picks up a rotated refresh token", () => {
    useAuthStore.getState().login(makeUser(), "access-1", "refresh-1");
    const { result } = renderHook(() => useAuth());

    act(() => useAuthStore.getState().setTokens("access-2", "refresh-2"));

    expect(result.current.refreshToken).toBe("refresh-2");
  });

  it("updateUser replaces the user without touching the session", () => {
    useAuthStore.getState().login(makeUser(), "access-1", "refresh-1");
    const { result } = renderHook(() => useAuth());

    act(() => result.current.updateUser(makeUser({ first_name: "Renamed" })));

    expect(result.current.user?.first_name).toBe("Renamed");
    expect(result.current.isAuthenticated).toBe(true);
    expect(result.current.refreshToken).toBe("refresh-1");
  });
});
