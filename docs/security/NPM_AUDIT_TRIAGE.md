# Frontend `npm audit` triage

**Ticket:** [IR-918](https://citiris.atlassian.net/browse/IR-918) · **Taken:** 2026-11-06, `frontend/package-lock.json` at `origin/main` 5272bf9d, `npm audit --json` run locally

**Owners are proposed, not confirmed.** The author of this record cannot assign work. Every "Proposed owner" below is a suggestion for the person named to accept or reassign; until they do, treat the owner column as unassigned.

## Result

`npm audit` reports **38 findings: 0 critical, 0 high, 34 moderate, 4 low.** The CI `Security` job fails only on high or critical ([`TEST_PLAN.md`](../testing/TEST_PLAN.md) §Security gate), so the gate is green and [`security/allowlist.yml`](../../security/allowlist.yml) stays empty. Nothing here is accepted by exception; this file records why each finding is or is not a risk to IRIS, so it can be revisited rather than re-derived.

The 38 are six root advisories. The rest are packages npm lists only because they depend on a vulnerable one.

| # | Advisory | Package (installed) | Severity | In the browser bundle? | Findings it accounts for |
|---|---|---|---|---|---|
| 1 | [GHSA-cp6q-959q-f8rh](https://github.com/advisories/GHSA-cp6q-959q-f8rh) `mergeAttributes()` turns an own `__proto__` key into executable DOM attributes | `@tiptap/core` via `@tiptap/react` / `starter-kit` 2.27.3 | moderate | **No.** Not imported anywhere in `src/`, absent from `dist/` | 24 (`@tiptap/*`) |
| 2 | [GHSA-238p-pmpm-9mq7](https://github.com/advisories/GHSA-238p-pmpm-9mq7) KaTeX prototype pollution bypasses `trust` restrictions | `katex` 0.16.47, nested under `rehype-katex` and `micromark-extension-math` | low | Yes (Ask IRIS answers) | 4 (`katex`, `micromark-extension-math`, `rehype-katex`, `remark-math`) |
| 3 | [GHSA-g3hv-75wg-m249](https://github.com/advisories/GHSA-g3hv-75wg-m249) minimatch denial of service | `minimatch` 10.2.5 under `@typescript-eslint/typescript-estree` | moderate | **No.** Lint tooling | 6 (`@typescript-eslint/*`, `minimatch`) |
| 4 | [GHSA-rj75-hqrm-r3gf](https://github.com/advisories/GHSA-rj75-hqrm-r3gf) PostCSS selector parser quadratic complexity | `postcss-selector-parser` 6.0.10 under `@tailwindcss/typography` | moderate | **No.** Build-time CSS generation | 2 |
| 5 | [GHSA-wrjc-x8rr-h8h6](https://github.com/advisories/GHSA-wrjc-x8rr-h8h6) open redirect via backslash in `<Link>` / `useNavigate` | `react-router` 6.30.6 (via `react-router-dom`) | moderate | Yes | 2 (`react-router`, `react-router-dom`) with #6 |
| 6 | [GHSA-337j-9hxr-rhxg](https://github.com/advisories/GHSA-337j-9hxr-rhxg) arbitrary constructor injection in `deserializeErrors()` during SSR hydration | `react-router` 6.30.6 | moderate | Yes, but the code path is server rendering | (same packages as #5) |

## Per-finding triage

### 1. Tiptap, 24 findings: remove the dependency

`@tiptap/react` and `@tiptap/starter-kit` are listed in `frontend/package.json` and have been since the initial commit (`a350e06e`). **Nothing in `frontend/src/` imports them, and `dist/` holds no Tiptap or ProseMirror code**, so the advisory cannot be reached. npm's suggested fix is a semver-major move to Tiptap 3, which would add a large upgrade to a package nothing uses.

- **Decision:** not exploitable; the right fix is to delete the two dependencies, not upgrade them. That clears 24 of the 38 findings.
- **Not done in IR-918.** It is a `package.json` and lockfile change outside this ticket's scope. A follow-up ticket is needed; none exists yet, and one has not been invented here.
- **Proposed owner:** Lee Jasmin Adolfo (frontend). Confirm.

### 2. KaTeX, 4 findings: not reachable while `trust` stays off

The advisory lets an attacker bypass KaTeX's `trust` restrictions. IRIS never turns `trust` on: `PassageQuote.tsx` calls `katex.renderToString(source, { throwOnError: false, displayMode: true })` with the default `trust: false` and says so in its comment, and `CitationText.tsx` uses `rehype-katex` with default options. The top-level `katex@0.18.10` is already past the fixed version (0.18.2). The vulnerable 0.16.47 is the copy `rehype-katex` and `micromark-extension-math` nest. npm's suggested "fix" (`rehype-katex@1.2.0`, `remark-math@3.0.1`) is a **downgrade of several major versions**, which would break rendering and should not be taken.

- **Decision:** accepted as not exploitable under the current configuration; revisit when `rehype-katex` ships a release that depends on `katex >= 0.18.2`, and **never enable `trust`** until then.
- **Proposed owner:** Lee Jasmin Adolfo (frontend; the Ask IRIS reader). Confirm.

### 3. minimatch, 6 findings: lint tooling only

`minimatch` 10.2.5 is reached only through `@typescript-eslint/typescript-estree`, which runs when linting. It is never in `dist/`, and its input is this repository's own file globs, not user input. npm's suggested fix (`@typescript-eslint/parser@6.15.0`) is a downgrade.

- **Decision:** accepted; clears when `@typescript-eslint` moves to a release that depends on `minimatch >= 11.0.1`. Routine dependency upkeep.
- **Proposed owner:** Lee Jasmin Adolfo (frontend tooling). Confirm.

### 4. postcss-selector-parser, 2 findings: build-time only

Reached through `@tailwindcss/typography` while Tailwind generates CSS from our own config. Not shipped, and the selectors it parses are ours, not visitors'. npm's suggested fix (`@tailwindcss/typography@0.5.4`) is a downgrade.

- **Decision:** accepted; clears on a `@tailwindcss/typography` release using `postcss-selector-parser >= 6.1.5`.
- **Proposed owner:** Lee Jasmin Adolfo (frontend tooling). Confirm.

### 5 and 6. react-router, 2 findings: the one that ships, not exploitable today

- **#6 (SSR hydration).** IRIS is a single-page app with no server rendering, no `hydrateRoot` and no `StaticRouter`, so `deserializeErrors()` has no server-provided data to be fed.
- **#5 (open redirect by backslash in `<Link>` / `useNavigate`).** Every redirect destination that comes from outside the code (`?next=`, router state) passes through `safeRedirectPath` in `src/lib/redirectTarget.ts` first, which strips the control characters a browser drops and rejects `//` and `/\` prefixes (IR-236). Our own `<Link>`s take paths built from ids. So an attacker would need a path that survives that check, and the advisory's bypass is a backslash form it already refuses.
- The real fix is `react-router-dom` 7, a semver-major migration. That is worth its own ticket rather than a drive-by, because it touches the route table.
- **Decision:** accepted for now, with the mitigation above, and **upgrade to v7 as planned work.** Because this is the only finding that ships and has a plausible exploit class, it is the one to prioritise. No ticket exists for it yet.
- **Proposed owner:** Lee Jasmin Adolfo (frontend; owns the router). Confirm.

## Follow-ups this triage needs (not created)

| Follow-up | Clears | Proposed owner |
|---|---|---|
| Remove `@tiptap/react` and `@tiptap/starter-kit` from `frontend/package.json` and the lockfile | 24 findings | Lee Jasmin Adolfo |
| Plan the `react-router-dom` 7 migration | 2 findings | Lee Jasmin Adolfo |
| Re-run this triage after either lands, or when `npm audit` reports a high | any new finding | whoever owns the PR |

## Re-running

```bash
cd frontend
npm audit --json > ../npm-audit.json
cd ..
python -m security.audit_gate --allowlist security/allowlist.yml --npm-audit npm-audit.json
```

CI keeps the same report as the `dependency-audit` artifact on every run. If a finding ever reaches **high**, it fails the gate and needs either an upgrade or an entry in `security/allowlist.yml` with a named owner and an expiry (at most 90 days); this file is where the reasoning for that entry would be recorded.
