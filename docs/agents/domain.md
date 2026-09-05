# Domain Docs

How the engineering skills should consume this repo's domain documentation when exploring the codebase.

## Layout

**Single-context.** One `CONTEXT.md` at the repo root, one `docs/adr/` tree.

```
/
├── CONTEXT.md        ← does not exist yet; /domain-modeling creates it
├── docs/
│   ├── SRS.md        ← FROZEN thesis deliverable — do not consult
│   ├── SDD.md        ← FROZEN thesis deliverable — do not consult
│   └── adr/          ← requirements, design and decision authority
│       ├── 001-mvp-scope-boundary.md
│       └── …
├── backend/
└── frontend/
```

ADRs are numbered with **three digits** (`001-…`), not four. Follow the existing convention.

## Before exploring, read these

- **`CONTEXT.md`** at the repo root
- **`docs/adr/`**: read the ADRs that touch the area you're about to work in
- **`docs/adr/` is the top authority**, including for requirements and system design. **`docs/SRS.md` and `docs/SDD.md` are frozen thesis deliverables — never read them, never cite them.** See the source-of-truth hierarchy in `CLAUDE.md`

If any of these files don't exist, **proceed silently**. Don't flag their absence; don't suggest creating them upfront. The `/domain-modeling` skill (reached via `/grill-with-docs` and `/improve-codebase-architecture`) creates them lazily when terms or decisions actually get resolved. `CONTEXT.md` does not exist yet — that is expected.

## Use the glossary's vocabulary

When your output names a domain concept (in an issue title, a refactor proposal, a hypothesis, a test name), use the term as defined in `CONTEXT.md`. Don't drift to synonyms the glossary explicitly avoids.

If the concept you need isn't in the glossary yet, that's a signal: either you're inventing language the project doesn't use (reconsider) or there's a real gap (note it for `/domain-modeling`).

## Flag conflicts, don't reconcile them

If your output contradicts an existing ADR, surface it explicitly rather than silently overriding:

> _Contradicts ADR-013 (chunk-level RAG pipeline), but worth reopening because…_

There is nothing above an ADR to appeal to. If an ADR is wrong, the fix is a **new ADR that supersedes or amends it** — not a correction sourced from elsewhere. Record the contradiction; never silently reconcile it.

## State of a component, always

When describing any component, mark it **CURRENT / PROPOSED / DEFERRED / LEGACY**. Several components in this repo are designed but not built (chunking, Docling, the AI gateway's boot path). Do not describe a proposed component as if it exists.
