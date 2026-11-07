// New accounts made the way a person makes one: register, verify by the
// emailed link, wait for RDCO to approve the requested role. Used by journeys
// that need a user with no history (a second student, a user to lock).
// The account-lifecycle journey drives the same steps through the screens.
import { expect } from "@playwright/test";
import { anonymous, as, ok, type Client } from "./api";
import { linkPath, waitForMail } from "./mailpit";

export const NEW_PASSWORD = "Journey-Pass-2026!";

export function freshEmail(tag: string): string {
  return `e2e.${tag}.${Date.now().toString(36)}${Math.random().toString(36).slice(2, 5)}@cit.edu`;
}

export async function firstCourseId(): Promise<number> {
  const anon = await anonymous();
  const body = await ok(await anon.get("/api/v1/courses/"), "list courses");
  await anon.dispose();
  const list = Array.isArray(body) ? body : body.results;
  expect(list.length, "migration-seeded courses exist").toBeGreaterThan(0);
  return list[0].id;
}

export async function register(email: string, first = "Journey", last = "Student") {
  const anon = await anonymous();
  const res = await anon.post("/api/v1/auth/register/", {
    data: {
      email, first_name: first, last_name: last,
      password: NEW_PASSWORD, confirm_password: NEW_PASSWORD,
      consent_given: true, role_name: "Student", course_id: await firstCourseId(),
    },
  });
  await ok(res, `register ${email}`);
  await anon.dispose();
}

/** Follow the verification link Mailpit received; returns its path. */
export async function verify(email: string): Promise<string> {
  const mail = await waitForMail(email, /verify/i);
  // The secret is in the fragment (IR-928), so it goes to the API in a body.
  const path = linkPath(mail.text || mail.html, "/activate");
  const fields = new URLSearchParams(path.split("#")[1] ?? "");
  const anon = await anonymous();
  await ok(
    await anon.post("/api/v1/auth/activate/", { data: { uid: fields.get("uid"), token: fields.get("token") } }),
    `activate ${email}`,
  );
  await anon.dispose();
  return path;
}

/**
 * RDCO approves the pending role request of the person named `fullName`.
 * The queue names people, not addresses, so journeys register with a last
 * name no one else has (see `newStudent`).
 */
export async function approveRole(fullName: string) {
  const rdco = await as("rdco");
  let pending: any;
  await expect.poll(async () => {
    const body = await rdco.json("/users/role-requests/");
    const list = Array.isArray(body) ? body : body.results;
    pending = list.find((r: any) => r.user_name === fullName);
    return Boolean(pending);
  }, { message: `RDCO sees ${fullName}'s role request` }).toBe(true);
  await ok(await rdco.patch(`/users/role-requests/${pending.id}/`, { action: "approve" }), `approve ${fullName}`);
  await rdco.dispose();
}

/** `n` random lowercase letters, for a unique name: registration refuses a name with digits in it. */
export function letters(n = 8): string {
  return Array.from({ length: n }, () => String.fromCharCode(97 + Math.floor(Math.random() * 26))).join("");
}

/** Register, verify and approve: a signed-in Client for a brand-new student. */
export async function newStudent(tag: string): Promise<Client> {
  const email = freshEmail(tag);
  // Unique, so approveRole finds this request by name, and letters only, as
  // registration requires of a name.
  const last = `Journey${letters()}`;
  await register(email, "Journey", last);
  await verify(email);
  await approveRole(`Journey ${last}`);
  return as(email, NEW_PASSWORD);
}
