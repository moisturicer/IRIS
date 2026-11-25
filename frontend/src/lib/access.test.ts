/**
 * The role -> screen matrix, asserted (IR-160).
 *
 * Runs under vitest: `npm test` from `frontend/` (IR-210). This file predates
 * the runner and was executed by a hand-written esbuild-plus-node incantation;
 * its assertions are unchanged, only the harness around them is now real. The
 * `--define:import.meta.env={}` that incantation needed is gone with it: vitest
 * runs through Vite, so `lib/constants.ts` reading `import.meta.env` just works.
 *
 * Why this file exists: the defect IR-160 closes is that `Sidebar` and the router
 * each decided access independently -- the sidebar from `is_staff`, the router
 * from role names -- so ITSO and IERC were shown Role requests and Audit Log and
 * then bounced by a 403. A menu item the user cannot open is a bug that only
 * appears for the roles you don't happen to test as, and there are six of them.
 * Asserting the matrix here is what stops it recurring silently.
 *
 * The source of truth this pins is `docs/ui-ux/02-information-architecture.md`
 * section 5, as amended on 2026-09-06.
 */

import {
  canOpenPath,
  ALL_SCREENS,
  SCREEN_ACCESS,
  canAccess,
  canAuthor,
  hasReviewWork,
  navFor,
  type ScreenKey,
} from "./access";
import { ROLES, type RoleName } from "./constants";
import { describe, expect, test } from "vitest";


const EVERY_ROLE: RoleName[] = [
  ROLES.STUDENT, ROLES.ADVISER, ROLES.RDCO, ROLES.ITSO, ROLES.IERC, ROLES.KTTO, ROLES.SYSTEM_ADMIN,
];

// --- assertions ------------------------------------------------------------

function assertEqual<T>(actual: T, expected: T, what: string) {
  if (actual !== expected) {
    throw new Error(`${what}: expected ${String(expected)}, got ${String(actual)}`);
  }
}

/** Exactly `allowed` may reach `key`; every other role may not. */
function only(key: ScreenKey, allowed: RoleName[]) {
  for (const role of EVERY_ROLE) {
    assertEqual(
      canAccess(role, key), allowed.includes(role),
      `${role} -> ${key}`,
    );
  }
}

// --- everyone --------------------------------------------------------------

test("the corpus and the shared tools are open to every role", () => {
  for (const key of ["discover", "paper", "library", "opportunities", "ai",
                     "notifications", "settings"] as ScreenKey[]) {
    only(key, EVERY_ROLE);
  }
});

// --- authoring: the SRS narrowing -----------------------------------------

test("only Student and Adviser may author a disclosure", () => {
  // SRS Use Cases M2-2.1 / M2-2.2 name the actor "Record Owner (Student or
  // Adviser)". The clearing offices must not author what they later clear, and
  // RDCO performs both intake and final review.
  only("submit", [ROLES.STUDENT, ROLES.ADVISER]);
});

test("no role sees Submit Disclosure in the sidebar; /records/add stays open to authors (IR-534)", () => {
  // Discover is every role's home, and its Publish button is the way in
  // (IR-407), so the Adviser's sidebar shortcut went with the role split.
  // The route stays open to both authors: `/records/add` redirects to the
  // Publish dialog (`router/redirects.tsx`).
  for (const role of EVERY_ROLE) {
    assertEqual(
      navFor(role).some((item) => item.key === "submit"), false,
      `${role} sidebar shows Submit Disclosure`,
    );
  }
  assertEqual(canAccess(ROLES.STUDENT, "submit"), true, "Student may still open /records/add");
  assertEqual(canAccess(ROLES.ADVISER, "submit"), true, "Adviser may still open /records/add");
});

test("whether someone authors is the server's flag, never their role (IR-1096)", () => {
  assertEqual(canAuthor({ can_author: true }), true, "the server says yes");
  assertEqual(canAuthor({ can_author: false }), false, "the server says no");
  assertEqual(canAuthor({}), false, "a payload with no flag is not an author");
  assertEqual(canAuthor(null), false, "no user");
  assertEqual(canAuthor(undefined), false, "not yet loaded");
  // A role name is not consulted: a Student whose flag says no is not offered Publish.
  assertEqual(canAuthor({ role_name: ROLES.STUDENT, can_author: false } as never), false, "Student, flag false");
  assertEqual(canAuthor({ role_name: ROLES.ITSO, can_author: true } as never), true, "ITSO, flag true");
});

