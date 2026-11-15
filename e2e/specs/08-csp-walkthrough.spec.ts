// IR-823 · The Content-Security-Policy walk-through: every main screen, as each
// role that reaches it, records any violation the browser reports.
//
// IR-663 shipped the policy report-only, to be enforced once a walk-through of
// the main screens showed no violation. This is that walk-through, made
// repeatable: it opens each screen in a real Chromium behind the real nginx and
// collects every `securitypolicyviolation` event (fired for report-only and
// enforced policies alike) and every CSP console message. It writes them to
// test-results/csp-walkthrough.json and fails if there is any.
//
// The paper is published by the spec itself with a real manuscript, so Paper
// View draws the PDF with pdf.js and its worker, the likeliest place for a
// policy to bite.
import { expect, test, type Page } from "@playwright/test";
import { mkdirSync, writeFileSync } from "node:fs";
import { as, signInBrowser, type Client } from "../support/api";
import { uniqueTitle } from "../support/accounts";
import { multiPagePdf } from "../support/pdf";
import { createDraft, publishViaRdco } from "../support/workflow";

// Not serial: one role's failure must not skip the others, so every screen is walked.

// seed_demo's logins since IR-1067.
const EMAIL = {
  student: "student@iris.test",
  adviser: "adviser@iris.test",
  rdco: "rdco@iris.test",
  admin: "admin@iris.test",
} as const;

type Violation = { screen: string; directive: string; blocked: string; source: string; disposition: string };
const found: Violation[] = [];
const visited: string[] = [];

let student: Client, adviser: Client, rdco: Client;
let paperId: number;

test.beforeAll(async () => {
  [student, adviser, rdco] = await Promise.all([EMAIL.student, EMAIL.adviser, EMAIL.rdco].map((who) => as(who)));
  const title = uniqueTitle("csp");
  paperId = await createDraft(student, {
    title, type: "Thesis / Research", adviserId: adviser.userId,
    // The title in the text keeps each run's manuscript unique (duplicate check, IR-1104).
    manuscript: multiPagePdf([`Page one of ${title}.`, "Page two."]),
  });
  await publishViaRdco(student, adviser, rdco, paperId);
});

test.afterAll(async () => {
  await Promise.all([student, adviser, rdco].map((c) => c?.dispose()));
  mkdirSync("test-results", { recursive: true });
  writeFileSync("test-results/csp-walkthrough.json", JSON.stringify({ visited, violations: found }, null, 2));
});

/** Record violations on `page` from now on, under the name of the screen being shown. */
function listen(page: Page, current: { screen: string }) {
  page.on("console", (message) => {
    const text = message.text();
    if (/content.security.policy/i.test(text)) {
      found.push({ screen: current.screen, directive: "(console)", blocked: text.slice(0, 300), source: "", disposition: message.type() });
    }
  });
  return page.exposeFunction("__irisCspViolation", (v: Omit<Violation, "screen">) => {
    found.push({ screen: current.screen, ...v });
  });
}

async function walk(page: Page, who: string, screens: string[]) {
  const current = { screen: "" };
  await listen(page, current);
  await page.addInitScript(() => {
    document.addEventListener("securitypolicyviolation", (e) => {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      (window as any).__irisCspViolation({
        directive: e.effectiveDirective, blocked: e.blockedURI, source: `${e.sourceFile}:${e.lineNumber}`,
        disposition: e.disposition,
      });
    });
  });
  current.screen = `${who} ${screens[0]}`;
  await signInBrowser(page, who, screens[0]);
  for (const [index, path] of screens.entries()) {
    current.screen = `${who} ${path}`;
    if (index > 0) await page.goto(path);
    await page.waitForLoadState("networkidle");
    // Give lazy chunks, fonts and the pdf.js worker a moment to load.
    await page.waitForTimeout(1500);
    visited.push(current.screen);
  }
}

test("a student's screens report no CSP violation", async ({ page }) => {
  await walk(page, EMAIL.student, [
    "/", `/records/${paperId}`, `/records/${paperId}?page=2`, "/records/mine", "/opportunities",
    "/notifications", "/ai", "/help", "/profile", "/profile/edit", "/settings", "/there-is-no-such-page",
  ]);
  expect(found.filter((v) => v.screen.startsWith(EMAIL.student))).toEqual([]);
});

test("an adviser's screens report no CSP violation", async ({ page }) => {
  await walk(page, EMAIL.adviser, ["/review", `/records/${paperId}`, "/records/mine"]);
  expect(found.filter((v) => v.screen.startsWith(EMAIL.adviser))).toEqual([]);
});

