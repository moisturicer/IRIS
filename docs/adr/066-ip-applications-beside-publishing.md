# ADR-066: A paper's IP applications run beside its publishing, owned by KTTO

## Status

**Accepted** — 2026-11-13 (IR-978): reviewed, accepted and merged by Ashlee Sean (PR #712), as relayed by Hermoine Zozobrado. The decisions come from a design session with Hermoine Zozobrado on 2026-11-12–13. Not built yet.

It amends [ADR-018](018-conditional-parallel-office-routing.md) (KTTO, not ITSO, owns IP), [ADR-063](063-rdco-sets-requirements-and-templates.md) (the IP and commercialization upload slots move into applications) and [ADR-052](052-each-paper-states-its-embargo-and-a-person-ends-it.md) (starting an application sets the IP mark). It sets the shape that IR-979's commercialization application follows.

## Context

Observed on `main`, 2026-11-12:

- RDCO's requirements sheet (IR-969's design session) describes an IP application flow, **For Application → Reviewed → Filed → Approved / Disapproved**, and a commercialization flow, **For Commercialization → Reviewed**. IRIS has neither.
- What exists is scattered:
  - An **IP mark** (`Record.is_ip`): once set it never clears, and only KTTO's IP release lets a marked paper's text reach the AI (ADR-052 §11–13, IR-813).
  - A public **IP type** label (`Record.ip_type`): Patent, Copyright, Trade Secret or Utility Model, set by any office through `PATCH /records/<id>/tags/`. Discover filters by it and shows it.
  - A `for_commercialization` Yes/No flag.
- **Upload slots** for IP documents sit on the submission (ADR-063):
  - **Thesis/Research and Project:** Intellectual Property Application Status, Patent Search Report, Patent Draft, Utility Model, Industrial Design, Trademark, Copyright and Commercialization Assessment.
  - **Proposal:** Utility Model, Industrial Design, Trademark, Copyright, Patent Search Report and Commercialization Initial Assessment.
  - Nobody has written down what goes in each. ADR-063 notes that some are KTTO's outputs, and that no paper needs them all.
- **`UploadReview`** can put a status on any uploaded document, and no screen uses it. IPAMS, the system IRIS replaces, worked like that: any staff role set any status on any document, in any order, with no owner. IR-978 says not to copy it.
- **ADR-018's office table** gives ITSO "patent drafting assessment, prior-art checking" and KTTO "commercial potential". RDCO's sheet gives the IP application to KTTO, and IR-977/IR-979 give commercialization to a new TBI office.
- **Patents depend on order.** Making an invention public before filing can cost it its novelty. Philippine law allows a grace period of about twelve months, which is risky to rely on.
- **On iris-demo, 2026-11-13:** 2 papers, both published, no file in any slot this ADR moves or removes, and no `UploadReview` row.

## Decision

### Shape

1. **A paper has three parallel tracks:**
   - **Publishing:** the review workflow, unchanged.
   - **IP applications:** owned by KTTO.
   - **A commercialization application:** owned by TBI, designed in IR-979 once IR-977 makes TBI an office.

   The two kinds of application share one rule: an application belongs to a paper, is owned by one office, has its own steps in order, and never changes the paper's review. Each has its own flow; there is no generic application engine.
2. **KTTO owns the IP application**, from request to the IP office's decision. ITSO's technical review stays in the paper's review and may recommend an application, but doesn't own one. This amends ADR-018's office table.
3. **Outside the MVP, but part of the main workflow.** MVP validation doesn't wait for it.

### The IP application

4. **Kinds:** Patent, Utility Model, Industrial Design, Trademark and Copyright, the five IPOPHL registers. Trade Secret is never filed, so it has no application. Plant variety protection is out of scope until CIT-U asks for it.
5. **Several per paper, one open per kind.** For example, a patent for a method and a copyright for its software. An application that ended stays in the paper's history, and a new one of that kind can be started.
6. **Only on a Thesis/Research or Project**, once submitted: never on a draft, a deleted paper or a Proposal. A Proposal has nothing to file yet; its early checks stay as documents (decision 22).
7. **Who starts one:** the paper's owners or its Adviser ask, or KTTO opens one directly. A request lands in KTTO's **pool**, the same as review work. A member claims it, or the KTTO coordinator assigns it, and it shows in that person's My Reviews. There is no deadline: filing time depends on drafting and on the IP office, not on IRIS.
8. **Steps**, forward only:

   | Step | Means | KTTO must enter |
   |---|---|---|
   | **For Application** | Someone asked for the IP to be protected | (the request) |
   | **Reviewed** | KTTO examined it | a comment |
   | **Filed** | KTTO submitted it to an IP office | the filing date, the application number and the receipt |
   | **Approved** | The IP office granted or registered it | the grant or registration number and date |
   | **Disapproved** | The IP office refused it | the office's reason |
   | **Not filed** | KTTO ended it before filing | KTTO's reason |
   | **Withdrawn** | The owners ended it before filing | (who withdrew) |

   - Approved, Disapproved, Not filed and Withdrawn end the application.
   - Owners may withdraw only before Filed. After filing, only KTTO records what happens.
   - KTTO may correct the details of the latest step, such as a mistyped number, with a reason. A step is never undone, and an ended application is never reopened.
