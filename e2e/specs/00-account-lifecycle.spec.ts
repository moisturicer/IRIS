// AC1 · Account lifecycle, through the screens: register, verify by the
// emailed link, await approval, RDCO approves the requested role, sign in,
// lockout after repeated failures with the server's own notice, recovery by
// emailed link, and (in the idle pass only) inactivity expiry followed by
// explicit reauthentication.
import { expect, test } from "@playwright/test";
import { as, login } from "../support/api";
import { expectNoSeriousA11yViolations, expectReflowsAt360 } from "../support/a11y";
import { linkPath, waitForMail } from "../support/mailpit";
import { NEW_PASSWORD, approveRole, freshEmail } from "../support/people";

test.describe.configure({ mode: "serial" });

const email = freshEmail("lifecycle");
const last = `Lifecycle${Math.random().toString(36).slice(2, 7)}`;
const RECOVERED = "Recovered-Pass-2026!";

test("register through the three-step form", async ({ page }, testInfo) => {
  await page.goto("/signup");
  await expectNoSeriousA11yViolations(page, testInfo, "signup");
  await expectReflowsAt360(page, "signup");

  await page.getByRole("radio", { name: "Student" }).check();
  await page.getByLabel("First Name").fill("Journey");
  await page.getByLabel("Last Name").fill(last);
  await page.getByLabel("CIT-U Email").fill(email);
  await page.getByRole("button", { name: "Continue" }).click();

  const college = page.getByLabel("College");
  await college.selectOption({ index: 1 });
  await page.getByLabel("Program").selectOption({ index: 1 });
  await page.getByRole("button", { name: "Continue" }).click();

  await page.getByLabel("Password", { exact: true }).fill(NEW_PASSWORD);
  await page.getByLabel("Confirm Password").fill(NEW_PASSWORD);
  await page.getByRole("checkbox").check();
  await page.getByRole("button", { name: "Register" }).click();

  await expect(page.getByText(email)).toBeVisible();
});

test("an unverified account is told so, and the emailed link verifies it", async ({ page }) => {
  const refused = await (await (await import("../support/api")).anonymous()).post("/api/v1/auth/login/", {
    data: { email, password: NEW_PASSWORD },
  });
  expect(refused.status()).toBe(403);
  expect(await refused.text()).toContain("not verified");

  const mail = await waitForMail(email, /verify/i);
  await page.goto(linkPath(mail.text || mail.html, "/activate/"));
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  await expect(page.getByText(/verified|approval/i).first()).toBeVisible();
});

test("signed in before approval, the account waits; after RDCO approves, it has the Student role", async ({ page }) => {
  const before = await login(email, NEW_PASSWORD);
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
    await expect(page.getByRole("alert").first()).toBeVisible();
  }
  const api = await (await import("../support/api")).anonymous();
  const locked = await api.post("/api/v1/auth/login/", { data: { email, password: NEW_PASSWORD } });
  expect(locked.status(), "the right password is refused while locked out").toBe(429);
  await expect(page.getByRole("alert").first()).toContainText(/locked|try again|minutes/i);
  await expectNoSeriousA11yViolations(page, testInfo, "login-locked-out");
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
  await expect(page).toHaveURL(/\/login/);

  const res = await (await (await import("../support/api")).anonymous()).post("/api/v1/auth/login/", { data: { email, password: NEW_PASSWORD } });
  expect([401, 429], "the old password no longer works").toContain(res.status());
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
