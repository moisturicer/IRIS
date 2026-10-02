# IRIS — Source of Truth

**Status:** Active · **Established:** 2026-10-02 · **Supersedes nothing; outranks everything below it.**

This document reconciles the **answered CIT-U requirements questionnaire**
([`docs/requirements/CIT-U-ANSWERS-2026-10-02.md`](requirements/CIT-U-ANSWERS-2026-10-02.md))
against the ADRs and the code, and records every place they disagree.

It exists because a stakeholder answer and an accepted ADR can now contradict each other, and
when they do, **the stakeholder answer wins and the ADR is wrong until amended.** That is a new
rule in this repository. Before 2026-10-02, `docs/adr/` was the top of the hierarchy.

---

## 1. Authority

### 1.1 The hierarchy, amended

| Rank | Authority | What it settles |
|---|---|---|
| **0** | **Confirmed stakeholder answers** — [`CIT-U-ANSWERS-2026-10-02.md`](requirements/CIT-U-ANSWERS-2026-10-02.md), and this document's reading of them | What CIT-U actually does and wants. **Requirements ground truth.** |
| 1 | [`docs/adr/`](adr/) | Design and decision authority, *within* what rank 0 permits |
| 2 | [`docs/engineering/`](engineering/) | How the team builds, tests, reviews, releases |
| 3 | Code and tests | Actual behaviour |
| 4 | Jira | Planning and tracking. **Never a requirements authority.** |

`docs/SRS.md` and `docs/SDD.md` remain **FROZEN** and are not an authority at any rank.

**When ranks conflict, the higher wins *and the lower is corrected*.** Do not silently
reconcile. §3 is where the current conflicts are recorded; add to it rather than editing an ADR
into quiet agreement.

### 1.2 What this source does *not* settle

**This is one respondent, and they said so twice.** The answers come from a single engineering
professor who wrote *"please ask other colleges for their system"* (EB5) and *"this is just from
the perspective of an engineering professor"* (EB8).

So the questionnaire is rank-0 authority for three things:

1. **What the engineering college does**, concretely and reliably.
2. **Who holds authority elsewhere** — and it names RDCO three times (EB11, EB24, EB26).
3. **What CIT-U has not decided yet** — which is a finding, not a gap to fill with a guess.

It is **not** a university-wide policy statement, and it must never be cited as one. An answer
that reads "stick to the documents required by RDCO" is authority that *RDCO decides*, not
authority about what RDCO decided.

**Six questions came back blank** (Q9, Q19, Q26–Q31). A blank is **not** permission to choose.
See §4.

### 1.3 Using this document

- **Implementing something?** Check §3 for a conflict touching it before you follow an ADR.
- **Writing an ADR?** If it touches a §3 row, the ADR must cite the answer id (`EB1`–`EB27`) and
  say how it discharges the conflict.
- **Citing a requirement?** Cite the answer id. Never paraphrase an answer into an ADR without a
  link back to the transcript.
- **Found a new conflict?** Add a row to §3. Do not resolve it in code first.

---

## 2. What the source confirms

These are now settled requirements. Where IRIS already matches, that is recorded so the decision
is not reopened.

### 2.1 The Adviser is the assessor — confirmed

EB4 says the Commercialization Assessment applies only to work *"tagged 'for commercialization'
**as assessed by adviser**."* The adviser is the person who classifies the work.

This **independently confirms [ADR-032](adr/032-adviser-first-review-and-office-reviewer-pools.md)
§1 and §3** — adviser-first entry, with the Adviser deciding whether specialist review is needed.
ADR-032 reached that conclusion from an internal design session with the project lead; the
stakeholder has now reached it from institutional practice. **This is the strongest single
confirmation in the document.** One caveat is in §3 C-04: IRIS lets the *submitter* set the tag,
not the adviser.

### 2.2 Minimal submission, documents on demand — confirmed in spirit

Three answers push the same way:

- **EB1** — assessments should be *"simple tags and buttons"*; *"Validators would not like having
  to accomplish documents just for making decisions 'official'."*
- **EB2, EB3, EB4** — the Thesis Revision Form, the IP Application Status and the
  Commercialization Assessment should all be **optional**.
- **EB11** — *"For now, hold this thought and stick to the traditional documents."*

This supports [ADR-018](adr/018-conditional-parallel-office-routing.md)'s reduction of the
submission checklist to the manuscript alone, and the direction of
[ADR-022](adr/022-explicit-document-requests.md). The *seeded data* contradicts all of it — §3
C-03.

### 2.3 The manuscript is a distinct document — confirmed

**EB17:** *"Yes, it's a separate document."* The manuscript is not merely a member of IPAMS's
zipped "Documentation" bundle.

This underwrites every manuscript-centric design in IRIS: ADR-032 §5's `RecordVersion.manuscript`,
the chunking and RAG pipeline ([ADR-013](adr/013-chunk-level-rag-pipeline.md)), and
`load_corpus`'s `MANUSCRIPT` extraction. Caveat in §3 C-11: no manuscript slot is seeded.

### 2.4 Proposal → Thesis is a real institutional progression — confirmed

