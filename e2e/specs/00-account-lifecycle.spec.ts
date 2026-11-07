// AC1 · Account lifecycle, through the screens: register, verify by the
// emailed link, await approval, RDCO approves the requested role, sign in,
// lockout after repeated failures with the server's own notice, recovery by
// emailed link, and (in the idle pass only) inactivity expiry followed by
// explicit reauthentication.
import { expect, test } from "@playwright/test";
import { as, login } from "../support/api";
import { A11yLedger } from "../support/a11y";
import { linkPath, waitForMail } from "../support/mailpit";
import { NEW_PASSWORD, approveRole, freshEmail, letters } from "../support/people";
import { manage } from "../support/stack";

test.describe.configure({ mode: "serial" });

const a11y = new A11yLedger();

const email = freshEmail("lifecycle");
// Letters only: registration refuses a name with digits, so a random base-36
// suffix failed whenever it drew one.
const last = `Lifecycle${letters(5)}`;
const RECOVERED = "Recovered-Pass-2026!";
/** A session opened before the reset; the reset must end it. */
let earlierRefresh = "";

test("register through the three-step form", async ({ page }, testInfo) => {
  await page.goto("/signup");
  await a11y.scan(page, testInfo, "signup");
  await a11y.reflow360(page, "signup");

  await page.getByRole("radio", { name: "Student" }).check();
  await page.getByLabel("First Name").fill("Journey");
  await page.getByLabel("Last Name").fill(last);
  await page.getByLabel("Institutional email").fill(email);
  await page.getByRole("button", { name: "Continue" }).click();

  const college = page.getByLabel("College");
  await college.selectOption({ index: 1 });
  await page.getByLabel("Program").selectOption({ index: 1 });
  await page.getByRole("button", { name: "Continue" }).click();

  await page.getByLabel("Password", { exact: true }).fill(NEW_PASSWORD);
  await page.getByLabel("Confirm Password").fill(NEW_PASSWORD);
  await page.getByRole("checkbox").check();
  await page.getByRole("button", { name: "Register" }).click();

  // The confirmation, not the form's own echo of the address: "Check your
  // details" on the last step also shows the email, so matching the address
  // alone passed while registration was refused client-side.
  await expect(page.getByRole("heading", { name: "Check your email" })).toBeVisible();
  await expect(page.getByText(email)).toBeVisible();
});

test("an unverified account is told so, and the emailed link verifies it", async ({ page }) => {
  const refused = await (await (await import("../support/api")).anonymous()).post("/api/v1/auth/login/", {
    data: { email, password: NEW_PASSWORD },
  });
  expect(refused.status()).toBe(403);
  expect(await refused.text()).toContain("not verified");

  // ADR-045 (IR-643): opening the link changes nothing; the button verifies.
  const mail = await waitForMail(email, /verify/i);
  await page.goto(linkPath(mail.text || mail.html, "/verify-email"));
  await page.getByRole("button", { name: "Verify email" }).click();
  await expect(page.getByRole("heading", { name: "Email verified" })).toBeVisible();
  await expect(page.getByText(/may still need to approve/i)).toBeVisible();
});

test("signed in before approval, the account waits; after RDCO approves, it has the Student role", async ({ page }) => {
  const before = await login(email, NEW_PASSWORD);
  earlierRefresh = before.refresh;
  expect(before.user.role ?? before.user.role_name ?? null, "no role before approval").toBeFalsy();

  await approveRole(`Journey ${last}`);
  const after = await as(email, NEW_PASSWORD);
  const me = await after.json("/users/me/");
  expect(JSON.stringify(me)).toContain("Student");
  await after.dispose();

  await page.goto("/login");
  await page.getByLabel("Email Address").fill(email);
  await page.getByLabel("Password", { exact: true }).fill(NEW_PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).not.toHaveURL(/\/login/);
});

test("three wrong passwords lock the account, and the screen says what the server said", async ({ page }, testInfo) => {
  await page.goto("/login");
  for (let i = 0; i < 3; i++) {
    await page.getByLabel("Email Address").fill(email);
    await page.getByLabel("Password", { exact: true }).fill(`wrong-${i}-password`);
    await page.getByRole("button", { name: "Sign in" }).click();
    // The first two are inline errors; the third is the lockout itself, which
    // the login screen shows as an "Account Locked" dialog with the server's
    // own countdown and disables the form behind it.
    if (i < 2) await expect(page.getByRole("alert").first()).toBeVisible();
  }
  const notice = page.getByRole("dialog", { name: "Account Locked" });
  await expect(notice).toBeVisible();
  await expect(notice).toContainText(/try again in \d+:\d{2}/i);
  await expect(page.getByLabel("Email Address")).toBeDisabled();

  const api = await (await import("../support/api")).anonymous();
  const locked = await api.post("/api/v1/auth/login/", { data: { email, password: NEW_PASSWORD } });
  expect(locked.status(), "the right password is refused while locked out").toBe(429);
  await a11y.scan(page, testInfo, "login-locked-out");
});

test("recovery by emailed link sets a new password and ends old sessions", async ({ page }) => {
  await page.goto("/password/forgot");
  await page.getByLabel("Email Address").fill(email);
  await page.getByRole("button", { name: /send|reset|continue/i }).click();

  const mail = await waitForMail(email, /reset|password/i, 120_000);
  await page.goto(linkPath(mail.text || mail.html, "/password/reset"));
  await page.getByLabel("New password", { exact: true }).fill(RECOVERED);
  await page.getByLabel("Confirm new password").fill(RECOVERED);
  await page.getByRole("button", { name: /reset|save|set/i }).click();
  // Success is stated in place, with a way back to sign in; no redirect.
  await expect(page.getByText(/password updated/i).first()).toBeVisible();
  await expect(page.getByRole("link", { name: "Return to sign in" })).toBeVisible();

  const anon = await (await import("../support/api")).anonymous();
  const stale = await anon.post("/api/v1/auth/token/refresh/", { data: { refresh: earlierRefresh } });
  expect(stale.status(), "a session from before the reset is ended").toBe(401);
  // ADR-045 §1: a reset leaves the axes lockout as it was, so even the new
  // password waits it out. Lifting it (as the cool-off would) lets it in.
  const stillLocked = await anon.post("/api/v1/auth/login/", { data: { email, password: RECOVERED } });
  expect(stillLocked.status(), "the lockout outlives the reset (ADR-045 §1)").toBe(429);
  manage("axes_reset_username", email);
  const fresh = await anon.post("/api/v1/auth/login/", { data: { email, password: RECOVERED } });
  expect(fresh.status(), "once the lockout lifts, the new password signs in").toBe(200);

  const res = await anon.post("/api/v1/auth/login/", { data: { email, password: NEW_PASSWORD } });
  expect(res.status(), "the old password no longer works").toBe(401);
});

test("inactivity ends the session and the next request needs reauthentication", async ({ page }) => {
  test.skip(!process.env.E2E_IDLE_PASS, "Runs only in the idle pass (SESSION_IDLE_TIMEOUT_MINUTES=2); see e2e/README.md");
  const minutes = Number(process.env.E2E_IDLE_MINUTES ?? 2);
  test.setTimeout((minutes + 3) * 60_000);
  const session = await login("student@cit.edu");
  await page.addInitScript((r) => sessionStorage.setItem("iris_refresh_token", r), session.refresh);
  await page.goto("/");
  await page.waitForTimeout((minutes + 1) * 60_000);
  await page.reload();
  await expect(page).toHaveURL(/\/login/);
});

test("accessibility: no serious or critical findings on this journey's key screens", async ({}, testInfo) => {
  a11y.assertClean(testInfo);
});