9. **The IP office it was filed with:** IPOPHL by default, WIPO (PCT, Madrid or Hague), or another office KTTO names. "Application number" is that office's number. For Copyright, Approved means registered, since copyright exists without registration.
10. **Inventors:** a list of names on each application. It starts as the paper's byline authors, and KTTO edits it, for example to add an Adviser who co-invented. Names are stored as text, never as links to accounts.
11. **Recording an earlier filing:** KTTO may start an application directly at Filed or Approved, for IP filed before IRIS tracked it.

### What an application does to the paper

12. **Starting an application sets the IP mark**, if it isn't already set. The mark still never clears. Filing doesn't release the paper to the AI: KTTO's IP release stays a separate act (ADR-052).
13. **The publishing gate.** Before RDCO publishes a paper with an application of any kind that isn't yet Filed or ended, IRIS warns RDCO and names it ("Patent, at Reviewed"). RDCO may publish anyway, but must give a reason. The reason is audited, and KTTO and the paper's owners are notified.
14. **The IP type label is removed.** What the public sees comes from applications instead: "Patent: filed" from Filed, "Patent: granted" from Approved, one per application. Before filing, nothing is shown. Discover's IP-type filter reads the same. Trade Secret is no longer shown anywhere. The labels on iris-demo and in `seed_demo` are demo data, and are dropped.

### Visibility, notices and audit

15. **Who sees an application:** the paper's owners, its Adviser, KTTO and RDCO see the whole panel, with steps, comments, inventors and files. Anyone else gets the same 404 as for a missing application, and sees only the public line of decision 14.
16. **Notices:** the owners and the Adviser are notified in-app at every step. KTTO's pool shows each new request.
17. **Audited:** every step, with who acted and what they entered, every correction, and every gate override. The System Admin reads them in the Audit Log (ADR-051).

### Deletion

18. **An application goes with its paper.**
19. **Deleting an account keeps the application.** The person shows as "Former user" wherever they appear: as requester, as the KTTO member who moved a step, or as the writer of a comment. Files they uploaded stay ("a paper's files belong to the paper"), and inventor names, being text, are untouched. An application is declared in both account-data registries (`apps/accounts/deletion/registry.py`, `apps/accounts/personal_data/registry.py`). A person's personal-data download lists the applications they requested and the comments they wrote, with the paper's title only while they may still read it.

### Documents

20. **Each application has its own document slots**, managed on RDCO's **Setup** page. ADR-063 is extended so a slot can belong to "an IP application of kind X" or "a commercialization application" instead of a record type. One requirements system, edited without code. Required stays a label and never blocks, as in ADR-063. Starting lists:
    - **Patent, Utility Model and Industrial Design:** Patent Search Report, Patent Draft, and a slot named after the kind.
    - **Trademark and Copyright:** a slot named after the kind.
    - **Commercialization application:** Commercialization Assessment.
    - KTTO's own files (the receipt, the decision) go on the step that needs them.
21. **Removed from the paper's submission:**
    - for Thesis/Research and Project, every IP slot and the Commercialization Assessment;
    - **Intellectual Property Application Status**, altogether, because the application now shows its status.

    The Commercialization Assessment moves **now**, so it can't be uploaded anywhere until IR-979 builds the commercialization application.
22. **A Proposal keeps Patent Search Report and Commercialization Initial Assessment**, its early checks of whether the idea already exists and whether it could sell. Its Utility Model, Industrial Design, Trademark and Copyright slots are removed.
23. **The migration refuses to remove a slot that holds a file**, naming the slot and the paper, so a document uploaded before it runs is never lost silently. None did on iris-demo on 2026-11-13.
24. **`UploadReview` and `UploadStatus` are removed:** the model, its serializer, and its uses in the personal-data download and the unverified-account cleanup. iris-demo holds no row.

## Alternatives Considered

