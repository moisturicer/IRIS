# ADR-047: The Adviser forwards to the offices they choose, only RDCO publishes, and RDCO decides at any time

## Status

**Accepted** — 2026-11-01 by Lee Jasmin Adolfo, the project lead, as relayed by Hermoine Zozobrado. Proposed 2026-10-30, drafted from the review-workspace design session ([`../review_workspace_roadmap.md`](../review_workspace_roadmap.md) §5a and §7 #7).

**Amended 2026-11-01, before anything was built,** by Hermoine Zozobrado in a design session, from how CIT-U publishes a paper. Two rules in the accepted text changed:

- **Only RDCO publishes a Thesis/Research or Project.** The Adviser's *Accept & publish* is gone. The accepted text kept it as a default to confirm.
- **The Adviser picks the offices.** The accepted text had the Adviser send to RDCO alone, with RDCO picking the offices and the Adviser only suggesting them.

**Not built on `main` yet:** IR-767 implements it, and until that merges the code still follows ADR-032's routing.

**Supersedes, in part, [ADR-032](032-adviser-first-review-and-office-reviewer-pools.md):**

- §3: *Accept & publish* for the Adviser, *Accept & route*, "RDCO enters only on the specialist path", "Nobody routes to RDCO by hand", and the hand-back
- §4: the routing graph table, and the hand-back clause of the IR-269 amendment
- §5: the IR-272 amendment's rule that every Decision is refused while any Revision request is open, for RDCO only
- §12: the two tests that pin the hand-back
- Its alternative "RDCO decides every Thesis/Project", which the project lead did not choose then, is now the rule. Its statement that RDCO as a mandatory step misdescribes CIT-U no longer stands.

**Amends:**

- [ADR-043](043-review-turnaround-reminders-and-escalation.md) §1: RDCO's clock starts when the Adviser forwards the Record, not at the hand-back.

**Unchanged:**

- ADR-032 §1 (every Record enters with its Adviser) and §2 (a Proposal is the Adviser's alone)
- Pools, Seats, claim, assign and *Add a reviewer* (§4)
- Versions and lineage (§5–§6)
- [ADR-003](003-clearance-aware-resubmission.md)'s clearance-aware resubmission, and [ADR-004](004-restart-all-comparison-mode.md)'s comparison policy

## Context

ADR-032 made the Adviser the router: on accepting a Thesis/Research or Project, the Adviser either publishes it or routes it to ITSO, IERC or KTTO. RDCO enters only when the last of those offices completes (the hand-back), and nobody routes to RDCO by hand.

CIT-U's process, as Hermoine Zozobrado described it on 2026-11-01:

1. A person submits a Thesis/Research or Project, and it goes to the Adviser first.
2. The Adviser reviews it, with back and forth until it is satisfactory.
3. The Adviser forwards it to the offices they think it should go to, several at once if needed.
4. The offices review it. Back and forth, such as missing documents, goes to the submitter, who provides them.
5. **Only RDCO publishes.**

Walking through the review workspace prototype added two more rules:

- **Offices can request offices.** RDCO, ITSO, IERC and KTTO may ask for review. A request names the office as a whole (its Pool) or specific officers in it.
- **RDCO has executive authority.** It does not wait for the other offices to finish before it decides.

ADR-032's central claim, "the person who has read the paper decides whether anyone else needs to", holds: the Adviser picks the offices. What changes is that no accepted Thesis/Research or Project can skip RDCO.

Built today, and touched by this decision:

- the routing graph in `apps/reviews/routing.py` (`ROUTE_TARGETS`)
- the hand-back in `apps/reviews/office_review.py` (`_hand_back`)
- the Decision predicate in `apps/reviews/decisions.py` and `apps/reviews/revisions.py`, including the Adviser's `PUBLISH` outcome
- the `accept_publish` and `accept_route` capabilities and the route dialog in Paper View

## Decision

### 1. The Adviser accepts and forwards

For a Thesis/Research or Project, the Adviser's academic choices stay *request revision · reject · accept*. **Accept & forward** is the only way to accept. It replaces both *Accept & publish* and *Accept & route*.

- **RDCO is always included.** Only RDCO can publish, so the Adviser cannot leave it out. A forward that names no other office goes to RDCO alone.
- **The Adviser adds any of ITSO, IERC and KTTO** they think it should go to. Each opens in parallel with RDCO and with each other.
- **It is the same request an office makes** (§3): a required reason, and for each office either its Pool or named officers. The author's ADR-018 hints are shown beside the choice.
- The Adviser's assignment completes, and the Record stays `in_review`.
- **Accept & forward is not a Decision.** Like *Accept & route* before it, it closes nothing, and it is refused while a Revision request is open.
- **The Adviser's only Decision on a Thesis/Research or Project is reject.**
- **Proposals are unchanged.** The Adviser alone decides them, and they are never forwarded or published (ADR-032 §2).

### 2. The routing graph

| From | May request review from |
|---|---|
| `adviser` (on accept) | `rdco`, always, and any of `itso`, `ierc`, `ktto` |
| `rdco` | `itso`, `ierc`, `ktto` |
| `itso` / `ierc` / `ktto` | the other two specialist offices |

- Nothing requests the Adviser.
- Only the Adviser's forward reaches RDCO. A specialist office tells RDCO by finishing (§4), never by routing to it.
- The other rules of ADR-032 §4 hold:
  - routing to an office that already holds the Record opens nothing new
  - a cleared clearance is never reset by routing
  - a re-routed office starts a new Review round

### 3. A request names an office, or officers in it

Every request between offices, and the Adviser's forward, carries a **required reason** and one of these targets:

- **The office**: an assignment in its Pool, as today.
- **Specific officers**: one or more members of that office, each given a nominated Seat. Today a router may nominate one member per office; this ADR allows several.

Further rules:

- One request may name several offices, each with or without officers.
- **An office already holding the Record may be named only with officers.** Naming its Pool again would open nothing (§2). This is today's nominee requirement, kept.
- *Add a colleague* (ADR-032 §4's *Add a reviewer*) stays a separate act, within one's own office. The UI never merges it with a request to another office.

### 4. There is no hand-back

RDCO holds the Record from the Adviser's forward onward. When a specialist office completes, IRIS records its Clearance as today and **notifies RDCO** that the office is done (the existing office-completed notice). It opens nothing.

- `_hand_back` and its `RoutingEvent` with `actor = None` are retired. History rows already written by it stay as they are.
- The RDCO row on the party tracker reads *Waiting* from the forward onward, until RDCO decides.

### 5. Only RDCO publishes, and it decides at any time

Only RDCO can *accept & publish* or *keep unlisted* a Thesis/Research or Project. An RDCO Seat holder may make any Decision (*accept & publish*, *keep unlisted*, *reject*) while specialist offices are still reviewing. What the Decision closes is unchanged from ADR-032 §3's IR-270 amendment:

- active office assignments and their open Seats are withdrawn, with `closed_by_decision`
- open document requests are withdrawn
- each closed Seat's holder is told that their review is closed
- completed rounds keep their Clearance

The party tracker shows which offices are still reviewing, and the Decision dialog names each of them and each Finding already recorded before RDCO confirms. This is a warning, not a block: the judgement is RDCO's.

**RDCO may also decide over an open Revision request.**

- An RDCO Decision withdraws every open Revision request, its own included. It records the Decision as the reason, through a new nullable `ResubmissionRequest.closed_by_decision` (the same shape as the IR-270 links on Seats, assignments and document requests).
- The owners' Decision notice names each request it withdrew and which party asked.
- **The Adviser's rejection is still refused while any Revision request is open.** RDCO's executive authority is RDCO's alone.
- *Rejected: RDCO waits for open Revision requests, as every decider does today.* An office's request would then block the institution's decision indefinitely when the author never answers.
- *Rejected: RDCO may reject but not accept over an open request.* That is half an override, and harder to explain than either rule.

### 6. Capabilities and acts

- **`accept_route` becomes `accept_forward`.** The act is the existing route endpoint, which reads its targets from the graph in §2. No second endpoint is added.
- **`accept_publish` is RDCO's alone** on a Thesis/Research or Project. The Adviser's allowed outcomes on one become `reject`.
- **`route` stays the key for office-to-office requests.**
- **`decision.blocked` stops returning the open-Revision-request reason for an RDCO viewer.** `decision.closes` gains the Revision requests a Decision would withdraw. The table-driven capabilities test (ADR-032 §12) covers both.

### 7. Records already in review at cutover

A one-off data migration, in the same change as the code:

- **A Thesis/Research or Project that is `in_review`, has passed its Adviser, and has no active RDCO assignment** gets one opened in RDCO's Pool. The reason is *"Opened when RDCO began holding every routed Record (ADR-047)"*, and the `RoutingEvent` carries `actor = None`, as the hand-back's did. Its offices continue as they are.
- **Records with RDCO already active, and records still with their Adviser,** are untouched. An Adviser still holding one uses *Accept & forward* from then on.
- **A paper an Adviser already published stays published.** IRIS is not deployed, so this concerns only demo and proxy data.
- The migration writes no `Review`, changes no Clearance, and is reversible: reversing it removes only the assignments it opened.
- *Rejected: keeping the hand-back for Records routed before cutover.* Two rules would then live in the code for the life of those Records, which is the brittleness ADR-032 §13 avoided.

### 8. Tests that pin the decisions

At the REST seam, replacing ADR-032 §12's two hand-back tests:

- An Adviser's accept & forward naming IERC and ITSO opens RDCO, IERC and ITSO in parallel.
- An Adviser's accept & forward naming no office opens RDCO alone.
- A forward cannot leave RDCO out: RDCO opens whichever offices are named.
- An Adviser publishing a Thesis/Research or Project is refused, and their capabilities offer no such act. Rejecting still works.
- A specialist office routing to `rdco` is refused.
- RDCO routes to ITSO with two named officers: two nominated Seats and no Pool-only assignment.
- Naming ITSO's Pool while ITSO holds the Record is refused; naming an officer adds a Seat.
- The last office completing opens nothing and notifies RDCO.
- RDCO publishes while IERC is still reviewing: IERC's assignment and Seats are withdrawn with `closed_by_decision`, and ITSO's completed Clearance stands.
- RDCO rejects while IERC's Revision request is open: the request is withdrawn with `closed_by_decision`, and the owners' notice names it.
- The Adviser's accept & forward and rejection are still refused while a Revision request is open.
- The cutover migration opens exactly one RDCO assignment for an in-flight specialist Record and none for an Adviser-stage or RDCO-held one.
- Clearance-aware: unchanged. IERC requests a revision after ITSO cleared, and the new Version resets IERC only.

## Alternatives Considered

**The Adviser sends to RDCO alone, and RDCO picks the offices.** The text Adolfo accepted, and what PR #410 was built to. One office would own all routing. Rejected by the amendment: the Adviser has read the paper and knows which offices it needs, and suggestions would only add a step.

**Keep the Adviser's Accept & publish.** RDCO would handle only papers that need it, and it is already built. Rejected: only RDCO publishes at CIT-U.

**RDCO enters only after the last office finishes (ADR-032's hand-back).** Offices would always finish first. Rejected: one slow office would hold up the paper, and RDCO could not see it until then.

**Let the Adviser choose whether to include RDCO.** It treats RDCO like any other office. Rejected: forgetting it would leave a paper nobody can publish.

**Office-to-RDCO requests.** A specialist office asking RDCO "please look now" would duplicate the completion notice (§4), and RDCO already holds the Record.

## Decision Rationale

IRIS should publish the way CIT-U does: the person who read the paper decides which offices need it, and one institutional office has the last word. Keeping RDCO on every accepted Record from the forward onward removes the hand-back, the one transition no person performs, and gives RDCO sight of the review as it happens.

## Consequences

**Positive:**

- One rule for every accepted Thesis/Research or Project: nothing reaches Discover without RDCO.
- The hand-back's actorless event goes.
- RDCO can stop work that no longer matters (a Record it will reject anyway) without waiting for every office.
- Requests to named officers, several at once, match how offices actually ask for help.

**Negative:**

- **RDCO handles every accepted Thesis/Research or Project, including ordinary capstones.** Its workload rises, its Turnaround (ADR-043) runs while offices review, and publication can wait on RDCO alone. This is the cost ADR-032 avoided.
- **It reverses a choice the project lead made in ADR-032.**
- **RDCO can publish while an office is still reviewing.** The tracker and dialog show it, and nothing stops it.
- **RDCO can override an office's open Revision request** (§5). An office's request becomes advisory to RDCO, though still binding on the Adviser. This must be visible in the tracker and in the owners' notice, or the office will not know why its request disappeared.

## Research Impact

ADR-003's contribution is unaffected. Clearance-aware resubmission still resets only the requesting parties, and RDCO deciding early writes no new Version.

ADR-004's comparison changes in three ways, identically in both arms:

- **Every accepted Thesis/Research or Project now includes RDCO's time.** No Record skips it through the Adviser.
- **Turnaround now includes RDCO's parallel time.** An RDCO-held Record measures from the forward, not the hand-back.
- **A Revision request RDCO overrides ends a resubmission cycle early.** IR-144's workflow events must record it as `closed_by_decision`, so the analysis can exclude or report those cycles rather than count them as answered.

Records that crossed the cutover (§7) are tagged by their migration reason and should be reported separately.

## Related

- [`../review_workspace_roadmap.md`](../review_workspace_roadmap.md) §5a and §7 #7
- [`../ui-ux/prototypes/review-workspace.html`](../ui-ux/prototypes/review-workspace.html): the routing, request and Decision flows, clickable. It shows the text before this amendment.
- [IR-678](https://citiris.atlassian.net/browse/IR-678): the review workspace's first phase. It reads request targets from the server's routing flags.
- `CONTEXT.md`: *Forward* is added, *Hand-back* is retired, and *Specialist path*, *Finding*, *Decision* and *Revision request* follow this ADR.
