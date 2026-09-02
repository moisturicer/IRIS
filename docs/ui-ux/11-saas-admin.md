# 11 — SaaS & Administration

**Verdict: build no administration suite. Build one label contract.**

[ADR-005](../adr/005-instance-per-tenant.md) chose instance-per-tenant. That decision removes most of what a SaaS product would normally need a UI for, and it converts the remainder into a deployment concern rather than a screen.

---

## 1 · What instance-per-tenant deletes

Each institution gets its own deployment: own database, own media volume, own stack. There is exactly one institution inside any running instance.

| Normally required | Under instance-per-tenant |
|---|---|
| Tenant switcher | **No** — there is one institution per instance |
| Organisation management | **No** — the instance *is* the organisation |
| Cross-tenant admin console | **No** — no cross-tenant surface exists |
| Provisioning wizard | **No** — `SA-02` is a runbook, not a screen |
| Billing and subscription UI | **No** — out of scope by explicit instruction; no in-system payment |
| Per-tenant feature flags | **No** — configuration is deployment-time |
| Data export console | **No** — `SA-04` is `pg_dump` plus a volume copy |

**Every one of these is a screen that does not get designed, built, tested, documented or evaluated.** That is the largest single scope reduction in this document set, and it follows from one architecture decision rather than from cutting features.

Do not build an enterprise administration suite. The instance boundary already does that job.

---

## 2 · What SaaS-readiness actually requires of the UI

Not an admin console. **A label contract.**

If the next customer calls IERC "the Research Ethics Committee", calls a submission a "disclosure", and has four clearance offices instead of three, the interface must accommodate that **without a frontend change**. That is the entire UI-side requirement of the SaaS ambition.

### The finding

**Twenty frontend files hardcode CIT-U office and role names** (`itso`, `ierc`, `ktto`, `rdco`), including:

| File | What it hardcodes |
|---|---|
| `lib/utils.ts` | `PIPELINE_LABELS` — the stage vocabulary |
| `components/shared/StatusBadge.tsx` | 13 statuses → colours, **including a stale `ktto_review` key** |
| `features/review/EvaluationPage.tsx` | Its **own** `stageLabel` map of five stages |
| `lib/roleDisplay.ts`, `lib/roleDashboard.ts`, `hooks/useRole.ts` | Role vocabulary |
| `lib/constants.ts` | `AUDIT_LOG_ROLES` and friends |
| `router/index.tsx` | Route guards keyed to role names |

Three separate stage-label maps exist, each with a different subset of stages, and one contains a status the backend no longer emits. This is not primarily a SaaS problem — it is why the same stage can appear under two different names on two screens today.

### The contract

The API supplies display text; the frontend renders it.

```
route[]      → [{ key, stage_label, kind: "sequential" | "parallel" }]
clearances[] → [{ office, office_label, status, status_label, … }]
record_types → [{ key, label, route_preview[], required_slots[] }]
terminology  → { submission, record, office, clearance, decision }
```

| Rule | Consequence |
|---|---|
| **The frontend never maps a key to English** | One vocabulary, defined once, server-side |
| **Colour and icon are keyed to the *semantic status***, not the office | A fourth office needs no frontend change |
| **Unknown key → render the label, neutral styling** | New stages degrade gracefully instead of rendering blank |
| **No `if (office === 'ierc')` anywhere** | The condition that makes a fourth customer a code change |

This is supplied by `W-01`'s transition table ([ADR-002](../adr/002-workflow-transition-table.md)) and delivered by `W-07`. **No new backend work is required for the SaaS story beyond what the thesis contribution already needs** — which is why `W-01` is described in [`docs/architecture-tasks/04-workflow.md`](../architecture-tasks/04-workflow.md) as one piece of work satisfying three requirements at once.

> The SaaS-readiness of the interface is achieved by *deleting* string maps, not by adding an admin screen.

---

## 3 · The one administration screen

**Role approvals.** `/users/role-requests`, RDCO only.

`RoleRequestsPage` (145 lines) is the **best-behaved screen in the codebase**: `ConfirmDialog` before a decision, toasts on success and failure, `.catch` on load, `.finally` on loading state. It should be the reference other screens are corrected against.

One defect: `_acting` is set but never read, so the confirmation button shows no loading state and a double-click can fire two decisions.

### Specification — Role Approvals

**User.** RDCO.

**Goal.** Approve or decline a user's request for a role.

**Primary action.** Approve.

