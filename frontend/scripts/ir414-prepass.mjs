// IR-414 automated pre-pass: every redesigned screen at the four viewports of
// docs/frontend_redesign_spec.md Appendix F · F12 (360, 768, 1280, 1745 px)
// plus 200 % zoom, in headless Chromium.
//
// It is a PRE-PASS, not F12's evidence. It cannot judge what a person must
// (legibility, whether a focus order makes sense, a real device, NFR-U2's timed
// participants), so its output says "automated" on every line and feeds the
// human pass rather than replacing it.
//
// Per screen x viewport it records:
//   * horizontal overflow (WCAG 1.4.10 Reflow): scrollWidth > clientWidth;
//   * axe-core violations (WCAG 2.x A/AA tags), with impact — colour contrast
//     included, because this is a real browser, unlike jsdom;
// and at 360 px and 1280 px a keyboard walk: Tab up to MAX_TABS stops, noting
// each stop with no visible focus indicator, each stop covered by another
// element (a sticky bar, a header), and whether focus cycles in a short loop.
// Separately, at 360, 1280 and 200 %, F6's deferred Review-section checks
// (IR-414 comment of 2026-10-07): toolbar arrow keys, the sticky bar over the
// timeline's last entry, and the Request documents dialog's focus in, Tab
// trap, Escape and focus return. It opens that dialog and never sends it.
//
// 200 % zoom is emulated as a 1280x720 window at 200 %: a 640x360 CSS-pixel
// viewport at device scale factor 2, which is what the browser lays out.
//
// Run (from frontend/, with the stack up and the seeded demo accounts):
//   npm i --no-save playwright@1.64.1 && npx playwright install chromium
//   npm run dev -- --port 5174 &
//   node scripts/ir414-prepass.mjs --base http://localhost:5174 --out <dir> \
//     [--api http://127.0.0.1:<port> --backend-ref <commit>]
// The backend must run the same commit as this frontend: see --api below.
// It signs in twice per role (1x and 2x), roughly 20 of the backend's 100
// anonymous requests a day per IP, and moves between screens without reloading.
// It writes <dir>/prepass.json, <dir>/prepass.md and a screenshot per cell.
// prepass.json is saved after every cell; rerunning into the same <dir> resumes,
// skipping cells that finished cleanly. `--only <text>` runs a slice by name.
// It never submits a form, sends an Ask IRIS question, or records a decision:
// it reads screens only.

import { chromium } from "playwright";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { execSync } from "node:child_process";
import { createRequire } from "node:module";
import path from "node:path";
import { fileURLToPath } from "node:url";

const args = Object.fromEntries(
  process.argv.slice(2).reduce((acc, a, i, all) => (a.startsWith("--") ? [...acc, [a.slice(2), all[i + 1]]] : acc), []),
);
const BASE = args.base ?? "http://localhost:5174";
// --api <origin> sends the browser's /api calls to that backend instead of the
// dev server's proxy. The frontend and the backend must be the same commit: a
// pass against an older backend reports the API's gaps as the interface's
// failures (found 2026-11-01 — a backend 78 commits behind crashed Paper View
// for want of IR-685's `routing.targets`). --backend-ref names what it runs.
const API = args.api ? args.api.replace(/\/$/, "") : null;
const FRONTEND_REF = (() => {
  try { return execSync("git rev-parse --short HEAD", { cwd: path.dirname(fileURLToPath(import.meta.url)) }).toString().trim(); } catch { return "unknown"; }
})();
const OUT = path.resolve(args.out ?? "ir414-prepass-out");
const PASSWORD = args.password ?? "IrisDemo123!";
const MAX_TABS = 60;
mkdirSync(path.join(OUT, "shots"), { recursive: true });

const require = createRequire(import.meta.url);
const AXE_SOURCE = readFileSync(require.resolve("axe-core/axe.min.js"), "utf8");

