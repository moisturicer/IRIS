/**
 * The role-name guard (IR-411; spec §4.8): no screen under Paper View, My
 * Library, My Reviews or Publish decides by role or reads `can_act`. Those
 * decisions belong to the capabilities adapter, `features/records/capabilities.ts`.
 *
 * It reads each guarded file as text, like the palette guard, and fails
 * naming the file and what it found.
 */
import { describe, expect, it } from "vitest";

import { roleDecisions } from "./roleGuard";

/** The screens the rule covers (spec §4.8). */
const GUARDED_DIRECTORIES = [
  "src/features/records/paper-view/", // Paper View
  "src/features/document-requests/",  // Paper View's request panels
  "src/features/library/",            // My Library
  "src/features/review/",             // the review queue, which becomes My Reviews (IR-268)
  "src/features/publish/",            // Publish
];

const ADAPTER = "src/features/records/capabilities.ts";

/**
 * Files that still decide by role. **This list must only shrink**: each entry
 * names the ticket that deletes or converts it. Never add a file to it.
 */
const NOT_YET_CONVERTED: readonly string[] = [
];

const SOURCES: Record<string, string> = Object.fromEntries(
  Object.entries(
    import.meta.glob<string>("/src/**/*.{ts,tsx}", { query: "?raw", import: "default", eager: true }),
  ).map(([path, text]) => [path.replace(/^\//, ""), text]),
);

const guarded = (path: string) =>
  GUARDED_DIRECTORIES.some((dir) => path.startsWith(dir)) && !/\.test\.tsx?$/.test(path);

describe("what counts as deciding by role", () => {
  it("catches a role comparison, a role list, a role hook and can_act", () => {
    expect(
      roleDecisions(`
        const a = user?.role_name === ROLES.RDCO;
        const b = STAFF_ROLES.includes(role);
        const c = useIsReviewer();
        const d = "Adviser" === user.role_name;
        const e = record.can_act.length > 0;
      `),
    ).toEqual([
      "a role_name comparison: role_name ===",
      "a ROLES constant: ROLES.RDCO",
      "a role list: STAFF_ROLES",
      "a role hook: useIsReviewer",
      "a role-name literal comparison: \"Adviser\" ===",
      "a role_name comparison: === user.role_name",
      "can_act: can_act",
    ]);
  });

  it("catches a role-name list, a switch on the role, and Django's staff flags", () => {
    expect(
      roleDecisions(`
        const offices = ["RDCO", "ITSO"].includes(user.role_name);
        switch (user?.role_name) {}
        const staff = user.is_staff || user.is_superuser;
      `),
    ).toEqual([
      'a role-name list: ["RDCO"',
      "a switch on role_name: switch (user?.role_name",
      "a Django staff flag: is_staff",
      "a Django staff flag: is_superuser",
    ]);
  });

  it("lets the access map's screen gate and plain prose through", () => {
    expect(
      roleDecisions(`
        // The adviser reads can_act; ROLES.RDCO once decided this.
        /* STAFF_ROLES is the adapter's business. */
        const isAuthor = role != null && rolesFor("submit").includes(role);
        const label = "Adviser";
        const role = user?.role_name ?? null;
      `),
    ).toEqual([]);
  });
});

describe("the role-name guard", () => {
  it("reads the guarded screens, not an empty tree", () => {
    // A broken glob would make the guard below pass by reading nothing.
    expect(SOURCES["src/features/records/paper-view/PaperViewPage.tsx"]).toContain("PaperViewPage");
    expect(SOURCES[ADAPTER]).toContain("capabilitiesFor");
    expect(Object.keys(SOURCES).filter(guarded).length).toBeGreaterThan(20);
  });

  it("finds the adapter itself deciding by role, which is where that belongs", () => {
    expect(roleDecisions(SOURCES[ADAPTER])).not.toEqual([]);
  });

  it("finds no role decision in a guarded screen outside the adapter", () => {
    const allowed = new Set(NOT_YET_CONVERTED);
    const offenders = Object.fromEntries(
      Object.entries(SOURCES)
        .filter(([path]) => guarded(path) && !allowed.has(path))
        .map(([path, text]) => [path, roleDecisions(text)])
        .filter(([, found]) => found.length > 0),
    );

    expect(offenders).toEqual({});
  });

  it("lists no file that has stopped deciding by role, so the list only shrinks", () => {
    const stale = NOT_YET_CONVERTED.filter((path) => !SOURCES[path] || roleDecisions(SOURCES[path]).length === 0);

    expect(stale).toEqual([]);
  });
});
