# ADR-047: The Adviser sends to RDCO, offices request offices, and RDCO decides at any time

## Status

**Proposed — 2026-10-30.** Awaiting the project lead (Lee Jasmin Adolfo). Drafted from the review-workspace design session ([`../review_workspace_roadmap.md`](../review_workspace_roadmap.md) §5a and §7 #7). No code may change routing, the hand-back or the Decision rules until this ADR is accepted.

**Supersedes, in part, [ADR-032](032-adviser-first-review-and-office-reviewer-pools.md):**

- §3: *Accept & route*, "RDCO enters only on the specialist path", "Nobody routes to RDCO by hand", and the hand-back
- §4: the routing graph table, and the hand-back clause of the IR-269 amendment
- §5: the IR-272 amendment's rule that every Decision is refused while any Revision request is open, for RDCO only
- §12: the two tests that pin the hand-back

**Amends:**

- [ADR-043](043-review-turnaround-reminders-and-escalation.md) §1: RDCO's clock starts when the Adviser sends the Record, not at the hand-back.

**Unchanged:**

- ADR-032 §1 (every Record enters with its Adviser) and §2 (a Proposal is the Adviser's alone)
- Pools, Seats, claim, assign and *Add a reviewer* (§4)
- Versions and lineage (§5–§6)
- [ADR-003](003-clearance-aware-resubmission.md)'s clearance-aware resubmission, and [ADR-004](004-restart-all-comparison-mode.md)'s comparison policy

Two points are marked **Default, confirm at acceptance**. Each can be overturned without reopening the rest.

## Context

ADR-032 made the Adviser the router: on accepting a Thesis/Research or Project, the Adviser either publishes it or routes it to ITSO, IERC or KTTO. RDCO enters only when the last of those offices completes (the hand-back), and nobody routes to RDCO by hand.

Walking through the review workspace prototype with the user, three rules came out differently:

1. **The Adviser asks RDCO, not the specialist offices.** The Adviser's request for further review goes to RDCO alone.
2. **Only offices request offices.** RDCO, ITSO, IERC and KTTO may ask one another for review. A request names the office as a whole (its Pool) or specific officers in it.
3. **RDCO has executive authority.** It does not wait for the other offices to finish before it decides.

ADR-032's central claim, "the person who has read the paper decides whether anyone else needs to", still holds for the first question. The Adviser decides whether the Record needs anything beyond their own acceptance. What changes is who picks the specialist offices: RDCO, the institutional office whose job that is. The Adviser's reading still reaches RDCO through the send's reason and suggested offices (§1).

Built today, and touched by this decision:

- the routing graph in `apps/reviews/routing.py` (`ROUTE_TARGETS`)
- the hand-back in `apps/reviews/office_review.py` (`_hand_back`)
- the Decision predicate in `apps/reviews/decisions.py` and `apps/reviews/revisions.py`
- the `accept_route` capability and the route dialog in Paper View

## Decision

### 1. The Adviser's two acceptances: publish, or send to RDCO

For a Thesis/Research or Project, the Adviser's academic choices stay *request revision · reject · accept*. On accept, the Adviser chooses one of these:

| Choice | Result |
|---|---|
| **Accept & publish** | Unchanged from ADR-032 §3: `published`, and RDCO is never involved. **Default, confirm at acceptance.** |
| **Accept & send to RDCO** | Replaces *Accept & route*. Opens RDCO's assignment in its Pool with the Adviser's required reason. The Adviser's assignment completes and the Record stays `in_review`. |

- **The send may nominate RDCO officers**, one or several, as any request may (§3). With no nominee it lands in RDCO's Pool.
- **The send may suggest specialist offices.** The Adviser can tick ITSO, IERC or KTTO as *suggested*, alongside the author's ADR-018 hints. A suggestion routes nothing. RDCO sees both, labelled by who made them, and decides the routing. This keeps the reader's judgement in front of the router, which was ADR-032's reason for making the Adviser the router.
- **Accept & send to RDCO is not a Decision.** Like *Accept & route* before it, it closes nothing, and it is refused while a Revision request is open.
- **Proposals are unchanged.** The Adviser alone decides them, and they are never sent or routed (ADR-032 §2).
- *Why keep Accept & publish:* ADR-032 considered "RDCO decides every Thesis/Project" and the project lead did not choose it. An ordinary capstone with no institutional question should not cost RDCO a hand-off. Removing *Accept & publish* would reverse that decision too, and the user did not ask for it.

### 2. The routing graph

| From | May request review from |
|---|---|
| `adviser` (on accept) | `rdco` only |
| `rdco` | `itso`, `ierc`, `ktto` |
| `itso` / `ierc` / `ktto` | the other two specialist offices |

- Nothing requests the Adviser.
- Only the Adviser's send reaches RDCO. A specialist office tells RDCO by finishing (§4), never by routing to it.
- The other rules of ADR-032 §4 hold:
  - routing to an office that already holds the Record opens nothing new
  - a cleared clearance is never reset by routing
  - a re-routed office starts a new Review round

### 3. A request names an office, or officers in it

Every request between offices, and the Adviser's send, carries a **required reason** and one of these targets:

- **The office**: an assignment in its Pool, as today.
- **Specific officers**: one or more members of that office, each given a nominated Seat. Today a router may nominate one member per office; this ADR allows several.

Further rules:

- One request may name several offices, each with or without officers.
- **An office already holding the Record may be named only with officers.** Naming its Pool again would open nothing (§2). This is today's nominee requirement, kept.
- *Add a colleague* (ADR-032 §4's *Add a reviewer*) stays a separate act, within one's own office. The UI never merges it with a request to another office.

### 4. There is no hand-back

RDCO holds the Record from the Adviser's send onward. When a specialist office completes, IRIS records its Clearance as today and **notifies RDCO** that the office is done (the existing office-completed notice). It opens nothing.

- `_hand_back` and its `RoutingEvent` with `actor = None` are retired. History rows already written by it stay as they are.
- The RDCO row on the party tracker reads:
  - *Not required* when the Adviser published the Record directly
  - *Waiting* from the send onward, until RDCO decides

### 5. RDCO decides at any time

An RDCO Seat holder may make any Decision (*accept & publish*, *keep unlisted*, *reject*) while specialist offices are still reviewing. What the Decision closes is unchanged from ADR-032 §3's IR-270 amendment:

- active office assignments and their open Seats are withdrawn, with `closed_by_decision`
- open document requests are withdrawn
- each closed Seat's holder is told that their review is closed
- completed rounds keep their Clearance

The Decision dialog names every office still reviewing, and each Finding already recorded, before RDCO confirms.

**RDCO may also decide over an open Revision request. Default, confirm at acceptance.**

- An RDCO Decision withdraws every open Revision request, its own included. It records the Decision as the reason, through a new nullable `ResubmissionRequest.closed_by_decision` (the same shape as the IR-270 links on Seats, assignments and document requests).
- The owners' Decision notice names each request it withdrew and which party asked.
- **The Adviser's Decision is still refused while any Revision request is open.** RDCO's executive authority is RDCO's alone.
- *Rejected: RDCO waits for open Revision requests, as every decider does today.* An office's request would then block the institution's decision indefinitely when the author never answers. The user asked that RDCO "not have to wait".
- *Rejected: RDCO may reject but not accept over an open request.* That is half an override, and harder to explain than either rule.

### 6. Capabilities and acts

- **`accept_route` becomes `send_to_rdco`.** The act is the existing route endpoint, which reads its targets from the graph in §2. No second endpoint is added.
- **`route` stays the key for office-to-office requests.**
- **`decision.blocked` stops returning the open-Revision-request reason for an RDCO viewer.** `decision.closes` gains the Revision requests a Decision would withdraw. The table-driven capabilities test (ADR-032 §12) covers both.

### 7. Records already in review at cutover

A one-off data migration, in the same change as the code:

- **A Thesis/Research or Project that is `in_review`, has passed its Adviser, and has no active RDCO assignment** gets one opened in RDCO's Pool. The reason is *"Opened when RDCO began holding every routed Record (ADR-047)"*, and the `RoutingEvent` carries `actor = None`, as the hand-back's did. Its offices continue as they are.
- **Records with RDCO already active, and records still with their Adviser,** are untouched.
- The migration writes no `Review`, changes no Clearance, and is reversible: reversing it removes only the assignments it opened.
- *Rejected: keeping the hand-back for Records routed before cutover.* Two rules would then live in the code for the life of those Records, which is the brittleness ADR-032 §13 avoided.

### 8. Tests that pin the decisions

At the REST seam, replacing ADR-032 §12's two hand-back tests:

- An Adviser's accept & send opens an RDCO assignment immediately, and no specialist assignment.
- An Adviser asking for `itso`, `ierc` or `ktto` is refused (400), naming the allowed target.
- A specialist office routing to `rdco` is refused.
- RDCO routes to ITSO with two named officers: two nominated Seats and no Pool-only assignment.
- Naming ITSO's Pool while ITSO holds the Record is refused; naming an officer adds a Seat.
- The last office completing opens nothing and notifies RDCO.
- RDCO publishes while IERC is still reviewing: IERC's assignment and Seats are withdrawn with `closed_by_decision`, and ITSO's completed Clearance stands.
- RDCO rejects while IERC's Revision request is open: the request is withdrawn with `closed_by_decision`, and the owners' notice names it.
- The Adviser's accept & publish is still refused while a Revision request is open.
- The cutover migration opens exactly one RDCO assignment for an in-flight specialist Record and none for an Adviser-stage or RDCO-held one.
- Clearance-aware: unchanged. IERC requests a revision after ITSO cleared, and the new Version resets IERC only.

## Alternatives Considered

**Keep ADR-032's routing and only let RDCO decide early.** RDCO would still enter only by hand-back, so it could not decide early without first being routed to. That means restoring routing to RDCO by hand anyway, and the Adviser would still pick the offices.

**The Adviser routes to RDCO *and* to offices.** It keeps the Adviser as router and adds RDCO in parallel. The user asked that only offices request offices. The Adviser's suggested offices (§1) keep the Adviser's reading in front of RDCO without giving the Adviser the act.

**RDCO decides every Thesis/Project (removing Accept & publish).** Already offered and not chosen in ADR-032. Kept as is, subject to confirmation (§1).

**Office-to-RDCO requests.** A specialist office asking RDCO "please look now" would duplicate the completion notice (§4), and RDCO already holds the Record.

## Decision Rationale

The workflow now has one institutional owner from the moment the Adviser asks for more than their own acceptance. RDCO already decides every specialist-path Record. Making it the router too, and letting it decide when it judges enough is known, removes the hand-back, the one transition no person performs. It also removes the confusion this ADR started from: a reviewer can no longer ask "who sends it to RDCO?", because nobody has to.

The Adviser's role shrinks only in which offices they pick. Their acceptance, their reason and their suggested offices all still reach RDCO.

## Consequences

**Positive:**

- One path into RDCO, taken by a person with a reason. The hand-back's actorless event goes.
- RDCO can stop work that no longer matters (a Record it will reject anyway) without waiting for every office.
- Requests to named officers, several at once, match how offices actually ask for help.

**Negative:**

- **RDCO sees every Record that leaves its Adviser for further review**, including ones that end up needing no specialist office. RDCO's workload rises, and its Turnaround (ADR-043) now runs while offices review.
- **The router is no longer the person who read the paper.** This is mitigated, not removed, by the send's reason and suggested offices.
- **RDCO can override an office's open Revision request** (§5, if confirmed). An office's request becomes advisory to RDCO, though still binding on the Adviser. This must be visible in the tracker and in the owners' notice, or the office will not know why its request disappeared.

## Research Impact

ADR-003's contribution is unaffected. Clearance-aware resubmission still resets only the requesting parties, and RDCO deciding early writes no new Version.

ADR-004's comparison changes in two ways, identically in both arms:

- **Turnaround now includes RDCO's parallel time.** An RDCO-held Record measures from the send, not the hand-back.
- **A Revision request RDCO overrides ends a resubmission cycle early.** IR-144's workflow events must record it as `closed_by_decision`, so the analysis can exclude or report those cycles rather than count them as answered.

Records that crossed the cutover (§7) are tagged by their migration reason and should be reported separately.

## Related

- [`../review_workspace_roadmap.md`](../review_workspace_roadmap.md) §5a and §7 #7
- [`../ui-ux/prototypes/review-workspace.html`](../ui-ux/prototypes/review-workspace.html): the routing, request and Decision flows, clickable
- [IR-678](https://citiris.atlassian.net/browse/IR-678): the review workspace's first phase. It reads request targets from the server's routing flags, so it is unaffected by whether this ADR is accepted.
- **`CONTEXT.md` on acceptance:**
  - retire *Hand-back*
  - redefine *Specialist path* as "a Thesis/Research or Project its Adviser sent to RDCO"
  - in *Decision*, replace *Accept & route* with *Accept & send to RDCO*, and note RDCO's override of open Revision requests
  - in *Finding*, change "It travels to RDCO" to "RDCO is told"