const VIEWPORTS = [
  { name: "360", width: 360, height: 740, scale: 1, keyboard: true },
  { name: "768", width: 768, height: 1024, scale: 1 },
  { name: "1280", width: 1280, height: 800, scale: 1, keyboard: true },
  { name: "1745", width: 1745, height: 982, scale: 1 },
  { name: "1280@200%", width: 640, height: 360, scale: 2 },
];

// Record ids are the seeded demo catalogue's (seed_demo), checked against the dev
// database 2026-11-01: 20 published, 17 ITSO-cleared in RDCO's pool, 18 at its
// Adviser, 14 with an IERC clearance pending. --records overrides.
const R = { published: 20, inReview: 17, submitted: 18, officePending: 14, ...(args.records ? JSON.parse(args.records) : {}) };

const SCREENS = [
  { role: null, name: "Sign in", url: "/login" },
  { role: null, name: "Create account", url: "/signup" },
  { role: null, name: "Forgot password", url: "/password/forgot" },

  { role: "student", name: "Discover", url: "/" },
  { role: "student", name: "Publish dialog", url: "/?publish=new" },
  { role: "student", name: "My Library", url: "/records/mine" },
  { role: "student", name: "Paper View · Overview (published)", url: `/records/${R.published}` },
  { role: "student", name: "Paper View · Paper (published)", url: `/records/${R.published}?section=paper` },
  { role: "student", name: "Paper View · Review (owner, in review)", url: `/records/${R.inReview}?section=review` },
  { role: "student", name: "Ask IRIS", url: "/ai" },
  { role: "student", name: "Settings & Profile", url: "/settings" },
  { role: "student", name: "Notifications", url: "/notifications" },
  { role: "student", name: "Help", url: "/help" },
  { role: "student", name: "Calls & Conferences", url: "/opportunities" },

  { role: "adviser", name: "My Reviews (adviser)", url: "/review" },
  { role: "adviser", name: "Paper View · Review (adviser, submitted)", url: `/records/${R.submitted}?section=review` },

  { role: "itso", name: "My Reviews (office)", url: "/review" },
  { role: "itso", name: "Office console", url: "/review/office" },
  { role: "itso", name: "Paper View · Review (office, in review)", url: `/records/${R.inReview}?section=review` },

  // A coordinator assigns from the pool a member claims from (IR-478), so the
  // queue screens differ; DEV-19 names coordinator screens explicitly.
  { role: "itso.coordinator", name: "My Reviews (office coordinator)", url: "/review" },
  { role: "itso.coordinator", name: "Office console (coordinator)", url: "/review/office" },

  { role: "rdco", name: "Users", url: "/admin/users" },
  { role: "rdco", name: "Role requests", url: "/admin/role-requests" },
  { role: "rdco", name: "Download requests", url: "/admin/download-requests" },
  { role: "rdco", name: "Delete requests", url: "/admin/delete-requests" },
  { role: "rdco", name: "Audit log", url: "/admin/audit" },
  { role: "rdco", name: "Workflow analytics", url: "/review/analytics" },
  { role: "rdco", name: "Import records", url: "/records/import" },
];

// F6's deferred keyboard checks (IR-414 comment, 2026-10-07), scripted: the
// Review section's action bar and the dialog it opens. Run at the two keyboard
// viewports and at 200 % zoom, as the reviewer the API names on each record.
const INTERACTIONS = [
  { role: "adviser", name: "Review interactions (adviser, submitted)", url: `/records/${R.submitted}?section=review` },
  { role: "ierc", name: "Review interactions (office, clearance pending)", url: `/records/${R.officePending}?section=review` },
];
const INTERACTION_VIEWPORTS = ["360", "1280", "1280@200%"];

// --only <substring> narrows the run to matching screen names, for iterating.
const only = (list) => (args.only ? list.filter((s) => s.name.toLowerCase().includes(args.only.toLowerCase())) : list);

const firstLine = (e) => String(e?.message ?? e).split(/\r?\n/)[0];
const slug = (s) => s.replace("%", "pct").replace(/[^a-z0-9]+/gi, "_").replace(/^_|_$/g, "");

