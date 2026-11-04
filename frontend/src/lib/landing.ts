import { canAccess, hasReviewWork, pathFor } from "@/lib/access";
import type { RoleName } from "@/lib/constants";
import type { ReviewAccess } from "@/types/auth";

/**
 * Where a user lands after signing in (IR-534, spec §4.2).
 *
 * **System Admin: Users. Reviewers with work: My Reviews. Otherwise: Discover.**
 * This replaced a per-role table (IR-201) that sent every Adviser and office
 * user to the queue, including an Adviser with no advisees, who then met an
 * empty page or `ReviewAccessRoute`'s bounce back to Discover. The flag is
 * `review_access.my_reviews` (IR-415), read through `hasReviewWork`, the same
 * reading the sidebar and `/review`'s guard use, so the landing, the link and
 * the page cannot disagree.
 *
 * **Screen keys, never paths.** `pathFor` is the one map from screen to path,
 * so a renamed screen updates this automatically and a deleted one is a
 * compile error rather than a 404 after sign-in (IR-201).
 *
 * The role stays the outer gate: a user is never sent to a screen whose route
 * refuses their role, whatever the flag says.
 */
export function landingPathFor(user: {
  role_name: RoleName | null | undefined;
  review_access?: Pick<ReviewAccess, "my_reviews"> | null;
}): string {
  if (canAccess(user.role_name, "adminUsers")) return pathFor("adminUsers");
  if (canAccess(user.role_name, "reviewQueue") && hasReviewWork(user.review_access)) {
    return pathFor("reviewQueue");
  }
  // Discover is the floor: open to every authenticated role.
  return pathFor("discover");
}
