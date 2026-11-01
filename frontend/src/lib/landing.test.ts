/**
 * Where a user lands after signing in (IR-534, spec §4.2): My Reviews when the
 * server says they have review work, otherwise Discover. The role does not
 * decide it any more; an Adviser with no advisees lands on Discover.
 */
import { describe, expect, it } from "vitest";

import { ROLES } from "./constants";
import { landingPathFor } from "./landing";

const work = { my_reviews: true, offices: [], is_coordinator: false };
const none = { my_reviews: false, offices: [], is_coordinator: false };

describe("the post-login landing", () => {
  it("is My Reviews for a user whose my_reviews is true", () => {
    expect(landingPathFor({ role_name: ROLES.ADVISER, review_access: work })).toBe("/review");
    expect(landingPathFor({ role_name: ROLES.ITSO, review_access: work })).toBe("/review");
  });

  it("is Discover for a user whose my_reviews is false, whatever the role", () => {
    for (const role of [ROLES.STUDENT, ROLES.ADVISER, ROLES.RDCO, ROLES.ITSO, ROLES.IERC, ROLES.KTTO]) {
      expect(landingPathFor({ role_name: role, review_access: none })).toBe("/");
    }
  });

  it("is Discover when the payload carries no review_access", () => {
    expect(landingPathFor({ role_name: ROLES.KTTO })).toBe("/");
  });

  it("never sends a role to a screen its role gate refuses", () => {
    expect(landingPathFor({ role_name: ROLES.STUDENT, review_access: work })).toBe("/");
    expect(landingPathFor({ role_name: null, review_access: work })).toBe("/");
  });
});
