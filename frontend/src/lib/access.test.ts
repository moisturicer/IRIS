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
import { expect, test } from "vitest";


const EVERY_ROLE: RoleName[] = [
  ROLES.STUDENT, ROLES.ADVISER, ROLES.RDCO, ROLES.ITSO, ROLES.IERC, ROLES.KTTO,
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

test("a Student publishes from Discover, so the sidebar offers no Submit Disclosure (IR-407)", () => {
  // The route stays open to both authors -- `/records/add` redirects to the
  // Publish dialog -- only the sidebar shortcut narrows. An Adviser's home is
  // still the Dashboard, not Discover, so the shortcut is an Adviser's only
  // menu route into Publish until IR-413 makes Discover everyone's home.
  const inNav = (role: RoleName) => navFor(role).some((item) => item.key === "submit");

  assertEqual(inNav(ROLES.STUDENT), false, "Student sidebar shows Submit Disclosure");
  assertEqual(inNav(ROLES.ADVISER), true, "Adviser sidebar shows Submit Disclosure");
  assertEqual(canAccess(ROLES.STUDENT, "submit"), true, "Student may still open /records/add");
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
const labels = (role: RoleName, access?: { my_reviews: boolean }) =>
  navFor(role, access).map((item) => `${item.section}: ${item.label}`);

test("every role shares one short main list, in the spec's order", () => {
  expect(labels(ROLES.STUDENT)).toEqual([
    "Main: Discover", "Main: Ask IRIS", "Main: My Library", "Main: Calls & Conferences",
  ]);
  for (const role of [ROLES.ITSO, ROLES.IERC, ROLES.KTTO]) {
    expect(labels(role, REVIEW_WORK)).toEqual([
      "Main: Discover", "Main: Ask IRIS", "Main: My Library", "Main: My Reviews", "Main: Calls & Conferences",
    ]);
  }
});

test("an Adviser keeps Submit Disclosure until Discover is their home (IR-534)", () => {
  expect(labels(ROLES.ADVISER, REVIEW_WORK)).toEqual([
    "Main: Discover", "Main: Ask IRIS", "Main: My Library", "Main: Submit Disclosure",
    "Main: My Reviews", "Main: Calls & Conferences",
  ]);
});

test("RDCO's coordination screens, Import Records included, are one Administration group", () => {
  expect(labels(ROLES.RDCO, REVIEW_WORK)).toEqual([
    "Main: Discover", "Main: Ask IRIS", "Main: My Library", "Main: My Reviews", "Main: Calls & Conferences",
    "Administration: Import Records", "Administration: Users", "Administration: Role Requests", "Administration: Download Requests",
    "Administration: Delete Requests", "Administration: Audit Log",
  ]);
});

test("Settings & Profile is in the account menu, not the nav, and its page stays open", () => {
  for (const role of EVERY_ROLE) {
    assertEqual(navFor(role, REVIEW_WORK).some((item) => item.key === "settings"), false, `${role} nav lists Settings`);
    assertEqual(canAccess(role, "settings"), true, `${role} may open /settings`);
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
  // Audit is the headline case: AUDIT_LOG_ROLES has said [RDCO] all along and
  // was never wired to anything.
  only("audit", [ROLES.RDCO]);
  only("roleRequests", [ROLES.RDCO]);
  only("downloadRequests", [ROLES.RDCO]);
  only("deleteRequests", [ROLES.RDCO]);
  only("importRecords", [ROLES.RDCO]);
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
    for (const item of navFor(role, REVIEW_WORK)) {
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