test("Notifications is a sidebar link for every role, and its page stays open", () => {
  // It replaced the bell in the sidebar's header, which crowded the logo and
  // the collapse button. The phone bar keeps a bell of its own.
  for (const role of EVERY_ROLE) {
    assertEqual(
      navFor(role).some((item) => item.key === "notifications" && item.to === "/notifications"), true,
      `${role} sidebar lists Notifications`,
    );
    assertEqual(canAccess(role, "notifications"), true, `${role} may open /notifications`);
  }
});

// --- the sidebar's list (IR-413, spec §4.1) --------------------------------

const REVIEW_WORK = { my_reviews: true };
const NO_REVIEW_WORK = { my_reviews: false };
const COORDINATOR_WORK = { my_reviews: true, is_coordinator: true };
const labels = (role: RoleName, access?: { my_reviews: boolean; is_coordinator?: boolean }) =>
  navFor(role, access).map((item) => `${item.section}: ${item.label}`);

test("every role shares one short main list, in the spec's order", () => {
  expect(labels(ROLES.STUDENT)).toEqual([
    "Main: Discover", "Main: Ask IRIS", "Main: My Library", "Main: Notifications", "Main: Calls & Conferences", "Main: Guidelines",
  ]);
  // The Adviser included since IR-534: Discover is its home, so the Submit
  // Disclosure shortcut it kept until then is gone. Changed for IR-1337: My
  // Reviews and My Templates (the Adviser's alone, IR-975) left the main list
  // for a group named Adviser, as RDCO's pages are under RDCO.
  expect(labels(ROLES.ADVISER, REVIEW_WORK)).toEqual([
    "Main: Discover", "Main: Ask IRIS", "Main: My Library", "Main: Notifications",
    "Main: Calls & Conferences", "Main: Guidelines", "Adviser: My Reviews", "Adviser: My Templates",
  ]);
  // An office member's My Reviews is under its office's name (IR-1337); the
  // console is the coordinator's alone, and Workflow analytics RDCO's (IR-1216).
  for (const role of [ROLES.ITSO, ROLES.IERC, ROLES.KTTO]) {
    expect(labels(role, REVIEW_WORK)).toEqual([
      "Main: Discover", "Main: Ask IRIS", "Main: My Library", "Main: Notifications", "Main: Calls & Conferences",
      "Main: Guidelines", `${role}: My Reviews`,
    ]);
    expect(labels(role, COORDINATOR_WORK)).toContain(`${role}: Office Console`);
  }
});

test("RDCO's coordination screens, Import records included, are one RDCO group", () => {
  // Workflow analytics is in this group since IR-1216, not under My Reviews.
  // My Reviews leads it since IR-1337, with Office Console under it.
  expect(labels(ROLES.RDCO, COORDINATOR_WORK)).toEqual([
    "Main: Discover", "Main: Ask IRIS", "Main: My Library", "Main: Notifications", "Main: Calls & Conferences",
    "Main: Guidelines", "RDCO: My Reviews", "RDCO: Office Console", "RDCO: Import Records", "RDCO: Users",
    "RDCO: Role Requests", "RDCO: Download Requests", "RDCO: Call Requests", "RDCO: Delete Requests",
    "RDCO: Reported Comments", "RDCO: Workflow Analytics", "RDCO: Setup",
  ]);
});

// IR-974 (ADR-063 decision 7, amended 2026-11-19): every role but the System
// Admin has Guidelines last in its main list. Anyone signed in may open it.
test("every role but the System Admin opens Guidelines from the end of the main list", () => {
  only("guidelines", EVERY_ROLE);
  for (const role of EVERY_ROLE) {
    const main = navFor(role, REVIEW_WORK).filter((item) => item.section === "Main");
    const last = main[main.length - 1]?.to;
    if (role === ROLES.SYSTEM_ADMIN) assertEqual(last === "/guidelines", false, "the System Admin has no Guidelines link");
    else assertEqual(last, "/guidelines", `${role}'s last main link`);
  }
});

