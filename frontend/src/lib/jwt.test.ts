/**
 * Reading claims out of an access token (IR-916).
 *
 * Nothing here verifies a signature, and nothing in the browser can: the Django
 * API is the real boundary (NFR-S4). What matters is that a malformed token is
 * `null` rather than an exception, because the route guard calls this on every
 * navigation.
 */
import { afterEach, describe, expect, it, vi } from "vitest";

import { decodeJwtPayload, isJwtExpired } from "./jwt";
import { expiredToken, makeToken, validToken } from "@/test/authFixtures";

afterEach(() => vi.useRealTimers());

describe("decodeJwtPayload", () => {
  it("reads the claims", () => {
    const token = makeToken({ user_id: 7, role_id: 3, department: "CCS", exp: 1900000000 });

    expect(decodeJwtPayload(token)).toEqual({
      user_id: 7, role_id: 3, department: "CCS", exp: 1900000000,
    });
  });

  it("reads base64url, which swaps + and / for - and _ and drops the padding", () => {
    // "???>>>" encodes to base64 containing both "+" and "/".
    const token = makeToken({ department: "???>>>" });

    expect(token.split(".")[1]).toMatch(/^[A-Za-z0-9_-]+$/);
    expect(decodeJwtPayload(token)?.department).toBe("???>>>");
  });

  it.each([
    ["an empty string", ""],
    ["one segment", "abc"],
    ["two segments", "abc.def"],
    ["four segments", "a.b.c.d"],
    ["a payload that is not base64", "a.!!!.c"],
    ["a payload that is base64 but not JSON", `a.${btoa("not json")}.c`],
  ])("is null for %s", (_label, token) => {
    expect(decodeJwtPayload(token)).toBeNull();
  });

  it("does not throw on an empty-but-well-shaped token", () => {
    expect(() => decodeJwtPayload("..")).not.toThrow();
  });
});

describe("isJwtExpired", () => {
  it("is false while exp is in the future", () => {
    expect(isJwtExpired(decodeJwtPayload(validToken()) ?? {})).toBe(false);
  });

  it("is true once exp has passed", () => {
    expect(isJwtExpired(decodeJwtPayload(expiredToken()) ?? {})).toBe(true);
  });

  it("treats a token with no exp as expired, so it is never trusted", () => {
    expect(isJwtExpired({ user_id: 7 })).toBe(true);
  });

  it("is expired at the exact second exp is reached, and valid one second before", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date(1_000_000 * 1000));

    expect(isJwtExpired({ exp: 1_000_000 })).toBe(true);
    expect(isJwtExpired({ exp: 1_000_001 })).toBe(false);
  });
});
