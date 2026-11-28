# ADR-075: Readers mark a published paper Useful or Not useful, shown as two counts and never used for ranking

## Status

**Proposed** — 2026-11-28 ([IR-1346](https://citiris.atlassian.net/browse/IR-1346), spec [IR-1345](https://citiris.atlassian.net/browse/IR-1345)). Drafted by an AI agent (Claude Code) at Lee Jasmin Adolfo's request. Awaiting a reviewer's acceptance; nothing is built to it yet.

Lee Jasmin Adolfo made the decisions below on 2026-11-28, in a design session where each one was put to them with a recommendation. Three details were the agent's and were stated to them before the tickets were written:
- the buttons are toggle buttons;
- no rate limit of their own;
- votes cast before a Suspension stay counted.

Writing this ADR against the code changed three details of the spec. All three are recorded in IR-1345:
- **A paper that isn't published answers 404, not 403**, word for word like Comments (decision 4).
- **Suspension needs no rule of its own**: a suspended account can't sign in (decision 4).
- **A deleted account's votes lower the counts, which is not what happens to its Views**: account deletion keeps a paper's view count (decision 8).

## Context

**Nothing today lets a reader say a paper helped them.** A paper shows its **View** count (CONTEXT.md), and Discover can sort by views or by Trending. A view only records that someone opened the paper, not that it was any use to them. A **Saved Record** is private and tells no one anything; the glossary lists "like" and "star" as words to avoid for it.

**What already exists nearby:**

| Thing | Where | What it does | Relevant rule |
|---|---|---|---|
| View | `RecordView`, `apps/records/views_count.py` | one row per account per published paper, `Record.access_count` written with it | owners never count; who viewed is never shown |
| Comment | `PublicComment`, `apps/records/public_comments.py`, ADR-032 §7 | public thread on a published paper | published only, else 404 word for word; own posting throttle |
| Reader feedback on answers | [ADR-026](026-conversational-retrieval-and-memory.md) §15 | designed for Ask IRIS answers, not built | **never a ranking input** |
| For You signals | [ADR-062](062-personal-discovery-recipe-signals-and-snapshots.md) §5 | the recipe reads a fixed list of models | anything not on the list is never a signal |

**The corpus is small.** It's a few hundred papers at most, many of them student theses already cleared by an Adviser and the offices. On a corpus that size, a handful of votes can decide any ordering, and a few coordinated accounts could move it.

## Decision

### Proposal

1. **A vote means "this paper was useful to me".**
   - Two choices, labelled **Useful** and **Not useful** everywhere a reader sees them.
   - It is not agreement with the paper's findings. Research isn't judged by popular vote.
   - The word in code is `vote`, with values `up` and `down`. Readers never see "upvote", "like" or "rating".

2. **Both counts are shown, separately.**
   - For example, "12 useful · 2 not useful".
   - There is no net score.

3. **Voting is anonymous.**
   - Who voted which way is never shown to anyone: readers, the paper's owners, its Adviser, office staff or the System Admin.
   - The rows exist only to count each account once and to let a reader see and change their own vote. This is the same rule as a View.
   - A reader's own votes appear in their personal-data export (`apps/accounts/personal_data/`), as their views do. The export shows them only their own.

4. **Who may vote, and on what.**
   - Any signed-in account that can read the paper (`Record.objects.visible_to(user)`) may vote.
   - **Published papers only** (`pipeline_status` in `PUBLICLY_VISIBLE_STATUSES`). Never a draft, a paper under review, an unlisted paper or a Proposal.
     - A paper the reader can't read answers 404, identical to a missing one (IR-153).
     - A paper they can read that isn't published also answers 404, word for word, exactly as Comments do.
   - **The paper's own owners and its Adviser can't vote on it.** They see the counts, with the buttons disabled and the reason shown.
   - **The System Admin can't vote.** It has no Profile (CONTEXT.md **Profile**) and acts for the system, not as a reader.
   - **A suspended account can't sign in** (CONTEXT.md **Suspension**), so it can't vote; no separate rule is needed. Votes it cast before the Suspension stay counted, as its Comments stay.

5. **One vote per account per paper.**
   - Casting the other value switches the vote.
   - Clearing removes it.
   - A reader always sees their own current vote.
   - Two casts by the same reader at the same moment count once.

6. **Votes are never an input to anything.**
   - Ask IRIS retrieval, the AI runtime's tools and the answer path never read a vote or a count. This follows [ADR-026](026-conversational-retrieval-and-memory.md) §15's reasoning for answer feedback, which applies equally here.
   - The For You recipe never reads them; [ADR-062](062-personal-discovery-recipe-signals-and-snapshots.md) §5 is amended to say so.
   - **No ordering by votes**: not in Discover's sort, Best, Trending or Most viewed. Adding a sort later needs an amendment to this ADR, with evidence that there are enough votes to rank on.

7. **No side effects.**
   - No `AuditEvent`. An audit row would name the voter, which decision 3 rules out, and a vote decides nothing about a record's workflow.
   - No notification to the paper's owners.
   - No live update ([ADR-073](073-live-updates-by-server-sent-hints.md)). The reader's own click updates at once; other people's votes show on the next load.

8. **Lifecycle.**
   - **A paper that stops being published keeps its votes, hidden.** Its counts aren't sent while it isn't published, and they return when it is published again. This is the same as Comments.
   - **A paper that is deleted** loses its votes with it.
   - **A deleted account's votes are deleted** (`accounts.deletion.registry`, a `DELETE` rule), **and the counts drop by them**.
     - This is deliberately unlike a View. Account deletion keeps a paper's view count (`"records.RecordView.user"` in the registry).
     - A View is a fact about the past. A vote is a person's current opinion, so it leaves when they do.

9. **Storage.**
   - `RecordVote`: `record` (cascade), `user` (cascade), `value` (`up` | `down`), `created_at`, `updated_at`, and one row per (record, user) by a unique constraint.
   - `Record.up_count` and `Record.down_count` are non-negative integers, default 0. They are written in the same transaction as the row they count, the way `access_count` is written with `RecordView`, so Discover cards need no extra query.

10. **API.** The paper is resolved as every record action resolves it, through `RecordViewSet.get_object`.

    | Request | Body | Answer |
    |---|---|---|
    | `PUT /api/v1/records/<id>/vote/` | `{"value": "up" \| "down"}` | 200 `{"up_count": n, "down_count": n, "my_vote": "up" \| "down"}` |
    | `DELETE /api/v1/records/<id>/vote/` | — | 200 `{"up_count": n, "down_count": n, "my_vote": null}` |

    - `PUT` with the value the reader already has changes nothing and answers the same 200.
    - `DELETE` with no vote answers 200 too.
    - Any other `value` answers 400.
    - **Refusals**, 403, as `{"code": ..., "detail": ...}` in the shape record endpoints already use:

      | `code` | Who | `detail` (shown to the reader) |
      |---|---|---|
      | `own_paper` | an owner of the paper | "You can't vote on your own paper." |
      | `advised_paper` | the paper's Adviser | "You can't vote on a paper you advised." |
      | `not_a_reader` | the System Admin | "The System Admin account doesn't vote on papers." |

    - **Record serializers**:
      - List and detail both carry `up_count` and `down_count`. They are `null` while the paper isn't published.
      - Detail also carries `my_vote` (`"up"`, `"down"` or `null`).
      - Detail's `capabilities` includes `vote` when the reader may vote.
      - Detail carries `vote_refused`: one of the codes above, or `null` when voting is allowed or the paper isn't published.
      - A published paper whose `capabilities` lacks `vote` always has a `vote_refused` code, so the page can show why.
    - No response ever carries who voted.
    - **No rate limit of its own.** Voting uses the API's ordinary per-user throttle. A vote changes at most one row, so there's nothing to flood. Comments' posting budget guards text other people must read, which a vote doesn't produce.

11. **Where it appears.**
    - The paper page shows the two buttons with their counts, next to Save. Each button is a toggle (`aria-pressed`), named with its count ("Useful, 12").
    - Discover result cards show both counts read-only, beside the view count. No buttons on cards.

## Alternatives Considered

**"Agree / Disagree" as the meaning.**
- Gains: invites a reader's view of the findings, which some research platforms show.
- Costs: turns a thesis repository into a vote on whether research is right, a question for review, not for a count. A student's correct but unpopular finding would carry a public "disagree" tally.
- Rejected (Lee Jasmin Adolfo, 2026-11-28).

**Bare arrows with no stated meaning.**
- Gains: familiar from forums.
- Costs: each reader decides what a vote means, so the counts mean nothing in particular.
- Rejected.

**A single net score (+10).**
- Gains: one number, compact on a card.
- Costs: hides how divided readers are. 10 up and 0 down reads the same as 60 up and 50 down.
- Rejected.

**Only the Useful count public; Not useful kept but shown to no one, or to RDCO only.**
- Gains: the same positive signal without a public mark against a student's cleared paper.
- Costs: a Not useful button whose count no reader ever sees, which looks broken; and asking for both visible was the point of the request.
- Considered seriously and rejected (Lee Jasmin Adolfo, 2026-11-28). The reputational cost to students is accepted in exchange for a complete signal. Revisit if owners object once it is live.

**Counts not public at all; evidence for people to read.**
- Gains: no reputational cost; mirrors ADR-026 §15's feedback.
- Costs: readers get nothing from voting, so few would.
- Rejected.

**Votes are visible by name, like Comments.**
- Gains: accountability; harder to vote carelessly.
- Costs: readers vote kindly, or not at all, on a classmate's or a lecturer's paper; the counts stop being honest.
- Rejected.

**Owners and the Adviser may vote, as they may comment.**
- Gains: one rule fewer.
- Costs: the people most invested in a paper add votes to it. Their own Views already don't count.
- Rejected.

**A "Most useful" sort in Discover now.**
- Gains: readers can find well-received papers.
- Costs: on a few hundred papers a handful of votes decides the order, and a few accounts could move it, the same reasoning ADR-026 §15 gives. Ordering is also what ADR-062 governs, so it needs its own amendment.
- Deferred to a later amendment (decision 6).

**An `AuditEvent` per vote.**
- Gains: a vote can be traced if counts look manipulated.
- Costs: the audit log names the voter and their choice, which defeats decision 3 for anyone who can read the log. It also writes a row on every click.
- Rejected. If manipulation is ever suspected, the `RecordVote` rows themselves say which accounts voted, without anything being published.

**A deleted account's votes stay counted, as its Views do.**
- Gains: counts never fall; one rule for Views and votes.
- Costs: a person who has left IRIS keeps an opinion on its papers.
- Rejected (decision 8).

**Its own rate limit, like Comments' posting budget.**
- Gains: caps a script toggling a vote thousands of times.
- Costs: more settings for an act that changes one row and is visible to no one as text. The ordinary throttle already caps it.
- Not proposed; a reviewer may reasonably choose otherwise.

**Live count updates through ADR-073 hints.**
- Gains: counts move while a reader watches.
- Costs: a hint per vote to every open copy of the paper, for numbers nobody needs to the second.
- Deferred.

## Decision Rationale

A vote that means "useful to me" is something any reader can answer honestly about any paper. Anonymous counting is what keeps it honest, and showing both counts keeps it informative. Keeping votes out of every ordering and every AI input means a small, gameable signal can't change what readers find or what Ask IRIS cites, so the feature can be added without touching retrieval quality or the discovery recipe. Reusing the Comment and View rules for who and what keeps one idea of "a published paper a reader can act on".

## Consequences

- **A student's paper can carry a public "not useful" count.** This is accepted in decision 2. Owners may object; that is the revisit trigger.
- **Counts can fall**, when a reader clears or switches a vote and when an account is deleted. A view count never falls.
- **`Record` gains two columns** and IRIS gains one table, with a migration.
- **Account deletion and the personal-data export each gain one declaration.** Their tests fail until they exist.
- **Nothing checks that votes stay out of ranking except a test.** IR-1347 adds one that fails if `apps/ai/`, `ai/` or the discovery recipe references `RecordVote`, `up_count` or `down_count`.
- **No one can tell from IRIS whether counts were manipulated**, short of reading the table.

## MVP Impact

None to the workflow or its evaluation. This is supporting reader scope; if capacity is short, it is cut before workflow or RAG work (CLAUDE.md §Scope).

## SaaS Impact

Votes are per instance (ADR-005). Nothing crosses tenants.

## Security Impact

- The paper is resolved through the one visibility predicate, so voting can't confirm that an unreadable paper exists.
- Refusals are by role on a paper the reader can already read, so they reveal nothing new.
- No response names a voter.
- The new endpoint has its object-level check in `RecordViewSet.get_object`, as CLAUDE.md §Security requires.

## Deployment Impact

One migration (`RecordVote`, two `Record` columns, default 0). No setting, no service and no backfill: every paper starts at zero.

## Research Impact

None. Votes never reach retrieval, the AI runtime or any evaluation instrument, and the workflow doesn't read them. They are not a measure of research quality and must not be cited as one in the thesis.

## Amends

- [ADR-062](062-personal-discovery-recipe-signals-and-snapshots.md) §5: votes join the list of things that are never signals.
- [ADR-026](026-conversational-retrieval-and-memory.md) §15: a cross-reference only. Votes are not that section's answer feedback, and they follow the same rule: never a ranking input.

## Related Requirements

No FR- id. CONTEXT.md **Vote**, **View**, **Comment**, **Suspension**.

## Related Tasks

[IR-1345](https://citiris.atlassian.net/browse/IR-1345) (spec), [IR-1346](https://citiris.atlassian.net/browse/IR-1346) (this ADR), [IR-1347](https://citiris.atlassian.net/browse/IR-1347) (backend), [IR-1348](https://citiris.atlassian.net/browse/IR-1348) (frontend).
