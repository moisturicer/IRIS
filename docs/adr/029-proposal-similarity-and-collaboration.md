# ADR-029: Proposal similarity — collaboration by opt-in, novelty checks by default

## Status

> **§3–§4 partially superseded by [ADR-032](032-adviser-first-review-and-office-reviewer-pools.md) §8**
> (Accepted 2026-09-26). The unbuilt Collaboration opt-in becomes a Proposal's **Discoverable**
> visibility setting, and that setting *does* permit listing the title and abstract in Discover,
> the larger disclosure §4 said would need its own consent. The manuscript stays unreadable and
> `visible_to()` is still not widened. Matching (§1, §2, §5–§7) is unchanged.

**Accepted** — 2026-09-19.

**Depends on** IR-281 for record-level vectors. Nothing here can be built before those exist.

**Touches [ADR-009](009-authorization-model.md)'s territory** without amending it: a Collaboration opt-in permits a notification, never a read. The visibility predicate is unchanged.

## Context

IRIS stores one vector per Record and never asks it a question. `RecordEmbedding` exists to be stage 1 of a *question* search; nothing compares one Record against another.

There is already a crude version of the idea shipped: `GET /records/<id>/similar/` seeds the Ask IRIS search with a Record's title and abstract and returns the top three. It matches keywords, so two submissions describing the same idea in different words never find each other.

**That endpoint calls `search_records`, which IR-285 deletes.** The caller lives outside `apps/ai` and was missed when IR-285 was written. This ADR is where it gets migrated rather than discovered when the build turns red.

### Two scoping facts that shape everything below

**Proposals are the subject of a check, not finished work.** A Proposal is work about to start, so a collaboration is still possible and a warning is still actionable. A completed thesis is done — telling someone to collaborate on it is pointless, and comparing finished work against finished work is a plagiarism question nobody asked for. `record_type == "Proposal"` is already a first-class decision in the codebase: it is what routing branches on to send a submission to adviser review rather than RDCO intake.

**Consent already exists in this system, and it is a different consent.** The disclosure gate reads `Record.dpa_accepted` — the per-submission Data Privacy Act stamp — to decide whether content may go to a commercial vendor.

## Decision

### 1. Only a Proposal is checked

A similarity check runs when a Proposal is submitted. Thesis / Research and Project Records are never the *subject* of one.

### 2. Two comparison directions, with different privacy profiles

| Direction | Catches | Consent |
|---|---|---|
| **Proposal → Proposal** | Two people proposing the same or adjacent thing right now — collaboration, and duplicate proposals at intake | **Required** |
| **Proposal → completed work** — a **Novelty check** | "Something close to this was finished here in 2023" | **None** |

**Proposal → Proposal is built first**, then the Novelty check.

That ordering is the project lead's call and is recorded with its cost: the Novelty check needs no consent, reads only the public catalogue, and could have shipped in days. Building collaboration first puts the consent model, its field, its migration and its submission-time question on the critical path before anything ships. The trade is accepted because collaboration is the capability actually wanted; the cost is that nothing lands early.

**Finished → finished is out of scope.** Comparing completed theses against each other is a plagiarism question, and a considerably more fraught one.

### 3. Collaboration consent is its own opt-in, never the DPA stamp

A new, explicit **Collaboration opt-in** on the Record (see `CONTEXT.md`).

Reusing `dpa_accepted` was rejected outright. Accepting terms for how a submission's data is processed and agreeing that strangers may be told your unsubmitted work exists are different acts, and someone may reasonably say yes to one and no to the other. Reusing the flag would silently opt in everyone who accepted DPA terms — consent nobody gave.

Inferring consent from pipeline status was also rejected: published work is already in Discover, so matching it adds nothing. The entire value is in-flight work, which is exactly what needs asking.

### 4. An opt-in permits an introduction, not a read

**This is the part that keeps the authorization model intact.**

A Collaboration opt-in does not make a Record readable, does not widen `visible_to`, and does not place the other party's Proposal anywhere the recipient can open it. What it permits is a **notification revealing one bounded fact**: that another opted-in proposer is working in a similar area, and who they are.

**The notification carries the other owner's identity and nothing about their content** — no title, no abstract, no extract. The two people take it from there, outside IRIS, as colleagues.

Consent to be *introduced* is a far smaller thing than consent to have your proposal *read*, and only the first is being asked for. Anything richer — surfacing a title or abstract — is a materially larger disclosure and would need asking for separately.

A match is only ever notified when **both** parties have opted in. One-sided matching is not a feature.

### 5. Similarity is computed from record-level vectors

One vector per Record, compared directly. Not chunk-level.

A record vector is built from title and abstract, so it answers "are these two Proposals broadly about the same thing?" It will **miss** the more interesting case: two Proposals on different topics that share a method — the same architecture on the same dataset, described in the middle of each document. That is the match most worth catching, for duplicate detection and as a collaboration lead both.

