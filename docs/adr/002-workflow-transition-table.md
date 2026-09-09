# ADR-002: Workflow as a declarative transition table

## Status

Accepted — 2026-09-01 · **amended 2026-09-09, §Amendment (shape and mechanism — PROPOSED, not yet built)**

## Context

`Record.pipeline_status` is assigned in **18 places across four modules**. `reviews/services.py` owns 11 of them, guarded by `InvalidPipelineTransition`. The other seven live in views and one service, guarded by hand-written HTTP 400s or nothing at all:

| Site | Transitions | Guard |
|---|---|---|
| `reviews/services.py` | 11 | `InvalidPipelineTransition` ✓ |
| `records/views.py:76` (create) | 1 | n/a |
| `records/views.py:135-138` (`submit`) | 2 | hand-written 400 |
| `records/views.py:208` (`complete`) | 1 | hand-written 400 |
| `records/views.py:254` (`perform_destroy`) | 1 | **none** |
| `records/views.py:334` (`import_excel`) | 1 → `published` | **none** |
| `records/views.py:690-693` (delete decline) | 1 | none; re-derives the type rule |
| `records/services.py:33` (`soft_delete_record`) | 1 | none |

The type-routing rule — *"Proposal → `adviser_review`, everything else → `rdco_intake`"* — is written three times, once inverted. SRS Module 5 is still marked draft, so it will change again.

Three separate requirements converge on the same missing artefact:

1. **The thesis contribution** needs the routing model to be an explicit, describable object, not branches scattered across four files.
2. **The SaaS product** needs offices and routing to be *configurable per institution*. Today CIT-U's four offices are baked into code — `ROLE_TO_OFFICE`, `OFFICE_CHOICES`, `STAFF_ROLES` and `if rt == "Proposal"` branches.
3. **The research evaluation** needs resubmission policy to be switchable so clearance-aware can be compared against restart-all (ADR-004).

## Decision

Introduce `records/lifecycle.py`: a **declarative transition table** keyed by `(from_status, event, actor_role) → to_status`, with a single entry point `apply(record, event, actor)` that wraps each transition in `transaction.atomic()`.

Views name **events** (`submit`, `approve`, `decline`, `mark_complete`, `legacy_import`), never status strings. `reviews/services.py` calls the table instead of assigning. `core/enums.py` supplies the status, stage, office and event vocabularies.

Resubmission policy is a table parameter, not a code branch (ADR-004).

## Amendment — 2026-09-09: the table's shape and where it lives

**Status of everything below: PROPOSED, not CURRENT.** None of it is built. It is the design
IR-136 will be implemented to, settled in review on 2026-09-09 *before* that card was started,
and recorded here because `docs/adr/` is the design authority — a mechanism this load-bearing
should not exist only in a ticket comment. Read every "carries", "declares" and "asserts" below
as *will*, and check the code before believing any of it describes today.

**A conflict this amendment is recorded against, rather than reconciling.**
[`SDLC.md`](../engineering/SDLC.md) §10 has two rows that disagree about this case: a *design
change* takes "a new **or amended** ADR", while *an architectural decision* takes "a new ADR —
never edit an accepted one; supersede it." Amending in place follows established practice
here — ADR-010, ADR-013 and ADR-016 all do it — and this change records the shape of an
already-accepted decision rather than making a new one, so it is treated as the first row. The
contradiction in SDLC.md is real and is left standing to be resolved deliberately, per
CLAUDE.md's source-of-truth rule.

The Decision above fixes the *key* and names the module. It does not say what the table is made
of, nor how "configuration rather than a fork" is actually discharged.

**1. Two structures, not one.** The key `(from_status, event, actor_role)` describes an *edge*.
"IERC and KTTO clear concurrently" is a property of a *node*, and no edge table can express it.
`records/lifecycle.py` will therefore carry a `STAGES` registry — per stage: its kind, its
participating offices, and its label — alongside the `TRANSITIONS` edge table.

**2. Stage kind is declared, not inferred.** Each stage is declared `sequential` or `parallel`.
This one declaration serves three call sites that today each re-derive it:

- `resubmit_record` chooses preserve-vs-restart by testing `last_decline.stage` against a set
  literal, `CLEARANCE_OFFICES`. **That set literal is where ADR-003's primary research
  contribution currently lives**, which is not where a reader — or an examiner — would look for
  it. It reads the table instead.
- `submit_clearance`'s guard uses a second, parallel notion of the same idea at the status
  level (`CLEARANCE_STATUSES = {itso_review, parallel_review}`). Two notions of "is this a
  clearance stage" are two things to keep in sync.
- `apply()` needs it to know how to populate `Review.stage` — see 5 below.

**3. The table is settings-overridable per instance.** A dict literal edited per tenant is a
fork of application code, which is precisely what the Consequences section says this ADR
prevents. `lifecycle.py` holds CIT-U's table as the default; a Django setting overrides it per
instance. This is what makes ADR-005's "configuration within the instance" literally true
without a `tenant_id`, a migration, or DB-backed routing rows. ADR-004 sets its resubmission
policy "per instance", and this is the mechanism that will carry it.

**What this does NOT achieve: IR-136's "adding a fourth office requires no code change" is not
satisfiable as written, and that criterion needs weakening.** A settings-overridable table
*references* offices; it does not *define* them. Office identity lives in application code and
in several places at once: `core/enums.py`'s `Office` hardcodes `itso`/`ierc`/`ktto`,
`ROLE_TO_OFFICE` in `reviews/services.py` maps the same three, `RecordClearance.office` binds
`choices=Office.choices`, and a fourth office also needs a `RoleName` member and a seeded
`Role` row. Decision 3 above — offices stay in code, not database rows — is what makes this
true; the two are consistent, not in tension, but only once stated plainly.

