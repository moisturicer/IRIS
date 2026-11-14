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
 * from role names -- so ITSO and IERC were shown Role Requests and Audit Log and
 * then bounced by a 403. A menu item the user cannot open is a bug that only
 * appears for the roles you don't happen to test as, and there are six of them.
 * Asserting the matrix here is what stops it recurring silently.
 *
 * The source of truth this pins is `docs/ui-ux/02-information-architecture.md`
 * section 5, as amended on 2026-09-06.
 */

import {
  ALL_SCREENS,
  SCREEN_ACCESS,
  canAccess,
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
                     "notifications", "settings", "help"] as ScreenKey[]) {
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

test("Notifications is the bell, not a sidebar link, and its page stays open (IR-519)", () => {
  // The bell at the top of the sidebar is the one notification entry; a link
  // beside it said the same thing twice. Its "View all" still reaches the page.
  for (const role of EVERY_ROLE) {
    assertEqual(
      navFor(role).some((item) => item.key === "notifications"), false,
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
    "Main: Discover", "Main: Ask IRIS", "Main: My Library", "Main: Calls & Conferences",
  ]);
  // The Adviser included since IR-534: Discover is its home, so the Submit
  // Disclosure shortcut it kept until then is gone. No office, so nothing
  // nests under My Reviews.
  expect(labels(ROLES.ADVISER, REVIEW_WORK)).toEqual([
    "Main: Discover", "Main: Ask IRIS", "Main: My Library", "Main: My Reviews", "Main: Calls & Conferences",
  ]);
  // An office member also has its Workflow analytics, nested under My Reviews
  // (IR-1085, D5); the console is the coordinator's alone.
  for (const role of [ROLES.ITSO, ROLES.IERC, ROLES.KTTO]) {
    expect(labels(role, REVIEW_WORK)).toEqual([
      "Main: Discover", "Main: Ask IRIS", "Main: My Library", "Main: My Reviews",
      "Main: Workflow analytics", "Main: Calls & Conferences",
    ]);
  }
});

test("RDCO's coordination screens, Import Records included, are one RDCO group", () => {
  expect(labels(ROLES.RDCO, REVIEW_WORK)).toEqual([
    "Main: Discover", "Main: Ask IRIS", "Main: My Library", "Main: My Reviews",
    "Main: Workflow analytics", "Main: Calls & Conferences",
    "RDCO: Import Records", "RDCO: Users", "RDCO: Role Requests", "RDCO: Download Requests",
    "RDCO: Delete Requests", "RDCO: Setup",
  ]);
});

// IR-1085, D5: Office console and Workflow analytics nest under My Reviews, for
// the roles that already have them, and keep the addresses they had.
describe("the pages nested under My Reviews (IR-1085, D5)", () => {
  const nested = (role: RoleName, access?: { my_reviews: boolean; is_coordinator?: boolean } | null) =>
    navFor(role, access)
      .filter((item) => item.parent === "reviewQueue")
      .map(({ label, to }) => ({ label, to }));

  test("a coordinator reaches the console and analytics at their existing addresses", () => {
    expect(nested(ROLES.ITSO, COORDINATOR_WORK)).toEqual([
      { label: "Office console", to: "/review/office" },
      { label: "Workflow analytics", to: "/review/analytics" },
    ]);
  });

  test("RDCO's coordinator gets them too, and a missing flag is not a coordinator", () => {
    expect(nested(ROLES.RDCO, COORDINATOR_WORK).map((i) => i.label))
      .toEqual(["Office console", "Workflow analytics"]);
    expect(nested(ROLES.RDCO, { my_reviews: true, is_coordinator: undefined }).map((i) => i.label))
      .toEqual(["Workflow analytics"]);
  });

  test("an office member who is not a coordinator sees analytics but not the console", () => {
    expect(nested(ROLES.IERC, REVIEW_WORK).map((i) => i.label)).toEqual(["Workflow analytics"]);
    expect(nested(ROLES.IERC, { my_reviews: true, is_coordinator: false }).map((i) => i.label))
      .toEqual(["Workflow analytics"]);
  });

  test("roles without the screens see neither, even with the flags set", () => {
    for (const role of [ROLES.STUDENT, ROLES.ADVISER, ROLES.SYSTEM_ADMIN]) {
      expect(nested(role, COORDINATOR_WORK), role).toEqual([]);
    }
  });

  test("they hang from My Reviews: no My Reviews, no nested pages", () => {
    expect(nested(ROLES.ITSO, { my_reviews: false, is_coordinator: true })).toEqual([]);
    expect(nested(ROLES.ITSO, null)).toEqual([]);
  });

  test("the office console is the offices', and its gate is the one the sidebar reads", () => {
    only("reviewOffice", [ROLES.RDCO, ROLES.ITSO, ROLES.IERC, ROLES.KTTO]);
  });
});

test("the System Admin's nav is Discover, Users, Audit Log, Account Deletions and Retention (IR-783, IR-788, IR-795, IR-972)", () => {
  expect(labels(ROLES.SYSTEM_ADMIN)).toEqual([
    "Main: Discover",
    "Administration: Users", "Administration: Audit Log", "Administration: Account Deletions",
    "Administration: Retention",
  ]);
});

// IR-972 (ADR-063 decision 9): the Notices page became Setup's Notice section.
// Nobody has a Notices link; the System Admin reads publications in the Audit Log.
test("no role has a Notices link, and the Notice is RDCO's, on Setup", () => {
  for (const role of Object.values(ROLES)) {
    expect(navFor(role).filter((item) => item.label === "Notices"), role).toEqual([]);
  }
  expect(canAccess(ROLES.RDCO, "setup")).toBe(true);
  expect(canAccess(ROLES.SYSTEM_ADMIN, "setup")).toBe(false);
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

test("workflow analytics is the four offices, not the Adviser (IR-626)", () => {
  only("reviewAnalytics", [ROLES.RDCO, ROLES.ITSO, ROLES.IERC, ROLES.KTTO]);
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
    { label: "Delete Requests", to: "/rdco/delete-requests", section: "RDCO" },
    { label: "Setup", to: "/rdco/setup", section: "RDCO" },
  ]);
});
