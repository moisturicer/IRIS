// IR-904 smoke: sign-in and the session gate, with the network mocked.
import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "./support/mock-api";
import { mockShell, signedIn, student, token } from "./support/fixtures";

test("a signed-out visitor to a protected page is sent to the sign-in screen", async ({ page }) => {
  await page.goto("/records/mine");
  await expect(page).toHaveURL(/\/login/);
  await expect(page.getByLabel("Email Address")).toBeVisible();
});

test("the sign-in screen has no serious or critical accessibility findings", async ({ page }) => {
  await page.goto("/login");
  await expect(page.getByLabel("Email Address")).toBeVisible();
  const { violations } = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
    .analyze();
  expect(violations.filter((v) => v.impact === "serious" || v.impact === "critical")).toEqual([]);
});

test("rejected credentials keep the visitor on sign-in with an explanation", async ({ page, api }) => {
  api.on("POST", "/auth/login/", { detail: "Invalid credentials." }, 401);
  await page.goto("/login");
  await page.getByLabel("Email Address").fill("student@cit.edu");
  await page.getByLabel("Password", { exact: true }).fill("wrong-password");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("alert")).toBeVisible();
  await expect(page).toHaveURL(/\/login/);
});

test("valid credentials land on Discover", async ({ page, api }) => {
  mockShell(api);
  api.on("POST", "/auth/login/", { user: student(), access: token(), refresh: "refresh-1" });
  await page.goto("/login");
  await page.getByLabel("Email Address").fill("student@cit.edu");
  await page.getByLabel("Password", { exact: true }).fill("any-password");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/$/);
  await expect(page.getByRole("heading", { name: "Discover", level: 1 })).toBeVisible();
});

test("a reload restores the session from the stored refresh token", async ({ page, api }) => {
  await signedIn(page, api);
  mockShell(api);
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Discover", level: 1 })).toBeVisible();
  expect(api.seen).toContain("POST /auth/token/refresh/");
});
