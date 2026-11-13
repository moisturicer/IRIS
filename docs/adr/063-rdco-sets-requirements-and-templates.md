# ADR-063: RDCO sets each record type's requirements and Templates, Advisers share proposal Templates, and Guidelines shows them

## Status

**Accepted on merge** — 2026-11-08. The decisions are Hermoine Zozobrado's, from a design session under IR-969 on 2026-11-07 and 2026-11-08. Merging this PR records acceptance by Lee Jasmin Adolfo, the project lead, as relayed by Hermoine Zozobrado. Not built yet: IR-971 to IR-975 build it.

It **amends [ADR-051](051-system-admin-account-deletion-and-consent.md)** decision 16, the System Admin's role description and its shared `/notices` page: only RDCO publishes a Notice (decision 9). It **reverses [`institution_configuration_boundary.md`](../institution_configuration_boundary.md) C7**, which kept upload slots per record type as deployment-time configuration with no configuration screen (decision 1). It **restores labels** that migration `documents/0005` removed, under a rule that keeps that migration's point: a label never blocks submitting (decision 3).

**Amended 2026-11-13 by [ADR-066](066-ip-applications-beside-publishing.md) (IR-978; Accepted).** A slot can belong to an IP application of one kind, or to a commercialization application, instead of a record type, and Setup manages those lists too. The IP slots and the Commercialization Assessment leave the Thesis/Research and Project submissions, Intellectual Property Application Status is removed, and a Proposal keeps only Patent Search Report and Commercialization Initial Assessment (ADR-066 decisions 20–23).

It leaves [ADR-018](018-conditional-parallel-office-routing.md) and [ADR-022](022-explicit-document-requests.md) standing, since offices still ask for what they need through document requests. It does not bring back IR-118's request presets, which stay deferred.

## Context

People preparing a Proposal, Thesis / Research or Project have no place in IRIS to see what documents each type asks for, or to download the forms and formats they should follow. RDCO, which owns those forms, has no screen to say so, and Advisers can't share their own proposal formats.

IRIS already holds the list. Each record type has named upload slots (`documents.UploadSlot`), 41 in all, seeded by `documents/0003` from the institution's workflow documentation. They are identical to IPAMS's `Upload` list, the system IRIS replaces. Migration `0005` (IR-118) made every slot optional, because the seeded Required flags described a completed file rather than a submission. The flags couldn't all be satisfied: a paper doesn't need a Patent Draft, Utility Model, Industrial Design, Trademark and Copyright at once. Some items are KTTO's own outputs. And ADR-018 makes documents something an office asks for at the stage it needs them. IPAMS never enforced its list either: "(optional)" was only part of two names.

RDCO's requirements sheet, reviewed in the session, marks some documents Required and some Optional for each type.

## Decision

### Requirements

1. **A Requirement is the existing upload slot, and RDCO edits it in IRIS.** No second list is built. A slot gains a description, an order within its record type and at most one current Template. RDCO adds, edits, reorders and removes requirements per record type. Whatever RDCO sets shows at once wherever slots show (decision 6). This replaces C7's deployment-time configuration for slots only; offices, deciders and record types stay as C1–C4 describe them.
2. **Requirements are per record type only:** Proposal, Thesis / Research and Project, the same for every college. Per-college lists are not built. New record types are not configurable here (IR-976, post-MVP), because each type carries workflow rules: who reviews it first, who decides it (ADR-047) and whether it needs a Proposal.
3. **Each requirement is labelled Required or Optional, and the label never blocks submitting.** A Record with an empty Required slot is accepted, as today. The label tells people what RDCO expects; an office that needs a missing document asks for it through a document request (ADR-022). Enforcing the label would bring back `0005`'s problem, a student stopped by a document they can't produce yet, and would reverse ADR-018.
4. **The Manuscript is a fixed first requirement of every record type.** It is the paper itself (`Record.manuscript`), not a slot. It is always shown first and labelled Required, and that is already the one thing submitting requires. RDCO can edit its description and Template, but not remove it or make it Optional.
5. **Removing a requirement never loses a file.** A requirement that any Record has uploaded to is hidden: it leaves Setup's list, Guidelines, Publish and new document requests, and the files stay on their papers under its name. A requirement nobody has used is deleted.

### Where requirements and Templates show

6. **Compact slots, in Publish and in Paper View.** Each requirement shows as one compact row: name, label, a Template link and a small Upload button. This replaces today's large per-slot cards with their own drop zones (`DocumentCard` in `FilesSection`). Publish, which asks only for the manuscript today, lists the record type's requirements this way. A document request shows the requested slot's Template. Publish links to Guidelines and points out the chosen Adviser's Templates.
7. **Guidelines** (`/guidelines`) is a page every signed-in person reaches from the main sidebar, Publish and Help. It has one section per record type: its description, then its requirements with their labels, descriptions and Template downloads. The Proposal section also lists Advisers' Templates, with a search by Adviser. Guidelines only shows and downloads; it changes nothing.

### Templates

8. **A Template is a file people download and follow.**
   - **Accepted types:** PDF, `.doc`, `.docx`, `.odt`, `.xls`, `.xlsx`, `.ods`, `.png`, `.jpg` and `.jpeg`, up to 50 MB.
   - **Refused:** everything else, including slides, plain text, `.csv`, archives, video, programs, scripts and web pages.
   - **Delivery:** a Template is always served as a download, never opened inside IRIS.
   - **Versions:** only the newest Template of a requirement, or of an Adviser's entry, is offered. A replacement is audited, and the old file is not offered again.

   **Advisers' Templates.** An Adviser has a **My Templates** page for Proposal Templates, each with a title, a short description and a file, in any number and in the Adviser's order. RDCO cannot remove an Adviser's Template. An Adviser's Templates stop showing everywhere while the Adviser is suspended, after their account is deleted, or once they no longer hold the Adviser role. They are separate from RDCO's requirements and never change them.

