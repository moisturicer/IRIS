// IR-823 · The Content-Security-Policy walk-through: every main screen, as each
// account type that reaches it, records any violation the browser reports.
//
// IR-663 shipped the policy report-only, to be enforced once a walk-through of
// the main screens showed no violation. This is that walk-through, made
// repeatable: it opens each screen in a real Chromium behind the real nginx and
// Django and collects every `securitypolicyviolation` event (fired for
// report-only and enforced policies alike) and every CSP console message,
// workers' included. Each test writes what it saw to
// test-results/csp-walkthrough/<test>.json, and fails on any violation.
//
// Papers are made by the spec itself: one published with a real manuscript, so
// Paper View draws the PDF with pdf.js and its worker, and one left in review at
// its Adviser, so the review workspace is walked too.
import { expect, test, type Page } from "@playwright/test";
import { mkdirSync, writeFileSync } from "node:fs";
import { as, signInBrowser, type Client } from "../support/api";
import { uniqueTitle } from "../support/accounts";
import { multiPagePdf } from "../support/pdf";
import { createDraft, publishViaRdco, submit } from "../support/workflow";

// seed_demo's logins since IR-1067. support/accounts.ts still names the old
// @cit.edu ones (IR-1148), so this spec names its own.
const PASSWORD = "IrisDemo123!";
const EMAIL = {
  student: "student@iris.test",
  adviser: "adviser@iris.test",
  rdco: "rdco@iris.test",
  itso: "itso@iris.test",
  ierc: "ierc@iris.test",
  ktto: "ktto@iris.test",
  itsoCoordinator: "itso.coordinator@iris.test",
  admin: "admin@iris.test",
} as const;

type Violation = { screen: string; directive: string; blocked: string; source: string; disposition: string };

let student: Client, adviser: Client, rdco: Client;
let paperId: number, inReviewId: number;

test.beforeAll(async () => {
  [student, adviser, rdco] = await Promise.all([EMAIL.student, EMAIL.adviser, EMAIL.rdco].map((who) => as(who)));
  const title = uniqueTitle("csp");
  // The title in the text keeps each run's manuscript unique (duplicate check, IR-1104).
  paperId = await createDraft(student, {
    title, type: "Thesis / Research", adviserId: adviser.userId,
    manuscript: multiPagePdf([`Page one of ${title}.`, "Page two."]),
  });
  await publishViaRdco(student, adviser, rdco, paperId);
  inReviewId = await createDraft(student, {
    title: `${title} in review`, type: "Thesis / Research", adviserId: adviser.userId,
    manuscript: multiPagePdf([`Page one of ${title} in review.`]),
  });
  await submit(student, inReviewId);
});

test.afterAll(async () => {
  await Promise.all([student, adviser, rdco].map((c) => c?.dispose()));
});

/**
 * Collect violations on `page` under the name of the screen being shown, and
 * write them, with the screens visited, when the test ends.
 */
async function recorder(page: Page) {
  const current = { screen: "" };
  const found: Violation[] = [];
  const visited: string[] = [];
  page.on("console", (message) => {
    const text = message.text();
    if (/content.security.policy/i.test(text)) {
      found.push({ screen: current.screen, directive: "(console)", blocked: text.slice(0, 300), source: "", disposition: message.type() });
    }
  });
  await page.exposeFunction("__irisCspViolation", (v: Omit<Violation, "screen">) => {
    found.push({ screen: current.screen, ...v });
  });
  await page.addInitScript(() => {
    document.addEventListener("securitypolicyviolation", (e) => {
      (window as unknown as { __irisCspViolation: (v: object) => void }).__irisCspViolation({
        directive: e.effectiveDirective, blocked: e.blockedURI, source: `${e.sourceFile}:${e.lineNumber}`,
        disposition: e.disposition,
      });
    });
  });
  return {
    found,
    /** Open `path` (or the page already there) as screen `name`, and wait for it to settle. */
    async show(name: string, path?: string) {
      current.screen = name;
      if (path) await page.goto(path);
      await page.waitForLoadState("networkidle");
      // A paper's PDF is drawn by pdf.js in a worker after the page settles.
      if (/\/records\/\d+/.test(page.url())) {
        await page.locator("canvas").first().waitFor({ state: "visible", timeout: 15_000 }).catch(() => {});
      }
      visited.push(name);
    },
    save() {
      mkdirSync("test-results/csp-walkthrough", { recursive: true });
      const file = test.info().title.replace(/[^a-z0-9]+/gi, "-").toLowerCase();
      writeFileSync(`test-results/csp-walkthrough/${file}.json`, JSON.stringify({ visited, violations: found }, null, 2));
    },
  };
}

async function walk(page: Page, who: string, screens: string[]) {
  const rec = await recorder(page);
  try {
    await signInBrowser(page, who, screens[0], PASSWORD);
    for (const [index, path] of screens.entries()) {
      await rec.show(`${who} ${path}`, index === 0 ? undefined : path);
    }
  } finally {
    rec.save();
  }
  expect(rec.found).toEqual([]);
}