An earlier draft of this amendment claimed the criterion *was* satisfied because a settings
edit is not an application-code change. **That was wrong**, and it was caught in review rather
than by its author. Recorded here rather than quietly deleted, because the reasoning is
seductive and someone will re-derive it.

**The honest criterion is: adding a fourth office touches one enum, one role map and the
table — not eighteen call sites.** That is still the SaaS seam ADR-002 is claiming, and it is
still a large improvement on today. Making the office roster itself configuration is a
different, larger decision, out of scope for IR-136 and not taken here.

**4. Labels default from the enums and may be overridden.** `core/enums.py` (IR-135) supplies
the label for every stage and office. The settings table may override any of them, so a tenant
that calls IERC "Ethics Review Board" changes one key rather than restating twelve. The
frontend still never maps a key to English — it reads whichever label the API serialized.

**5. `Review.stage` is populated two different ways, and that asymmetry is deliberate.**
`Review.stage` is a union: three sequential gates (`adviser`, `rdco_intake`, `rdco`) and three
offices (`itso`, `ierc`, `ktto`) — `submit_clearance` already writes an office into it. For a
sequential stage the value is a property of the stage, so `STAGES` declares it (absorbing
`_STATUS_TO_STAGE`). For a parallel stage it is **not**: `parallel_review` records `ierc` or
`ktto` depending on who acted, resolved through `ROLE_TO_OFFICE`, so `apply()` derives it from
the actor's role.

`ReviewStage` and `Office` therefore remain two enums that deliberately share three values, and
the overlap is load-bearing rather than accidental. An invariant test will assert
`Office.values ⊆ ReviewStage.values` so they cannot drift.

**6. The table does not become the authorization mechanism.** It declares which transitions are
*legal*; it does not decide who may act — that stays where ADR-009 and IR-165 put it. This is
forced rather than chosen, and the reason is worth recording because keying edges on
`actor_role` makes the opposite look natural: `_can_review` checks
`record.adviser_id == user.pk` — **the assigned adviser, not any Adviser.** That is a
per-record condition, and a table keyed on a *role* cannot express it. Two checks, both of
which must pass. IR-136 lists the role→stage authorization rule as out of scope, and this is
why that boundary holds rather than being a convenience.

**What this amendment does not change:** the key, the module, the rejection of `django-fsm` and
BPM engines, and the instruction not to grow the table into a workflow engine.

## Alternatives Considered

**Leave the split as it is.** Rejected. Every future workflow change touches three files; SRS Module 5 is draft and *will* change; and it leaves the Excel importer's unguarded jump to `published` invisible.

**Move all transitions into `reviews/services.py`.** Better than today, and genuinely tempting because that module is already good. Rejected because records-owned edges — create, soft-delete, import — do not belong in the `reviews` app, and because branches in one file are still branches. The value is in the table being *data*.

**Adopt `django-fsm`.** Rejected. Upstream is effectively unmaintained, and a ~30-row table does not need a library. The dependency would also make the institutional-configuration requirement harder, not easier.

**Adopt a BPM engine (Camunda, Flowable).** Rejected. A JVM service alongside a 5-service stack, for a workflow that fits in a dict — and it would move the thesis contribution into a third-party engine, weakening rather than strengthening the claim. See ADR-003 for the related novelty argument.

## Decision Rationale

**Deletion test passes decisively.** Removing this module scatters ~30 rules back across 18 sites in four modules. Complexity concentrates rather than relocating — the signal that an abstraction earns its place.

This is the rare case where one 3-day piece of work satisfies the research contribution, the product requirement and the experimental design simultaneously. Against a 27-day budget that ratio is why it survives when almost every other abstraction proposed in the architecture review was rejected.

It also upgrades the thesis claim. *"CIT-U's workflow, implemented"* becomes *"a configurable type-differentiated routing model, instantiated for CIT-U's four-office structure."* Generality is what a panel asks for, and the table is the generality.

## Consequences

**Positive.** One readable definition of the lifecycle. Table-driven tests with no HTTP. The Excel bypass becomes a declared, auditable edge. Institution #2 becomes configuration rather than a fork.

**Negative.** It touches the core write path for the central domain object — the highest-risk refactor in the plan. It must not be attempted before an import-smoke test exists.

**Risk.** Scope creep into a general workflow engine. The table is ~30 rows for IRIS's stages; it is explicitly **not** a BPMN implementation, and should not grow conditional expressions, timers or sub-processes.

## MVP Impact

**MVP Required, P1.** ~3 dev-days plus ~1 for `core/enums.py`. Thesis-critical and protected from further cuts.

## SaaS Impact

The core enabler. Offices, stages and routing become data; institutional onboarding becomes configuration. Terminology and per-institution stage naming hang off the same table.

## Security Impact

Positive. The unguarded transitions at `records/views.py:254` and `:334` become guarded edges. `transaction.atomic()` closes the partial-application defect where a record could advance having been cleared by one office instead of two.

## Deployment Impact

None.

## Research Impact

**This is where the contribution lives.** The table is what the paper describes and what the evaluation varies.

## Related Requirements

FR-M5-01 (hierarchical submission workflow) · FR-M5-03 · FR-M2-04 (import as a declared edge) · NFR-R3 (integrity under concurrency).

## Related Tasks

`W-01`, `W-02`, `W-03`, `F-03` (enums), `T-03` (transition tests). See [`04-workflow.md`](../architecture-tasks/04-workflow.md).
