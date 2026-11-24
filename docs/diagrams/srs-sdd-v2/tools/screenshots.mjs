// Screenshots for SRS v2 / SDD v2 (IR-1275), from a LOCAL production build.
//
// Every caption that uses these images must say "local build": they show the
// app built from this repository (`npm run preview:local`) against the local
// development stack with `manage.py seed_demo` data, never the live site.
//
// The demo password is read from IRIS_DEMO_PASSWORD and is never written to a
// file, a log line or an image. Sign-in screens are captured empty or with a
// deliberately wrong password, so no real password is typed into a screenshot.
//
//   cd e2e   (for its Playwright install)
//   IRIS_DEMO_PASSWORD=... node ../docs/diagrams/srs-sdd-v2/tools/screenshots.mjs [id-prefix ...]
//
// Writes docs/diagrams/srs-sdd-v2/screens/S-*.png.
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { createRequire } from 'node:module';

// Resolved from the folder it is run in (e2e/), which holds the Playwright install.
const { chromium } = createRequire(path.join(process.cwd(), 'package.json'))('@playwright/test');

const HERE = path.dirname(fileURLToPath(import.meta.url));
const OUT = path.join(HERE, '..', 'screens');
const BASE = process.env.IRIS_PREVIEW_URL || 'http://localhost:4173';
const PASSWORD = process.env.IRIS_DEMO_PASSWORD;
const VIEWPORT = { width: 1440, height: 900 };

// [id, role or null, path, optional action before the shot]
const SHOTS = [
  ['S-1.1-sign-up', null, '/signup'],
  ['S-1.2a-sign-in', null, '/login'],
  ['S-1.2b-session-ended', null, '/login?reason=session_expired'],
  ['S-1.2c-sign-in-error', null, '/login', async (p) => {
    await p.getByLabel(/email/i).first().fill('student@iris.test');
    await p.getByLabel(/password/i).first().fill('not-the-password');
    await p.getByRole('button', { name: 'Sign In' }).click();
    await p.waitForTimeout(1500);
  }],
  ['S-1.4-forgot-password', null, '/password/forgot'],
  ['S-2.8-discover', 'student', '/'],
  ['S-2.1-publish', 'student', '/', async (p) => {
    await p.getByRole('button', { name: 'Publish' }).first().click();
    await p.waitForTimeout(1500);
  }],
  ['S-2.1b-publish-leave', 'student', '/', async (p) => {
    await p.getByRole('button', { name: 'Publish' }).first().click();
    await p.waitForTimeout(1500);
    await p.getByRole('radio', { name: /Thesis \/ Research/ }).first().check();
    await p.waitForTimeout(500);
    await p.getByRole('button', { name: 'Close' }).filter({ visible: true }).first().click();
    await p.waitForTimeout(1200);
  }],
  ['S-2.8b-discover-people', 'student', '/', async (p) => {
    await p.getByRole('button', { name: 'People', exact: true }).filter({ visible: true }).first().click();
    await p.waitForTimeout(2000);
  }],
  ['S-6.1-my-library', 'student', '/records/mine'],
  ['S-6.1b-my-library-empty', 'adviser', '/records/mine'],
  ['S-2.4-paper-view', 'student', '/records/1'],
  ['S-2.5a-download-request', 'student', '/records/2'],
  ['S-5.4-ask-iris', 'student', '/ai'],
  ['S-6.4-calls', 'student', '/opportunities'],
  ['S-4.1-notifications', 'student', '/notifications'],
  ['S-1.7-settings-privacy', 'student', '/settings?tab=privacy'],
  ['S-7.3-settings-help', 'student', '/settings?tab=help'],
  ['S-2.2b-guidelines', 'student', '/guidelines'],
  // seed_demo record ids on a freshly seeded database (local build at the pinned commit).
  ['S-3.4-owner-revision', 'student', '/records/13?section=review', async (p) => {
    await p.getByRole('tab', { name: 'Documents' }).filter({ visible: true }).first().click();
    await p.waitForTimeout(1500);
  }],
  ['S-3.1a-my-reviews', 'adviser', '/review'],
  ['S-3.1b-adviser-review', 'adviser', '/records/15?section=review'],
  ['S-3.1c-request-changes', 'adviser', '/records/15?section=review', async (p) => {
    // Opening the review first is what a reviewer does; it changes only this throwaway database.
    const open = p.getByRole('button', { name: 'Open review' }).filter({ visible: true });
    if (await open.count()) { await open.first().click(); await p.waitForTimeout(2000); }
    await p.getByRole('button', { name: /^Finish review/ }).filter({ visible: true }).first().click();
    await p.waitForTimeout(1000);
    await p.getByRole('radio', { name: /Request changes/ }).first().check();
    await p.waitForTimeout(1000);
  }],
  ['S-3.5-document-request', 'student', '/records/16?section=review', async (p) => {
    await p.getByRole('tab', { name: 'Documents' }).filter({ visible: true }).first().click();
    await p.waitForTimeout(1500);
    // A held upload (ADR-022 Amendment 8): a placeholder PDF named by IRIS_SCREENSHOT_UPLOAD,
    // uploaded and not sent, so the shot shows "Added, not sent yet" and Submit added documents.
    if (process.env.IRIS_SCREENSHOT_UPLOAD) {
      const chooser = p.waitForEvent('filechooser', { timeout: 10000 });
      await p.getByRole('button', { name: /^Upload/ }).filter({ visible: true }).first().click();
      await (await chooser).setFiles(process.env.IRIS_SCREENSHOT_UPLOAD);
      await p.waitForTimeout(4000);
    }
  }],
  ['S-3.2a-rdco-decide', 'rdco', '/records/17?section=review'],
  ['S-3.2b-rdco-offices-reviewing', 'rdco', '/records/19?section=review'],
  ['S-3.4b-preserved-clearances', 'rdco', '/records/14?section=review', async (p) => {
    await p.getByRole('tab', { name: 'Details' }).filter({ visible: true }).first().click();
    await p.waitForTimeout(1500);
  }],
  ['S-1.5-role-requests', 'rdco', '/rdco/role-requests'],
  ['S-1.6-users', 'rdco', '/rdco/users'],
  ['S-2.5b-download-requests', 'rdco', '/rdco/download-requests'],
  ['S-2.6-delete-requests', 'rdco', '/rdco/delete-requests'],
  ['S-2.2a-setup', 'rdco', '/rdco/setup'],
  ['S-2.2c-add-requirement', 'rdco', '/rdco/setup', async (p) => {
    await p.getByRole('button', { name: 'Add a requirement' }).first().click();
    await p.waitForTimeout(1200);
  }],
  ['S-3.7-analytics', 'rdco', '/rdco/analytics'],
  ['S-6.4b-call-requests', 'rdco', '/rdco/call-requests'],
  ['S-3.3-office-console', 'ierc.coordinator', '/review/office'],
  ['S-2.7-import', 'rdco', '/records/import'],
  ['S-7.1-audit-log', 'admin', '/admin/audit'],
  ['S-7.2a-retention', 'admin', '/admin/retention'],
  ['S-7.2b-deletion-requests', 'admin', '/admin/account-deletion-requests'],
];