async function settle(page) {
  await page.waitForLoadState("networkidle", { timeout: 8000 }).catch(() => {});
  await page.waitForTimeout(400);
}

// Signed in, move between screens as the app does — push the URL and let the
// router answer popstate — never by reloading. A reload re-hydrates the
// session from the refresh token, and /auth/token/refresh/ counts against the
// same anonymous throttle as sign-in: reloading per cell spent the whole day's
// budget for localhost in one run. A cell then also starts from a clean page:
// the previous screen's dialogs and focus are gone with the route.
async function nav(page, url, signedIn) {
  if (!signedIn) return page.goto(BASE + url);
  await page.evaluate((to) => {
    window.history.pushState({}, "", to);
    window.dispatchEvent(new PopStateEvent("popstate", { state: window.history.state }));
  }, url);
  await page.waitForURL((u) => u.pathname + u.search === url, { timeout: 10000 });
  await page.evaluate(() => window.scrollTo(0, 0));
}

// The dev backend restarts whenever a backend file changes (StatReloader), so
// a sign-in that meets a restart is retried rather than failing a whole role.
// Only "no answer" or a 5xx is retried; any other status stops at once.
async function signIn(page, role, attempts = 3) {
  for (let attempt = 1; ; attempt++) {
    let status = null;
    const onResponse = (r) => { if (r.url().includes("/auth/login/")) status = r.status(); };
    page.on("response", onResponse);
    try {
      await page.goto(`${BASE}/login`);
      await page.getByLabel("Email Address").fill(`${role}@cit.edu`);
      await page.getByLabel("Password", { exact: true }).fill(PASSWORD);
      await page.getByRole("button", { name: "Sign In" }).click();
      await page.waitForURL((u) => !u.pathname.startsWith("/login"), { timeout: 15000 });
      return;
    } catch (e) {
      if (status === 429) throw new Error(`login throttled or locked (429) for ${role}@cit.edu`);
      // A refusal is an answer: retrying it counts as another failed attempt
      // toward the account lockout (IR-555). Found when a coordinator account
      // missing from an older seed was retried until it locked.
      if (status !== null && status < 500) throw new Error(`login refused (${status}) for ${role}@cit.edu — is the account seeded (manage.py seed_demo)?`);
      if (attempt >= attempts) throw new Error(`${firstLine(e)} (login status ${status ?? "none"}, ${attempt} attempts)`);
      await page.waitForTimeout(20000);
    } finally {
      page.off("response", onResponse);
    }
  }
}

async function overflow(page) {
  return page.evaluate(() => {
    const doc = document.documentElement;
    const over = doc.scrollWidth - doc.clientWidth;
    if (over <= 1) return null;
    // Name the widest offenders so a person knows where to look.
    const offenders = [...document.querySelectorAll("body *")]
      .filter((el) => el.getBoundingClientRect().right > doc.clientWidth + 1)
      .filter((el) => !el.parentElement || el.parentElement.getBoundingClientRect().right <= doc.clientWidth + 1)
      .slice(0, 5)
      .map((el) => `${el.tagName.toLowerCase()}${el.id ? "#" + el.id : ""}${el.className && typeof el.className === "string" ? "." + el.className.split(/\s+/).slice(0, 3).join(".") : ""}`);
    return { px: over, offenders };
  });
}

async function axe(page) {
  await page.addScriptTag({ content: AXE_SOURCE });
  return page.evaluate(async () => {
    const res = await window.axe.run(document, {
      runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"] },
    });
    return res.violations.map((v) => ({
      id: v.id, impact: v.impact, help: v.help, count: v.nodes.length,
      targets: v.nodes.slice(0, 3).map((n) => n.target.join(" ")),
    }));
  });
}

