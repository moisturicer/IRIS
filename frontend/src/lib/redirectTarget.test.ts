/**
 * The one destination validator, exercised against the inputs that matter
 * (IR-236).
 *
 * The interesting cases here are all hostile. `safeRedirectPath` is what stands
 * between "sign in and land where you asked" and "the login screen is an open
 * redirector", so the tests below are mostly a list of the ways a string can
 * look like an in-app path and not be one.
 */
import { describe, expect, it } from "vitest";

import { safeRedirectPath } from "./redirectTarget";

describe("safeRedirectPath", () => {
  it("accepts an in-app path", () => {
    expect(safeRedirectPath("/records/42")).toBe("/records/42");
  });

  it("keeps the query string and the fragment", () => {
    // A deep link into the review queue carries its filters in the query. A
    // validator that returned only `pathname` would sign you in and then drop
    // you on an unfiltered queue -- the same disappointment this ticket exists
    // to remove, one step later.
    expect(safeRedirectPath("/review?status=pending&office=ktto#row-3")).toBe(
      "/review?status=pending&office=ktto#row-3",
    );
  });

  it("accepts the root path", () => {
    expect(safeRedirectPath("/")).toBe("/");
  });

  it("rejects an absolute URL to another origin", () => {
    expect(safeRedirectPath("https://evil.example/steal")).toBeNull();
  });

  it("rejects an absolute URL back to our own origin", () => {
    // Even a same-origin absolute URL is refused rather than parsed down to its
    // path: the guard never produces one, so anything absolute arrived from
    // somewhere else and gets no benefit of the doubt.
    expect(safeRedirectPath(`${window.location.origin}/records/42`)).toBeNull();
  });

  it("rejects a protocol-relative URL", () => {
    // `//evil.example` is the classic open-redirect payload: it starts with a
    // slash, so a naive `startsWith("/")` check waves it through, and the
    // browser reads it as "same scheme, different host".
    expect(safeRedirectPath("//evil.example/steal")).toBeNull();
  });

  it("rejects the backslash spelling of a protocol-relative URL", () => {
    // WHATWG URL parsing treats a backslash as a slash for http(s), so
    // `/\evil.example` resolves to `//evil.example`.
    expect(safeRedirectPath("/\\evil.example/steal")).toBeNull();
    expect(safeRedirectPath("\\\\evil.example/steal")).toBeNull();
  });

  it("rejects a protocol-relative URL smuggled past the check with a control character", () => {
    // Browsers strip tab, newline and carriage return from a URL before parsing
    // it, so `/<tab>/evil.example` navigates to `//evil.example`. The validator
    // has to strip them too, or it validates a different string from the one
    // the browser will act on.
    expect(safeRedirectPath("/\t/evil.example")).toBeNull();
    expect(safeRedirectPath("/\n/evil.example")).toBeNull();
    expect(safeRedirectPath("  //evil.example")).toBeNull();
  });

  it("rejects a protocol-relative URL assembled out of dot segments", () => {
    // The bypass that checking only the *input* misses. `new URL` resolves
    // `/..` by popping a segment, and popping the empty leading segment turns
    // `/..//evil.example` into the pathname `//evil.example` — so the input
    // never starts with `//`, `url.origin` is still ours, and a validator that
    // trusts those two facts hands back the protocol-relative string it exists
    // to refuse. The check has to run on what is returned.
    expect(safeRedirectPath("/..//evil.example")).toBeNull();
    expect(safeRedirectPath("/../..//evil.example")).toBeNull();
    expect(safeRedirectPath("/a/../..//evil.example/steal")).toBeNull();
  });

  it("still accepts a path whose dot segments resolve to somewhere in-app", () => {
    // The fix must not be "reject anything containing `..`" -- that would also
    // throw away destinations that are perfectly fine once resolved.
    expect(safeRedirectPath("/review/12/../13")).toBe("/review/13");
  });

  it("rejects a javascript: URL", () => {
    expect(safeRedirectPath("javascript:alert(1)")).toBeNull();
  });

  it("rejects a data: URL", () => {
    expect(safeRedirectPath("data:text/html,<script>alert(1)</script>")).toBeNull();
  });

  it("rejects a bare relative path", () => {
    // Not hostile, just unusable: without a leading slash the destination
    // depends on whatever the current URL happens to be when it is applied.
    expect(safeRedirectPath("records/42")).toBeNull();
    expect(safeRedirectPath("../admin/audit")).toBeNull();
  });

  it("rejects the auth screens, which would be a loop", () => {
    expect(safeRedirectPath("/login")).toBeNull();
    expect(safeRedirectPath("/login?reason=session_expired")).toBeNull();
    expect(safeRedirectPath("/signup")).toBeNull();
  });

  it("rejects anything that is not a non-empty string", () => {
    expect(safeRedirectPath(undefined)).toBeNull();
    expect(safeRedirectPath(null)).toBeNull();
    expect(safeRedirectPath("")).toBeNull();
    expect(safeRedirectPath("   ")).toBeNull();
    expect(safeRedirectPath(42)).toBeNull();
    expect(safeRedirectPath({ from: "/records/42" })).toBeNull();
  });
});
