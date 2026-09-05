# Issue tracker: Jira

Work for IRIS is tracked in **Jira** — site `citiris.atlassian.net`, project **`IR`**.

This file owns the Jira **state mapping and label taxonomy** (moved here from the retired `WORK_ITEM_LIFECYCLE.md` §11-12). The gates between states are [`../engineering/DEFINITION_OF_DONE.md`](../engineering/DEFINITION_OF_DONE.md); the board flow is [`../engineering/SDLC.md`](../engineering/SDLC.md) §11.

---

## Access

Jira is reachable through the **official Atlassian Remote MCP Server**, registered at project scope in `.mcp.json`:

```json
{ "mcpServers": { "atlassian": { "type": "http", "url": "https://mcp.atlassian.com/v2/mcp" } } }
```

The file carries **no credentials**. Each team member authenticates separately through OAuth (`/mcp` → `atlassian` → Authenticate), and the server acts **as that user** — an agent can only see and change what the authenticated person can. Grant least privilege.

**Site cloudId:** `0e2327e8-dd75-4928-8968-84ef4c2fd413` — pass as a top-level `cloudId` argument on every call. Verified read-write on Jira.

| Operation | Tool |
|---|---|
| Search / list issues | `searchJiraIssuesUsingJql` |
| Read one issue | `getJiraIssue` |
| Create issue | `createJiraIssue` |
| Edit fields, including labels | `editJiraIssue` |
| Move between states | `transitionJiraIssue` |
| Comment | `addOrEditJiraIssueComment` |
| Anything else | `discover`, then `executeRead` / `executeWrite` / `executeDestructive` |

> **Reading labels requires `view: "evidence"`.** The default `compact` view silently omits the `labels` field — asking for it in `fields` is not enough, and an issue with a full label set comes back looking unlabelled. Every label-dependent query must set the view explicitly.

**If the MCP server is unavailable**, fall back to drafting: write the ticket as markdown under `docs/jira-sync/drafts/<effort-slug>/`, following the precedent in `docs/jira-sync/`, and tell the user a human must transfer it. **Never claim an issue was created when it was only drafted.**

---

## State mapping

| Lifecycle state | Jira status | Board column | Marker |
|---|---|---|---|
| Not Ready | To Do | To Do | `not-ready` label |
| Ready to Pull | To Do | To Do | `ready-to-pull` label, no assignee |
| In Progress | In Progress | In Progress | assignee set |
| Blocked | *unchanged* | *unchanged* | `blocked` label + comment |
| Review | In Review | Review | PR linked |
| Done | Done | Done | reviewer approval recorded |

These statuses already exist in project `IR`; **no new status is required**.

**Board filter must include `s2-active`** so the Semester 2 queue is continuously visible, and must not depend on sprint membership. Semester 1 issues carry `legacy-s1` and are excluded from the active board.

---

## Labels

| Group | Values |
|---|---|
| Lifecycle | `s2-active` `legacy-s1` `delivered` |
| MVP | `mvp-blocker` `mvp-required` `mvp-recommended` `do-not-build` |
| Phase | `phase-w1-w2` `phase-w3` `phase-w4-w7` `phase-w8-w10` `phase-w11-w12` `phase-w13-w15` |
| Area | `area-backend` `area-frontend` `area-workflow` `area-security` `area-rag` `area-saas` `area-deployment` `area-testing` `area-mvp-validation` `area-uiux` `area-research` `area-documentation` `area-commercialization` `area-architecture` |
| Thesis | `thesis-critical` |
| Flow | `ready-to-pull` `blocked` `not-ready` `ready-for-agent` |

Every active ticket carries `s2-active` and one or more `area-*` labels covering every system area it touches — verified 2026-09-03: 17 of 57 issues legitimately carry more than one (epics, and cross-cutting stories like IR-60 "Object-level authorization on records and documents", which is both `area-backend` and `area-security`). **Do not invent labels** — this table is the taxonomy.

**Simplified 2026-09-03** (verified against all 57 live issues, view `evidence`). Dropped seven values that were never applied to a real issue and had no other purpose in this doc set: `superseded` `duplicate` `merged` `deferred` `historical` (the "Legacy class" group folded `delivered` — its one real member — into Lifecycle) `post-mvp` `post-semester`. [`docs/jira-sync/00-reconciliation-plan.md`](../jira-sync/00-reconciliation-plan.md) §2's own rule was "a card exists only for work that will be pulled this semester; deferred work gets no card" — so these disposition labels were never actually the mechanism, omission was. `not-ready` and `do-not-build` stay despite zero current uses: both are mapping targets for triage roles in [`triage-labels.md`](triage-labels.md) and `not-ready` is the Not Ready state marker above — they're reserved, not dead.

**`thesis-critical` items are protected from scope cuts.** If capacity slips, cut from RAG and supporting frontend work first — never from the workflow contribution or its measurement.

Priority maps to the Jira field: **P0 → `Highest` · P1 → `High` · P2 → `Medium` · P3 → `Low`.**

Triage roles map onto these labels — see [`triage-labels.md`](triage-labels.md).

**`ready-for-agent`** means the item is specified well enough that an agent may pick it up unattended: acceptance criteria are concrete, the files in scope are identifiable, and no architectural or research decision is left open. It does **not** waive review — [`../engineering/DEFINITION_OF_DONE.md`](../engineering/DEFINITION_OF_DONE.md) §3 still requires a human approver.

---

## When a skill says "publish to the issue tracker"

Create a Jira issue in project `IR`. It must satisfy the **Definition of Ready** (`DEFINITION_OF_DONE.md` §1) or carry `not-ready`. Set `s2-active`, one `area-*`, a priority, and leave it **unassigned** — assignment happens at pull time, never at creation.

## When a skill says "fetch the relevant ticket"

Read the issue by its key (`IR-63`). **Never invent a ticket's contents from its key alone.**

---

## Wayfinding operations

Used by `/wayfinder`. The **map** is one issue with **child** issues as tickets.

- **Map**: an issue labelled `wayfinder-map`, holding the Notes / Decisions-so-far / Fog body.
- **Child ticket**: an issue linked to the map as a Jira subtask, with the question in the body. A `wayfinder-<type>` label records the type (`research`/`prototype`/`grilling`/`task`).
- **Blocking**: Jira's native **"is blocked by"** issue link. A ticket is unblocked when every blocker is `Done`.
- **Frontier**: the map's open children with no open blocker and no assignee; first in map order wins.
- **Claim**: assign yourself — the session's first write.
- **Resolve**: comment the answer, transition to `Done`, then append a context pointer (gist + link) to the map's Decisions-so-far.

Wayfinder labels (`wayfinder-map`, `wayfinder-*`) sit outside the taxonomy above because they are tooling, not board signal. Create them once, and do not add them to the board filter.
