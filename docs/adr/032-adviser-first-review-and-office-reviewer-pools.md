# ADR-032: Adviser-first review, office reviewer pools, record versions and lineage, and one capability-driven Paper View

## Status

**Accepted** — 2026-09-26, by **Lee Jasmin Adolfo** (project lead), after [PR #133](https://github.com/moisturicer/IRIS/pull/133) merged. Tracked on [IR-373](https://citiris.atlassian.net/browse/IR-373).

**The five design defaults are confirmed as part of acceptance.** They were marked as defaults in the Proposed draft; they are now decisions:

1. the record's Adviser must not be one of its owners (§1);
2. RDCO keeps *accept, keep unlisted* (§3);
3. the Proposal *complete* act is retired (§2);
4. one continuation per Proposal (§6);
5. the author takes part in the review discussion (§7).

**Amended 2026-09-26 (same day, project lead, IR-374 design session): §8 and §10.**

- **§8:** a Discoverable Proposal is listed only while `in_review`. Acceptance ends its listing and its collaboration matching.
- **§8:** the "Looking for" `collaboration_note` is dropped.
- **§10:** Ask IRIS is not part of Review mode.

Details are in the *Amendment* notes under §8 and §10. The original text is kept for the record.

**Amended 2026-10-06 (project lead, IR-411): §10 gains two capabilities**, `continue_draft` and `attach_file`. See the *Amendment* note under §10.

**Amended 2026-10-08 (project lead, IR-269): §4 and §10.**

- **§4** settles how an office's result is formed when it is routed more than once: the latest completed review round wins.
- **§4** settles that an office cannot finish while its own document request is open.
- **§10** settles when RDCO reads "Not required", and who sees the names of an office's reviewers.
- **§10 (IR-479, same day)** settles who reads review content at all: reviewer names and review comments are read by participants only.

See the *Amendment* notes under §4 and §10.

**Amended 2026-10-08 (project lead, IR-416): §5 and §13.** The manuscript was never a `RecordUpload`, so a version names the stored manuscript file directly. The server locks the manuscript once a record is submitted. Earlier versions are participants-only. The backfill records only what can be known. See the *Amendment* notes under §5 and §13.

**Amended 2026-10-08 (project lead, IR-272): §5.** Who may ask for a revision, one open request per party, what an open request blocks, and why *Changes requested* is derived rather than stored. See the *Amendment* note under §5.

**The new tickets in §14 are deliberately not created yet.** The project lead asked for them to wait for the frontend redesign specification, so the ticket architecture can be reconciled with it and no frontend work is specified twice or in conflict. The re-planned IR-255 subtasks carry the same hold on their frontend parts.

**Lee Jasmin Adolfo** (project lead) reopened the submission workflow on 2026-09-26 and settled it as a business decision. Every rule in §1–§9 comes from that session. Where the design had to fill a gap, the section says so and names the default it chose, so a reviewer can overturn that default without reopening the rest.

**Supersedes, in part:**

- **[ADR-021](021-reviewer-directed-routing.md).** The intake party (§1–§2), the Proposal authority rule "Adviser or RDCO decides and completes" (§3), the rule that RDCO is a mandatory gate for Thesis/Research and Project (§3, §10), and party-only assignment are all replaced. ADR-021's assignment/routing/resubmission machinery (§4, §6, §8, §11, §12, §14) is **kept** and builds on what is already in `main`.
- **[ADR-029](029-proposal-similarity-and-collaboration.md) §3–§4.** Its unbuilt "Collaboration opt-in" becomes the **Discoverable** visibility setting (§8). That setting permits Discover to list a Proposal's title and abstract, which is the larger disclosure ADR-029 §4 said would need its own consent. §8 is where that consent is asked for.
- **[ADR-018](018-conditional-parallel-office-routing.md).** Its requested-office booleans, which ADR-021 had already reduced to "a suggestion to triage", no longer have a triage step to feed. From here on they are the Adviser's hint (§3).

**Unchanged:** [ADR-002](002-workflow-transition-table.md) as amended by 021 · [ADR-003](003-clearance-aware-resubmission.md) · [ADR-004](004-restart-all-comparison-mode.md) · [ADR-022](022-explicit-document-requests.md), except that "intake" disappears from its list of requesting parties · [ADR-009](009-authorization-model.md), which gains predicates in §10.

### What is already built, and what this invalidates

These IR-255 slices are merged and **stay**:

- IR-256: tables and vocabulary
- IR-257: shadow dual-write
- IR-258: tracker
- IR-259: frontend reads the workflow
- IR-262 and IR-263: document requests
- IR-265, IR-266, IR-267 and IR-264: prefactors

`RecordAssignment`, `RoutingEvent`, `ResubmissionRequest` and `DocumentRequest` are the foundation this ADR builds on.

The **unbuilt** subtasks were written against ADR-021 and need re-planning before anyone picks them up:

- IR-261 (route)
- IR-268 (queues)
- IR-269 (clear / finding / hand-back)
- IR-270 (RDCO decides)
- IR-271 (Proposal decision)
- IR-272 (request resubmission)
- IR-273 (resubmit and reset)
- IR-260 (cutover)
- IR-274 (delete the old pipeline)

§14 maps each one.

## Context

ADR-021 put every Thesis/Research and Project through an **Intake & Triage** step run by RDCO staff, and made RDCO the mandatory decider for both types. Two things were wrong with that as a description of CIT-U.

**The Adviser is the person who actually knows the work.** Triage by RDCO staff meant someone who had not read the paper decided which specialist offices should read it. The Adviser has read it, and is the one who can tell "this has a patentable mechanism" from "this is an ordinary capstone".

**Most records never need an office.** An ordinary thesis with no IP, ethics or commercialisation concern would have gone through intake and RDCO anyway. That meant two extra hand-offs, and RDCO staff time, spent confirming there was nothing to look at.

The session also surfaced four needs that ADR-021 never modelled:

1. **Offices are staffed by several people.** `RecordAssignment` is per *party*, so "ITSO has it" could not say *which* ITSO member is responsible, and two ITSO members could not both be asked.
2. **Revisions need to be browsable as versions.** `RecordUpload.version` numbers files per slot. Nothing ties "the manuscript as it stood when IERC asked for changes" to IERC's review.
3. **An accepted Proposal becomes a Thesis or Project**, and that relationship has nowhere to live.
4. **Proposals are a collaboration surface.** Students want to find each other by proposal, which ADR-021 §13 had removed from Discover entirely.

## Decision

### 1. Every record enters with its Adviser. There is no intake party.

```
Party = adviser | itso | ierc | ktto | rdco
```

`intake` is **retired**. Nothing new is assigned to it, routed to it, or asked for changes by it. The stored rows that hold it are history, and IR-260's migration handles them (§13). `ENTRY_PARTY` becomes `adviser` for every record type.

**The record's Adviser must not be one of its owners.** Nobody reviews their own submission. A faculty member who submits their own Thesis or Project names a different faculty member as its Adviser. *Confirmed at acceptance. It was not stated in the session; it exists because, without it, "faculty upload" plus "Adviser may publish" (§3) lets a person publish their own work unreviewed.*

### 2. Proposal

| Adviser action | Result |
|---|---|
| **Request revision** | `ResubmissionRequest` opened. The owner uploads a new **version** of the *same* record (§5). |
| **Reject** | `rejected`, shown as **Archived**. Terminal. To try again, the student submits a new Proposal. |
| **Accept** | `approved`, shown as **Accepted**. The owner may now **continue it as a Thesis or a Project** (§6). |

- **The Adviser alone decides a Proposal.** RDCO has no Proposal role, and specialist offices are not routed on Proposals.
- **The "complete" act is retired.** Before, `approved → completed` meant "research finished". That meaning now lives in the child record (§6), so `approved` is a Proposal's resting state. Existing `completed` Proposals keep their value, and nothing new writes it.

### 3. Thesis / Research and Project

The Adviser makes two decisions in one review.

**Academic:** request revision · reject (`rejected`, Archived, terminal) · accept.

**On accept, whether specialist review is needed:**

| Choice | Result |
|---|---|
| **Accept & publish** | No specialist review. `published`, and the record appears in Discover. **RDCO is never involved.** |
| **Accept & route** | The Adviser picks one or more of ITSO / IERC / KTTO and gives a reason. They may also nominate a reviewer for each office (§4). The Adviser's assignment completes. The record stays `in_review`. |

The ADR-018 office booleans on the submission form are shown to the Adviser as the author's hint ("the author flagged possible IP"). They route nothing by themselves.

**RDCO enters only on the specialist path.** When the last active specialist assignment completes (ITSO, IERC or KTTO, however many rounds of routing it took), IRIS opens an RDCO assignment in RDCO's pool. This is ADR-021 §10's hand-back, now fired only when an office was involved. **Nobody routes to RDCO by hand**, which is what "until all reviewers agree, it can only then go to RDCO" means mechanically.

**RDCO's actions:**

- request revision
- reject (Archived)
- **accept & publish**
- **accept, keep unlisted** (`completed`)
- route to an office for further review

*"Keep unlisted" is kept from ADR-021 and was not raised in the session. It is kept because the specialist path exists largely for IP concerns, and a record ITSO flagged as patentable may need to be accepted without being published before a filing. Confirmed at acceptance.*

**Specialist offices never reject and never publish.** This is unchanged from ADR-021 §7.

### 4. Office ≠ reviewer: assignments have seats

A party's `RecordAssignment` says **"this office has the record"**. A new row, the **seat**, says **"this person is reviewing it for that office"**.

```
NEW  ReviewerSeat   assignment (FK RecordAssignment), reviewer (FK User),
                    state ∈ assigned | in_review | done | withdrawn,
                    source ∈ entry | claimed | assigned | nominated | added,
                    assigned_by, assigned_at, opened_at, done_at
                    at most one non-withdrawn seat per (assignment, reviewer)
```

**How a seat is created, by party:**

| Party | How a seat is created |
|---|---|
| **Adviser** | Automatically for `record.adviser` when the record is submitted (`source=entry`). |
| **ITSO / IERC / KTTO / RDCO** | A routed record lands in the office's **pool**, as an active assignment with no seat. Then one of: a member of that office **claims** it; an **office coordinator** **assigns** a member; or the router had **nominated** a member when routing. |

**Who counts as an office member, and who is a coordinator.** A member is a user whose role staffs that party, as today. A coordinator is a member with `User.is_office_coordinator = true`, granted by a system administrator. Coordinators may assign, reassign and withdraw seats **within their own office only**.

**Adding a reviewer.** A seat holder may **add a reviewer** from their *own* office (`source=added`). That is a different act from **routing to another office**, and the UI keeps them as two separate actions. There is never one ambiguous "Reroute" button.

**When an office's assignment completes:** it has at least one seat, every non-withdrawn seat is `done`, and that office has no open `ResubmissionRequest`. The office's `RecordClearance` then carries its finding. Each seat's verdict stays its own `Review` row.

**Opening a review** moves a seat from `assigned` to `in_review` and stamps `opened_at`. This is the GitHub-style "start review" moment the queue tabs (§9) and the timeline (§7) show. It also gives IR-144 a real start time for time-on-task.

**Routing graph.** `route()` is unchanged from ADR-021 §6 except for its targets:

| From | May route to |
|---|---|
| `adviser` (on accept) | `itso`, `ierc`, `ktto` |
| `itso` / `ierc` / `ktto` | the other two offices |
| `rdco` | `itso`, `ierc`, `ktto` |

Nothing routes to `adviser` or `rdco`. Routing to an office that already has an active assignment opens nothing new. With a nomination, it adds a seat. **An existing `cleared` clearance is never reset by routing** (ADR-021 §6, kept).

**Amendment, 2026-10-08 (project lead, IR-269): an office's result, and when it may finish.** Settled in a design grilling.

- **A review round** is one office's assignment, from routing until it completes. An office routed the same record again starts a new round.
- **The latest completed round wins, in both directions.** While a new round runs, the earlier `cleared` or `not_cleared` stands, and routing never resets it. When the round completes, its outcome replaces the clearance: `not_cleared` if any seat in *that* round recorded a finding, `cleared` otherwise.
    - *Rejected:* making a first clearance permanent. A finding from a second look would then never reach RDCO.
    - *Rejected:* refusing to route to an office that already finished. That contradicts the routing graph above.
- **The clearance row records the office's outcome only.** Each seat's verdict, and its reason, is that seat's own `Review`.
- **An office cannot finish while its own `DocumentRequest` is open.** Both Clear and Record finding are refused until that office withdraws the request or it is settled. A record must never read "awaiting document" after the office that asked has finished. This narrows the completion rule above; it adds no state.
- **Clear and Record finding need an opened seat.** A seat still `assigned` is refused, so `opened_at` is always set for time-on-task.
- **The hand-back (§3) fires whenever the last specialist office completes.** That includes completion by a coordinator withdrawing the last unfinished seat. If RDCO already holds the record, nothing new opens. An office whose seats were *all* withdrawn has not completed: it returns to its pool.

### 5. Versions

```
NEW  RecordVersion   record, number (1, 2, 3…), manuscript (FK RecordUpload),
                     created_by, created_at,
                     cause ∈ submission | revision
                     unique (record, number)
EXT  Review          + version (FK RecordVersion, nullable for rows written before this)
```

- **v1 is written when the record is first submitted.** Each resubmission writes the next version and resolves every open `ResubmissionRequest` (ADR-021 §11).
- **A version is a snapshot of what was under review, not a file slot.** `RecordUpload.version` keeps numbering files. `RecordVersion` points at the manuscript upload that was current at that moment.
- **What "changed" means.** ADR-021 §11 counts a metadata-only revision as a change. Such a revision writes a version whose `manuscript` is the same upload as the version before it. The version is still recorded, because a reviewer asked for it.
- **Clearance-aware resubmission is unchanged**, and this is the thesis contribution:
  - Only the parties that requested the revision have their clearance reset (under `CLEARANCE_AWARE`), and only their seats return to `in_review`.
  - Every other party's `cleared` clearance and `done` seat survive.
  - If RDCO requests a revision, only RDCO re-reviews. An Adviser-stage revision returns to the Adviser alone.
- The Paper View's **version picker** opens that version's manuscript. The review timeline marks which version each review and comment was made against.

**Amendment, 2026-10-08 (project lead, IR-416): what a version points at, who sees it, and what writes one.** Settled in a design grilling.

- **The manuscript is not a `RecordUpload`.** It is `Record.abstract_file`, one file field replaced in place, with no history. The `manuscript (FK RecordUpload)` above, and "`RecordUpload.version` keeps numbering files" as a description of the manuscript, assumed otherwise. **`RecordVersion.manuscript` is a file field naming the stored manuscript file** current when the version was written. It is **nullable**, because the server has never refused a submission with no manuscript, and this ticket adds no such rule.
    - Each upload is stored under a fresh random name, so a later upload never touches a file an earlier version names. **No code may delete a manuscript file that a version still names**, and a test pins that.
    - *Rejected:* copying the file into version-owned storage. That doubles storage for no gain the shared name lacks.
    - *Rejected:* moving the manuscript into `RecordUpload` under a slot. It would rewrite the manuscript extraction, chunking, `/manuscript/`, `load_corpus` and the serializers for a field nobody needs moved.
- **The server locks the manuscript once a record is submitted.** A request that replaces `abstract_file` is refused (400, naming the status) unless the record is a `draft`, or a legacy `declined` until IR-274. IR-273 adds `awaiting_resubmission`. Staff are not exempt. Correcting a published paper's file would be a deliberate act of its own, not an edit. Other detail fields are the `edit_details` capability's concern, not this rule's.
- **One function writes every version**, called by:
    - the legacy `POST /records/<id>/submit/` (v1, `submission`);
    - `routing.enter_at_adviser()` (v1, `submission`);
    - the legacy `resubmit_record()` (the next version, `revision`);
    - IR-273's resubmission.

  So every record submitted from today on has an accurate history. IR-274 deletes the legacy call sites with the rest of the old pipeline.
- **A review records the latest version when it is written**, wherever it is written:
    - the legacy services;
    - Clear and Record finding (IR-269);
    - accept & route (IR-261).
- **Earlier versions are review material** and follow IR-479's rule, `may_read_review`. A participant gets the version list in the record payload, the picker, and `GET /records/<id>/versions/<n>/manuscript/`. Anyone else gets no list and a 404, and reads the current manuscript as before. Serving a version is audited as a `DOWNLOAD` carrying the version number.
- **The picker renders only when a record has two or more versions.** There is nothing to choose between with one.
- **Opening an earlier version** sets `?version=N` and shows "You are viewing vN of M · Back to current". Citation highlights are off while an earlier version is open, because their coordinates are the current manuscript's (ADR-031). Paper Chat says it answers about the current version. Earlier versions are not indexed.
- **The timeline** shows each version as its own entry ("v2 submitted"), and tags each review with `Review.version`. Nothing else is tagged from timestamps. A comment's version is IR-419's (`ReviewComment.version`).
- **Settled, built in IR-273:** a non-owner's "current" manuscript is the latest version's, and an owner sees their unsubmitted upload, labelled as such. Until then, the gap exists only while a legacy record is `declined`, when no reviewer is acting.

**Amendment, 2026-10-08 (project lead, IR-272): asking for a revision.** Settled in a design grilling.

- **Who asks.** A holder of an **opened** seat (`in_review`), as that seat's party, on a record on the new model. An unopened seat is refused with "Open the review first", as Clear and Record finding are (§4 *Amendment*). The reason is required and shown to the owner as plain text.
- **One open request per party, not per person.** A second reviewer from an office that already asked is refused and pointed at the existing request. Their point belongs in the review discussion (§7). This is ADR-022's "party, not person".
- **What an open request blocks.**
    - While **any** request is open, every *decision* is refused: accept & route today; accept & publish, keep unlisted, reject and the Proposal decisions when IR-270 and IR-271 build them, through the same predicate.
    - While an office's **own** request is open, every seat of that office is refused both Clear and Record finding. This mirrors the §4 *Amendment*'s document-request rule, and narrows the completion rule, which already waits on it.
    - **Other offices may still clear and record findings.** Their outcome then survives the new version, which is exactly what clearance-aware resubmission preserves.
    - Routing and document requests still work.
    - *Rejected:* refusing every Clear while any request is open, as the ticket first read. It splits `office_review` in two and refuses an outcome ADR-003 would preserve anyway.
- **"Changes requested" is derived, not stored.** A party with an open request is shown as *Changes requested*, and `RecordClearance` is left alone. Writing `declined` to it would overwrite an earlier completed review round's outcome while the office has not completed, and the Adviser and RDCO have no clearance row at all. IR-273's resubmission resets the requesting parties' clearances.
- **The version a request was made against** is its `Review`'s version. That `Review` is required and cannot be deleted from under the request, so no column is added.
- **Withdrawal.** Any seat holder of the requesting party may withdraw its open request. No reason is asked for. The owners are told, and the tracker keeps the request as `withdrawn`.
- **Notifications** go to every owner, and to nobody else. Reviewers see the *Waiting on author* badge (§9).

**Amendment, 2026-10-08 (IR-273): answering with a new version.** Built to the card and to the IR-416 hand-off above. The points the card left open were decided in the implementation and are **pending the project lead's review** on the IR-273 pull request.

- **The act.** `POST /records/<id>/new-version/`, by an **owner** only. A reviewer who can see the record gets a 403; anyone else gets a 404. It needs a record on the new model with at least one open request. It writes v(n+1) through the one writer, resolves **every** open request as `resubmitted`, and records `resubmission_count` and `last_resubmitted_at`, so `preserved` is derived exactly as on the legacy path.
- **What resets.** Under `CLEARANCE_AWARE`, only the requesting parties' clearance rows go back to pending. Under `RESTART_ALL`, every row does.
    - Seats are the same under both policies, which is the card's "the two policies differ only in which clearances reset". Every `done` seat on a requesting party's active assignment returns to `in_review`, so an office whose second reviewer asked re-reviews the new version in full. Nobody else's seat changes.
    - *Consequence, for review:* under `RESTART_ALL`, an office that had already completed keeps its completed assignment, and its pending clearance is re-cleared only if it is routed again. If the comparison arm should instead reopen those offices, that is a change to this rule.
- **What counts as a change** since the **newest** open request:
    - a manuscript other than the latest version's;
    - a supporting document an owner uploaded (`RecordUpload`);
    - a detail that actually changed. That is the new `Record.details_edited_at` (`records/0016`), stamped only when a PATCH changes a value, so saving identical details answers nothing.

  Otherwise the act is refused, naming who asked and what would count.
- **The manuscript lock** also opens while `awaiting_resubmission` (new model, a request open), **for an owner only**. Staff stay locked.
- **Which manuscript is current.** Between the owner's upload and their new version, `/manuscript/` serves everyone but an owner the latest version's file. An owner reads their own upload, and record detail's `manuscript_unsubmitted` labels it. Paper Chat and chunking still read the stored file. That is the AI pipeline's, flagged to its owner, not changed here.
- **Notifications** go to the open seat holders of the requesting parties, in-app, and to nobody else.

### 6. Lineage: an accepted Proposal continues as a new record

```
EXT  Record  + derived_from (FK Record, nullable, unique)
```

- **Continue as Thesis / Continue as Project** is available to an owner of an `approved` Proposal. It creates a new `draft` record of the chosen type with `derived_from` set to the Proposal. It pre-fills title, abstract, keywords, classification, owners and Adviser, all editable. The owner then uploads the full manuscript and submits it, and the new record enters with its Adviser (§1) as any other record does.
- **The Proposal is never mutated.** Its versions, reviews and discussion stay on it.
- **The two records point at each other.** The Thesis shows *"Developed from Proposal #123 — View proposal"*. The Proposal shows *"Continued as Thesis #456"*.
- **One continuation per Proposal.** That is what `unique` enforces. *Confirmed at acceptance. A Proposal that genuinely splits into two outputs would need the constraint lifted, and nothing else would change.*
- **Direct submission still exists.** A Thesis or Project can be submitted with no Proposal behind it. It then has no origin, and nothing else differs.

### 7. Two discussions, never mixed

| | Review discussion | Public discussion |
|---|---|---|
| **Model** | `ReviewComment` (record, author, body, version, reply_to, created_at, edited_at) | `PublicComment` (record, author, body, reply_to, created_at, hidden_by, hidden_at) |
| **Who reads and writes** | The record's owners, plus every user who has ever held a seat on it | Any signed-in user |
| **On which records** | Every submitted record | `published` records and Discoverable Proposals (§8) only |
| **Shown as** | One **timeline** interleaving comments, versions, seat openings, reviews and findings, routing, document requests, and resubmission requests and their resolution. The shape of a GitHub pull request. | A flat thread under the paper |

- **The author takes part in the review discussion.** It is their pull request. *Confirmed at acceptance. If an office later needs notes the author must not see, that is a third, reviewer-only channel, not a visibility flag on this one.*
- **The timeline is derived** from the rows that already exist plus `ReviewComment`, the same way the tracker is (ADR-021 §14). Nothing is duplicated into an event table.
- **Public comments are moderated by hiding, not by deleting.** Owners and system administrators can hide a comment.

### 8. Discover: research, and Discoverable Proposals

**Research** lists `published` Thesis/Research and Project records. It is unchanged, and `PUBLICLY_VISIBLE_STATUSES = (PUBLISHED,)` stays.

**Proposals** is a separate section of the same page:

```
EXT  Record  + proposal_visibility ∈ private | discoverable   (default private)
             + collaboration_note (text — "Looking for: an ML collaborator")
```

- **The owner sets it** at submission or at any time after. It is meaningful for Proposals only.
- **A Discoverable Proposal is listed** while it is `in_review` or `approved`. It is never listed as a draft or once rejected.
- **What a stranger sees is a summary, not a read:** title, abstract, classification, authors' names, the collaboration note, and an unmistakable **"Proposal · In development — not institutionally approved research"** label.
- **The manuscript, versions, reviews and review discussion stay private.** For a stranger, `GET /records/<id>/`, the manuscript and the tracker all still 404. Public discussion (§7) is open on the summary.
- **Ask IRIS never retrieves or cites a Discoverable Proposal for a non-participant.** Retrieval reads `visible_to()`, which this ADR does not widen.

**This is a second read path, on purpose.** The CLAUDE.md rule is "visibility is one predicate used everywhere, so a citation can never point at an unreadable record". `visible_to()` stays that single predicate for **reading a record**. `Record.objects.discoverable_proposals()` grants something narrower, a **summary card**, and only through `ProposalSummarySerializer`, which has no file, version or review fields. The rule's purpose still holds, because nothing that cites or opens a record reads the summary path. Tests pin both halves (§12).

**Amendment, 2026-09-26 (project lead):**

1. **A Discoverable Proposal is listed only while `in_review`.** An Adviser's acceptance (`approved`) takes it off Discover and out of collaboration matching, because an accepted proposal is no longer open for collaboration. This replaces "while it is `in_review` or `approved`" above.
2. **No `collaboration_note`.** The "Looking for" field is dropped from the model, Publish, Edit details and the summary. The summary is title, abstract, classification, authors' names and the *Proposal · In development* label.
3. **Closing collaboration early** is done by switching the Proposal back to Private. There is no separate toggle.
4. **The Discoverable control's own text is the consent:** *"Other IRIS users can see your title, abstract and names, and IRIS's AI will compare your proposal with other open proposals to suggest collaborators."* It covers both visibility and AI matching, and remains subject to IR-250's disclosure policy. The matching rules are amended in ADR-029.

**ADR-029's consent is this setting.** Marking a Proposal Discoverable is the explicit, separate consent ADR-029 §3 required. It is never inferred from `dpa_accepted`. It also covers ADR-029's collaboration matching, so there is one opt-in, not two.

### 9. Review queues: **To review · In review · Done**

"My Reviews" replaces "Awaiting me / Cleared / Sent back". It lists **your own seats only**. Nobody sees another reviewer's queue, with one exception: coordinators see their own office's.

| Tab | Contains |
|---|---|
| **To review** | Your seats in `assigned`, not yet opened. **For office members, also your office's unclaimed records**, each marked *Unassigned* with **Claim review**. Coordinators additionally get **Assign reviewer** on them. |
| **In review** | Your seats in `in_review`. A record waiting on its author carries a *Waiting on author* or *Waiting on document* badge (derived from open `ResubmissionRequest` or `DocumentRequest` rows) and stays in this tab. |
| **Done** | Your seats in `done`, as your decision history. |

**Why these are not outcome tabs.** Rejected, Cleared and Archived are outcomes, not work, so they are filters on Done. They are not tabs.

### 10. One Paper View, driven by capabilities

There is **one** Paper View. There is no per-role page.

The record detail payload carries a **`capabilities`** list, computed by `core.permissions` for the requesting user. Examples: `create_version`, `continue_as`, `set_visibility`, `open_review`, `request_revision`, `request_document`, `route`, `add_reviewer`, `claim`, `assign_reviewer`, `record_finding`, `decide_proposal`, `accept_publish`, `accept_route`, `final_decide`, `comment_review`, `comment_public`, `cite`.

- **The frontend renders what the list contains and never compares role names.** Every action endpoint re-checks the same predicate, so the list is a rendering hint and **the server stays authoritative**.
- **New predicates in `core.permissions`:**
  - `holds_seat(user, record, party)`
  - `is_office_member(user, party)`
  - `is_office_coordinator(user, party)`
  - `is_record_participant(user, record)`, meaning an owner or anyone who has ever held a seat. It gates the review discussion and the timeline.

**What each mode of the Paper View shows:**

| Mode | Who sees it | What it shows |
|---|---|---|
| **Reading** | Anyone who can read the record | Paper, abstract, Cite, Save, public discussion, lineage links |
| **Author** | Owners | Reading, plus the version picker, **New version** (when a revision is requested), the Action Required panel (ADR-022), **Continue as…** (on an accepted Proposal), visibility, and the review timeline read/reply |
| **Review** | Seat holders, after **Open review** | The paper beside the review timeline (*amended 2026-09-26: no Ask IRIS here; it stays on the Paper tab, IR-372*), the party status strip (Adviser ✓ · ITSO ● · IERC ● · KTTO — · RDCO ○), and an action bar built from `capabilities` |
| **Summary** | Strangers on a Discoverable Proposal | The §8 summary and public discussion. No PDF. |

**Amendment, 2026-10-06 (project lead, IR-411): two more capabilities.** The list above is examples, not a closed set; these two are named so the capabilities payload (IR-418) sends them and the frontend never derives them itself once it does:

- **`continue_draft`**: an owner reopens their own `draft` in Publish. Granted to an owner of a draft only.
- **`attach_file`**: an office files a supplementary file of its own on a record it takes part in, and may remove one. It complements ADR-022's document requests: a request asks the owner for a document, an attachment is the office's own. Until IR-418 the frontend adapter derives it from the office role (the server's `IsStaff`), as it does `tag_ip`.

**Amendment, 2026-10-06 (project lead, IR-474 and IR-476): what "of its own" and "takes part" mean for `attach_file`.** Settled in a design grilling and built in IR-474 (attach) and IR-476 (remove):

- **Taking part** is an active assignment the user can staff (`tracker.requestable_parties`). A completed assignment grants nothing.
- **A file belongs to an office, not a person.** `RecordFile.party` records the office that filed it, the same "party, not person" rule as a document request. RDCO always files as `rdco`, never `intake`.
- **Removing a file** takes both: the file's party is one the user can staff, and the user's office is taking part right now. Another office's file, or a file on a record the office no longer takes part in, is refused.
- **Owners do not remove office attachments.** An office's file is part of its review record.
- **The escape hatch is Django admin, superuser only.** It removes the stored file and writes an audit event. There is no API override, for RDCO or anyone. A row with no party (one backfilled from an uploader who was gone or not an office) can be removed only there.
- **The screen follows the server.** Each file carries a server-computed `can_remove`, and Paper View offers Remove only where it is true.
- **Refusals follow ADR-022 §Amendment 4:** 404 for a file that does not exist or is on a record the caller cannot see, 403 for one they can see but may not remove.
- **Out of scope:** KTTO filing on a published record (for example a patent receipt). If needed, it becomes its own capability.

**The party status strip** follows ADR-021 §14, with two changes. The Intake row is gone. The RDCO row reads **"Not required"** on a record no office was routed to, instead of "awaiting".

**Amendment, 2026-10-08 (project lead, IR-269): the strip, settled in a design grilling.**

- **"Not required" applies whenever no specialist office has ever held the record.** That includes a Thesis still with its Adviser, because nothing waits on RDCO there. The row reads "Waiting" from the moment an office is routed to.
- **Per-seat detail is shown to participants only** (`is_record_participant`: the owners, and anyone who has ever held a seat). Who is reviewing is review-discussion information (§7). Anyone else who can see the record sees the strip without names. *Widened by the IR-479 amendment below to `may_read_review`, which also admits a member of an office holding the record now.*
- **An office reviewing again** shows its earlier outcome beside the new round, as in *"Cleared (earlier review) · reviewing again"* (§4 *Amendment*).
- **Clear and Record finding share one capability, `office_review`,** and `add_reviewer` stays its own. The key was renamed from `record_finding` so that it does not grant a "Clear" it does not name.

**Amendment, 2026-10-08 (project lead, IR-479): who reads review content.** Settled in a design grilling, after IR-269 found the gap.

- **Reviewer names and review comments are internal workflow data.** Reading the record is not enough to read them: every office member reads every record, and every signed-in user reads a published one.
- **One predicate decides it, `may_read_review(user, record)`.** It is true for:
    - an owner;
    - anyone who has ever held a seat on the record (`is_record_participant`);
    - a member of an office whose assignment on the record is **active now**, its pool included. A reviewer needs the history before claiming, and on the legacy pipeline one decides straight from the pool.
- **What it gates:**
    - on record detail: `reviews`, and each clearance's comment and signer;
    - on the tracker: `reviews`, the per-seat detail, each resubmission request's reason and who asked for it and who closed it, who routed the record and why, and who opened each current assignment.
- **What everyone else gets:** each gated field is `null`, meaning not disclosed. Every outcome stays visible: where the record went, each party's state and result, and `workflow_state`.
- **No role reads it everywhere, RDCO included.** An audit goes through Django admin, superuser only, the escape hatch the 2026-10-06 amendment above already uses.
- **Document requests keep their own rule** (ADR-022 §Amendment 5, `may_read_requests`). That rule admits every member of any office that *ever* took part. The two differ on purpose:
    - an office's request to the author is its office's ongoing business;
    - one reviewer's candid comment is not the business of every colleague who later joins.
    
    Aligning them would reopen ADR-022, so it was not done here.

### 11. Lifecycle

`pipeline_status` stores:

| Value | Meaning |
|---|---|
| `draft` | not yet submitted |
| `in_review` | in the workflow |
| `approved` | an accepted Proposal (resting state) |
| `published` | in Discover |
| `completed` | a Thesis/Project accepted by RDCO and kept unlisted |
| `rejected` | Archived |
| `pending_delete` | awaiting a delete decision |

`workflow_state` (derived, from ADR-021 §4, with intake removed) is the first rule that matches:

1. `awaiting_resubmission`
2. `awaiting_document`
3. `submitted`: the Adviser's seat is not yet opened
4. `final_review`: RDCO holds the record
5. `in_review`

A decision still closes the record's other open work (ADR-021 §12). A decision is still refused while any resubmission request is open.

### 12. Tests that pin the decisions

Each rule above has a test at the REST seam Lee confirmed for IR-255:

- A Thesis that the Adviser accepts and publishes is `published` with **no** RDCO assignment ever created.
- A Thesis routed to ITSO + IERC gets an RDCO assignment only after **both** complete, and never after only one.
- An office assignment with two seats does not complete until both are `done`.
- A member of another office cannot claim.
- A non-coordinator cannot assign.
- Clearance-aware: IERC requests a revision after ITSO cleared. The new version resets IERC only, and ITSO's clearance and seat survive. Under `RESTART_ALL`, both reset.
- Continuing a Proposal creates a linked `draft`, leaves the Proposal byte-identical, and refuses a second continuation.
- A stranger gets the summary of a Discoverable Proposal, a 404 on `/records/<id>/` and on its manuscript, and **no** Ask IRIS citation of it.
- A non-participant gets a 404 on the review timeline. A participant who is not an owner sees it.
- An owner who is also named as Adviser is refused at submission.
- `capabilities` for each role × state matches the action endpoints' own refusals. This is one table-driven test, so the rendering hint cannot drift from the authority.

### 13. Migration

The migration is additive first, following ADR-021 §7's expand/contract plan.

- **New tables:** `ReviewerSeat`, `RecordVersion`, `ReviewComment`, `PublicComment`.
- **New fields:** `Record.derived_from`, `proposal_visibility`, `User.is_office_coordinator`, `Review.version`. (`collaboration_note` was dropped by the 2026-09-26 amendment to §8.)

**The backfill:**

- **Seats.** One seat per existing active assignment. It goes to `record.adviser` for Adviser assignments, and to the most recent reviewer of that party where one exists. Otherwise it is left seatless, which puts it in the pool.
- **Versions.** v1 per submitted record, from its current manuscript upload. Older uploads become earlier versions only where their dates bracket a recorded resubmission. Nothing is invented.

**Amendment, 2026-10-08 (project lead, IR-416): the version backfill.** No older manuscript is recorded anywhere (§5 *Amendment*), so the "older uploads" clause can never apply. The backfill is, per non-draft record:

- **never resubmitted** (`resubmission_count = 0`): one **v1**, `submission`, naming the current manuscript;
- **resubmitted k times**: one version numbered **k + 1**, `revision`, dated `last_resubmitted_at`, naming the current manuscript. No v1…vk rows are made up, so that history starts at v(k + 1), and the next resubmission writes v(k + 2).

The rules that apply to both:

- Records made by import, seed or `load_corpus` get a version with no `created_by`.
- A record with no manuscript gets a version with none.
- **Every existing `Review.version` stays null**, as IR-257 left `Review.assignment`. Dating a review against a reconstructed version would invent the link.
- **In-flight records at `intake`.** Where the record has an Adviser, an Adviser assignment is opened and the intake assignment is withdrawn with reason "ADR-032: intake retired". Records **without** an Adviser are listed by a management command for a person to assign. They are never guessed.

## Alternatives Considered

**Keep Intake & Triage and add the Adviser in front of it.** Rejected. Two gatekeepers would both have to decide which offices are needed, and the one who has read the paper would be overruled by the one who has not.

**RDCO decides every Thesis/Project, even with no specialist review.** Offered to the project lead and not chosen. It keeps a single institutional gate on Discover, at the cost of an RDCO hand-off on every ordinary thesis.

**Route to a named person only, with no office pool.** Offered and not chosen. An Adviser rarely knows who at ITSO should look, and a pool with claim/assign matches how offices already share work. Nomination keeps the named-person path for the Adviser who does know.

**Add a reviewer FK to `RecordAssignment`, with one row per person.** Rejected. "The office has it but nobody has claimed it" becomes a row with a null reviewer that competes with the per-(record, party) uniqueness, and "ITSO's clearance" would be spread over several rows. Seats keep the office-level fact and the person-level fact apart, as ADR-021 kept assignment apart from clearance.

**Mutate a Proposal into a Thesis.** Rejected. It destroys the Proposal's own review history, and "the Proposal was accepted" stops being a fact that can be shown.

**Copy the Proposal's history into the Thesis.** Rejected. It duplicates facts and would drift. A link is enough.

**Make a Discoverable Proposal fully readable.** Offered and not chosen. The idea is not yet protected, and the manuscript is where the IP is. A summary is enough to start a collaboration.

**Role-keyed pages** (`AdviserPaperView`, `ITSOReviewView`…). Rejected in the session. With six roles and several states the pages would drift, and a role name says less than "can this user do X to this record now".

**Show the review discussion to reviewers only.** Not taken as the default (§7). The author has to answer the review, and one shared thread is what a pull request is.

## Decision Rationale

The session's central correction: **the person who has read the paper decides whether anyone else needs to.** The Adviser becomes entry point, academic reviewer and router. Specialist review happens because a reader saw a reason, not because a record type prescribes it, and RDCO's scarce time goes only to records that actually raised an institutional question.

Everything else follows from taking that seriously at CIT-U's real staffing. An office is several people, so seats. A revision is something you want to look back at, so versions. A proposal grows into a thesis, so lineage. Once the actions available depend on seat, party, state and ownership together, a role name cannot drive the UI, so capabilities.

What is kept matters as much. Assignment, routing, resubmission requests and clearance-aware reset are already built, and they carry ADR-003's contribution. This ADR changes who enters, who decides and who sits in a seat. It does not change how a revision preserves peer clearances.

## Consequences

**Positive:**

- An ordinary thesis goes Adviser → Discover with one reviewer and no hand-off.
- Offices are only asked when there is a reason, and a named person is responsible for every open seat.
- Revisions are browsable, and every review says which version it judged.
- Proposal → Thesis history survives without copying.
- The collaboration feature gets a real, consented surface.
- One Paper View, one permission source.

**Negative:**

- **Adviser authority grows.** An Adviser can now publish a Thesis to the institutional catalogue alone. The only checks are the rule that the Adviser is not an owner (§1), and the record's full history.
- **New models and a second read path.** Four new models, five new fields, and a summary read path that must be kept narrow deliberately.
- **Re-planning.** IR-255's unbuilt subtasks need re-planning (§14), and the IR-259 tracker work needs its Intake row removed.
- **A record can still bounce between offices indefinitely**, as ADR-021 recorded.

**Risk.** Adviser-only publication makes a stale or absent Adviser a blocker for the whole record. There is no triage fallback. A coordinator-level "reassign Adviser" is not in this ADR, and the first time an Adviser leaves mid-review is the trigger to add it.

## MVP Impact

The following are **workflow, and thesis-critical**:

- adviser-first entry
- seats, pool, claim and assign
- versions
- lineage
- the capability-driven Review mode
- the review timeline

These are **supporting, and cut first under the CLAUDE.md Scope rule**:

- public discussion
- Discoverable Proposals and the Proposals section of Discover

**Rough effort:** ~12–15 dev-days on top of what IR-255 has already delivered. That is partly offset by work it deletes: the intake queue, intake triage UI, and the Proposal complete act.

## SaaS Impact

Neutral to positive. The routing graph and the entry party remain configuration (ADR-002). An institution that does want triage could configure an entry party other than `adviser`. That is not built, and CIT-U-only scope means it is not planned.

## Security Impact

**New authority:**

- An Adviser may publish.
- Office members may claim.
- Coordinators may assign.

Each authority is a named predicate in `core.permissions`, checked at the endpoint, and never inferred from the `capabilities` list.

**New surfaces:**

- **The summary read path for Discoverable Proposals.** Its serializer is allow-listed, and a test fails if a file, version or review field appears on it.
- **Public comments.** Stored text, rendered escaped, and hideable.

**Review discussion** is record data gated by `is_record_participant`. It refuses with a 404, per IR-153.

**No change** to `visible_to()` or to Ask IRIS retrieval.

## Deployment Impact

Migrations only (§13). Test them against a copy of the seeded database. Back up `postgres_data` before applying them to the pilot.

## Research Impact

**ADR-003's contribution is unchanged, and easier to show.** A Thesis routed to ITSO and IERC, where IERC requests a revision, demonstrates the preserved clearance directly. The versions and timeline now make it visible to a panel without reading the database.

**For ADR-004 / ADR-011:**

- Adviser-only records have no parallel clearance to preserve, so the controlled comparison must be run on specialist-path records.
- Route length now varies by reviewer choice. ADR-021 already recorded that variance, and it is sharper here.
- `ReviewerSeat.opened_at` gives the time-on-task measurement a real start point.

**The CMMN positioning question** (ADR-021 §Research considerations) is still open, and is sharper now that routing is chosen by readers.

## Related Requirements

FR-M5-01 · FR-M5-03 · FR-M4 · NFR-R3 · NFR-S4. These are stable labels only.

## Related Tasks

- **This ADR:** IR-373.
- **Built foundation:** IR-255 (parent), IR-256, IR-257, IR-258, IR-259, IR-262, IR-263.

### 14. How the unbuilt IR-255 subtasks change

| Ticket | Was (ADR-021) | Becomes |
|---|---|---|
| IR-261 | route, with intake as initial router | **Every record type enters at the Adviser.** Route from Adviser-accept, office to office, and RDCO to office. Targets land in pools. Adds nominate. |
| IR-268 | queues per party incl. Intake & Triage | **My Reviews** over seats: To review · In review · Done. Office pool with claim/assign. |
| IR-269 | clear / finding, hand-back | Holds. Office completion = all seats done. Hand-back opens RDCO only on the specialist path. |
| IR-270 | RDCO decides every Thesis/Project | RDCO decides specialist-path records only. Adds *accept & publish* for the Adviser on the non-specialist path. |
| IR-271 | Adviser **or RDCO** decides and **completes** a Proposal | Adviser alone: revise / reject / accept. **Complete retired.** Continuation moves to a new ticket. |
| IR-272 | request resubmission | Holds. The request records the version it was made against. |
| IR-273 | resubmit and reset | Resubmit **writes a `RecordVersion`**. Only the requesting seats reopen. |
| IR-260 | cutover incl. `rdco_intake` → `intake` rename | Cutover retires intake instead of renaming it (§13). New submissions enter at the Adviser, and an owner named as Adviser is refused. |
| IR-274 | delete the old pipeline | Holds, and also deletes the intake queue and UI. |

**Re-planned 2026-09-26.** Each ticket above has been rewritten in Jira to this column, relabelled `not-ready` until the tickets it now depends on exist, and has its frontend acceptance criteria held for the frontend redesign specification.

**New tickets, to be created after the frontend redesign specification is reconciled:**

- seats, pool and coordinator
- record versions and the version picker
- Proposal continuation and lineage
- capabilities payload and Paper View modes
- review timeline and `ReviewComment`
- public discussion
- Discoverable Proposals and the Discover Proposals section

The UI specification is [`docs/ui-ux/16-paper-view-and-review.md`](../ui-ux/16-paper-view-and-review.md).
