# IR-770 — Paper View and My Reviews text contrast

Measured on 2026-11-02 in headless Chromium 156 with the real React interface,
Tailwind CSS and seeded demo accounts. This is automated contrast evidence,
not a claim of complete WCAG conformance or human approval.

## Change and measurements

Use the existing `text-stone-600` utility in place of `text-stone-500` for
the affected text on `stone-100`. No palette token, layout, font size or
interaction changed. Both the active My Reviews count and Back's hover color
retain their existing utilities.

| Text | Before | After |
|---|---|---|
| Paper View Back and single-version label | `#78716c` on `#f5f5f4`, 4.3977:1 | `#57534e` on `#f5f5f4`, 6.9934:1 |
| Paper reader zoom percentage | 4.3977:1 | 6.9934:1 |
| Paper Chat AI tag and paper title breadcrumb | 4.3977:1 | 6.9934:1 |
| Inactive My Reviews tab counts | 4.3977:1 | 6.9934:1 |
| Review workspace / current record label | 4.3977:1 | 6.9934:1 |

The review timeline's byline/date/detail labels already use `stone-600` on
this baseline; version badges use `stone-700`. They pass the browser audit
without further changes. The targeted probe includes the open Paper Chat.
See [before-pairs.json](before-pairs.json) and [after-pairs.json](after-pairs.json)
for computed colors, browser-measured elements and axe findings.

## Reproduce

Baseline: `23efea669b32e046361773f67c3f7c3208f6ae84`. The frontend ran from
this task's worktree at `http://localhost:5177`; Django ran from the same
baseline at `http://127.0.0.1:8077`. The backend used a task-owned copy of the
development database with all pending migrations applied, and the shared
demo media volume. The shared database was not migrated. The isolated
backend's `API_THROTTLE_USER` and `API_THROTTLE_ANON` were raised to
`100000/day` for the repeated audit; an earlier attempt hit the shared
development cache's request limit and is excluded from the final evidence.

From `frontend/`, with Playwright installed locally:

```powershell
npm run dev -- --port 5177 --strictPort
node scripts/ir414-prepass.mjs --base http://localhost:5177 --api http://127.0.0.1:8077 --backend-ref 23efea66 --out ../ir770-audit --only "Paper View"
node scripts/ir414-prepass.mjs --base http://localhost:5177 --api http://127.0.0.1:8077 --backend-ref 23efea66 --out ../ir770-audit --only "My Reviews"
```

The final [prepass.json](prepass.json) and [prepass.md](prepass.md) cover
360, 768, 1280 and 1745 px plus 200% zoom (640×360 CSS pixels, scale 2).
Screenshots are retained for representative Paper View, review workspace
and My Reviews states; a rerun regenerates all audit screenshots.

## Checks

- TypeScript (`npx tsc --noEmit`) and production build: passed.
- ESLint: passed, with three existing warnings.
- Focused My Reviews suite: 23 passed; timeline suite: 13 passed.
- No jsdom contrast test was added: the existing real-browser audit is the
  acceptance seam, and the failing browser measurements were captured before
  changing the utilities.

Human review and approval remain required before merge.
