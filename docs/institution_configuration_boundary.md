# Institution configuration boundary

**Ticket:** IR-94 (P2-08, task `SA-01`) · **Written:** 2026-11-02 · **Builds on:** [`ui-ux/11-saas-admin.md`](ui-ux/11-saas-admin.md) §2 and §5

**Settled, cited here and not re-argued:** [ADR-002](adr/002-workflow-transition-table.md) (the transition table and its 2026-09-09 amendment), [ADR-005](adr/005-instance-per-tenant.md) (instance-per-tenant), [ADR-009](adr/009-authorization-model.md) (the authorization model), [ADR-032](adr/032-adviser-first-review-and-office-reviewer-pools.md) and [ADR-047](adr/047-rdco-routes-and-decides-at-any-time.md) (how review is routed and decided today).

*Notation:* "ADR-002 §Amendment N" means numbered item N of ADR-002's single 2026-09-09 Amendment.

---

## 0 · Why this document exists

IRIS is meant to be sold to more than one institution. CIT-U is the first. Each institution has its own offices, its own names for them and its own words for things. Some of them have more offices than CIT-U.

**Without a written line between "what an institution may change" and "what IRIS is", CIT-U's specifics leak into the core**, and the second customer becomes a fork. The opposite mistake is just as costly: making everything configurable turns IRIS into a generic workflow engine, which ADR-002 explicitly rejects.

This document draws that line. **The test it has to pass:** someone who has never worked on IRIS should be able to read §1 and say whether a proposed change is *configuration* or *product*.

How to read the status words used throughout (per CLAUDE.md):

| Word | Meaning |
|---|---|
| **CURRENT** | Exists in the code on `main` today; checked on 2026-11-02 |
| **PROPOSED** | Decided in an ADR, not yet built |
| **DEFERRED** | Deliberately not being built in this phase |

---

## 1 · The boundary

### 1a · Configuration — what an institution may change

Configuration is **per instance and set at deployment time** (ADR-005). There is no configuration screen and none is planned: under instance-per-tenant, configuring IRIS for a university means setting up that university's deployment, the way you would set its database password.