test("a student's screens report no CSP violation", async ({ page }) => {
  await walk(page, EMAIL.student, [
    "/", "/?publish=new", `/records/${paperId}`, `/records/${paperId}?page=2`, `/records/${inReviewId}`,
    "/records/mine", "/opportunities", "/notifications", "/ai", "/ai/conversations/00000000-0000-4000-8000-000000000000",
    "/settings?tab=help", "/profile", "/settings?tab=profile", `/people/${adviser.userId}`, "/settings?tab=security", "/there-is-no-such-page",
  ]);
});

test("an Adviser's screens, with a paper in review, report no CSP violation", async ({ page }) => {
  await walk(page, EMAIL.adviser, ["/review", `/records/${inReviewId}`, `/records/${inReviewId}?page=1`, `/records/${paperId}`, "/records/mine"]);
});

test("RDCO's screens report no CSP violation", async ({ page }) => {
  await walk(page, EMAIL.rdco, [
    "/review", "/review/office", "/rdco/analytics", `/records/${inReviewId}`, "/records/import", "/rdco/users",
    "/rdco/role-requests", "/rdco/download-requests", "/rdco/delete-requests", "/notices",
  ]);
});

for (const office of ["itso", "ierc", "ktto"] as const) {
  test(`an ${office.toUpperCase()} member's screens report no CSP violation`, async ({ page }) => {
    await walk(page, EMAIL[office], ["/review", "/review/office", `/records/${inReviewId}`, `/records/${paperId}`]);
  });
}

test("an office coordinator's screens report no CSP violation", async ({ page }) => {
  // No analytics: RDCO's alone since IR-1216.
  await walk(page, EMAIL.itsoCoordinator, ["/review", "/review/office"]);
});

test("the System Admin's screens report no CSP violation", async ({ page }) => {
  await walk(page, EMAIL.admin, ["/admin/users", "/admin/account-deletion-requests", "/admin/retention", "/admin/audit", "/notices"]);
});

test("the signed-out screens report no CSP violation", async ({ page }) => {
  const rec = await recorder(page);
  try {
    for (const path of [
      "/login", "/signup", "/password/forgot", "/password/reset#token=not-a-real-token", "/verify-email/resend",
      "/verify-email#token=not-a-real-token", "/activate/abc/def",
    ]) {
      await rec.show(`anonymous ${path}`, path);
    }
  } finally {
    rec.save();
  }
  expect(rec.found).toEqual([]);
});

// Django sends its own, stricter policy on what it renders, which is the Django
// admin. nginx closes /django-admin/ except to DJANGO_ADMIN_ALLOWED_NETWORKS, so
// this runs only when the stack opens it to the test (E2E_DJANGO_ADMIN=1).
test("the Django admin reports no CSP violation", async ({ page }) => {
  test.skip(!process.env.E2E_DJANGO_ADMIN, "set E2E_DJANGO_ADMIN=1 and allow this network in DJANGO_ADMIN_ALLOWED_NETWORKS");
  const rec = await recorder(page);
  try {
    // The login page itself, as anyone sees it.
    await rec.show("django-admin /django-admin/login/", "/django-admin/login/");

    // This stack has no Caddy, so a browser form post carries an http:// Origin
    // while Django, told https by X-Forwarded-Proto, expects https:// and refuses
    // it as CSRF (Chromium won't let a test rewrite Origin). Sign in through the
    // context's request API, which shares the page's cookies and sends the
    // Origin Caddy would: nginx forwards `Host: $host`, which drops the port.
    const https = `https://${new URL(test.info().project.use.baseURL!).hostname}`;
    const api = page.context().request;
    const form = await (await api.get("/django-admin/login/")).text();
    const csrf = /name="csrfmiddlewaretoken" value="([^"]+)"/.exec(form)?.[1];
    expect(csrf, "the admin login form carries a CSRF token").toBeTruthy();
    const signedIn = await api.post("/django-admin/login/?next=/django-admin/", {
      form: { csrfmiddlewaretoken: csrf!, username: EMAIL.admin, password: PASSWORD, next: "/django-admin/" },
      headers: { Origin: https, Referer: `${https}/django-admin/login/` },
      maxRedirects: 0,
    });
    expect(signedIn.status(), "the admin sign-in redirects into the admin").toBe(302);

    for (const path of [
      "/django-admin/", "/django-admin/accounts/user/", "/django-admin/accounts/user/add/",
      `/django-admin/records/record/${paperId}/change/`, `/django-admin/records/record/${paperId}/history/`,
      `/django-admin/records/record/${paperId}/delete/`, "/django-admin/records/record/",
    ]) {
      await rec.show(`django-admin ${path}`, path);
    }
  } finally {
    rec.save();
  }
  expect(rec.found).toEqual([]);
});