async function keyboardWalk(page) {
  await page.evaluate(() => { document.activeElement?.blur?.(); window.scrollTo(0, 0); });
  await page.locator("body").focus().catch(() => {});
  const stops = [];
  for (let i = 0; i < MAX_TABS; i++) {
    await page.keyboard.press("Tab");
    const stop = await page.evaluate(() => {
      const el = document.activeElement;
      if (!el || el === document.body) return { body: true };
      const cs = getComputedStyle(el);
      const outline = cs.outlineStyle !== "none" && parseFloat(cs.outlineWidth) > 0;
      const shadow = cs.boxShadow && cs.boxShadow !== "none";
      const r = el.getBoundingClientRect();
      const inView = r.width > 0 && r.height > 0 && r.top >= 0 && r.bottom <= innerHeight && r.left >= 0 && r.right <= innerWidth;
      let coveredBy = null;
      if (r.width > 0 && r.height > 0) {
        const x = Math.min(Math.max(r.left + r.width / 2, 0), innerWidth - 1);
        const y = Math.min(Math.max(r.top + r.height / 2, 0), innerHeight - 1);
        const hit = document.elementFromPoint(x, y);
        if (hit && hit !== el && !el.contains(hit) && !hit.contains(el)) {
          coveredBy = `${hit.tagName.toLowerCase()}${hit.closest("[role=toolbar],header,nav,footer") ? " in " + hit.closest("[role=toolbar],header,nav,footer").tagName.toLowerCase() : ""}`;
        }
      }
      const name = (el.getAttribute("aria-label") || el.textContent || el.getAttribute("placeholder") || el.getAttribute("name") || "").trim().replace(/\s+/g, " ").slice(0, 50);
      const key = `${el.tagName.toLowerCase()}|${el.id}|${name}|${Math.round(r.left)},${Math.round(r.top + scrollY)}`;
      return { key, label: `${el.tagName.toLowerCase()} "${name}"`, indicator: outline || shadow, inView, coveredBy, zero: r.width === 0 || r.height === 0 };
    });
    if (stop.body) break;
    stops.push(stop);
    // A short cycle: focus came back to the first stop.
    if (stops.length > 1 && stop.key === stops[0].key) break;
  }
  const unique = new Map(stops.map((s) => [s.key, s]));
  const cycled = stops.length > 1 && stops[stops.length - 1].key === stops[0].key;
  return {
    stops: unique.size,
    cycled,
    reachedLimit: stops.length >= MAX_TABS,
    noIndicator: [...unique.values()].filter((s) => !s.indicator && !s.zero).map((s) => s.label),
    covered: [...unique.values()].filter((s) => s.coveredBy).map((s) => `${s.label} under ${s.coveredBy}`),
    invisible: [...unique.values()].filter((s) => s.zero).map((s) => s.label),
  };
}