**EB5.2:** a thesis is *"the 2nd official document after proposal."* Department names vary
("Project 1"/"Concept Paper" for the proposal, "Project 2"/"Final paper" for the thesis) but the
sequence is the same.

This confirms [ADR-032 §6](adr/032-adviser-first-review-and-office-reviewer-pools.md) (lineage:
an accepted Proposal continues as a new linked record) as modelling something real, and it
confirms that **the stored type names are local vocabulary, not universal terms** — relevant to
ADR-002 §Amendment 4's label-override mechanism.

### 2.5 Intellectual property ownership — answered, with one gap

| Stage | Owner | Answer |
|---|---|---|
| During development | **CIT-U** | EB22 |
| After final submission | **All parties: the school, the adviser, and the student** | EB23 |
| After patent / commercialization / publication | **A "70/30 deal"** — the split's parties are **not stated** | EB24 |
| Industry-sponsored | **Depends on the university's NDA with the industry partner** | EB25 |
| Written policy | **Exists. Held by RDCO. Not yet obtained.** | EB26 |

**Do not infer who takes the 70 and who takes the 30.** EB24 does not say, and it directs the
team to RDCO. Obtaining the written policy (EB26) is the single highest-value follow-up in the
document, because it is the only thing that can close §4's consent questions on a legal basis
rather than a guess.

### 2.6 Named owners of two statuses

- **Patent application status → RDCO** (EB18)
- **Commercialization status → TBI** (EB19)

IRIS models neither status as a record-level fact — §3 C-09.

### 2.7 There is no official inter-office workflow document

**EB20:** *"Not completely streamlined yet. That is the current project of Innovation group for
now."* **EB21:** the only commercialization-process file that exists is *"not official, and it's
only purpose is to plan commercialization process with IRIS."* Q19 was left blank.

**This is a confirmed fact with a large consequence**, recorded as §3 C-15.

---

## 3. Conflict register

Every row is a place where the rank-0 source disagrees with an ADR, with the code, or with
both. **Severity** is about consequence, not effort.

| | Severity | Meaning |
|---|---|---|
| 🔴 | **BLOCKING** | Work is proceeding on an assumption the source contradicts or leaves open. Stop and decide. |
| 🟠 | **HIGH** | A written decision is wrong or unsupported. Amend before building on it. |
| 🟡 | **MEDIUM** | A real mismatch with a bounded fix. |
| ⚪ | **LOW** | Narrow and mechanical. |

