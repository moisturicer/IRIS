/**
 * `useRole`'s flags decide what a screen offers (IR-916), so each role is
 * pinned against the whole set: a flag that is true for the wrong role shows a
 * control to someone the server will then refuse. UX only; the API re-checks.
 */
import { beforeEach, describe, expect, it } from "vitest";
import { act, renderHook } from "@testing-library/react";

import { useRole } from "./useRole";
import { useAuthStore } from "@/store/auth.store";
import { ROLES, type RoleName } from "@/lib/constants";
import { makeUser } from "@/test/authFixtures";

beforeEach(() => {
  useAuthStore.setState({ user: null, accessToken: null, refreshToken: null, isAuthenticated: false });
});

function roleFlags(user: ReturnType<typeof makeUser> | null) {
  useAuthStore.setState({ user, isAuthenticated: user !== null });
  const { result } = renderHook(() => useRole());
  const { roleName, isDjangoStaff, isReviewer, isStaff, ...named } = result.current;
  return { roleName, isDjangoStaff, isReviewer, isStaff, named };
}

describe("useRole", () => {
  it("has no role and no access when signed out", () => {
    const flags = roleFlags(null);

    expect(flags.roleName).toBeNull();
    expect(flags.isDjangoStaff).toBe(false);
    expect(flags.isReviewer).toBe(false);
    expect(flags.isStaff).toBe(false);
    expect(Object.values(flags.named).some(Boolean)).toBe(false);
  });

  // role, the one named flag it sets, reviewer, staff
  it.each<[RoleName, string, boolean, boolean]>([
    [ROLES.STUDENT, "isStudent", false, false],
    [ROLES.ADVISER, "isAdviser", true, false],
    [ROLES.KTTO, "isKTTO", true, true],
    [ROLES.RDCO, "isRDCO", true, true],
    [ROLES.ITSO, "isITSO", true, true],
    [ROLES.IERC, "isIERC", true, true],
    [ROLES.SYSTEM_ADMIN, "", false, false],
  ])("%s", (role, flag, reviewer, staff) => {
    const flags = roleFlags(makeUser({ role_name: role }));

    expect(flags.roleName).toBe(role);
    expect(flags.isReviewer).toBe(reviewer);
    expect(flags.isStaff).toBe(staff);
    expect(flags.isDjangoStaff).toBe(false);
    // Exactly the one named flag for this role, and none other.
    const set = Object.entries(flags.named).filter(([, on]) => on).map(([name]) => name);
    expect(set).toEqual(flag ? [flag] : []);
  });

  it("an Adviser reviews but is not office staff", () => {
    const flags = roleFlags(makeUser({ role_name: ROLES.ADVISER }));

    expect(flags.isReviewer).toBe(true);
    expect(flags.isStaff).toBe(false);
  });

  it("a Django staff account counts as reviewer and staff even with no role", () => {
    const flags = roleFlags(makeUser({ role_name: undefined, is_staff: true } as never));

    expect(flags.isDjangoStaff).toBe(true);
    expect(flags.isReviewer).toBe(true);
    expect(flags.isStaff).toBe(true);
    expect(Object.values(flags.named).some(Boolean)).toBe(false);
  });

  it("a superuser counts as Django staff", () => {
    const flags = roleFlags(makeUser({ role_name: ROLES.STUDENT, is_superuser: true }));

    expect(flags.isDjangoStaff).toBe(true);
    expect(flags.isStaff).toBe(true);
    // The named flag still says what the account's role is.
    expect(flags.named.isStudent).toBe(true);
  });

  it("is_staff false is not enough: only a strict true grants it", () => {
    const flags = roleFlags(makeUser({ role_name: ROLES.STUDENT, is_staff: false, is_superuser: false }));

    expect(flags.isDjangoStaff).toBe(false);
    expect(flags.isStaff).toBe(false);
  });

  it("follows the user when the session changes", () => {
    useAuthStore.setState({ user: makeUser({ role_name: ROLES.STUDENT }), isAuthenticated: true });
    const { result } = renderHook(() => useRole());
    expect(result.current.isStudent).toBe(true);

    act(() => useAuthStore.setState({ user: makeUser({ role_name: ROLES.RDCO }) }));

    expect(result.current.isStudent).toBe(false);
    expect(result.current.isRDCO).toBe(true);
    expect(result.current.isStaff).toBe(true);
  });
});