async function signIn(context, role) {
  const page = await context.newPage();
  await page.goto(`${BASE}/login`);
  await page.getByLabel(/email/i).first().fill(`${role}@iris.test`);
  await page.getByLabel(/password/i).first().fill(PASSWORD);
  await page.getByRole('button', { name: 'Sign In' }).click();
  await page.waitForURL((u) => !u.pathname.startsWith('/login'), { timeout: 20000 }).catch(async () => {
    await page.screenshot({ path: path.join(OUT, `debug-signin-${role}.png`) });
    throw new Error(`sign-in as ${role} did not leave /login`);
  });
  await page.close();
}

async function main() {
  const only = process.argv.slice(2);
  if (!PASSWORD) throw new Error('Set IRIS_DEMO_PASSWORD (the seed_demo password) in the environment.');
  fs.mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch();
  const contexts = new Map();
  for (const [id, role, url, act] of SHOTS) {
    if (only.length && !only.some((o) => id.startsWith(o))) continue;
    const key = role || 'guest';
    if (!contexts.has(key)) {
      const ctx = await browser.newContext({ viewport: VIEWPORT, deviceScaleFactor: 1.5 });
      if (role) await signIn(ctx, role);
      contexts.set(key, ctx);
    }
    const page = await contexts.get(key).newPage();
    try {
      // Not 'networkidle': every signed-in page holds its live-update stream open (ADR-073).
      await page.goto(`${BASE}${url}`, { waitUntil: 'load', timeout: 30000 });
      await page.waitForTimeout(3500);
      if (act) await act(page);
      await page.screenshot({ path: path.join(OUT, `${id}.png`) });
      console.log(`ok   ${id}  ${url}`);
    } catch (e) {
      console.log(`FAIL ${id}  ${url}  ${String(e.message).split('\n')[0]}`);
    } finally {
      await page.close();
    }
  }
  await browser.close();
}

main().catch((e) => { console.error(e); process.exit(1); });