test("Profile and Settings are in the account menu, not the nav, and their pages stay open (IR-933)", () => {
  for (const role of EVERY_ROLE) {
    for (const key of ["profile", "settings"] as ScreenKey[]) {
      assertEqual(navFor(role, REVIEW_WORK).some((item) => item.key === key), false, `${role} nav lists ${key}`);
      assertEqual(canAccess(role, key), true, `${role} may open ${key}`);
    }
  }
});

// --- review ----------------------------------------------------------------

test("the review queue is every reviewer, and excludes Student", () => {
  only("reviewQueue", [ROLES.ADVISER, ROLES.RDCO, ROLES.ITSO, ROLES.IERC, ROLES.KTTO]);
});

test("workflow analytics is RDCO's alone, in its own section at /rdco/analytics (IR-626, IR-1216)", () => {
  only("reviewAnalytics", [ROLES.RDCO]);
  expect(navFor(ROLES.RDCO, REVIEW_WORK).filter((item) => item.key === "reviewAnalytics"))
    .toMatchObject([{ section: "RDCO", to: "/rdco/analytics" }]);
  expect(navFor(ROLES.RDCO, REVIEW_WORK).find((item) => item.key === "reviewAnalytics")?.parent).toBeUndefined();
});

test("My Reviews is listed only when the server says the user has review work", () => {
  const listed = (role: RoleName, access?: { my_reviews: boolean } | null) =>
    navFor(role, access).some((item) => item.key === "reviewQueue");

  // An Adviser with no advisees has the role and nothing to review.
  assertEqual(listed(ROLES.ADVISER, NO_REVIEW_WORK), false, "Adviser with my_reviews false");
  // An office member with no seats still has the office pool to claim from.
  assertEqual(listed(ROLES.ITSO, REVIEW_WORK), true, "ITSO with my_reviews true");
  // No payload is no review work: the route guard reads it the same way.
  assertEqual(listed(ROLES.KTTO, undefined), false, "KTTO with no review_access");
  assertEqual(listed(ROLES.KTTO, null), false, "KTTO with null review_access");
  // The role stays the outer gate: a Student never sees it, whatever the flag.
  assertEqual(listed(ROLES.STUDENT, REVIEW_WORK), false, "Student with my_reviews true");
  assertEqual(hasReviewWork(REVIEW_WORK), true, "hasReviewWork(true)");
  assertEqual(hasReviewWork(NO_REVIEW_WORK), false, "hasReviewWork(false)");
});

// --- RDCO coordination -----------------------------------------------------

test("RDCO alone holds the coordination screens", () => {
  only("roleRequests", [ROLES.RDCO]);
  only("downloadRequests", [ROLES.RDCO]);
  only("deleteRequests", [ROLES.RDCO]);
  only("importRecords", [ROLES.RDCO]);
});

test("the System Admin alone reads the Audit Log, and has its own Users address beside RDCO (ADR-051 §3-4)", () => {
  // Changed deliberately by IR-781: the Audit Log was RDCO's.
  only("audit", [ROLES.SYSTEM_ADMIN]);
  only("users", [ROLES.RDCO]);
  only("adminUsers", [ROLES.SYSTEM_ADMIN]);
});

test("KTTO is not an administrator", () => {
  // ADMIN_ROLES was {KTTO, RDCO}. KTTO evaluates commercial potential; it has
  // no reason to read the audit log or approve a deletion.
  for (const key of ["audit", "roleRequests", "users", "deleteRequests"] as ScreenKey[]) {
    assertEqual(canAccess(ROLES.KTTO, key), false, `KTTO must not reach ${key}`);
  }
});

// --- the structural guarantees --------------------------------------------

test("every screen declares its roles, and none declares an empty set", () => {
  for (const key of ALL_SCREENS) {
    const roles = SCREEN_ACCESS[key].roles;
    if (roles.length === 0) throw new Error(`${key} is reachable by nobody`);
  }
});

