/**
 * One top-level heading per entry screen, at every window size (IR-211).
 *
 * A screen-reader user orients by the `<h1>`. Before IR-211 the only one in the
 * shared entry layout lived inside the desktop brand panel, and only in its
 * signup variant: login never had one, and when IR-208 made the panel
 * `hidden lg:flex` signup lost its own on a phone, because `display:none`
 * removes an element from the accessibility tree.
 *
 * **What "at every breakpoint" means under jsdom.** jsdom loads no stylesheet
 * and evaluates no media query, so rendering at 360, 768 and 1440 px would
 * render the same tree three times and prove nothing. Breakpoints reach these
 * screens only as Tailwind display utilities (`hidden`, `lg:flex`,
 * `lg:hidden`), so the third test asserts the thing that would actually take
 * the heading away at some width: no utility of that kind, and no
 * `aria-hidden`, on the `<h1>` or on anything containing it. The rendered
 * check at the three widths is a browser check, recorded on the PR.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ReactElement } from "react";
import { Route, Routes } from "react-router-dom";

import { accountsApi } from "@/api/accounts";
import { authApi } from "@/api/auth";

import { renderScreen, screen } from "@/test/render";

import EmailVerifyPage from "./EmailVerifyPage";
import LoginPage from "./LoginPage";
import SignupPage from "./SignupPage";

const EMPTY_PAGE = { data: { count: 0, next: null, previous: null, results: [] } };

interface EntryScreen {
  name: string;
  render: () => void;
  /** The per-screen title, which sits one level below the layout's `<h1>`. */
  title: string;
}

function routed(element: ReactElement, path: string, route: string) {
  renderScreen(
    <Routes>
      <Route path={path} element={element} />
    </Routes>,
    { route },
  );
}

const SCREENS: EntryScreen[] = [
  {
    name: "login",
    render: () => renderScreen(<LoginPage />, { route: "/login" }),
    title: "Welcome Back",
  },
  {
    name: "signup",
    render: () => {
      vi.spyOn(accountsApi, "colleges").mockResolvedValue(EMPTY_PAGE as never);
      vi.spyOn(accountsApi, "departments").mockResolvedValue(EMPTY_PAGE as never);
      vi.spyOn(accountsApi, "courses").mockResolvedValue(EMPTY_PAGE as never);
      renderScreen(<SignupPage />, { route: "/signup" });
    },
    title: "Create an Account",
  },
  {
    name: "email verification",
    render: () => {
      vi.spyOn(authApi, "activate").mockResolvedValue({ data: {} } as never);
      routed(<EmailVerifyPage />, "/verify-email/:uidb64/:token", "/verify-email/abc/def");
    },
    title: "Email Verified",
  },
];

/** A Tailwind utility that sets `display:none` at some width, or `visibility:hidden`. */
const HIDING_UTILITY = /^(?:[a-z0-9]+:)*(?:hidden|invisible)$/;

/** The utilities and attributes on `element` or any ancestor that could hide it. */
function hidersOf(element: Element): string[] {
  const found: string[] = [];
  for (let node: Element | null = element; node; node = node.parentElement) {
    if (node.getAttribute("aria-hidden") === "true") found.push(`aria-hidden on <${node.tagName.toLowerCase()}>`);
    if (node.hasAttribute("hidden")) found.push(`hidden attribute on <${node.tagName.toLowerCase()}>`);
    for (const cls of Array.from(node.classList)) {
      if (HIDING_UTILITY.test(cls)) found.push(`${cls} on <${node.tagName.toLowerCase()}>`);
    }
  }
  return found;
}

function headingLevel(heading: HTMLElement): number {
  return Number(heading.tagName.slice(1)) || Number(heading.getAttribute("aria-level"));
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe.each(SCREENS)("the $name screen", ({ render, title }) => {
  it("has exactly one top-level heading", async () => {
    render();
    await screen.findByRole("heading", { name: title });

    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
  });

  it("puts its title one level below that heading, and never skips a level", async () => {
    render();
    const titleHeading = await screen.findByRole("heading", { name: title });

    expect(headingLevel(titleHeading)).toBe(2);

    const levels = screen.getAllByRole("heading").map(headingLevel);
    expect(levels[0]).toBe(1);
    levels.forEach((level, i) => {
      if (i > 0) expect(level, `heading ${i + 1} of ${levels.join(", ")}`).toBeLessThanOrEqual(levels[i - 1] + 1);
    });
  });

  it("keeps the top-level heading out of anything a breakpoint can hide", async () => {
    render();
    await screen.findByRole("heading", { name: title });

    const [h1] = screen.getAllByRole("heading", { level: 1 });
    expect(hidersOf(h1)).toEqual([]);
  });
});
