# ADR-052: Each paper states its embargo, and a person ends it

## Status

**Accepted on merge** — 2026-11-01. The decisions are Hermoine Zozobrado's, from a design session under IR-250. Merging this PR records acceptance by Lee Jasmin Adolfo, the project lead, as relayed by Hermoine Zozobrado. Being built: IR-811 adds decisions 1 to 4, 15 and 18 (the answer, the gate and who sees it), and IR-816 adds the question itself. Decision 2 is amended and decision 18 added in the Amendment below. The acts, the reminders and the bypass's removal are still to come.

It answers the four questions IR-250 left open, and it amends [ADR-015](015-voyage-embedding-and-reranking.md)'s disclosure gate. ADR-015 calls these questions CIT-U has to answer. The answers here come from the project team, and no CIT-U office's sign-off is recorded.

## Context

ADR-015 requires a gate before any paper's text reaches an outside AI company. It checks three facts: IP status, embargo and author consent. Observed on `main`, 2026-11-01:

- **`Record` has no embargo field.** `apps/ai/policy/records.py` reads `embargoed_until` with `getattr` and falls back to `EmbargoUnknown`, so every paper is refused.
- **A blank date would open the gate for every existing paper.** `disclosure.py` reads `None` as "known not embargoed", so a nullable field alone reads as a "no" on every row.
- **A date ends an embargo by itself.** `_embargo_reason` treats the date as over on the day itself. IRIS has no way of knowing whether a patent or an agreement has actually finished.
- **A refused paper is never tried again.** `embed_active_chunk_set` returns `refused=True`, `embed_chunk_set` is only queued after chunking, and nothing in `CELERY_BEAT_SCHEDULE` looks for such papers.
- **An IP mark blocks forever.** `is_ip` refuses a paper with no way to release it, even after it is published.
- **Any office can clear an IP mark.** `PATCH /records/<id>/tags/` lets KTTO, RDCO, ITSO and IERC set `is_ip` to false, which would open the gate for that paper.
- **The form's question about IP is already fixed once submitted** (`FIXED_ONCE_SUBMITTED`), and consent is stamped once at submission.

Development runs through IR-317's bypass, which refuses to start with `DEBUG` off. A deployed IRIS therefore can't answer from any paper until this is built.

## Decision

### What is recorded

1. **An embargo is its own fact**, separate from publication status, IP status and consent. A published paper can still be under an agreement, so "published" never implies "no embargo".
2. **Every paper answers one question at submission:** a toggle and a date on the publish form, beside the IP question. Off records "no embargo". On requires a date. The answer is stored with who gave it and when, the way consent is.
3. **An unanswered paper stays blocked.** A paper has one of four states:

   | State | Meaning | Reaches the AI? |
   |---|---|---|
   | Unknown | Nobody has answered | No |
   | None | Answered "no embargo" | Yes |
   | Active | Answered with a date, or set later | No |
   | Released | A person ended it | Yes |

   The adapter must stop reading a blank date as "none". The field names are the implementer's, for example `embargoed_until`, `embargo_answered_at` and `embargo_released_at`.
4. **A new Version doesn't ask again.** The answer stands, and decisions 5 and 6 can change it.

### Who can change it

5. **Owners or the Adviser can set or extend an embargo.** Before submission the toggle is the owners' to change freely, because nothing has been sent.
6. **Only the Adviser or RDCO can release one.** Student owners can't, even on their own paper. A release can't be undone, and an embargo may protect a sponsor's agreement or the other owners' wishes. If the Adviser has left, RDCO releases it.
7. **A paper has one Adviser.** ADR-032 stands. Many advisers with a main adviser was considered and withdrawn.
8. **Every set, extend and release is audited.**

### How an embargo ends

9. **The date never ends an embargo.** It is a reminder. On the date, IRIS tells the owners and the Adviser in-app to review the embargo, then every 5 working days until someone extends or releases it, the same rhythm as ADR-043's overdue reminders. The paper stays blocked meanwhile. As in ADR-043, a date decides nothing.
10. **Releasing sends the paper to the AI.** The act queues the paper's indexing, so a paper refused during its embargo isn't left out for good. No separate job looks for such papers.

### IP-marked papers

11. **KTTO releases an IP-marked paper**, because KTTO evaluates IP submissions. Today the mark blocks forever. The paper stays marked as IP, and the release is a separate, audited act.
12. **Only KTTO's release opens the gate for a marked paper.** `PATCH /records/<id>/tags/` must stop letting other offices clear `is_ip`.
13. **The two are independent.** A paper with both an embargo and an IP mark needs both released, and consent still applies.

### Publishing

14. **An embargo doesn't stop RDCO publishing.** RDCO's Decision dialog warns that the paper is under embargo and gives the date, and the choice stays RDCO's, as with ADR-047's warning about offices still reviewing. The embargo keeps stopping text going to AI companies either way.

### Getting there

15. **The migration leaves existing rows Unknown.** IRIS isn't deployed, so only demo and test papers exist, and no real paper is cleared by a default. Real papers imported later, under IR-278, stay Unknown until someone answers.
16. **Test data answers the question itself.** `seed_demo` answers "no" for most papers and gives one demo paper a future date. `load_corpus` takes the same answer. The development database's 40 proxy papers are marked once.
17. **IR-317's bypass is deleted in the same change:** the setting, its startup check, `index_with_disclosure_bypass` and the status flag, as ADR-015 requires.

