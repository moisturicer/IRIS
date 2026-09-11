/**
 * Signed-in users and the tokens that carry them (IR-236).
 *
 * Lives in `src/test/` for the same reason `render.tsx` does: two suites — the
 * route guard's and the login screen's — need the same KTTO reviewer, and a
 * fixture copied into both drifts silently. When a third suite needs a
 * different role it adds an argument here rather than a second copy.
 */
import { ROLES, type RoleName } from "@/lib/constants";
import type { User } from "@/types/auth";

/**
 * A JWT the guard will accept or reject on `exp` alone.
 *
 * The signature is the literal string "signature" and that is fine: nothing in
 * the browser verifies one. `decodeJwtPayload` reads the claims, the Django API
 * is the real boundary (NFR-S4), and a test that signed its tokens properly
 * would be testing a guarantee this code does not make.
 */
export function makeToken(payload: Record<string, unknown>): string {
  const encode = (value: unknown) =>
    btoa(JSON.stringify(value)).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
  return `${encode({ alg: "HS256", typ: "JWT" })}.${encode(payload)}.signature`;
}

/** Seconds-since-epoch, which is the unit `exp` is in. */
const secondsFromNow = (offset: number) => Math.floor(Date.now() / 1000) + offset;

/** A token whose `exp` is an hour away. */
export function validToken(claims: Record<string, unknown> = {}): string {
  return makeToken({ user_id: 7, role_id: 3, exp: secondsFromNow(3600), ...claims });
}

/** A token whose `exp` passed an hour ago. */
export function expiredToken(claims: Record<string, unknown> = {}): string {
  return makeToken({ user_id: 7, role_id: 3, exp: secondsFromNow(-3600), ...claims });
}

/**
 * A KTTO reviewer — an office role, so it exercises the interesting paths: it
 * may open the review queue, and it is not Django staff, so the role check
 * actually runs rather than being bypassed.
 */
export function makeUser(overrides: Partial<User> = {}): User {
  return {
    id: 7,
    email: "ktto@cit.edu",
    first_name: "Kay",
    middle_initial: "",
    last_name: "Tee",
    role: 3,
    role_name: ROLES.KTTO,
    is_staff: false,
    is_superuser: false,
    is_verified: true,
    is_locked: false,
    consent_given: true,
    date_joined: "2026-01-05T00:00:00Z",
    college_name: "",
    department_name: "",
    course_name: "",
    ...overrides,
  };
}

/** The role whose landing page the fixtures above imply. */
export const FIXTURE_ROLE: RoleName = ROLES.KTTO;
