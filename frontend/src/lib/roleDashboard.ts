import { pathFor, type ScreenKey } from "@/lib/access";
import { ROLES, type RoleName } from "@/lib/constants";

/**
 * Where each role lands after signing in.
 *
 * **Screen keys, never paths.** This file used to hold its own path strings and
 * sent Adviser, KTTO, RDCO and IERC to `/review/pending` — a route IR-143
 * deleted when it merged the review queues into `/review`. Nothing failed until
 * a user signed in and got a 404, because a string here has no relationship to
 * the router that TypeScript can check.
 *
 * Naming a `ScreenKey` closes that. `access.ts` is the one map from screen to
 * path, so a renamed screen updates this automatically and a *deleted* one is a
 * compile error rather than a 404 in someone's face (IR-201).
 *
 * The keys are also access-checked already: `SCREEN_ACCESS` says which roles may
 * open each screen, so a landing choice cannot send a role somewhere its own
 * sidebar would not offer it.
 */
const ROLE_LANDING: Record<RoleName, ScreenKey> = {
  [ROLES.STUDENT]: "discover",

  // Every reviewing office lands on the queue it is expected to work.
  // ITSO is included deliberately (IR-201): it is in `REVIEWERS`, the queue is
  // already in its sidebar, and it was landing on Discover for no recorded
  // reason while the other three offices went to the queue. If that was
  // intentional, it is a one-key revert back to "discover".
  [ROLES.ADVISER]: "reviewQueue",
  [ROLES.KTTO]: "reviewQueue",
  [ROLES.RDCO]: "reviewQueue",
  [ROLES.ITSO]: "reviewQueue",
  [ROLES.IERC]: "reviewQueue",
};

/** Default landing route after login for each role. */
export function getRoleDashboardPath(roleName: RoleName | null | undefined): string {
  const key = roleName ? ROLE_LANDING[roleName] : undefined;
  // Discover is the floor: open to every authenticated role, so an unknown or
  // missing role still reaches a real page instead of failing to navigate.
  return pathFor(key ?? "discover");
}
