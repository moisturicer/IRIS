/**
 * Runs once before every test file (IR-210).
 *
 * `@testing-library/jest-dom/vitest` is the `/vitest` entry point rather than
 * the bare package: it registers the matchers *and* their type augmentation
 * against vitest's `Assertion` interface, so `toHaveAccessibleDescription` is
 * both available at runtime and known to `tsc`.
 */
import "@testing-library/jest-dom/vitest";

import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

// Without this, each test's markup stays in the shared jsdom `document` and
// the next `getByRole` sees two matching controls. The failure reads as an
// ambiguous query rather than as leaked state, which is a long way to travel
// for a missing line.
afterEach(() => {
  cleanup();
});
