/**
 * Screens load on demand (IR-1248).
 *
 * Every screen is in a chunk of its own except the two a visit can open on,
 * Discover and Sign in: making the first screen lazy would add a second
 * download before anything can be drawn. A sidebar or account-menu link
 * prefetches its screen when hovered or focused, so the click finds it loaded.
 */
import { describe, expect, it } from "vitest";

import routerSource from "./index.tsx?raw";
import { preloadScreen, SCREEN_LOADERS } from "./lazyScreens";

/** Static imports of feature code, by module path. */
function staticFeatureImports(text: string): string[] {
  return [...text.matchAll(/^\s*import\s+(?!type\s)[^;]*?from\s+["'](@\/features\/[^"']+)["']/gm)]
    .map((m) => m[1])
    .sort();
}

describe("the router (IR-1248)", () => {
  it("imports statically only the screens a visit can open on, and the error screens", () => {
    expect(staticFeatureImports(routerSource)).toEqual([
      "@/features/auth/LoginPage",
      "@/features/dashboard/HomePage",
      "@/features/errors/NotFoundScreen",
      "@/features/errors/RouteErrorScreen",
    ]);
  });
});

describe("preloadScreen (IR-1248)", () => {
  it("starts loading the screen at a path the sidebar links to", async () => {
    for (const path of ["/records/mine", "/settings", "/review", "/notifications", "/opportunities", "/ai"]) {
      expect(SCREEN_LOADERS.has(path), path).toBe(true);
    }
    await expect(preloadScreen("/settings")).resolves.toBeUndefined();
  });

  it("does nothing for a path with no screen of its own, and never throws", async () => {
    await expect(preloadScreen("/records/29")).resolves.toBeUndefined();
    await expect(preloadScreen("/no-such-page")).resolves.toBeUndefined();
  });
});