**Secondary actions.** Decline · view the requester's details.

**Required data.** `accountsApi.roleRequests()` → per request: requester name, email, requested role, current role, submitted date, and any supporting note.

**Permissions.** RDCO only. Server-enforced (`S-05`). **Granting a role is a privilege escalation** — the strictest check in the product, and one that must be audited (`ROLE_CHANGE` already exists in the audit vocabulary, unlike every workflow event, [10](10-audit-history.md)).

**States.** Pending requests · empty · loading · acting on one request · confirmation open.

**Errors.** Load fails → toast plus an inline retry, **not** an empty list that reads as "no requests". Decision fails → toast, the request stays in the list, the dialog closes. Already correct today, except that the failure toast should name what failed.

**Empty states.** *"No pending role requests."* Positive framing — an empty queue is the normal state.

**Loading states.** Skeleton rows. **The acting request shows a per-row busy state** and its buttons disable — the `_acting` fix.

**Accessibility.** Requests are a list, not a table — each is a small record, not tabular data. `ConfirmDialog` must trap and restore focus ([12](12-accessibility.md)). The role change is stated in the confirmation in full — *"Grant A. Reyes the IERC reviewer role?"* — never *"Approve this request?"*, because the consequence is the thing being confirmed. Outcomes announce via the toast region with `role="status"`.

**Responsive.** Single column. At < 768 px the approve and decline actions become full-width stacked buttons, with the destructive action second ([13](13-responsive.md)).

**MVP/Post-MVP.** **MVP** — list, approve, decline, confirm, audit. **Post-MVP** — bulk approval, role revocation, invitation flow, request history.

**Backend/API dependencies.** `GET /accounts/role-requests/`, `POST /accounts/role-requests/:id/decide/` — **both exist**. `S-05` to narrow permission from `IsAdminUser`. Audit already emits `ROLE_CHANGE`.

---

## 4 · The other administration screens

| Screen | Lines | Disposition | Reason |
|---|---|---|---|
| `RoleRequestsPage` | 145 | **KEEP** | The only administration the pilot needs |
| `UserListPage` | 209 | **DEFER** — remove the route | Read-only user directory; Django admin covers it for the pilot |
| `SettingsPage` | 184 | **DEFER** — remove the route | Nothing in it is configurable per user in the MVP |
| `SessionsPage` | 142 | **DEFER** | Session revocation is real, but it is an operator task at pilot scale |
| `DownloadRequestsPage` | 204 | **DEFER** | The download-token flow is broken at import (`views.py:535–579`) |
| `DeleteRequestsPage` | 205 | **DEFER** | Deletion requests are not on the workflow spine ([02](02-information-architecture.md)) |
| `DocumentReviewsPage` | 13 | **DEFER** | Stub |
| `AccessRequestsPage` | 146 | **REMOVE** | Superseded by role requests; two request systems for one concept |

**Deferred means the route is removed and the component is retained** — no code is deleted, and any of these can be re-routed in a day if the pilot shows a need. Full reasoning in [15](15-mvp-ui-scope.md).

Django admin covers the operator cases for a pilot of this size. Building a second administration UI in front of a database that already has one is the definition of the enterprise suite this project cannot afford.

---

## 5 · What is designed but not built

[ADR-005](../adr/005-instance-per-tenant.md) commits to designing pooled multi-tenancy on paper for the commercial defence. Its UI implications, recorded here so the paper design is complete and so nothing in the MVP forecloses them:

| Pooled-tenancy feature | UI implication | Foreclosed by the MVP? |
|---|---|---|
| Tenant switcher in the Header | One control, one store field | **No** — `AppShell` accommodates it |
| Institution branding | Design tokens already exist ([01](01-design-system.md)) | **No** — provided the `#6B0F12` literals are retired |
| Cross-tenant admin | A separate application, not a route in this one | **No** |
| Per-tenant terminology | **The label contract in §2** | **No — §2 is exactly this work** |
| Self-service onboarding | A public signup and provisioning flow | **No** |

Nothing in the MVP interface prevents the pooled model later. The label contract is the migration's largest UI dependency, and it is being built for the thesis contribution regardless.

**Backend/API dependencies for this file as a whole.** `W-01` (transition table as the configuration source) · `W-07` (labels delivered in the record payload) · `SA-01` (which knobs are institutional configuration) · `S-05` (narrow `IsAdminUser`). No SaaS-specific frontend work exists beyond removing the twenty files' hardcoded vocabulary.