// Each check answers one yes/no question from the F6 hand-off; `null` means it
// could not be asked here (no such control for this viewer), which the summary
// reports as "n/a" rather than as a pass.
async function reviewInteractions(page) {
  const out = {};
  const bar = page.getByRole("toolbar", { name: "Review actions" });
  // An office member sees the bar only after claiming the review from the
  // pool, and claiming writes to the database, which this pass never does.
  if (!(await bar.count())) return { skipped: "no Review actions toolbar for this viewer (a pool review must be claimed first; left to the human pass)" };
  const enabled = bar.locator("button:not(:disabled)");
  const n = await enabled.count();
  out.actions = await bar.locator("button").allInnerTexts().then((t) => t.map((x) => x.trim()));

  // Arrow keys move along the bar and wrap (APG toolbar pattern). Focus is
  // read as a position among the enabled controls, never by text: two
  // controls may share a label. Left from the first must wrap to the last.
  if (n >= 2) {
    const at = () => bar.evaluate((el) =>
      [...el.querySelectorAll("button:not(:disabled), a[href]")].indexOf(document.activeElement));
    await enabled.first().focus();
    await page.keyboard.press("ArrowRight");
    const right = await at();
    await page.keyboard.press("ArrowLeft");
    const back = await at();
    await page.keyboard.press("ArrowLeft");
    const wrapped = await at();
    out.arrowKeysMove = right === 1 && back === 0;
    out.arrowKeysWrap = wrapped === n - 1;
  } else {
    out.arrowKeysMove = null;
    out.arrowKeysWrap = null;
  }

  // Below lg the bar is sticky: when scrolled to the end, the timeline's last
  // entry must not sit underneath it.
  out.lastEntryCovered = await page.evaluate(() => {
    const last = document.querySelector('ol[aria-label="Review timeline"] > li:last-child');
    const barEl = document.querySelector('[role=toolbar][aria-label="Review actions"]');
    if (!last || !barEl) return null;
    last.scrollIntoView({ block: "end" });
    window.scrollTo(0, document.documentElement.scrollHeight);
    const a = last.getBoundingClientRect();
    const b = barEl.getBoundingClientRect();
    if (getComputedStyle(barEl.closest("[class*=sticky]") ?? barEl).position !== "sticky") return false;
    return a.bottom > b.top + 1 && a.top < b.bottom;
  });

  // The Request documents dialog: focus moves in, Tab stays in, Escape closes,
  // focus returns to the button. It is opened and closed, never submitted.
  // The dialog is found by its name and the opener by a mark set on that very
  // element, so another dialog or another "Request documents" button on the
  // page cannot answer for them.
  const opener = bar.getByRole("button", { name: "Request documents" });
  if ((await opener.count()) && (await opener.isEnabled())) {
    await opener.evaluate((el) => el.setAttribute("data-ir414-opener", ""));
    await opener.focus();
    await page.keyboard.press("Enter");
    const dialog = page.getByRole("dialog", { name: "Request documents" });
    await dialog.first().waitFor({ timeout: 4000 }).catch(() => {});
    const inDialog = () => dialog.first().evaluate((d) => d.contains(document.activeElement)).catch(() => false);
    out.dialogOpened = (await dialog.count()) > 0;
    out.focusMovesIn = out.dialogOpened ? await inDialog() : null;
    if (out.dialogOpened) {
      let escaped = false;
      for (let i = 0; i < 25; i++) {
        await page.keyboard.press(i % 5 === 4 ? "Shift+Tab" : "Tab");
        if (!(await inDialog())) { escaped = true; break; }
      }
      out.tabStaysIn = !escaped;
      await page.keyboard.press("Escape");
      await page.waitForTimeout(300);
      out.escapeCloses = (await dialog.count()) === 0;
      out.focusReturns = await page.evaluate(() => document.activeElement?.hasAttribute("data-ir414-opener") ?? false);
    }
  } else out.dialogOpened = null;
  return out;
}

// One sign-in per role per device scale factor, not per cell: the backend's
// anonymous throttle (100/day per IP, DEFAULT_THROTTLE_RATES["anon"]) counts
// every login, and signing in per viewport exhausted it in one run. A page is
// resized in place for the 1x viewports; 200 % needs its own 2x context.
async function openContext(scale, first) {
  const context = await browser.newContext({ viewport: { width: first.width, height: first.height }, deviceScaleFactor: scale });
  if (API) {
    // A path that starts with /api/ — not "**/api/**", which also catches the
    // dev server's own modules (/src/api/auth.ts) and breaks the app.
    await context.route((url) => url.pathname.startsWith("/api/"), (route) =>
      route.continue({ url: route.request().url().replace(/^https?:\/\/[^/]+/, API) }));
  }
  const page = await context.newPage();
  const consoleErrors = [];
  page.on("console", (m) => { if (m.type() === "error") consoleErrors.push(m.text().slice(0, 200)); });
  return { context, page, consoleErrors };
}

async function measure(page, screen, vp, consoleErrors) {
  consoleErrors.length = 0;
  const cell = { ...screen, viewport: vp.name, device: "headless Chromium (emulated viewport)" };
  try {
    await nav(page, screen.url, Boolean(screen.role));
    await settle(page);
    cell.landedOn = new URL(page.url()).pathname + new URL(page.url()).search;
    cell.overflow = await overflow(page);
    cell.axe = await axe(page);
    if (vp.keyboard) cell.keyboard = await keyboardWalk(page);
    const shot = slug(screen.name) + "__" + slug(vp.name) + ".jpg";
    await page.screenshot({ path: path.join(OUT, "shots", shot), fullPage: true, type: "jpeg", quality: 55 });
    cell.shot = "shots/" + shot;
    cell.consoleErrors = [...new Set(consoleErrors)].slice(0, 5);
  } catch (e) {
    cell.error = firstLine(e);
  }
  return cell;
}

