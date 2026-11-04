# ADR-052: Each paper states its embargo, and a person ends it

## Status

**Accepted on merge** — 2026-11-01. The decisions are Hermoine Zozobrado's, from a design session under IR-250. Merging this PR records acceptance by Lee Jasmin Adolfo, the project lead, as relayed by Hermoine Zozobrado. Being built: IR-811 adds decisions 1 to 4, 15 and 18 (the answer, the gate and who sees it), IR-816 adds the question itself, IR-815 adds decisions 16 and 17 (test data answers for itself, and IR-317's bypass is gone), and IR-812 adds decisions 5 to 8 and 10 (setting, extending and releasing). IR-813 adds decisions 11 to 13 (KTTO's release of an IP mark), IR-817 puts decisions 5, 6 and 11 on Paper View, IR-818 adds decision 14's warning to RDCO's Decision dialog, and IR-814 adds decision 9's reminders. Decision 6 is clarified in the IR-812 Amendment below. Decision 2 is amended and decision 18 added in the Amendment below.

**Corrected 2026-11-04: what is built.** Beyond the slices named above, the code also holds KTTO's IP release (decisions 11–12: `apps/records/ip_release.py`, and `tags/` refusing to clear `is_ip`, `apps/records/views.py:1202-1204`), decision 9's daily reminder job (`config/settings/base.py:356-360`) and decision 14's embargo warning in RDCO's Decision (`apps/reviews/decisions.py:366`).

**Amended 2026-11-04 (Hermoine Zozobrado, design session; Accepted): decision 14 is reversed.** See the *Amendment — 2026-11-04* section at the end.

**Amended again 2026-11-04 (Hermoine Zozobrado, IR-879 design session; Accepted): every paper is embargoed by default.** Decisions 2, 3, 5 and 16 and the IR-816 and IR-812 amendments change. See *Amendment — 2026-11-04 (IR-879): embargoed by default* at the end. Built by IR-882.

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

## Amendment — 2026-11-02 (IR-812): a released paper can be held again

Decided by Hermoine Zozobrado while building IR-812.

**Decision 6 says "a release can't be undone". That's about text that has already left, and it doesn't stop a new embargo.** Decision 5 lets owners or the Adviser set an embargo, and a released paper is no exception. Further sending stops, the response says text already sent can't be recalled, and only the Adviser or RDCO can release it again. The audit log keeps every step.

**What it costs.** A student owner can overrule their Adviser's release, until the Adviser or RDCO releases it again. That errs toward holding text back, which is the direction a mistake here should go, because a wrong release can't be taken back and a wrong hold can.

**Two rules that follow from decisions already made:**

- **A date may move earlier as well as later.** It's a reminder and ends nothing (decision 9), so nothing is gained by refusing it.
- **An earlier chat answer is the paper's text.** A Turn citing a paper the check now refuses stays out of chat history, recall and the answer backfill, and the reader keeps it in their own transcript.

**What this doesn't catch.** IRIS knows what an answer drew on from what it cites, because a Turn stores nothing else. An answer that repeats a paper without citing it, or a later answer that restates an earlier one while citing a different paper, still goes back to the model. Closing that means storing every passage a model was shown, per Turn, which is a schema change and isn't built.

## Amendment — 2026-11-04: an embargo stops publishing

Decided by Hermoine Zozobrado in a design session on the review workflow. Transcribed by an agent.

**Decision 14, as amended.** **A paper under an Active embargo, or with no answer, can't be published.** RDCO's Decision offers *Accept, keep unlisted* instead of *Accept & publish*, and says to release the embargo first. Once the Adviser or RDCO releases it (decision 6), RDCO publishes the Unlisted paper through ADR-047 §10's `publish_unlisted`. The release has already queued it for the AI (decision 10).

**What this supersedes.** Decision 14's "An embargo doesn't stop RDCO publishing" and its warning-only dialog. The rejected alternative "An embargo blocks publishing" is now the rule. The Consequences line "RDCO can publish a paper that's meant to stay private" no longer holds.

**Why.** An Active embargo means a person has said the paper isn't free yet, and publishing is as public as an act gets. Keep unlisted already gives RDCO a way to accept the work without waiting.

**What it costs.** Two acts instead of one: release, then publish. RDCO can do both itself (decision 6). The objection the original decision raised, that RDCO would wait "even when publishing is fine", is met by releasing, which is the statement that publishing is fine.

## Amendment — 2026-11-04 (IR-879): embargoed by default

Decided by Hermoine Zozobrado in the review-workspace design session. Transcribed by an agent. Built by IR-882.

**Decisions 2 and 3, as amended: no question, and every paper starts embargoed.** Publish no longer opens on the embargo question (the IR-816 amendment's "Every paper answers one question first" is withdrawn). A paper starts **Active with no date**: the AI can't read it (ADR-015's gate) and RDCO can't publish it (the first 2026-11-04 amendment). A first submission no longer needs an embargo answer. **Unknown** stays a state only for rows nobody has touched. The migration moves those to Active, and "no embargo" answers to Released.

**Decision 5, as amended: only the Adviser or RDCO set or extend a date.** They add one during review when they see IP or patent potential. Owners no longer set or extend an embargo, before or after submission. The IR-812 amendment's "a student owner can overrule their Adviser's release" goes with it, while its other rules stand: a release doesn't recall text already sent, a released paper can be embargoed again by the Adviser or RDCO, and a date may move earlier.

**Unchanged:** only the Adviser or RDCO release (decision 6). A date never ends an embargo and is only a reminder (decision 9), so a paper with no date gets no reminder. Releasing queues the paper for the AI (decision 10). KTTO's IP release is separate (decisions 11–13).

**Decision 16, as amended: test data.** `seed_demo` leaves some submitted papers Released and some Active, so both paths can be shown. `load_corpus --clear-for-ai` and `mark_corpus_cleared` mark test papers **Released** instead of answering "no embargo".

**Why.** "Nothing goes out until a person releases it" is one rule, applied to every paper. The question first, as amended by IR-816, still let a student send text out with one "No", and it put a decision about IP in front of the person least placed to judge it.

**What it costs.**

- Every paper needs an explicit release, by the Adviser or RDCO, before Ask IRIS can use it or RDCO can publish it. Unreleased papers stay out of Ask IRIS, and keyword search still finds them (ADR-008).
- Students can no longer say their paper is free of agreements. They tell their Adviser.
- One more act on every reviewed paper.
