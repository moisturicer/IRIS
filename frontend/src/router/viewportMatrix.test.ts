// IR-910: every routed screen is put through four widths by the viewport matrix
// (e2e/smoke/viewport-matrix.spec.ts). The list of screens it must cover is
// `matrixRoutes.json`, which sits here so this test reads only its own stack
// (CODING_STANDARDS X1); the e2e suite, which is allowed to read across, checks
// its catalogue against the same file (e2e/smoke/viewport-coverage.spec.ts).
// This test fails when a route is added or removed without the file being
// updated, which is the prompt to add the screen to the matrix.
import type { RouteObject } from "react-router-dom";
import { describe, expect, it } from "vitest";
import matrixRoutes from "./matrixRoutes.json";
import { routes } from "./index";
import { REDIRECTS } from "./redirects";

/** Every address pattern the router draws a page for, as the full path a visitor types. */
function screenPatterns(list: RouteObject[], base = ""): string[] {
  return list.flatMap((route) => {
    const own = route.path ? `${base}/${route.path}`.replace(/\/+/g, "/") : base;
    const below = route.children ? screenPatterns(route.children, own) : [];
    // A leaf, or an index route, is a page; a pathless layout or a guard is not.
    const isPage = (route.index || !route.children) && (route.path !== undefined || route.index);
    return isPage ? [own || "/", ...below] : below;
  });
}

describe("viewport matrix routes (IR-910)", () => {
  // A retired address only moves the visitor on; the page it lands on is a screen of its own.
  const retired = new Set(REDIRECTS.map((r) => `/${r.path}`));
  const routed = [...new Set(screenPatterns(routes))]
    .filter((pattern) => !retired.has(pattern))
    .map((pattern) => (pattern === "/*" ? "*" : pattern))
    .sort();

  it("lists every routed screen", () => {
    expect(routed.filter((p) => !matrixRoutes.includes(p)), "routes missing from matrixRoutes.json").toEqual([]);
  });

  it("lists no route the router lacks", () => {
    expect(matrixRoutes.filter((p) => !routed.includes(p)), "matrixRoutes.json entries with no route").toEqual([]);
  });
});