- **IP as stages inside the review workflow.** One pipeline and one tracker. Rejected:
  - Publication would wait for the IP office, which can take years.
  - Every paper's pipeline would grow, though most have no IP.
  - It would change the thesis-critical workflow (ADR-002's transition table, parallel clearance and clearance-aware resubmission).
- **IP as the last step of publishing.** Matches "the paper must be finished first". Rejected: for a patent the order has to be the reverse, with filing before the work goes public. Waiting for the IP office's decision would also hold publication for years.
- **A choice between publishing and IP.** Each path stays simple. Rejected: the same paper usually needs both.
- **A hard publishing gate.** No publication before filing. Rejected: RDCO keeps the decision, and an override with a reason is enough to stop novelty being lost by accident.
- **A gate for Patent, Utility Model and Industrial Design only.** Publication doesn't harm copyright or trademark. Rejected: one rule is simpler for RDCO to follow, and the gate is only a warning.
- **One generic application engine for IP and commercialization.** Rejected: two cases don't justify it, and TBI doesn't exist yet.
- **Starting applications on a Proposal.** Rejected: there's nothing to file yet.
- **Owners set the IP mark by hand, or it's set at Reviewed.** Rejected: an unfiled invention could reach an AI company in the meantime.
- **Keep the IP type label** beside applications, or **fill it in automatically**. Rejected: two places that can disagree, or two sources with sync rules. Showing only what has been filed is public when publicity is safe.
- **Leave the IP slots on the submission**, linked into the application. Rejected: every student would keep seeing seven IP slots with no IP at all.
- **Ask for IP documents only through document requests** (ADR-018). Rejected: each kind's slots tell the owners up front what that kind needs, and RDCO keeps the lists on Setup.
- **Keep the old files under a heading.** Rejected: there are none to keep.
- **Let ITSO review novelty, and KTTO file** (ADR-018's split). Rejected: RDCO's sheet gives the whole application to KTTO, and splitting it means a hand-off on every application.
- **Copy IPAMS's status dropdown on every document.** Rejected: no order, no owner and no comments, which is what IR-978 asked not to port.

## Decision Rationale

Keeping the tracks apart lets publication move in weeks while an IP office takes years, and leaves the thesis-critical review untouched. The single gate is the one place they have to meet, because the order matters for novelty. Giving each application its own slots and steps puts IP work where KTTO does it, and stops asking students for documents their paper doesn't need.

## Consequences

- **RDCO can still publish an unfiled invention.** The gate warns and records the override; it doesn't prevent it.
- **KTTO has a new queue with no deadline.** A request can sit unclaimed. The pool shows it, but nothing chases it.
- **A Commercialization Assessment can't be uploaded** between this change and IR-979.
- **Trade Secret disappears** from what readers see.
- **Inventors are names, not accounts,** so IRIS can't link an inventor to a Profile or notify them.
- **An application can be recorded wrongly** (a wrong number, an outcome entered early). Corrections are audited, but IRIS doesn't check the IP office.
- **ADR-018, ADR-052 and ADR-063** each carry a note pointing here (added 2026-11-13).

## MVP Impact

None. MVP validation doesn't wait for it. It is part of the main workflow, so it comes soon after.

## SaaS Impact

The kinds follow IPOPHL. Another country's institution would need its own list and offices. The application's owning office maps to whichever office handles technology transfer there, as RDCO does elsewhere. The slot lists are already per deployment, through Setup.

## Security Impact

- The authorization matrix gains the application routes. A stranger's request answers the same 404 as a missing application.
- An application's comments and files can hold unfiled inventions. They are readable only by the people in decision 15, never by Ask IRIS, and never chunked (ADR-013's manuscript-only rule).
- Setting the IP mark at the request keeps an unfiled invention away from AI vendors.
- Removing `UploadReview` removes a way for any staff role to change any document's status.

## Deployment Impact

- **Migrations:**
  - add the application, its steps, inventors and files;
  - extend upload slots to belong to an application kind;
  - move and remove the slots in decisions 20–22, refusing if any holds a file;
  - remove `Record.ip_type`, `UploadReview` and `UploadStatus`.
- **New audit event types and notification kinds.**
- No new service or setting.

## Research Impact

None on the workflow contribution's evaluation, since the review workflow is unchanged apart from the gate's warning. None on RAG: no application text is chunked or retrieved.

## Related Requirements

None. IR-978 and RDCO's requirements sheet are the source. Implementation tickets add their `docs/testing/traceability/IR-XXX.md`.

## Related Tasks

IR-978 (this design), IR-977 (TBI as an office), IR-979 (the commercialization application), IR-969 and ADR-063 (Setup), IR-813 and ADR-052 (the IP mark and release), ADR-018 (office scopes).