| id | Severity | Conflict | Primary authority |
|---|---|---|---|
| [C-01](#c-01) | 🟠 | "Project" vs "Thesis/Research" is undefined, and the stakeholder asks *us* to define it | EB5.3, EB6 |
| [C-02](#c-02) | 🟡 | A fourth type is requested for non-thesis innovation outputs, unnamed | EB5.4, EB6 |
| [C-03](#c-03) | 🟠 | Seeded `UploadSlot` requirements contradict the source on ten of thirteen rows | EB1–EB4, EB13, EB16 |
| [C-04](#c-04) | 🟡 | The commercialization tag is set by the submitter; the source says the adviser assesses it | EB4 |
| [C-05](#c-05) | 🔴 | The modelled office roster does not match the offices CIT-U names | EB12, EB14, EB15, EB19 |
| [C-06](#c-06) | 🟡 | Who conducts the commercialization assessment is answered as WIL, not KTTO | EB15, EB19 |
| [C-07](#c-07) | 🟠 | Ethics clearance "should be required"; under ADR-032 it is always discretionary | EB16 |
| [C-08](#c-08) | 🟠 | RDCO defines the required documents but, under ADR-032, never sees most records | EB11, EB12 |
| [C-09](#c-09) | 🟡 | Patent and commercialization statuses are tracked in IPAMS with named owners; IRIS models neither | EB18, EB19 |
| [C-10](#c-10) | ⚪ | `IPType` omits Industrial Design and Trademark, and invents Trade Secret | EB13 |
| [C-11](#c-11) | 🟡 | The manuscript is the one confirmed document and has no seeded slot | EB17 |
| [C-12](#c-12) | 🔴 | Whether AI processing harms patentability is unknown to CIT-U — and content has already been sent | EB27 |
| [C-13](#c-13) | 🔴 | Every consent, retrospective-use and corpus question is unanswered; IR-250 is not unblocked | Q26–Q31 blank |
| [C-14](#c-14) | 🟡 | ADR-022's central premise was asked as Q9 and not answered | Q9 blank |
| [C-15](#c-15) | 🟠 | IRIS is partly *defining* the inter-office workflow, not digitising one | EB20, EB21, Q19 blank |

---

### C-01

**🟠 "Project" vs "Thesis/Research" is undefined, and the stakeholder asks us to define it.**

**Source.** EB5.3: *"You have to define the difference between Thesis and Project. IE has design
project, but we produce thesis for it. Engineering theses are called project, and they are
usually machine/product design."* EB6: *"Maybe we can merge thesis and Projects, because some
departments use the terms interchangeably, or their outputs are almost similar, it's hard to
discern."*

**What IRIS assumes.** Three `RecordType` rows seeded by `records/0002_seed_record_types.py`.
[ADR-002](adr/002-workflow-transition-table.md) §Context names the type-routing rule *"Proposal →
`adviser_review`, everything else → `rdco_intake`"*. `CLAUDE.md` and
[ADR-001](adr/001-mvp-scope-boundary.md) name **type-differentiated routing** as part of the
thesis contribution.

**The conflict.** Not that the types are wrong — EB5 says they are "okay" — but that **the
distinction the system is built on is one the institution cannot articulate and may want
collapsed.** The request is inverted: the stakeholder is asking the system to supply a definition
the institution lacks.

**What softens it.** [ADR-032](adr/032-adviser-first-review-and-office-reviewer-pools.md) already
removed almost all behavioural weight from the Thesis/Project distinction. Every record type
enters at the Adviser (§1); which specialist offices review it is the Adviser's choice (§3), not
the type's. The only type distinction ADR-032 preserves is **Proposal vs everything else** —
and that one EB5.2 confirms.

**Disposition.** Do **not** merge the types. Nothing in the source instructs it, and EB6 is
tentative ("Maybe"). But two things must change:

1. **Stop claiming three-way type-differentiated routing as the contribution.** After ADR-032 it
   is not what the code does, and the source now says the institution could not defend the
   distinction anyway. The defensible claim is *reviewer-directed routing with clearance-aware
   resubmission* — which is stronger, and which ADR-032 and ADR-003 already describe.
2. **Decide whether Project survives as a type.** Project lead decision. If it does, it needs the
   definition EB5.3 asks for, and that definition has to come from a wider survey than one
   college.

**Affects.** ADR-001 · ADR-002 · ADR-018 · ADR-032 · `CLAUDE.md` §Repository · the thesis claim.

---

### C-02

**🟡 A fourth record type is requested for non-thesis innovation outputs, and the source cannot
name it.**

**Source.** EB5.4: *"Course Outcomes (?) - Maybe build another term for projects that are not
considered thesis. Like outcomes from CTT, GCED, or any course projects that contains
innovation."* EB6: *"Other outputs can be the outputs from non-thesis subjects but have
innovations requirements. However, find another term for this."*

**What IRIS assumes.** Three types. `RecordTypeName` in `backend/core/enums.py`. "Other Outputs"
exists in IPAMS as a label beside Project and is not modelled.

**The conflict.** A category of real institutional output — innovative coursework from non-thesis
subjects — has nowhere to go. The source asks for it **twice** and declines to name it both
times.

**Disposition.** New requirement, unscoped, **not** in ADR-001's MVP scope. It is additive
(`RecordType` is a table, not an enum constraint), so it is deferrable without debt. Park it;
raise it when the record-type question in C-01 is resolved, since the two answers should be
designed together.

**Affects.** ADR-001 (scope) · `records/0002` · C-01.

---

### C-03

**🟠 The seeded document requirements contradict the source almost everywhere.**

**Source.** The returned documents table, plus EB1–EB4, EB13 and EB16.

**What IRIS assumes.** `backend/apps/documents/migrations/0003_seed_upload_slots.py` seeds 13
slots for Thesis/Research, 12 for Proposal and 16 for Project, **nearly all with
`is_required=True`**.

**The conflict, row by row:**

| Seeded slot | Seeded as | Source says | Verdict |
|---|---|---|---|
| Thesis Revision Form | **Proposal, required** | A **Thesis/Research** document; *"maybe consider them as optional"* (EB2) | Wrong record type **and** wrongly required |
| Patent Search Report | Required on **all three** | "—" for Thesis/Research in the table; *"required for design projects"* (EB13) | Over-applied |
| NDA | **Required** on Proposal and Project | **Optional** in the table | Wrongly required |
| Intellectual Property Application Status | Required | *"not all theses require IP. consider this optional"* (EB3) | Wrongly required |
| Commercialization Assessment | Required | *"optional. This is only for those that are tagged 'for commercialization' as assessed by adviser"* (EB4) | Wrongly required **and** unconditional |
| Community Extension | Required document | *"not necessarily documents… we would prefer these as simple tags and buttons"* (EB1) | Should not be a document |
| Commercialization / Community Extension Initial Assessment | Optional | Should be **tags and buttons** (EB1) | Right requiredness, wrong kind |
| Ethics Clearance | Required on **all three** | Absent from IPAMS; *"Should be required, but not yet streamlined"* (EB16) | **Unsourced**; see C-07 |
| Patent Draft | Required on all three | **Appears nowhere in the source** | **Unsourced** |
| Assessment File | Required on all three | **Appears nowhere in the source** | **Unsourced** |
| Utility Model · Industrial Design · Trademark · Copyright | Four separate required slots | *"reports that will depend on what type the product/software is"* (EB13) | Contingent, not required |

**Why this has not broken anything yet.** ADR-018 reduced the *submission wizard* to the
manuscript alone, and ADR-022 repurposes these slots as the **picklist a reviewer chooses from**
rather than a submission gate. So no student is currently blocked by the wrong data. But
`is_required` is stored, it is what ADR-022's picklist is built on, and it is the only written
statement in the system of what CIT-U requires. **It is now provably wrong.**

**Disposition.**

1. Re-seed `is_required=False` for everything except what the source actually requires.
2. Mark the three unsourced slots (Patent Draft, Assessment File, Ethics Clearance) as
   **unsourced** rather than deleting them — Ethics Clearance in particular is wanted (EB16),
   just not yet institutionally settled.
3. Move Thesis Revision Form to Thesis/Research.
4. Do **not** invent requiredness for anything. Per EB11, RDCO's list is the authority and the
   team does not have it yet.

Needs a migration and an ADR amendment, not a silent data edit.

**Affects.** ADR-018 · ADR-022 · `documents/0003_seed_upload_slots.py` · IR-118.

---

### C-04

**🟡 The commercialization tag is set by the submitter; the source says the adviser assesses it.**

**Source.** EB4: *"only for those that are tagged 'for commercialization' **as assessed by
adviser**."*

**What IRIS assumes.** `Record.for_commercialization` is a submitter-set boolean on the
submission wizard. [ADR-018](adr/018-conditional-parallel-office-routing.md) describes the
frontend pre-checking office requests from the submitter's own flags, and
[ADR-032](adr/032-adviser-first-review-and-office-reviewer-pools.md) §3 reduces them further to
*"the author's hint"* that the Adviser sees.

**The conflict.** Narrow but real: the source makes this an **adviser assessment**, and IRIS
makes it an **author claim** that the adviser may read. Under EB4 the tag has downstream force —
it is what makes the Commercialization Assessment apply at all.

**What softens it.** ADR-032 §3 already demotes these booleans to a hint and gives the Adviser
the routing decision. The gap is only that there is no adviser-owned field that records the
adviser's own assessment as a durable fact.

**Disposition.** Keep the author's flags as a hint, per ADR-032. Add an adviser-set assessment
(or treat the Adviser's routing choice as that assessment and say so explicitly in ADR-032 §3).
Same question applies to `community_extension` and `is_ip`. Small; fold into ADR-032's unbuilt
work rather than raising separately.

**Affects.** ADR-018 · ADR-032 §3 · `Record.for_commercialization`.

---

### C-05

**🔴 The modelled office roster does not match the offices CIT-U names.**

**Source.** The respondent names: **RDCO** (EB11, EB16, EB18, EB24, EB26) · **TBI** (EB19) ·
**CES — Community Extension Service, c/o Maam Luni** (EB14) · **WIL — Wildcat Innovation Labs,
c/o Sir Ralph** (EB15) · **a research committee per department** (EB12) · **the Innovation
group** (EB20).

**What IRIS assumes.** `Office` = `itso | ierc | ktto` (`backend/core/enums.py`). `RoleName`
adds `RDCO`, `Adviser`, `Student`. ADR-032 §1 fixes the party set at
`adviser | itso | ierc | ktto | rdco`.

**The conflict.**

- **ITSO and KTTO are never confirmed by the respondent.** They appear only inside the team's own
  Q17, which EB20 answered *"Not completely streamlined yet."* No answer in the document
  attributes a function to either.
- **CES, WIL, TBI and the departmental research committee have no representation in IRIS at
  all** — not as an `Office`, not as a `RoleName`, not as an ADR-032 party.
- **EB12's research committee is a reviewing body between the Adviser and the offices.** ADR-032
  has no such layer.
- IPAMS attributes community extension to "Sir Alein"; EB14 says **CES, c/o Maam Luni**. The
  legacy system's attribution is stale or wrong.

**Why this is BLOCKING.** IRIS's central claim is that it implements CIT-U's multi-office
clearance workflow. The source does not confirm two of the three clearance offices and names four
bodies the system does not model. **This is not a bug to fix from the questionnaire** — the
questionnaire cannot settle it, because EB20 says the inter-office process is still being
designed by the Innovation group.

**Disposition.** Escalate to RDCO. Specifically ask: *which offices clear a research record
today, what does each clear for, and where do CES, WIL and TBI sit relative to ITSO and KTTO?*
Until answered, **do not present the three-office model as validated** in the thesis, the
defence or the demo.

Note that ADR-002 §Amendment already concedes office identity lives in code in several places
(`Office`, `ROLE_TO_OFFICE`, `RecordClearance.office`, `RoleName`, a seeded `Role` row), so
adding or renaming an office is a bounded change — *"one enum, one role map and the table."*
The blocker is knowing what to put there, not the cost of putting it there.

**Affects.** ADR-002 · ADR-018 · ADR-021 · ADR-032 §1, §4 · `core/enums.py` · the thesis claim.

---

### C-06

**🟡 The commercialization assessment is conducted by WIL, and TBI updates the status — neither
is KTTO.**

**Source.** Q12 asked which office conducts the Commercialization Assessment and what TBI's role
is. **EB15:** *"WIL: Wildcat Innovation Labs. C/o Sir Ralph."* **EB19:** commercialization status
is updated by **TBI**.

**What IRIS assumes.** KTTO owns commercial potential and technology-transfer readiness
(ADR-018's scope table). Neither WIL nor TBI exists in the system.

**The conflict.** Three named bodies for one concern, and the answer does not say how they
relate. TBI's role — the thing Q12 actually asked — is still unstated apart from EB19.

**Disposition.** Subsumed by C-05; listed separately because it is the most concrete instance and
the easiest to put to RDCO as a question. Do not map WIL onto KTTO without confirmation.

**Affects.** ADR-018 · ADR-032 · C-05 · C-09.

---

### C-07

**🟠 Ethics clearance "should be required"; under ADR-032 it can never be mandatory.**

**Source.** EB16: *"Should be required, but not yet streamlined. Usually for Grad School. This is
handled by RDCO."*

**What IRIS assumes.** IERC is the ethics office. `Record.requires_ethics_review` is a
**submitter-set** boolean (ADR-018). [ADR-032](adr/032-adviser-first-review-and-office-reviewer-pools.md)
§3 makes **all** specialist routing the Adviser's discretionary choice, so ethics review is never
compulsory. `documents/0003` nonetheless seeds Ethics Clearance as a **required document on all
three record types** (C-03).

**The conflict, in three parts.**

1. **Requiredness.** The source wants it required; ADR-032's design cannot express a mandatory
   office.
2. **Ownership.** The source says **RDCO** handles ethics clearance. IRIS has a dedicated
   **IERC**. The source never mentions IERC.
3. **Reachability.** Under ADR-032 §3, an Adviser who chooses *accept & publish* means *"RDCO is
   never involved"* — so on the ordinary path the record never reaches the office the source says
   owns ethics.

**What softens it.** *"not yet streamlined"* is the respondent telling us the institution has not
decided. This is **PENDING-INSTITUTION, not a defect**. Building a mandatory ethics gate now
would be inventing policy — exactly what ADR-015's bypass section warns against.

**Disposition.** Do not make ethics review mandatory yet. Do three things:
(a) record in ADR-032 that a mandatory party is currently inexpressible, since that is a design
limit worth knowing before it is needed; (b) correct the seeded Ethics Clearance slot per C-03;
(c) put ethics ownership (RDCO vs IERC) to RDCO alongside C-05.

**Affects.** ADR-018 · ADR-032 §3 · `documents/0003` · C-03 · C-05 · C-08.

---

### C-08

**🟠 RDCO defines the required documents, but under ADR-032 it never sees most records.**

**Source.** EB11: *"stick to the traditional documents and the documents required by **RDCO**."*
EB12: *"There is a **research committee per department**."* EB16: ethics *"is handled by RDCO."*
EB18: patent status is updated by RDCO.

**What IRIS assumes.** ADR-032 §3: on *accept & publish*, **"RDCO is never involved"**. RDCO
enters only when the Adviser routes to a specialist office. There is no departmental research
committee party.

**The conflict.** The body the source names as the document authority, the ethics owner and the
patent-status owner is, by design, absent from the path most records take. If RDCO's document
requirements are institutional requirements, **nothing enforces them on the Adviser-only path.**
And EB12's departmental research committee — a reviewing layer between the Adviser and the
offices — is not modelled at all.

**Why this is not simply "ADR-032 is wrong."** ADR-032's central insight is sound and
independently confirmed by EB4 (§2.1): the person who read the paper should decide who else needs
to. The source does **not** say RDCO must review every record; it says RDCO defines required
documents. Those are compatible — **a requirement RDCO sets can be enforced by the system on
every record without RDCO reviewing any of them.**

**Disposition.** Treat RDCO as a **policy authority** distinct from RDCO as a **reviewing party**.
ADR-032 governs the second; nothing yet governs the first. That distinction should be written into
ADR-032 §3 explicitly, because its current wording ("RDCO is never involved") reads as denying
both. Separately, put the departmental research committee to RDCO as part of C-05.

**Affects.** ADR-022 · ADR-032 §3 · C-03 · C-05 · C-07.

---

### C-09

**🟡 Patent and commercialization statuses have named owners and a defined lifecycle; IRIS models
neither as a record fact.**

**Source.** The questionnaire's uncontested background records the IPAMS lifecycles — patent:
*For Application → Reviewed → Filed → Approved / Disapproved*, with comments at Reviewed and
Filed; commercialization: *For Commercialization → Reviewed*, with recommendations. **EB18**
assigns patent status to **RDCO**; **EB19** assigns commercialization status to **TBI**.

**What IRIS assumes.** `documents/0003` seeds the five patent-lifecycle names as `UploadStatus`
rows, but they attach to a **`RecordUpload`**, not to the record's IP lifecycle.
`Record.ip_type` stores a classification with **no status**. There is no commercialization status
anywhere, and no ADR covers either.

**The conflict.** Two statuses the institution tracks today, each with a named owner, are not
first-class facts in the system meant to replace IPAMS. **This is a regression against the
superseded system**, which is a harder thing to defend at a pilot than a missing new feature.

**Disposition.** Needs an ADR; none exists. Smallest honest version: a record-level patent status
with RDCO as the only writer, and a commercialization status whose writer is blocked on C-05/C-06
(TBI is not a modelled party). Scope against ADR-001 before building.

**Affects.** `Record.ip_type` · `documents/0003` · C-05 · C-06 · **no ADR covers this**.

---

### C-10

**⚪ `IPType` omits two IP kinds the source names and invents one it does not.**

**Source.** EB13 and the IPAMS grouping name five: **Patent · Utility Model · Industrial Design ·
Trademark · Copyright**.

**What IRIS assumes.** `IPType` in `backend/core/enums.py` = `patent · copyright · trade_secret ·
utility_model`. **Industrial Design and Trademark are missing. Trade Secret appears nowhere in the
source.**

**Disposition.** Add `industrial_design` and `trademark`. Leave `trade_secret` and flag it as
unsourced rather than removing it — removing a choice already stored on records is a migration
with data loss, and the source does not deny trade secrets exist, it simply never mentions them.

Note EB13 also reframes these: *"UM, ID, trademark, and Copyright are **reports** that will depend
on what type the product/software is"* — i.e. contingent outputs, not a fixed per-record
classification. That is C-03's point; the enum fix here is independent and safe.

**Affects.** `core/enums.py` · `Record.ip_type` · C-03.

---

### C-11

**🟡 The manuscript is the one document the source confirms, and it has no seeded slot.**

**Source.** EB17: the manuscript is *"a separate document"*, distinct from zipped Documentation.

**What IRIS assumes.** ADR-018 reduced the submission checklist to *"the manuscript only"*;
ADR-032 §5 makes `RecordVersion.manuscript` a FK to a `RecordUpload`; `load_corpus` creates a
`MANUSCRIPT` `PdfExtraction`; the whole RAG pipeline reads it.

**The conflict.** `documents/0003_seed_upload_slots.py` seeds **no Manuscript slot** — only tests
create one ad hoc (`apps/ai/ingestion/tests/test_ingest_extraction.py`,
`apps/records/test_tracker.py`). So the seeded requirement list contains three documents the
source never mentions (C-03) and omits the one it confirms.

**Disposition.** Seed a Manuscript slot per record type, required. Fold into C-03's migration.

**Affects.** `documents/0003` · ADR-018 · ADR-032 §5 · C-03.

---

### C-12

**🔴 Whether AI processing harms patentability is unknown to CIT-U — and CIT-U content has already
been sent.**

**Source.** Q25 asked: *"If a full thesis is sent to an AI company for processing, could that
affect anyone's ability to patent something in it?"* **EB27:** *"This is a very new problem and
I'm not so sure."*

**What IRIS assumes.** [ADR-015](adr/015-voyage-embedding-and-reranking.md) §Security Impact
requires a `DisclosurePolicy` gating every outbound call on IP status, embargo date and author
consent. That gate is working — it refuses everything, because `Record` has no embargo field
(IR-250). IR-317 added a `DEBUG`-only bypass to let development proceed.

**The conflict is not a disagreement. It is the absence of an answer where one was needed.**

**And it is retrospective.** ADR-015 records that **real CIT-U paper content was sent to Voyage
on 2026-09-20** — records 29, 45, 54 and 55, during manual verification, *"under a monkeypatched
gate, before this section existed, and with the opt-out status not verified at the time."* The
ADR itself says *"what was already sent cannot be un-sent"* and that it is *"a fact for a person
to weigh."*

EB27 is that person's answer: **nobody at CIT-U knows whether it mattered.**

Two further facts bear on it, neither of which the respondent was given (see transcript §Part 8):

1. Voyage's ToS §3(iii) licenses Voyage to train on customer content **unless the account opts
   out**; the toggle needs a payment method and is **not retroactive**.
2. The questionnaire told the respondent these services *"state they don't retain it or use it
   for training"* — accurate only post-opt-out. EB27 was answered on an incomplete description.

**Disposition.** This cannot be closed by engineering.

1. **Put the patentability question to RDCO**, with the written IP policy request (EB26). RDCO
   holds the policy and is already named as the patent-status owner (EB18).
2. **Confirm the Voyage training opt-out is flipped**, and record the date, before IR-317's
   bypass sends anything further.
3. **Disclose the 2026-09-20 send** to the project lead and to RDCO. It concerns three published
   CIT-U papers; publication status likely makes it benign, but that is RDCO's call, not ours.
4. **Do not point the bypass at unpublished student work.** ADR-015's condition 4 already forbids
   it; EB27 is now the reason that condition exists.

**Affects.** ADR-013 · **ADR-015 §Security Impact** · IR-250 · IR-317 · IR-278.

---

### C-13

**🔴 Every consent, retrospective-use and corpus question came back blank — and they are exactly
the questions the blocked work depends on.**

**Source.** Q26, Q27, Q28, Q29, Q30, Q31 — **all unanswered.**

**What each blocks:**

| Question | Blocks |
|---|---|
| **Q26** — may an author decline AI processing? | ADR-015's `DisclosurePolicy` "author consent" input. No field exists, because nobody has said whether the choice exists. |
| **Q27** — should consent be granular (storage/search · AI processing · visibility to others)? | **The code has already answered this by default.** `Record.dpa_accepted_at` is a **single combined timestamp** stamped at submission (IR-226). ADR-032 §8 adds a *second* consent for Discoverable Proposals. So IRIS has one-and-a-half consents, chosen by neither design nor stakeholder. |
| **Q28** — essential T&C and Data Privacy terms? | Nothing is written. The Discoverable control's consent text (ADR-032 §8 amendment 4) is the only consent wording in the system, and it was drafted internally. |
| **Q29 / Q30** — may pre-IRIS work be ingested, and AI-processed, without re-consent? | `load_corpus`; ADR-015 bypass condition 4 (*"points only at content already cleared to leave"*) — which currently has no institutional basis; IR-278's real corpus. |
| **Q31** — can we get a corpus of past CIT-U theses? | **The entire retrieval evaluation.** `eval_retrieval`'s baseline runs on a **40-paper arXiv proxy corpus**, and `CLAUDE.md` already warns it must *"never [be cited] as a finding about CIT-U research."* |

**The consequence for IR-250, stated plainly.** ADR-015's development-bypass section says the
disclosure gate *"turns on four questions CIT-U has to answer, with external lead time."* **This
questionnaire asked those questions and they came back blank.** IR-250 is therefore **not
unblocked**, the IR-317 bypass remains the only way to exercise the RAG path, and its removal
deadline — *before IR-278 delivers a real corpus* — is unchanged and now has no visible path to
being met.

**The consequence for the research evaluation.** If Q31 is never answered, the thesis ships a
retrieval evaluation measured entirely on arXiv papers. That is a methodologically honest result
about the *pipeline* and says nothing about *CIT-U research*, which is what the contribution
claims. **This is the highest research risk currently on the project**, and it is now evidenced
rather than suspected.

**Disposition.**

1. **Re-ask Q26–Q31, to RDCO**, as their own short document — not bundled into a 31-question
   form. They are legal/policy questions, and the respondent who left them blank is a faculty
   member, not the data-privacy or IP authority.
2. **Request the written IP policy (EB26) in the same message.** It may answer Q29/Q30 directly,
   since EB22 establishes CIT-U as owner during development.
3. **Escalate Q31 separately and immediately.** It has the longest lead time and the largest
   consequence, and it is the one question a cooperative department can answer in a day.
4. **Record the one-checkbox consent as a decision taken by default.** Either write an ADR
   adopting it deliberately, or mark it provisional pending Q27. Do not leave it as an
   unexamined implementation detail.

**Affects.** **ADR-015** · ADR-013 · ADR-023-retrieval · ADR-032 §8 · IR-226 · IR-250 · IR-278 ·
IR-317 · `Record.dpa_accepted_at` · `eval_retrieval` · **the thesis evaluation**.

---

### C-14

**🟡 ADR-022's central premise was asked as Q9 and not answered.**

**Source.** Q9: *"Is it acceptable for an office to request a document during review instead of
requiring it at submission?"* — **blank**.

**What IRIS assumes.** [ADR-022](adr/022-explicit-document-requests.md) (Accepted) decides exactly
this: a reviewer creates a `DocumentRequest`, the record stays in review, no clearance resets.

**The conflict.** Formal rather than substantive. **EB1** (documents are friction validators
dislike) and **EB11** (*"hold this thought and stick to the traditional documents"*) both lean in
ADR-022's favour, and nothing in the source opposes it.

**Disposition.** Low risk; continue building ADR-022. Record here that its premise is **inferred
from EB1/EB11, not confirmed**, so nobody later cites Q9 as validation. Include it in the re-ask
in C-13.

**Affects.** ADR-022 · IR-262 · IR-263.

---

### C-15

**🟠 IRIS is partly *defining* the inter-office workflow, not digitising an existing one.**

**Source.** EB20: *"Not completely streamlined yet. That is the current project of Innovation
group for now."* EB21: the only commercialization-process file is *"not official, and it's only
purpose is to plan commercialization process with IRIS."* Q19 — *"Is there official documentation
of this workflow we can read?"* — **blank**.

**What IRIS assumes.** ADR-018, ADR-021 and ADR-032 all read as **descriptions of an existing
institutional process**. ADR-032 §Context criticises ADR-021 for being *"wrong as a description
of CIT-U."*

**The conflict.** There is no official description to be right or wrong about. The one process
document that exists was written **to plan the process around IRIS** — so the system is shaping
the workflow, not only recording it.

**Why this matters, and why it is not fatal.** It changes what the thesis can claim. *"We
implemented CIT-U's workflow"* is not supportable. *"We designed a configurable workflow model
with an institution whose process was not yet formalised, and instantiated it for CIT-U"* is both
supportable and a **stronger** contribution — it makes ADR-002's configurability and ADR-003's
clearance-aware resubmission design decisions rather than transcriptions.

But it also means **IRIS's workflow has no external validation**, and the validation story must
come from elsewhere: usability evaluation (ADR-011), the controlled resubmission comparison
(ADR-004), and eventual sign-off from the Innovation group once their work lands.

**Disposition.**

1. Restate the contribution in `CLAUDE.md` and the thesis as *designed with*, not *derived from*.
2. Treat the Innovation group as a stakeholder IRIS has not yet engaged — EB20 names them as the
   owners of the very process ADR-018/021/032 model. **They have not been interviewed.**
3. Ask for EB21's unofficial commercialization file. It is the only written artefact of the
   intended process and was written with IRIS in mind.

**Affects.** ADR-002 · ADR-018 · ADR-021 · ADR-032 · ADR-011 · `CLAUDE.md` §Repository · the
thesis claim.

---

## 4. Open questions

**Nine questions are open.** Six were asked and returned blank; three are answers that defer to a
body the team has not yet reached. **An open question is not a licence to choose a default.**

### 4.1 Asked and unanswered

| # | Question | Blocked work | Severity |
|---|---|---|---|
| **Q31** | Can we get a corpus of past CIT-U theses for testing, development and validation? | The entire retrieval evaluation | 🔴 |
| **Q30** | May past work be AI-processed without re-asking its authors? | IR-250, IR-278, `load_corpus` | 🔴 |
| **Q29** | May pre-IRIS work be added for viewing and discovery without re-asking? | IR-250, IR-278 | 🔴 |
| **Q26** | May an author decline AI processing while still being stored and searched? | ADR-015 `DisclosurePolicy` | 🔴 |
| **Q27** | Should consent be granular, or one combined checkbox? | `Record.dpa_accepted_at`, ADR-032 §8 | 🟠 |
| **Q28** | Essential Terms & Conditions and Data Privacy terms? | T&C; consent wording | 🟠 |
| **Q19** | Is there official workflow documentation? | C-15 (EB21 implies **no**) | 🟠 |
| **Q9** | May an office request a document during review? | ADR-022 (C-14) | 🟡 |

### 4.2 Answered by deferral — the authority named but not yet reached

| From | Question to put to RDCO | Severity |
|---|---|---|
| **EB26** | The **written CIT-U IP policy**. Named as existing, held by RDCO, not obtained. | 🔴 |
| **EB24** | The 70/30 split — **which party takes which share**. Not stated. | 🟠 |
| **EB27** | Does sending a full thesis to an AI vendor affect patentability? *"Not so sure."* | 🔴 |
| **EB11** | **RDCO's actual required-document list.** Named as the authority for C-03. | 🟠 |
| **EB14/EB15/EB19/EB12** | What do **CES, WIL, TBI** and the **departmental research committee** do, and how do they relate to ITSO/IERC/KTTO? | 🔴 |
| **EB16** | Who owns ethics clearance — RDCO or IERC? Will it become mandatory? | 🟠 |
| **EB20/EB21** | The **Innovation group's** in-progress workflow design, and EB21's unofficial commercialization file. | 🟠 |

### 4.3 The one decision already taken by default

**Consent granularity (Q27).** `Record.dpa_accepted_at` is a single combined consent stamped at
submission; ADR-032 §8 adds a second, narrower consent for Discoverable Proposals. Nobody chose
this shape against the alternative. **Either adopt it deliberately in an ADR, or mark it
provisional.** Leaving it unexamined is how a placeholder becomes a policy — the exact failure
mode [ADR-015](adr/015-voyage-embedding-and-reranking.md) §A development bypass warns against.

---

## 5. What changes now

Ordered by consequence. None of these is "write code".

### 5.1 Immediate — escalate to RDCO

A single short request, not another 31-question form:

1. The **written IP policy** (EB26).
2. **Q26–Q31**, as policy questions, to the data-privacy / IP authority rather than to faculty.
3. The **patentability question** (EB27) with the Voyage facts the first respondent was not
   given.
4. The **office roster** (C-05): who clears what, and where CES, WIL, TBI and the departmental
   research committees sit.
5. **RDCO's required-document list** (EB11).

### 5.2 Immediate — disclose and contain

- Report the **2026-09-20 Voyage send** (ADR-015) to the project lead, now that EB27 shows CIT-U
  cannot assess its consequence.
- **Confirm and date the Voyage training opt-out** before IR-317's bypass sends anything further.
- Keep the bypass pointed only at published papers. ADR-015 condition 4, unchanged, now
  evidenced.

### 5.3 Short — correct what is provably wrong

- **C-03 + C-11:** re-seed `UploadSlot` requiredness, move the Thesis Revision Form, add a
  Manuscript slot, mark the three unsourced slots. One migration, one ADR amendment.
- **C-10:** add `industrial_design` and `trademark` to `IPType`.
- **C-13:** record the one-checkbox consent as a deliberate or provisional decision.

### 5.4 Short — correct what is claimed

- **C-01 + C-15:** restate the contribution in `CLAUDE.md` and the thesis as **reviewer-directed
  routing with clearance-aware resubmission**, *designed with* CIT-U rather than *derived from* a
  documented process. Both halves are more defensible than what is claimed today, and both are
  now evidenced.

### 5.5 Deferred — needs an answer first

- **C-02** (fourth record type), **C-06/C-09** (commercialization and patent statuses, their
  owners), **C-07** (mandatory ethics). Each is blocked on §4, not on capacity.

---

## 6. Maintaining this document

- **A new stakeholder answer supersedes this document's reading of the old one.** Add the new
  source under `docs/requirements/`, give its answers stable ids, and update §3 — never edit the
  transcript.
- **A conflict is closed by a decision, not by a commit.** Record the decision and who made it,
  and leave the row with its resolution. A disappeared row looks like an oversight.
- **Never resolve a §3 row by editing an ADR into agreement without saying so.** The ADR gets an
  amendment that cites the answer id, per `CLAUDE.md` §Source-of-truth hierarchy.
- **Never fill a §4 blank with a plausible default.** ADR-015 §A development bypass states the
  reasoning: a plausible rule is *more* dangerous than a labelled gap, because it reads as a
  decision somebody made.