Chunk-level similarity is the follow-up that would catch it, and it is **deliberately not abstracted for in advance**. One implementation is a seam that is not yet real, and unlike ADR-027's Area source there is no evaluation that requires both to exist side by side. Build it when there is a reason.

**The value of that follow-up depends on an open question**: the RAG corpus is a single file per Record, `Record.abstract_file`. If that file is genuinely an abstract, a record vector already captures nearly all of it and chunk-level adds little. If it is a full proposal document, record vectors are blind to everything past the first page. Nobody has looked at a real one. This is the second decision in the RAG work that turns on that question, and it should be answered when IR-278 delivers records.

### 6. Notified at intake, recomputed on view

A match is computed when a Proposal is submitted and delivered as a **notification** — arriving unasked, at the moment routing already branches on Proposal, while intake review is happening. A reviewer who has to go looking will not.

The on-demand panel **recomputes**, because a similarity score shown months later is worse than none.

Delivery uses the existing notification machinery, which already models sender, recipient, record and type, and tracks reads.

### 7. The existing `similar/` endpoint migrates onto this

`GET /records/<id>/similar/` moves from keyword matching to record-vector similarity, and stops calling the module IR-285 deletes.

## Alternatives Considered

**Reusing `dpa_accepted` as collaboration consent.** Rejected — one flag doing two jobs, where the second job is disclosing unsubmitted research.

**Inferring consent from published status.** Rejected — it only ever matches work that is already public, so it delivers nothing.

**Novelty check first.** Recommended and not taken. Recorded above with its cost.

**Chunk-level similarity now.** Rejected as premature: it is more expensive, it requires deciding how to roll many paragraph matches into one score per Record, and its marginal value cannot be judged until someone has read a real Proposal.

**Surfacing the matched Proposal's title or abstract in the notification.** Rejected as a materially larger disclosure than the opt-in asks for.

**One-sided matching** — notify A about B when only A opted in. Rejected: the opt-in exists to protect B.

**Comparing finished work against finished work.** Out of scope.

## Decision Rationale

The through-line is that the mechanics were never the hard part — one vector per Record already exists, and the query is trivial. The hard part is that the useful version of this feature discloses someone's unsubmitted work, and the visibility predicate refuses that correctly.

An opt-in that permits an *introduction* rather than a *read* is what makes the feature possible without weakening the authorization model: the recipient learns that a person exists and is working nearby, which is what makes a collaboration happen, and learns nothing about the work itself.

## Consequences

- **Blocked on IR-281.** Unlike ADR-027's Research landscape, this needs vectors.
- The consent model is on the critical path, by the ordering chosen in §2.
- A new field on `Record` plus a migration, and a question at submission time. `Record` and the submission flow are thesis-critical territory, so this is the higher-risk half of the RAG backlog to touch.
- **IR-285's scope is larger than that ticket states.** `GET /records/<id>/similar/` calls the module it deletes. Either this work lands first, or IR-285 must migrate the caller itself.
- Duplicate-proposal detection falls out of the same query at no extra cost, and is arguably more valuable to CIT-U than the collaboration feature — two students proposing the same thing, caught before either starts.
- Record-level similarity will miss shared methodology across differently-titled Proposals. Stated so it is a known limit rather than a surprise.
- A Proposal whose owner has not opted in is never surfaced and never notified about. Low adoption means the feature rarely fires, which is correct and should not be engineered around.

## MVP Impact

Not MVP-required. Current-phase RAG work, thesis-critical per ADR-013's 2026-09-04 amendment.

## SaaS Impact

Matching is per-instance under [ADR-005](005-instance-per-tenant.md). A Proposal must never be matched against a Record in another tenant, and an opt-in is scoped to the instance it was given in.

## Security Impact

**This is the RAG feature with the largest disclosure surface, and the smallest amount of content disclosed.**

The opt-in does not widen `visible_to`; a matched Record stays unreadable. The notification reveals one bounded fact — that an opted-in person is working nearby — and never any content. Both parties must have opted in.

The Novelty check discloses nothing at all: it reads only completed work already in the public catalogue.

The failure to guard against is scope creep in the notification. "It would be more useful with the title in it" is true and is a different decision, requiring a different consent.

## Deployment Impact

None. No new services.

## Research Impact

Modest but real. A system that tells a proposer their idea was completed two years ago changes an outcome in a way a search box does not, and it is a concrete demonstration of the corpus being useful rather than merely searchable.

## Related Requirements

FR-M4 — stable label only, per the frozen-SRS rule.

## Related Tasks

IR-281 (record vectors — blocks this), IR-285 (deletes the module the existing endpoint calls), IR-278 (the corpus that would settle the record-versus-chunk question), IR-282 (chunk vectors, for the follow-up).
