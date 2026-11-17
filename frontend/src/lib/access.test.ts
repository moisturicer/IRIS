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
    "RDCO: Call Requests", "RDCO: Delete Requests", "RDCO: Reported Comments", "RDCO: Notices",
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

test("the System Admin's nav is Discover, Users, Audit Log, Account Deletions, Reported Comments, Retention and Notices (IR-783, IR-788, IR-693, IR-795, IR-800)", () => {
  expect(labels(ROLES.SYSTEM_ADMIN)).toEqual([
    "Main: Discover",
    "Administration: Users", "Administration: Audit Log", "Administration: Account Deletions",
    "Administration: Reported Comments", "Administration: Retention", "Administration: Notices",
  ]);
});

// IR-693 (decision 2026-11-15): one Reported comments page, in RDCO's and the
// System Admin's navigation and nobody else's.
test("the Reported comments page is RDCO's and the System Admin's alone, at /moderation/comments", () => {
  for (const role of Object.values(ROLES)) {
    const page = navFor(role).filter((item) => item.label === "Reported Comments");
    const allowed = role === ROLES.RDCO || role === ROLES.SYSTEM_ADMIN;
    expect(page.map((item) => item.to), role).toEqual(allowed ? ["/moderation/comments"] : []);
  }
});

// IR-800: one Notices page at one address, in RDCO's and the System Admin's
// navigation and nobody else's. RDCO publishes there; the System Admin reads.
test("the Notices page is RDCO's and the System Admin's alone, at /notices", () => {
  for (const role of Object.values(ROLES)) {
    const notices = navFor(role).filter((item) => item.label === "Notices");
    const allowed = role === ROLES.RDCO || role === ROLES.SYSTEM_ADMIN;
    expect(notices.map((item) => item.to), role).toEqual(allowed ? ["/notices"] : []);
  }
  expect(canAccess(ROLES.RDCO, "notices")).toBe(true);
  expect(canAccess(ROLES.SYSTEM_ADMIN, "notices")).toBe(false);
  expect(canAccess(ROLES.SYSTEM_ADMIN, "adminNotices")).toBe(true);
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
    { label: "Call Requests", to: "/rdco/call-requests", section: "RDCO" },
    { label: "Delete Requests", to: "/rdco/delete-requests", section: "RDCO" },
    { label: "Reported Comments", to: "/moderation/comments", section: "RDCO" },
    { label: "Notices", to: "/notices", section: "RDCO" },
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