| # | Configuration item | Example of a change | Where it lives | Status |
|---|---|---|---|---|
| C1 | **Office labels** — what each office is called | CIT-U's "IERC" becomes "Research Ethics Board" | Labels of `Office`, `ReviewStage` (`core/enums.py`), serialized by the API | **CURRENT** as enum labels (a one-line backend edit per label). **PROPOSED:** settings override per ADR-002 §Amendment 4, so a relabel needs no code at all |
| C2 | **Which offices exist, and how many** | A fourth clearance office | The office vocabulary — see §4 for the exact seams | **CURRENT** as code in a short, named list of places. Making the roster itself configuration is **not decided** (ADR-002 §Amendment 3) |
| C3 | **Who decides each record type** | Proposals decided by the Adviser or RDCO; everything else by RDCO alone | `DECIDING_PARTIES` in `apps/records/lifecycle.py` | **CURRENT**, as a CIT-U default in code |
| C4 | **Record-owned workflow edges** | Who may restore a record whose deletion was declined | `TRANSITIONS`, overridable through `settings.WORKFLOW_TABLE["TRANSITIONS"]` (`lifecycle.load_table()`) | **CURRENT** |
| C5 | **Resubmission policy** | `clearance_aware` (production) or `restart_all` (evaluation only) | `settings.WORKFLOW_TABLE["RESUBMISSION_POLICY"]`, validated at startup | **CURRENT**. ADR-004 restricts `restart_all` to dedicated evaluation instances, never a customer's production one |
| C6 | **Record types** | Adding "Capstone Project" | `RecordType` table rows | **CURRENT** as data. *Behaviour* that turns on a type name (e.g. "a Proposal is never routed") is product, keyed by `RecordTypeName` |
| C7 | **Upload slots per record type** | A thesis requires "Approval Sheet" and "Turnitin Report" | `UploadSlot` table rows, one per `(record_type, name)` | **CURRENT** as data. **CURRENT since IR-971 (2026-11-14):** RDCO edits them in IRIS on its Setup page (`/rdco/setup`), with labels, descriptions and Templates, not at deployment ([ADR-063](adr/063-rdco-sets-requirements-and-templates.md), IR-969) |
| C8 | **Terminology** | "Submission" → "Disclosure"; "Office" → "Committee" | The `terminology` object in [11 §2](ui-ux/11-saas-admin.md#the-contract) | **PROPOSED** — the API sends no terminology object today |
| C9 | **Branding** | Brand colour, logo, institution name | Tailwind design tokens (`colors.brand`), [01-design-system](ui-ux/01-design-system.md) | **PROPOSED / post-MVP.** Tokens exist; hardcoded `#6B0F12` literals must be retired first ([11 §5](ui-ux/11-saas-admin.md)) |

### 1b · Product — what no institution may change

These are what IRIS *is*. A change to any of them is a change to IRIS for every institution, and goes through an ADR.

| # | Product element | What it consists of | Decided in |
|---|---|---|---|
| P1 | **The workflow model** | Adviser-first entry; a decider who may route at any time; specialist offices that review in parallel, each settling its own clearance; Decisions; and **clearance-aware resubmission** — when one office asks for revisions, only that office's clearance resets. This is the thesis contribution | ADR-002, ADR-003, ADR-032, ADR-047 |
| P2 | **The authorization model** | `Record.objects.visible_to(user)` as the one visibility predicate, used everywhere including RAG retrieval; object-level checks in `core.permissions`; the per-record Adviser condition; office roles are not Django administrators; client-side role checks are UX only | ADR-009 |
| P3 | **The data model** | Records, record types, versions, assignments and seats, clearances, Decisions, document requests, the audit log; the *kinds* of party (adviser, specialist office, decider) | Migrations + ADRs |
| P4 | **The tenancy model** | One institution per instance | ADR-005 |
| P5 | **The label contract itself** | The rule that the API supplies display text and the frontend renders it (§2) | [11 §2](ui-ux/11-saas-admin.md) |

### 1c · The quick test

Ask these in order. The first "yes" answers it.

1. **Does the change alter who can see or do something?** → **Product** (P2), whatever it is called. See §3.
2. **Does it add, remove or reorder a step in how a record moves, or change what resubmission resets?** → **Product** (P1).
3. **Does it add a column, a table, or a new kind of thing?** → **Product** (P3).
4. **Does it only change a name, a word, a colour, a list of required uploads, or which existing party decides a type?** → **Configuration** (C1, C3, C7, C8, C9).
5. **Does it add a new office of a kind IRIS already has?** → **Configuration in intent, a bounded code change today** (C2, see §4).

| Proposed change | Answer | Why |
|---|---|---|
| "Call IERC the *Research Ethics Board*" | Configuration (C1) | A label |
| "Theses need a *Turnitin Report* upload" | Configuration (C7) | A row in `UploadSlot` |
| "Call submissions *disclosures*" | Configuration (C8) | Terminology |
| "Our ethics office must approve before the tech office looks" | **Product** (P1) | Sequencing offices replaces parallel clearance |
| "Let our licensing office publish papers" | **Product** (P2) | A power the model gives only the decider (ADR-047 §5) |
| "When ethics asks for changes, reset every office" | Configuration (C5) — **evaluation instances only** | `restart_all` exists as the comparison arm, ADR-004 |
| "Add a Data Protection Office that clears in parallel" | Configuration in intent, bounded code today (C2) | A new office of an existing kind — §4 |
| "Add a field for grant number on every record" | **Product** (P3) | A column |

---

## 2 · The label contract

Restated from [11-saas-admin §2](ui-ux/11-saas-admin.md#the-contract), which remains its home. **The rule:**

> **The frontend never maps a key to English. Labels come from the API.**

A *key* is the stable machine name (`ierc`, `in_review`, `Thesis / Research`). A *label* is what a reader sees ("IERC", "In review"). Keys may appear in frontend code — it has to send and compare them — but the frontend **does not author the label** and **does not enumerate the closed set** of offices. Those two habits are what make a fourth office a frontend change.

| Vocabulary | Key | Label supplied by | Status |
|---|---|---|---|
| **Offices / parties** | `Party` values (`adviser`, `itso`, `ierc`, `ktto`, `rdco`) | `Office` / `ReviewStage` labels, serialized per payload (e.g. `cleared_offices[].label`, the routing tracker's rows) | **CURRENT** in the record and tracker payloads; **not yet** everywhere the frontend shows an office (§5) |
| **Stages / states** | `workflow_state`, `pipeline_status` | `workflow_state_label`, `stage_label` (`apps/records/serializers.py`) | **CURRENT** |
| **Record types** | `RecordType` | Its `name`, a data row | **CURRENT**. The `route_preview[]` and `required_slots[]` extension in 11 §2 is **PROPOSED** |
| **Terminology** | `submission`, `record`, `office`, `clearance`, `decision` | A `terminology` object in a bootstrap payload | **PROPOSED** — not built |

**Four rendering rules** (from 11 §2, unchanged):

1. The frontend never maps a key to English.
2. Colour and icon are keyed to the **semantic status**, never to the office.
3. An unknown key renders its label with neutral styling — it never renders blank.
4. No `if (office === 'ierc')` anywhere.

**A note on 11 §2's sketch.** Its `route[] → [{ key, stage_label, kind: "sequential" | "parallel" }]` line was written against ADR-002's `STAGES` registry, which ADR-032 retired and IR-274 deleted: review is now assignments, seats and Decisions, and the decider chooses which offices to ask (ADR-047). The principle survives intact; the `route[]` field shape is historical and should not be built as written. Recorded here, not reconciled silently.

---

## 3 · Configuration cannot weaken authorization

**An institution can rename an office. It cannot give that office powers the authorization model does not define.**

Configuration changes *what a party is called* and *which existing party plays which existing part*. It never changes *what a part is allowed to do*. Concretely:

| Configuration may | Configuration may not |
|---|---|
| Call RDCO "the Research Council" | Let a party that does not decide publish a record (only the decider publishes, ADR-047 §5) |
| Call IERC "the Research Ethics Board" | Give a clearing office access to records it has not been asked to review |
| Add a required upload to a record type | Make a record visible outside `visible_to(user)` |
| Choose `clearance_aware` or (on an evaluation instance) `restart_all` | Turn any office role into a Django administrator (ADR-009 §2) |
| Name which existing party decides a record type | Replace the per-record Adviser check with "any Adviser" |

**Why this holds structurally, not by promise:**

- **The workflow table is not the authorization mechanism.** ADR-002 §Amendment 6 and `apps/records/lifecycle.py`'s own docstring: the table answers "is this transition legal"; `core.permissions` answers "may *this* user act on *this* record". Both checks must pass. An institution editing `WORKFLOW_TABLE` edits only the first.
- **Labels are display text.** Nothing in the server compares a label to decide anything. Renaming "IERC" changes what is shown, never what is permitted.
- **Visibility is one predicate.** `Record.objects.visible_to(user)` is applied in the queryset of every record action and inside RAG retrieval before scoring (CLAUDE.md, ADR-009). There is no per-institution variant of it, and adding one would be a product change.
- **Client checks are UX only** (ADR-009 §5). An institution that hid or showed a menu item would change nothing the server enforces.

**What a reviewer should reject:** any configuration key whose effect is a permission. If a proposed setting reads like "`OFFICE_CAN_PUBLISH`" or "`OFFICES_SEE_ALL_RECORDS`", it is not configuration — it is an authorization change wearing a setting's name, and it needs an ADR against ADR-009.

---

## 4 · Worked example — a four-office institution

**Northbridge Institute of Technology** (fictional) wants IRIS. It has a decider and **four** clearing offices, not CIT-U's three, and uses different words.

| Part played | CIT-U | Northbridge |
|---|---|---|
| Decider | RDCO | **Research Council** |
| Clearing office — technical | ITSO | **Technology Review Office** |
| Clearing office — ethics | IERC | **Research Ethics Board** |
| Clearing office — commercial | KTTO | **Innovation & Licensing Office** |
| Clearing office — **fourth** | *(none)* | **Data Protection Office** — checks a study's handling of personal data under the Data Privacy Act |
| "Submission" | submission | **disclosure** |
| "Office" | office | **committee** |

### 4a · What the API would send

A Northbridge record in review, asked of all four offices, with the ethics board having requested revisions. The keys are stable machine names; the labels are Northbridge's:

```jsonc
{
  "workflow_state": "in_review",
  "workflow_state_label": "With the committees",
  "current_holders": [
    { "party": "ierc", "label": "Research Ethics Board", "status": "revision_requested",
      "status_label": "Revisions requested" },
    { "party": "dpo",  "label": "Data Protection Office", "status": "reviewing",
      "status_label": "Reviewing" }
  ],
  "cleared_offices": [
    { "office": "itso", "label": "Technology Review Office",      "preserved": true },
    { "office": "ktto", "label": "Innovation & Licensing Office", "preserved": true }
  ],
  "terminology": { "submission": "disclosure", "office": "committee",
                   "record": "record", "clearance": "clearance", "decision": "decision" }
}
```

*(Illustrative shape, merged from two payloads: `current_holders` is on the record detail serializer and `cleared_offices` on the list serializer — both exist today; the field names inside `current_holders` and the `terminology` object are the contract's direction, not a promise of exact names.)*

Northbridge's keys can stay `itso`, `ierc`, `ktto` — a key is never shown, so there is no reason to rename it. `dpo` is new.

### 4b · What changes, and where

**Frontend: nothing** — once the twelve *logic* files in §5 follow the contract. That is the claim 11 §2 makes, and it holds because:

- every label above arrives in the payload, so the tracker shows "Data Protection Office" without knowing the word;
- colour follows `status` (`reviewing`, `revision_requested`), not `party`, so `dpo` is styled like any other office (rule 2);
- an unrecognised `dpo` key renders its label with neutral styling rather than blank (rule 3);
- the list of offices the decider may ask comes from the server, not from `["itso", "ierc", "ktto"]` in `RouteDialog.tsx` (rule 4).

**The relabelling of the three existing offices and the decider:** label overrides only — C1. Under ADR-002 §Amendment 4 (PROPOSED) that is a settings change; today it is the label string in `core/enums.py`, one line each.

**Clearance-aware resubmission is unchanged.** When the Research Ethics Board's revisions arrive, only its clearance resets; the Technology Review Office's and the Innovation & Licensing Office's clearances above are kept (`preserved: true`). That is the product (P1) behaving identically at Northbridge — no configuration was needed to get it.

**Backend: the fourth office is a bounded code change, not configuration — and the ADR says so.** ADR-002's amendment (item 3, in the "What this does NOT achieve" paragraph) states that "adding a fourth office requires no code change" **is not satisfiable** under the current design, because the table *references* offices but does not *define* them.

Re-derived against `main` on 2026-11-02 with:

```bash
cd backend
grep -rnE "Office\.(ITSO|IERC|KTTO)|Party\.(ITSO|IERC|KTTO)|ReviewStage\.(ITSO|IERC|KTTO)|RoleName\.(ITSO|IERC|KTTO)|choices=(Office|ReviewStage|Party)" \
  --include=*.py apps core config | grep -vE "test|migrations/|seed_demo"
```

adding `dpo` touches:

| Seam | File | Change |
|---|---|---|
| The office vocabulary | `core/enums.py` — `Office`, `ReviewStage` (`Party`), `RoleName` | One member each |
| Fields bound to those choices | `apps/reviews/models.py:40,88`, `apps/documents/models.py:225,256` | Generated `AlterField` migrations — no hand-written change |
| The seeded role | a data migration | One `Role` row ("DPO") |
| Role → party maps | `apps/reviews/tracker.py` (`ROLE_TO_PARTIES`, `TRACKER_ORDER`), `core/permissions.py:219-221` | One entry each |
| Role sets | `core/permissions.py` — `REVIEWER_ROLES`, `STAFF_ROLES` | Add the role |
| **The clearing-office set** | `apps/reviews/clearance_state.py:28` — `CLEARANCE_OFFICES` | Add `dpo`. **Miss this and the new office does not get clearance-aware resubmission** — this set is the one ADR-002 says the research contribution lives in |
| Specialist-party sets | `apps/reviews/office_review.py:60` (`SPECIALIST_PARTIES`), `apps/reviews/my_reviews.py:75` (`SPECIALIST_STAGES`), `apps/reviews/revisions.py:64` | Add `dpo` |
| Onward routing | `apps/reviews/routing.py:64-71` — who may request whom, `ONWARD_PARTIES` | One row, plus `dpo` in every other office's row |
| Author flags → office | `apps/reviews/routing.py:82-87` | Only if a submitter flag should suggest the DPO |
| Author flags → office (again) | `apps/records/models.py` — `requested_itso/ierc/ktto` | **Nothing.** ADR-018's IR-767 correction: the form never wrote these and no hint reads them. They are dead columns, serialized but unused, so `dpo` needs no counterpart |

**This is not small, and should not be described as small.** It is about a dozen backend sites across ten modules, one of which carries the thesis contribution. What keeps it a *seam* rather than a fork is that every site is a declared set or map of offices, findable by the command above, and none is a branch on an office's name in a view. It is still a backend code change, and no frontend change at all once §5's logic files are retired.

**Better than the ADR's own list, worse than its hope.** ADR-002's seam list names `ROLE_TO_OFFICE` in `reviews/services.py`, which no longer exists (its role is now `ROLE_TO_PARTIES` and `core/permissions.py`'s map), and predates the sets in `clearance_state.py`, `office_review.py`, `my_reviews.py`, `revisions.py` and `routing.py`, which arrived with ADR-032 and ADR-047. Collapsing those parallel sets into one declared office registry would bring the change back toward the ADR's "one enum, one role map and the table". Recorded here as a finding; not decided here.

The `requested_<office>` booleans are the one place where the *data model* names an office. ADR-018 (as corrected by IR-767) keeps them and reads none of them; removing them is a data-model change for its own ticket. Also a finding, not a decision.

### 4c · A contradiction this document records rather than reconciles

The Jira card's acceptance criterion reads *"a worked example shows a four-office institution needing no code change"*, and its testing requirement asks to *"assert the transition table can express a four-office institution without a code change."* **ADR-002 §Amendment 3 says this is not satisfiable as written**, and ADR-002 outranks Jira (CLAUDE.md §Source-of-truth hierarchy).

This document therefore satisfies the criterion in the form ADR-002 permits: **no frontend change, and a backend change confined to the seams in §4b.** The Jira card's wording should be corrected to match.

**No test was written for the card's testing requirement**, and none could pass: the assertion it asks for is false today, by ADR-002's own account and by §4b's list. A test that *could* be written is the opposite one — that every office-set literal in §4b agrees with `Office` — and that belongs to whichever ticket collapses those sets, not to this documentation card. Making the office roster itself configuration (database-backed offices) is a separate, larger decision that has not been taken; this document does not take it.

---

## 5 · Inventory — frontend files that hardcode CIT-U names

### 5a · How the count was derived

The figure in 11 §2 ("twenty files") and in the Jira card is stale, and so is a "34" figure quoted when this card was briefed. Re-derived on 2026-11-02 against `origin/main` at `820d3d69`, with:

```bash
cd frontend/src
grep -rlE "(^|[^A-Za-z])(itso|ierc|ktto|rdco)|ITSO|IERC|KTTO|RDCO" . \
  | grep -vE "\.test\.|/test/" | sort
```

The pattern catches lowercase keys (including prefixed ones like `requested_itso`, `send_to_rdco`), the uppercase labels, and the role constants. Different patterns give different numbers, which is why earlier counts disagree — a whole-word, lowercase-only search finds 9 files; including test files raises the total to 99.

**Result: 47 non-test source files.** A count of files is a weak measure, though: most of them only *mention* RDCO in a comment. What matters is the kind of hardcoding:

| Kind | What it means | Files | Effect on a second institution |
|---|---|---|---|
| **Logic** | The frontend enumerates the office set, compares a role or party to decide behaviour, or maps a key to English | **12** | **Blocks** a new office or a relabel. A real contract violation |
| **Copy** | Rendered text names an office ("RDCO will review your request") | **12** | A renamed office shows CIT-U's old name. Wrong, but nothing breaks |
| **Comment** | The name appears only in a code comment | **23** | None at runtime. Not a violation |

The **52 test files** that match are fixtures exercising CIT-U's vocabulary; each retires with the source file it tests and is not listed separately.

**The older finding has partly resolved itself.** 11 §2 named `lib/utils.ts`'s `PIPELINE_LABELS`, `StatusBadge.tsx`'s stale `ktto_review` key and `EvaluationPage.tsx`'s own `stageLabel` map. On `main` today `PIPELINE_LABELS` is gone (`utils.ts` matches only in a comment), `StatusBadge.tsx` no longer names any office, and `EvaluationPage.tsx` no longer exists. The "three separate stage-label maps" problem is retired; the remaining key-to-English map is in `AuditLogPage.tsx`.

### 5b · Retirement plans

Two plans, named so a card can cite them:

- **R1 — retired by the label payload.** Needs a server change first: the API must supply the label, the set or the terminology. Typically `W-07`'s labels in the record payload, or a bootstrap payload carrying roles, offices and terminology. Do the server half, then delete the frontend literal.
- **R2 — retired as the screen is touched.** The server already supplies what is needed, or the fix is a copy change using the terminology object once it exists. No dedicated ticket; whoever next edits the screen fixes it.

#### Logic — 12 files

| File | What it hardcodes | Plan |
|---|---|---|
| `lib/constants.ts` | `ROLES` (`KTTO`, `RDCO`, `ITSO`, `IERC`) and the role sets built from them | **R1** — role sets from a bootstrap payload. Last to go: everything below reads it |
| `lib/access.ts` | Route-access arrays: `COORDINATOR = [RDCO]`, `OFFICES = [RDCO, ITSO, IERC, KTTO]` | **R1** — server-supplied capabilities per user. Remains UX only either way (ADR-009 §5) |
| `hooks/useRole.ts` | `isKTTO`, `isRDCO`, `isITSO`, `isIERC` booleans | **R1** — replace with capability checks; retire alongside `access.ts` |
| `types/auth.ts` | `offices: ("itso" \| "ierc" \| "ktto" \| "rdco")[]` | **R1** — widen to `string`; the label arrives with the key |
| `types/records.ts` | Office unions on clearances and declines; `Party`; `requested_itso/ierc/ktto`; `send_to_rdco`; `rdco_note` | **R1** for the office unions and `Party` (widen to `string`). `requested_*` are dead fields (§4b) and go if the backend drops them. `send_to_rdco` and `rdco_note` are API keys, not labels — they may stay |
| `types/reviews.ts` | `MyReviewsParty` union | **R1** — widen to `string` with `types/records.ts` |
| `features/records/paper-view/RouteDialog.tsx` | `["itso", "ierc", "ktto"].map(...)` — the offices a decider may ask; "Accept & send to RDCO" copy | **R1** — the server sends the askable offices with labels (it already sends routing state). The clearest single blocker for a fourth office |
| `features/records/paper-view/reviewActions.tsx` | `OFFICE_PARTIES = ["itso", "ierc", "ktto", "rdco"]`; "Accept & send to RDCO…" label | **R1** — server sends which parties take an added colleague; label from the capability payload |
| `features/records/paper-view/DecisionDialog.tsx` | `flags.party === "rdco"` gate on the executive-decision notice; RDCO copy | **R1** — the server sends whether the viewer is the decider (it already sends `party`); compare a flag, not a name |
| `features/library/researchSections.ts` | `OFFICES = {"itso", "ierc", "ktto"}`; an `"rdco"` section; "With RDCO for a decision" | **R1** — group by party *kind* (decider / office) from the payload |
| `features/audit/AuditLogPage.tsx` | `WORDS` map: `itso: "ITSO"`, `ierc: "IERC"`, … — a key-to-English map | **R1** — audit payload carries labels |
| `features/settings/roleCapabilities.ts` | `ROLE_CAPABILITIES` keyed by `RDCO`/`KTTO`/`ITSO`/`IERC`, English per role. Also stale: its header says `IsAdmin = KTTO, RDCO`, while `access.ts` says RDCO alone | **R1** — role descriptions are institution text; serve them |

#### Copy — 12 files

All **R2**, once the terminology object (C8) supplies the decider's and offices' names. Until then the copy is correct for CIT-U and wrong only for a second institution.

| File | What it hardcodes |
|---|---|
| `components/records/DownloadRequestModal.tsx` | "RDCO will review your request", "RDCO reads this…" |
| `features/admin/DownloadRequestsPage.tsx` | "RDCO's note:" (renders the `rdco_note` API field, which may stay) |
| `features/auth/DataNotice.tsx` | "request to RDCO", "RDCO staff, who approve…" |
| `features/errors/RouteErrorScreen.tsx` | "Details for RDCO" |
| `features/help/helpSections.tsx` | Eleven mentions — the help text describes CIT-U's offices by name and expands RDCO in full. Largest copy file; help is institution text and is the strongest case for serving it whole |
| `features/library/DownloadRequestsView.tsx` | "RDCO's note:", "When you ask RDCO for a copy…" |
| `features/opportunities/CallsAndConferencesPage.tsx` | "RDCO and advisers post calls here…" |
| `features/opportunities/OpportunityFormDialog.tsx` | "ask RDCO"; a placeholder spelling out CIT-U's office name |
| `features/records/metadata/AdviserCombobox.tsx` | "Contact RDCO." |
| `features/records/paper-view/OfficeReviewDialog.tsx` | "RDCO sees it and decides", "RDCO and the author see this" |
| `features/records/paper-view/PaperDownloadControl.tsx` | "RDCO's note:" (variable names `rdcoNote` are not copy) |
| `features/settings/SettingsPage.tsx` | "Ask RDCO if this is wrong" |

#### Comment-only — 23 files

No runtime effect; no retirement needed. Listed so the count is checkable. When one of these files is edited for another reason, prefer the role ("the decider", "an office") where the comment is describing the model rather than CIT-U.

`api/accounts.ts` · `api/records.ts` · `api/reviews.ts` · `components/auth/AccountLockedModal.tsx` · `components/auth/ForbiddenScreen.tsx` · `components/auth/LoginForm.tsx` · `components/auth/ProtectedRoute.tsx` · `components/layout/Sidebar.tsx` · `features/accounts/RoleRequestsPage.tsx` · `features/accounts/UserListPage.tsx` · `features/auth/EmailVerifyPage.tsx` · `features/auth/LoginPage.tsx` · `features/auth/PendingApprovalPage.tsx` · `features/auth/SignupPage.tsx` · `features/auth/loginFailure.ts` · `features/discover/DiscoverIcons.tsx` · `features/records/metadata/metadataSchema.ts` · `features/records/paper-view/NewVersionDialog.tsx` · `features/records/paper-view/ReviewRoutingTracker.tsx` · `features/records/paper-view/ReviewStatus.tsx` · `features/review/ReviewAnalyticsPage.tsx` · `lib/utils.ts` · `router/index.tsx`

### 5c · Order of retirement

1. **`RouteDialog.tsx`, `reviewActions.tsx`, `researchSections.ts`, `DecisionDialog.tsx`** — the enumerations that literally prevent a fourth office from appearing. Each needs only a list the server already knows.
2. **`AuditLogPage.tsx`, `roleCapabilities.ts`** — the two remaining key-to-English maps.
3. **The `types/` unions** — widened once nothing narrows on them.
4. **`constants.ts`, `access.ts`, `useRole.ts`** — last, because every role check reads them, and because they are UX only: getting them wrong cannot weaken authorization (§3), only show the wrong menu.
5. **Copy files** — as screens are touched, once C8 exists.

**Out of scope for IR-94:** doing any of this. This ticket is the inventory, not the migration.

---

## 6 · Pooled multi-tenancy stays documented, not built

Confirmed, not re-decided. [ADR-005](adr/005-instance-per-tenant.md) chose instance-per-tenant for the MVP and designs pooled multi-tenancy **on paper only** as the scale path. Its UI implications are recorded in [11 §5](ui-ux/11-saas-admin.md#5--what-is-designed-but-not-built). Nothing in this document builds toward it beyond what the label contract already does, and the label contract is the largest UI dependency that migration would have.

What this boundary means under each model:

| | Instance-per-tenant (**CURRENT**) | Pooled (**DEFERRED**, ADR-005) |
|---|---|---|
| Where configuration lives | The instance's settings and seed data | Per-tenant rows |
| How it is changed | At deployment, by whoever runs the instance | Would need a tenant admin surface |
| Configuration UI | **None** — there is no admin console (11 §1) | Would be needed |
| Authorization (§3) | Intra-institution only (ADR-009 §SaaS Impact) | Every rule gains a tenant dimension (`SA-03`) |

---

## 7 · Acceptance criteria — where each is met

| Criterion (IR-94) | Section |
|---|---|
| Configuration and product are listed explicitly and separately | §1a, §1b, with a decision test in §1c |
| The label contract is documented — offices, stages, types, terminology | §2 |
| A worked example shows a four-office institution needing no code change | §4 — **no frontend change**; the backend seams ADR-002 §Amendment 3 requires are listed, and the wording conflict is recorded in §4c |
| Every file hardcoding CIT-U names is inventoried with a retirement plan | §5 — 47 files, re-derived, by kind |
| It is stated that configuration cannot weaken authorization | §3 |
| Pooled multi-tenancy remains documented-not-built (ADR-005) | §6 |
