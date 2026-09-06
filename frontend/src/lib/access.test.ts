/**
 * The role -> screen matrix, asserted (IR-160).
 *
 * There is no test runner in this repo yet (IR-82 / IR-163). Run from `frontend/`:
 *
 *   ./node_modules/.bin/esbuild src/lib/access.test.ts \
 *     --bundle --platform=node --format=esm --define:import.meta.env={} \
 *     --outfile=.tmp-access.mjs && node .tmp-access.mjs
 *
 * The `--define` is required: this pulls in `lib/constants.ts`, which reads
 * `import.meta.env.VITE_API_BASE_URL`, and node has no `import.meta.env`. Same
 * workaround `auth.store.test.ts` documents.
 *
 * Same hand-rolled conventions as `tokenRefresh.test.ts` and `focusTrap.test.ts`.
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
  navFor,
  type ScreenKey,
} from "./access";
import { ROLES, type RoleName } from "./constants";

const EVERY_ROLE: RoleName[] = [
  ROLES.STUDENT, ROLES.ADVISER, ROLES.RDCO, ROLES.ITSO, ROLES.IERC, ROLES.KTTO,
];

// --- assertions ------------------------------------------------------------

function assertEqual<T>(actual: T, expected: T, what: string) {
  if (actual !== expected) {
    throw new Error(`${what}: expected ${String(expected)}, got ${String(actual)}`);
  }
}

const results: string[] = [];

function test(name: string, fn: () => void) {
  try {
    fn();
    results.push(`ok   ${name}`);
  } catch (err) {
    results.push(`FAIL ${name}\n     ${err instanceof Error ? err.message : String(err)}`);
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
  only("workspace", [ROLES.STUDENT, ROLES.ADVISER]);
  only("editRecord", [ROLES.STUDENT, ROLES.ADVISER]);
});

// --- review ----------------------------------------------------------------

test("the review queue is every reviewer, and excludes Student", () => {
  only("reviewQueue", [ROLES.ADVISER, ROLES.RDCO, ROLES.ITSO, ROLES.IERC, ROLES.KTTO]);
  only("evaluate", [ROLES.ADVISER, ROLES.RDCO, ROLES.ITSO, ROLES.IERC, ROLES.KTTO]);
});

// --- RDCO coordination -----------------------------------------------------

test("RDCO alone holds the coordination screens", () => {
  // Audit is the headline case: AUDIT_LOG_ROLES has said [RDCO] all along and
  // was never wired to anything.
  only("audit", [ROLES.RDCO]);
  only("roleRequests", [ROLES.RDCO]);
  only("downloadRequests", [ROLES.RDCO]);
  only("deleteRequests", [ROLES.RDCO]);
  only("approvedProposals", [ROLES.RDCO]);
  only("importRecords", [ROLES.RDCO]);
});

test("KTTO is not an administrator", () => {
  // ADMIN_ROLES was {KTTO, RDCO}. KTTO evaluates commercial potential; it has
  // no reason to read the audit log or approve a deletion.
  for (const key of ["audit", "roleRequests", "deleteRequests"] as ScreenKey[]) {
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
    for (const item of navFor(role)) {
      assertEqual(canAccess(role, item.key), true,
        `nav offered ${role} the ${item.key} screen it cannot open`);
    }
  }
});

test("a role is never shown an empty nav section", () => {
  for (const role of EVERY_ROLE) {
    const sections = new Map<string, number>();
    for (const item of navFor(role)) {
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

const failed = results.filter((r) => r.startsWith("FAIL")).length;
console.log(results.join("\n"));
console.log(`\n${results.length - failed} passed, ${failed} failed`);

if (failed > 0) {
  throw new Error(`${failed} access-matrix test(s) failed`);
}
