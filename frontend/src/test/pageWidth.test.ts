/**
 * No page sets its own outer width (IR-519, IR-522).
 *
 * Pages each picked a cap -- 1152, 1200, 1400px -- which is how the app came
 * to leave wide empty margins at 90% zoom on some screens and not others.
 * The width now comes from one place: `PageContainer`, chosen per route by
 * `AppShell`. A page-sized cap written into a page brings the old problem
 * back, so this scans for one. Dialogs and reading columns use smaller caps
 * (`max-w-2xl`, `max-w-prose`) and are not caught.
 */
import { describe, expect, it } from "vitest";

const pages = Object.entries(
  import.meta.glob<string>("/src/features/**/*Page.tsx", { query: "?raw", import: "default", eager: true }),
);

/**
 * A cap wide enough to be a page's: 5xl (64rem) and up, the `page` token itself,
 * four-digit pixels, or 64rem and up written as an arbitrary value.
 */
const PAGE_CAP = /\bmax-w-(?:[5-7]xl|screen-\w+|page\b|\[\d{4}px\]|\[(?:6[4-9]|[7-9]\d|\d{3,})(?:\.\d+)?rem\])/g;

describe("page width", () => {
  it("finds the pages it scans", () => {
    expect(pages.length).toBeGreaterThan(10);
  });

  it("is set by PageContainer, never by a page", () => {
    const offenders = pages.flatMap(([path, source]) =>
      [...source.matchAll(PAGE_CAP)].map((m) => `${path}: ${m[0]}`),
    );
    expect(offenders).toEqual([]);
  });
});