### Setup and the Notice

9. **RDCO's Setup page** (`/rdco/setup`), for every RDCO account, has three sections:
   - **Requirements & Templates**, per record type.
   - **A description for each record type**, shown at the top of its Guidelines section. For example, a Thesis / Research needs a Proposal first, and a Project covers projects and other outputs.
   - **The Notice.** **Only RDCO publishes a Notice version.** This amends ADR-051 decision 16, which let RDCO or the System Admin publish. The System Admin no longer publishes, but it sees every publication in the Audit Log: who published, when, and which version. ADR-051 decision 17 stands: a published version never changes. ADR-051's shared `/notices` page becomes Setup's Notice section.

   Setup is not "Settings": `/settings` stays each person's own page.
10. **Descriptions are plain text.** Line breaks are kept and web links become clickable. There is no formatting, the same rule ADR-051 decision 17 applies to the Notice.
11. **Every change is audited:** adding, editing, reordering or removing a requirement, replacing or removing a Template, editing a record type's description, every My Templates change, and publishing a Notice. Downloads are not logged.

### Starting data

12. **The list starts as IRIS's current 41 slots, which match IPAMS.**
    - **Labels:** taken from RDCO's sheet where a document appears there, and Optional otherwise. Required means Thesis Revision Form; Patent Search Report for Proposal and Project; and Intellectual Property Application Status, Commercialization Assessment, Community Extension, Publication / Conference Presentation / Both, and Release Form for Thesis / Research and Project.
    - **Descriptions:** start from the sheet's notes, naming an office rather than a person. For example, "Coordinated with the TBI" replaces a staff member's name.
    - **Templates:** none at first. The sheet's "sample from IE" for the Thesis Revision Form becomes a Template when RDCO uploads one.

    RDCO corrects all of these from Setup.

## Alternatives Considered

- **A separate Guidelines list, not connected to submissions.** Simple, and editing it could break nothing. Rejected: the same documents would be described in two places that drift apart, and a Template would never reach the person at the moment they upload or are asked for that document. IR-118 also warns against a second requirements system.
- **Enforce Required at submission.** It would make the label mean something. Rejected: `0005`'s reasons still hold. A list RDCO hasn't yet corrected would block students on documents that don't exist yet, and ADR-018 already gives offices the act of asking.
- **Per-college requirement lists** (the older `docs/document_requirements_architecture.md` proposal). They would fit a Fine Arts thesis and a Computer Studies thesis differently. Rejected for now: no office has asked for it, and it needs a rule for which list applies. A later ADR can add it.
- **Copy IPAMS's labels** (everything without "(optional)" Required). Rejected: IPAMS had no labels, only two names containing "(optional)". Read as Required, that list marks all four IP types and Patent Draft Required on every Thesis.
- **A combined "Configuration" area, or RDCO's setup inside `/settings`.** Rejected: `/settings` is personal, and each RDCO page already does one job.

## Decision Rationale

One list, the slot, is what people upload into, what offices request and what Guidelines describes, so a description or Template written once reaches all three. Labels that inform but never block restore the information RDCO's sheet carries without repeating `0005`'s mistake. Making requirements RDCO's data rather than deployment configuration fits who owns them: the people who change the forms are RDCO, not a developer.

## Consequences

- C7 in the configuration boundary is no longer deployment configuration. Requirement changes need no release, and no review either, beyond the audit trail.
- A wrong Required label misleads until RDCO corrects it, but it cannot stop anyone.
- The four separate IP-type slots and the old-list items stay until RDCO removes them. Removing one with files only hides it (decision 5).
- The System Admin loses an act ADR-051 gave it. IR-799 changes to match, and IR-972 tracks it.
- Advisers' Templates are visible to every signed-in person, so an Adviser shouldn't put anything private in one.
- **Not decided here, each a follow-up story under IR-671:**
  - configurable record types (IR-976, post-MVP);
  - a TBI (Technology Business Incubator) office (IR-977). IPAMS put TBI in KTTO's step, but IRIS will make it its own specialist office;
  - a KTTO-owned IP application flow, For Application → Reviewed → Filed → Approved / Disapproved (IR-978). IPAMS had only a status dropdown on every document;
  - a TBI-owned commercialization review with recommendations (IR-979).

## MVP Impact

Built under IR-969, not labelled MVP-required.

## SaaS Impact

Another institution sets its own requirements and Templates from Setup, with no deployment change, which narrows what C7 asked an instance to configure.

## Security Impact

- **No new attack surface for the browser:** Templates are only ever downloaded, with no inline rendering. Scripts, programs, web pages and archives are refused.
- **No malware scan yet:** uploads aren't scanned until IR-666, so a Template carries the same risk any uploaded document does today. It's limited to the people RDCO and Advisers already are.
- **Access:** Setup is RDCO-only, My Templates is the Adviser's own, and Guidelines is signed-in only. Every route is declared in the access matrix.

## Deployment Impact

One migration adds the slot description, order and Template, and the record type description. One data migration sets decision 12's labels and descriptions. Both are reversible.

## Research Impact

None on the clearance-aware resubmission comparison: labels never block, so submission and review behave as before.

## Related Requirements

FR-M2-01 (stable label only).

## Related Tasks

IR-969 (spec), IR-970 to IR-975 (build), IR-118 (request presets, still deferred), IR-799 (Notice publishing), IR-976 to IR-979 (follow-ups).