// Resume: a cell that finished cleanly in an earlier run into this <dir> is
// kept and not measured again, so a crash or a throttled sign-in costs only
// the cells it touched. A role whose cells are all kept is not signed in.
// Only cells measured against this same stack are kept: the file is stamped
// with one frontend, backend and API, so a cell from another must not ride
// under that stamp. A run with --only keeps every cell outside its slice.
const STACK = { base: BASE, api: API ?? `${BASE} (dev proxy)`, frontendRef: FRONTEND_REF, backendRef: args["backend-ref"] ?? "unrecorded" };
const priorFile = existsSync(path.join(OUT, "prepass.json")) ? JSON.parse(readFileSync(path.join(OUT, "prepass.json"), "utf8")) : null;
const sameStack = priorFile && Object.entries(STACK).every(([k, v]) => priorFile[k] === v);
if (priorFile && !sameStack) console.log("earlier results in this <dir> were measured against another stack; starting afresh");
const prior = sameStack ? priorFile : null;
const key = (c) => `${c.name}|${c.viewport}`;
const kept = (list) => new Map((list ?? []).filter((c) => !c.error).map((c) => [key(c), c]));
const keptResults = kept(prior?.results);
const keptInteractions = kept(prior?.interactions);

const results = [];
const interactions = [];
const browser = await chromium.launch();
const browserVersion = browser.version();
// Earlier cells this run neither measured nor kept (outside --only) come back
// on every write, so a slice never truncates the file.
const withOthers = (now, earlier) => {
  const here = new Set(now.map(key));
  return [...now, ...(earlier ?? []).filter((c) => !here.has(key(c)))];
};
const save = () => writeFileSync(
  path.join(OUT, "prepass.json"),
  JSON.stringify({
    ...STACK, ranAt: new Date().toISOString(), browser: `chromium ${browserVersion}`, viewports: VIEWPORTS,
    results: withOthers(results, prior?.results), interactions: withOthers(interactions, prior?.interactions),
  }, null, 2),
);
const screens = only(SCREENS);
const checks = only(INTERACTIONS);
const roles = [...new Set([...screens, ...checks].map((s) => s.role))];
try {
  for (const role of roles) {
    for (const scale of [...new Set(VIEWPORTS.map((v) => v.scale))]) {
      const vps = VIEWPORTS.filter((v) => v.scale === scale);
      const mine = screens.filter((s) => s.role === role);
      const myChecks = checks.filter((c) => c.role === role);
      const todo = vps.some((vp) =>
        mine.some((s) => !keptResults.has(key({ ...s, viewport: vp.name }))) ||
        (INTERACTION_VIEWPORTS.includes(vp.name) && myChecks.some((c) => !keptInteractions.has(key({ ...c, viewport: vp.name })))));
      if (!todo) {
        for (const vp of vps) {
          for (const s of mine) results.push(keptResults.get(key({ ...s, viewport: vp.name })));
          if (INTERACTION_VIEWPORTS.includes(vp.name)) for (const c of myChecks) interactions.push(keptInteractions.get(key({ ...c, viewport: vp.name })));
        }
        process.stdout.write("k");
        continue;
      }
      const { context, page, consoleErrors } = await openContext(scale, vps[0]);
      let signInError = null;
      if (role) await signIn(page, role).catch((e) => { signInError = "sign-in failed: " + firstLine(e); });
      for (const vp of vps) {
        await page.setViewportSize({ width: vp.width, height: vp.height });
        for (const screen of mine) {
          const done = keptResults.get(key({ ...screen, viewport: vp.name }));
          const cell = done ?? (signInError ? { ...screen, viewport: vp.name, error: signInError } : await measure(page, screen, vp, consoleErrors));
          results.push(cell);
          save();
          process.stdout.write(done ? "k" : cell.error ? "E" : ".");
        }
        if (!INTERACTION_VIEWPORTS.includes(vp.name)) continue;
        for (const item of myChecks) {
          const done = keptInteractions.get(key({ ...item, viewport: vp.name }));
          const cell = done ?? { ...item, viewport: vp.name, device: "headless Chromium (emulated viewport)" };
          if (!done) {
            if (signInError) cell.error = signInError;
            else {
              try {
                await nav(page, item.url, true);
                await settle(page);
                Object.assign(cell, await reviewInteractions(page));
              } catch (e) {
                cell.error = firstLine(e);
              }
            }
          }
          interactions.push(cell);
          save();
          process.stdout.write(done ? "k" : cell.error ? "E" : "i");
        }
      }
      await context.close();
    }
  }
} finally {
  await browser.close();
  save();
}
process.stdout.write("\n");