test("no screen is reachable by an unknown role", () => {
  for (const key of ALL_SCREENS) {
    for (const role of SCREEN_ACCESS[key].roles) {
      if (!EVERY_ROLE.includes(role)) throw new Error(`${key} names unknown role ${role}`);
    }
  }
});

test("nav is derived from the same map, so a link cannot outrun its gate", () => {
  // The actual IR-160 defect, stated as a property: anything the nav offers a
  // role, that role can open.
  for (const role of EVERY_ROLE) {
    for (const item of navFor(role, COORDINATOR_WORK)) {
      assertEqual(canAccess(role, item.key), true,
        `nav offered ${role} the ${item.key} screen it cannot open`);
    }
  }
});

test("a role is never shown an empty nav section", () => {
  for (const role of EVERY_ROLE) {
    const sections = new Map<string, number>();
    for (const item of navFor(role, REVIEW_WORK)) {
      sections.set(item.section, (sections.get(item.section) ?? 0) + 1);
    }
    for (const [section, count] of sections) {
      if (count === 0) throw new Error(`${role} sees an empty "${section}" section`);
    }
  }
});

test("Student sees no administration section at all", () => {
  const sections = new Set(navFor(ROLES.STUDENT).map((i) => i.section));
  assertEqual(sections.has("Administration"), false, "Student sees Administration");
});

// --- report ----------------------------------------------------------------

// IR-783: each office has its own addresses and named section.
test("RDCO coordination links use the RDCO section and addresses", () => {
  expect(navFor(ROLES.RDCO).filter((item) => item.section !== "Main").map(({ label, to, section }) => ({ label, to, section }))).toEqual([
    { label: "Import Records", to: "/records/import", section: "RDCO" },
    { label: "Users", to: "/rdco/users", section: "RDCO" },
    { label: "Role Requests", to: "/rdco/role-requests", section: "RDCO" },
    { label: "Download Requests", to: "/rdco/download-requests", section: "RDCO" },
    { label: "Call Requests", to: "/rdco/call-requests", section: "RDCO" },
    { label: "Delete Requests", to: "/rdco/delete-requests", section: "RDCO" },
    { label: "Reported Comments", to: "/moderation/comments", section: "RDCO" },
    { label: "Workflow Analytics", to: "/rdco/analytics", section: "RDCO" },
    { label: "Setup", to: "/rdco/setup", section: "RDCO" },
  ]);
});

describe("canOpenPath: may this role open this address? (IR-1207)", () => {
  test("a role may open a page its screen allows, with query and fragment", () => {
    expect(canOpenPath(ROLES.RDCO, "/rdco/users?page=2#row-4")).toBe(true);
    expect(canOpenPath(ROLES.KTTO, "/review")).toBe(true);
  });

  test("a role may not open a page its screen refuses", () => {
    expect(canOpenPath(ROLES.STUDENT, "/rdco/users")).toBe(false);
    expect(canOpenPath(ROLES.KTTO, "/admin/audit")).toBe(false);
  });

  test("a page's own entry wins over a pattern that also matches it", () => {
    // `/records/:id` (everyone) matches `/records/import` too; the import
    // screen is RDCO's alone, and the router sends the address there.
    expect(canOpenPath(ROLES.STUDENT, "/records/import")).toBe(false);
    expect(canOpenPath(ROLES.STUDENT, "/records/42")).toBe(true);
  });

  test("a page two screens share is open to both screens' roles", () => {
    expect(canOpenPath(ROLES.SYSTEM_ADMIN, "/moderation/comments")).toBe(true);
    expect(canOpenPath(ROLES.RDCO, "/moderation/comments")).toBe(true);
    expect(canOpenPath(ROLES.STUDENT, "/moderation/comments")).toBe(false);
  });

  test("an address no screen names is left to the router", () => {
    // Retired addresses redirect, and unknown ones show Not Found; neither is
    // a refusal, so the login screen may still go there.
    expect(canOpenPath(ROLES.STUDENT, "/review/12/evaluate")).toBe(true);
  });

  test("no role opens nothing", () => {
    expect(canOpenPath(null, "/")).toBe(false);
  });
});
