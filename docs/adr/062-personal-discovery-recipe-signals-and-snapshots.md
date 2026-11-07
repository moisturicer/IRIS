# ADR-062: Personal discovery — a transparent metadata recipe, account-owned signals, and frozen feed snapshots

## Status

**Proposed** — 2026-11-07 (IR-946, under IR-557), awaiting a named approver. Records decisions already built in IR-567, IR-576 and IR-575 (IR-575 is in PR #596, not merged when this was written); it does not authorise anything new. The semantic extension (IR-582) is deliberately out of scope here and stays deferred.

## Context

Discover's catalogue orders by added date or lifetime access count. IR-557 adds a **For you** feed that learns from what a reader has told IRIS, with a reason on every item, reversible feedback and stable pagination. Three tickets built it in slices:

- **IR-567** — chosen Areas, a Latest fallback, per-item reasons, the snapshot and cursor.
- **IR-576** — Not interested with Undo, and a reset.
- **IR-575** — Areas of saved Records join the chosen ones, saved Records sink, saves invalidate the feed.

No ADR covers any of this. The rules live in the IR-557 spec text and in `docs/testing/traceability/`, and Jira and traceability files are not requirements authorities (CLAUDE.md §Source-of-truth hierarchy). Several decisions were made while building that the spec does not state; a reader of the code cannot tell which were deliberate.

This ADR is also the basis a later change must amend before it alters ordering, signals or cursor behaviour. It does not cover Related works or private custom feeds, which are separate decisions.

## Decision

1. **The recipe is metadata only and calls no vendor.** For you is `apps/records/discovery.py`, computed from catalogue metadata, the reader's own account data and the one visibility predicate. No model output, score or embedding takes part.

2. **Interest Areas are the reader's chosen Areas plus the Areas of Records they have saved and may still read.** An Area is a classification or a PSCED classification. A saved Record with no Area adds nothing; no Area is invented. The saved signal goes through `Record.objects.visible_to(user)` and the published-catalogue statuses, so a save the reader loses access to stops being a signal.

3. **Ordering.** Matching Records the reader has not saved rotate across the Areas in stable Area-ID order, each Area in added-date order and each Record once. Matching saved Records (a completed Record is a saved one) rotate the same way after them. The rest of the catalogue follows in added-date order. Older research stays eligible. With no usable signal the feed says so and shows Latest.

4. **A reason names an input the reader actually gave.** A Record in any chosen Area is explained by it ("Because you chose …"). A Record explained only by a saved Area says "Same Area as a paper you saved" and never names the saved paper. A reason is rechecked on every page: if the saved Area is no longer backed by a readable saved Record, the item stays where it is and its reason becomes Latest.

5. **Never signals: notes, chats, review activity and private reading.** The recipe reads only `DiscoveryInterests`, `DiscoveryDismissal`, `SavedRecord` and the catalogue. Reading status acts only through the save it lives on.

6. **Not interested and saving are independent acts.** A dismissal removes the item at once and persists. It does not unsave, and unsaving does not dismiss. A dismissed saved Record still contributes the Area it was saved in. Dismissing reorders nothing, so it does not invalidate the snapshot; Undo does.

7. **Reset clears chosen Areas and every dismissal, never saves.** The reset confirmation says that the papers the reader saved still shape For you until they unsave them.

8. **Snapshots freeze order, never access.** The first page of a feed stores its candidate order in a snapshot owned by the reader. The cursor is signed, opaque, expires after 24 hours, and carries the snapshot, the owner, an offset and the original catalogue filters. It is stale (409, `stale_cursor`) if the owner differs, the interest revision changed or the recipe version differs. Chosen-Area edits, Undo, reset, and any change to saves (a new save, a reading-status change or a real unsave) bump the revision in the same transaction. Repeating an identical request changes nothing and bumps nothing. Deletion and revocation are rechecked on every page, so a page never repeats a Record or returns one the reader cannot read.

9. **A change to the recipe bumps `RECIPE_VERSION`.** A page opened before a deploy gets one 409 and the existing "refresh" notice. IR-575 moved it from 1 to 2.

10. **Everything is owner-scoped.** The owner comes from authentication. Two accounts on one browser never share interests, feedback, saves or snapshots.

## Alternatives Considered

**A. A dismissal cancels the signal of the saved Record it hides.**
- *Gain:* matches how "Not interested" reads to most people.
- *Give up:* one act reaches into another, which IR-557 rules out, and the reader cannot restore the signal without un-dismissing.
- *Chosen instead:* §6, with the reset text making the consequence visible.

**B. Saved Records sink only inside their own Area.**
- *Gain:* simpler per-Area code.
- *Give up:* a saved Record in a short Area could outrank new Records in a longer one, which contradicts "saved or completed drop below new ones". IR-575's review found it; §3 replaced it.

**C. Recompute every page from the live catalogue, with no snapshot.**
- *Gain:* always current.
- *Give up:* new Records and edits reorder pages under the reader, so Load more repeats or skips items.
- *Chosen instead:* §8 freezes order and rechecks access.

**D. Invalidate a frozen snapshot when a saved Record is withdrawn.**
- *Gain:* the ranking drops the revoked signal at once.
- *Give up:* revocation has no hook today; building one adds coupling across the workflow and library apps. §4 only drops the reason. See §Consequences.

**E. Keep recipe version 1 and treat entries without `source` as chosen.**
- *Gain:* no one-time 409.
- *Give up:* two ranking rules live in one cursor. §9 takes the clean break.

**F. Rank with embeddings now.**
- *Gain:* finds related terminology.
- *Give up:* needs approved indexing, an evaluation decision and IR-250. It is the separately gated IR-582, not this ADR.

## Decision Rationale

The recipe is a transparent, explainable ordering a reader can verify from their own choices, which a small institutional catalogue needs more than a tuned ranking. Freezing order and rechecking access keeps pagination stable without letting a stored snapshot grant access. Keeping saving and dismissing separate makes each reversible by its own control.

## Consequences

- **Open:** a frozen snapshot keeps the order a revoked signal gave it for up to 24 hours; only its reasons are rechecked. The next snapshot drops it. Accepting this ADR accepts that.
- **Open:** a saved Record is itself a candidate, so it can carry "Same Area as a paper you saved" about itself. The IR-575 example treats saved papers as part of their Area; a different reason for an item that is itself saved is undecided.
- **Settled, but may surprise:** an Area that arrives only through a dismissed save still counts (§6). A reader who finds that surprising can unsave the paper; "Reset my interests" does not remove saves.
- A future save-changing path must call `invalidate_feed`. Nothing enforces it; the library views are the only callers today.
- `apps/records/discovery.py` and `apps/library` import each other.
- Tests, not this ADR, are the evidence for each rule: `apps/records/test_discovery_feed.py` and `DiscoverPage.test.tsx`.

## MVP Impact

For you is part of Stage 3 supporting scope in IR-557. It is a complete initial product without semantic candidates.

## SaaS Impact

All state is per account and per instance (ADR-005). Nothing crosses tenants.

## Security Impact

Candidates, signals and every page go through the one visibility predicate (CLAUDE.md §Security). A score never substitutes for it. Cursors are signed, owner-bound and expire. Private workflow data is never read, so discovery cannot grant or leak access.

## Deployment Impact

No migration for IR-575 (snapshot entries are JSON). A deploy that changes the recipe version causes one stale-cursor refresh per open feed.

## Research Impact

None directly. The feed is supporting scope, and its reasons are the reader's own inputs, not claims about scientific relevance.

## Related Requirements

IR-557 user stories 3, 4, 5, 6, 7, 9, 10, 11 and 12. [ADR-044](044-account-backed-research-library.md) (saved Records). [ADR-052](052-each-paper-states-its-embargo-and-a-person-ends-it.md) governs what the AI may read and is untouched here.

## Related Tasks

IR-557 (spec), IR-567, IR-576, IR-575 (PR #596), IR-946 (this ADR), IR-582 (deferred semantic candidates).