// A compact Markdown summary from the file just written (this run's cells and
// the earlier ones it kept): one row per screen x viewport, then the Review
// interactions. It names its stack first, so no table is read without it.
const final = JSON.parse(readFileSync(path.join(OUT, "prepass.json"), "utf8"));
const serious = (c) => (c.axe ?? []).filter((v) => v.impact === "serious" || v.impact === "critical");
const lines = [
  `Automated pre-pass, headless Chromium (${final.browser}), emulated viewports. Frontend ${final.frontendRef}; backend ${final.backendRef} at ${final.api}; ${final.ranAt}.`,
  "",
  "| Screen | Viewport | Overflow | axe serious/critical | axe other | Keyboard |",
  "|---|---|---|---|---|---|",
];
for (const c of final.results) {
  const k = c.keyboard;
  const kb = k
    ? `${k.stops} stops${k.reachedLimit ? ` (**stopped at ${MAX_TABS} Tabs without returning to the start**)` : k.cycled ? ", cycles" : ""}; ${k.noIndicator.length} no-indicator; ${k.covered.length} covered`
    : "—";
  lines.push(`| ${c.name} | ${c.viewport} | ${c.error ? "ERROR " + c.error : c.overflow ? `**${c.overflow.px}px**` : "none"} | ${c.error ? "" : serious(c).map((v) => `${v.id}×${v.count}`).join(", ") || "0"} | ${c.error ? "" : (c.axe ?? []).filter((v) => !serious(c).includes(v)).map((v) => `${v.id}×${v.count}`).join(", ") || "0"} | ${kb} |`);
}
const yn = (v) => (v === true ? "yes" : v === false ? "**no**" : "n/a");
lines.push(
  "",
  "| Review interactions | Viewport | Actions | Arrow keys move | Arrow keys wrap | Last entry under sticky bar | Dialog: focus in | Tab stays in | Escape closes | Focus returns |",
  "|---|---|---|---|---|---|---|---|---|---|",
);
for (const c of final.interactions) {
  if (c.error) { lines.push(`| ${c.name} | ${c.viewport} | ERROR ${c.error} | | | | | | | |`); continue; }
  if (c.skipped) { lines.push(`| ${c.name} | ${c.viewport} | skipped: ${c.skipped} | n/a | n/a | n/a | n/a | n/a | n/a | n/a |`); continue; }
  const covered = c.lastEntryCovered === true ? "**yes**" : c.lastEntryCovered === false ? "no" : "n/a";
  lines.push(`| ${c.name} | ${c.viewport} | ${(c.actions ?? []).join(", ")} | ${yn(c.arrowKeysMove)} | ${yn(c.arrowKeysWrap)} | ${covered} | ${yn(c.focusMovesIn)} | ${yn(c.tabStaysIn)} | ${yn(c.escapeCloses)} | ${yn(c.focusReturns)} |`);
}
writeFileSync(path.join(OUT, "prepass.md"), lines.join("\n") + "\n");
console.log(`wrote ${OUT}`);