## Alternatives Considered

**The date ends the embargo by itself.** It needs nobody to act. Rejected: text sent to a vendor can't be recalled, so a patent or agreement that runs late would leak with nobody having chosen it. The worst case of a person releasing is a paper missing from Ask IRIS, which anyone responsible can fix.

**"Published means no embargo."** It needs no new field and no question. Rejected: ADR-015 forbids a rule that merely sounds defensible, and a published paper can still be under an agreement.

**Any owner can release.** It's simpler for students. Rejected: one owner could send out a paper against an agreement or the other owners' wishes, and it can't be undone.

**An embargo blocks publishing.** It keeps a private paper fully private. Rejected: RDCO would have to wait even when publishing is fine, and ADR-047 warns rather than blocks.

**ITSO releases IP-marked papers.** Rejected: ITSO handles technical review of research outputs, and KTTO evaluates IP submissions.

**Many advisers with a main adviser.** Co-advisers could read and comment. Withdrawn: it reaches visibility, review and notices, and it reopens ADR-032.

## Decision Rationale

Sending text to a vendor is the one act here that can't be undone, so every default leans towards not sending. A paper is sent only when a person has said it may be, and a date alone never says so.

## Consequences

**Positive:**

- A normal paper reaches the AI with no special handling, once its owner says "no embargo".
- A late patent or agreement can't leak because a date passed.
- ADR-015's gate can stay on in production, and the bypass goes.

**Negative:**

- **Papers can stay out of Ask IRIS when nobody responds.** Keyword search still finds them (ADR-008).
- **Students depend on their Adviser** to release an embargo, or on RDCO if the Adviser has left.
- **KTTO, Advisers and RDCO each gain an act,** and the reminders may become noise on papers with long agreements.
- **RDCO can publish a paper that's meant to stay private.** The dialog warns, and nothing stops it.
- **Setting an embargo late can't recall text.** It stops further sending, and whatever was already sent stays sent. The form says so.

## MVP Impact

Required before deployment. Without it a deployed IRIS can't answer from any paper, because the bypass can't run with `DEBUG` off.

## SaaS Impact

The rules are the same per deployment. The office that releases IP-marked papers is CIT-U's, and would need configuring for another institution.

## Security Impact

The gate stays fail-closed: Unknown is refused. Every act is audited, and the new endpoints join the authorization matrix (`apps/tests/access/`). Closing the `tags/` path matters most, because it would otherwise open the gate with no release.

## Deployment Impact

One migration. Real papers stay blocked until answered. ADR-015's other conditions still apply before real text is sent, including Voyage's no-training setting.

## Research Impact

The evaluation's 40 proxy papers keep working once they're marked. Runs from then on use the real gate instead of the bypass. No finding about CIT-U research changes, because no real paper has been indexed.

## Related Requirements

`FR-M3-02` (a stable label).

## Related Tasks

IR-250 (builds this) · IR-317 (the bypass it removes) · IR-127 (the gate) · IR-226 (the consent precedent) · IR-630 and IR-631 (blocked by it) · IR-720 (uses its facts) · IR-278 (real papers) · IR-791 (consent withdrawal, which uses the same gate)

## Amendment — 2026-11-02 (IR-816): the question comes first, and who can see the answer

**Changed since by [ADR-054](054-each-person-answers-whether-ai-may-use-their-papers.md):** consent no longer stays on the last step, once that ADR is built. The Why below records the reasoning at the time.

**What this supersedes.** Decision 2's "at submission: a toggle and a date on the publish form, beside the IP question", and the word "toggle" in decision 5. Everything else stands. Decided by Hermoine Zozobrado. Decision 18 was accepted separately on 2026-11-02.

**Decision 2, as amended.** Every paper answers one question first, before its file is uploaded. Publish opens on it, alone, as a required No or Yes with a date. No records "no embargo", and Yes requires a date. It starts unanswered, because "no embargo" can send text out and must be something a person chose. The answer is saved before the file is sent, with who gave it and when, the way consent is, and a first submission with no answer is refused. Under Yes, nothing is filled in from the paper's content at upload.

**Decision 18.** Owners, the Adviser and office staff see an embargo's state and date on the record. Other readers of a published paper don't, because that a paper is under an agreement isn't theirs to learn from it.

**A Continuation answers for itself.** A Thesis or Project continuing a Proposal is asked the question from scratch, and a Proposal's embargo is not carried over. It's a different paper, and may not be covered by the same agreement. The cost is that a student can answer No on a Continuation of an embargoed Proposal, and its text can then go out once it's submitted.

**Why.**

- AI that fills in fields at upload is planned, and it has to know the answer before the file arrives. It still needs consent, which stays on the last step, so the gate refuses it until then.
- The IP question sits behind More details, which starts closed. A toggle there that started off would record "no embargo" for a student who never saw it, and text can't be recalled.
- A toggle's answer saved only at submission is lost when a student closes the dialog and comes back, which can turn a Yes into a No.

**What it costs.** One more screen and one more click on every submission. Under Yes, authors type their own title and abstract. The server does not refuse a file on an unanswered draft: Publish's order enforces "answer first", and the gate still refuses an unanswered paper.