test("RDCO's screens report no CSP violation", async ({ page }) => {
  await walk(page, EMAIL.rdco, [
    "/review", "/review/office", "/review/analytics", "/records/import", "/rdco/users", "/rdco/role-requests",
    "/rdco/download-requests", "/rdco/delete-requests", "/notices",
  ]);
  expect(found.filter((v) => v.screen.startsWith(EMAIL.rdco))).toEqual([]);
});

test("the System Admin's screens report no CSP violation", async ({ page }) => {
  await walk(page, EMAIL.admin, ["/admin/users", "/admin/account-deletion-requests", "/admin/retention", "/admin/audit"]);
  expect(found.filter((v) => v.screen.startsWith(EMAIL.admin))).toEqual([]);
});

test("the signed-out screens report no CSP violation", async ({ page }) => {
  const current = { screen: "" };
  await listen(page, current);
  await page.addInitScript(() => {
    document.addEventListener("securitypolicyviolation", (e) => {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      (window as any).__irisCspViolation({
        directive: e.effectiveDirective, blocked: e.blockedURI, source: `${e.sourceFile}:${e.lineNumber}`,
        disposition: e.disposition,
      });
    });
  });
  for (const path of ["/login", "/signup", "/password/forgot", "/verify-email/resend"]) {
    current.screen = `anonymous ${path}`;
    await page.goto(path);
    await page.waitForLoadState("networkidle");
    await page.waitForTimeout(1500);
    visited.push(current.screen);
  }
  expect(found.filter((v) => v.screen.startsWith("anonymous"))).toEqual([]);
});

// Django sends its own, stricter policy on what it renders, which is the Django
// admin. nginx closes /django-admin/ except to DJANGO_ADMIN_ALLOWED_NETWORKS, so
// this runs only when the stack opens it to the test (E2E_DJANGO_ADMIN=1).
test("the Django admin reports no CSP violation", async ({ page }) => {
  test.skip(!process.env.E2E_DJANGO_ADMIN, "set E2E_DJANGO_ADMIN=1 and allow this network in DJANGO_ADMIN_ALLOWED_NETWORKS");
  const current = { screen: "django-admin /django-admin/login/" };
  await listen(page, current);
  await page.addInitScript(() => {
    document.addEventListener("securitypolicyviolation", (e) => {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      (window as any).__irisCspViolation({
        directive: e.effectiveDirective, blocked: e.blockedURI, source: `${e.sourceFile}:${e.lineNumber}`,
        disposition: e.disposition,
      });
    });
  });
  // The login page itself, as anyone sees it.
  await page.goto("/django-admin/login/");
  await page.waitForLoadState("networkidle");
  visited.push(current.screen);

  // This stack has no Caddy, so a browser form post carries an http:// Origin
  // while Django, told https by X-Forwarded-Proto, expects https:// and refuses
  // it as CSRF (Chromium won't let a test rewrite Origin). Sign in through the
  // context's request API, which shares the page's cookies and sends the
  // Origin and Referer Caddy would. The pages are then browsed for real.
  // nginx forwards `Host: $host`, which drops the port, so the origin Django
  // expects is the bare host over https, as it is behind Caddy on 443.
  const base = new URL(test.info().project.use.baseURL!);
  const https = `https://${base.hostname}`;
  const api = page.context().request;
  const form = await (await api.get("/django-admin/login/")).text();
  const csrf = /name="csrfmiddlewaretoken" value="([^"]+)"/.exec(form)?.[1];
  expect(csrf, "the admin login form carries a CSRF token").toBeTruthy();
  const signedIn = await api.post("/django-admin/login/?next=/django-admin/", {
    form: { csrfmiddlewaretoken: csrf!, username: EMAIL.admin, password: "IrisDemo123!", next: "/django-admin/" },
    headers: { Origin: https, Referer: `${https}/django-admin/login/` },
    maxRedirects: 0,
  });
  expect(signedIn.status(), "the admin sign-in redirects into the admin").toBe(302);
  for (const path of [
    "/django-admin/", "/django-admin/accounts/user/", "/django-admin/accounts/user/add/",
    `/django-admin/records/record/${paperId}/change/`, "/django-admin/records/record/",
  ]) {
    current.screen = `django-admin ${path}`;
    await page.goto(path);
    await page.waitForLoadState("networkidle");
    await page.waitForTimeout(1000);
    visited.push(current.screen);
  }
  expect(found.filter((v) => v.screen.startsWith("django-admin"))).toEqual([]);
});
