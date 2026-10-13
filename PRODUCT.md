# Product

<!-- impeccable:product-schema 1 -->

> Product context for design work (the `impeccable` skill). It is **not** a requirements authority: `docs/adr/` wins wherever they differ (CLAUDE.md, source-of-truth hierarchy).

## Platform

web

## Users

- **Students** author research (Thesis / Research, Project, Proposal), publish it through the Publish dialog, and answer the reviewers who ask them for revisions or documents.
- **Advisers** review their advisees' records first, route them to the specialist offices, decide Theses and Projects, and also author research of their own.
- **Office reviewers** (ITSO, IERC, KTTO, RDCO) review what is routed to their office and clear it or record a finding.
- **Every signed-in user** reads the catalogue, saves papers, and asks Ask IRIS questions.

## Product Purpose

IRIS is Cebu Institute of Technology – University's (CIT-U) research and intellectual-property disclosure system. It takes a piece of research from draft through review to a readable, citable record. Success: an author always knows where their work stands and what is theirs to do next, and a reader can find and question the institution's research with every answer traceable to a cited passage.

## Positioning

IRIS has two mechanisms a neighbouring product could not truthfully claim:

- **Type-differentiated, parallel multi-office review with clearance-aware resubmission.** When one office asks for revisions, only that office's clearance resets; the others are kept. This is the thesis contribution.
- **Ask IRIS.** Answers come from passages of the institution's own papers, with citations that open the paper at the cited page.

## Operating Context

- **A capstone thesis with a demonstrated UI.** The interface is shown and graded, not just the API.
- **Built by a four-person team.** Requirements and decisions live in `docs/adr/`. Work is tracked in Jira project `IR`.
- **The workflow is the record of truth.** Workflow state is derived on the server; the client never derives a stage.
- **Visibility is one predicate.** A record a viewer may not read never appears, including in citations and saved lists.

## Capabilities and Constraints

- **CIT-U only.** There is no multi-institution or SaaS feature, even where older docs say otherwise.
- **Saved papers, folders, likes and reading history are stored in this browser only,** and the interface says so. Owned research is account-backed (`/records/mine/`).
- **Status uses the server's wording** (`workflow_state_label`), never a client mapping.
- **Fixed vocabulary.** *Archived* is a rejected record. *Unlisted* is a Thesis or Project kept out of the catalogue. *Accepted* is a Proposal its Adviser accepted.
- **Not built yet:** Proposal continuation ("Continue as Thesis / Project") and lineage. Leave a slot for them; do not show them as working.

## Brand Commitments

- **The maroon brand (`#6B0F12`) is the institution's identity** and stays. The interface uses white, black, grey (`stone`) and maroon only.
- **Type:** Inter for the interface, EB Garamond for titles.
- **The project lead's direction:** user-friendly, modern, artistic yet simple, like other education institutions' websites.
- **Design system changes are recorded in `docs/ui-ux/01-design-system.md`** in the same change.

## Evidence on Hand

- **Demo data:** `manage.py seed_demo` creates accounts and records in every workflow state.
- **Proxy corpus:** a 40-paper arXiv corpus for Ask IRIS evaluation. It is never presented as CIT-U research.
- **Not real yet:** there are no real CIT-U submissions indexed. Do not invent usage numbers, testimonials or institutional statistics.

## Product Principles

1. **Say what is waiting on whom.** The next step is stated in plain words from the server's state.
2. **One truth per fact.** Status, visibility and capabilities come from the server; the interface renders them.
3. **Calm, institutional, legible.** Prefer reading over dashboards. Show no counters where nothing is actionable.
4. **Honest about storage and scope.** Say what is local and what is not built yet.

## Accessibility & Inclusion

- **Standard:** WCAG 2.1 AA. Text contrast is at least 4.5:1, and status is never carried by colour alone (icon plus word).
- **Verified viewports:** 360, 768, 1280 and 1745 px wide, with no horizontal scroll at 360.
- **Tests:** axe stays clean (serious and critical) in every page test.
