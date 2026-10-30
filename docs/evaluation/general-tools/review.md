# IR-607 — label review, conversation review and counted scoring

This is how a draft conversation set becomes counted evidence. Each step has a gate the code enforces. All commands run from `backend/`.

## 1. Review the labels, then lock

A named person checks every conversation against the frozen corpus snapshot: category names, exact counts, paper and page facts, and the `supported_unambiguous` flag. They record it in a label review file:

```json
{"set_id": "general-tools-conversations-v1", "reviewer": "Full Name", "fixture": false,
 "corpus": {"...": "the set's corpus block, copied"},
 "set_digests": {"development": "...", "held_out": "..."},
 "conversations": {"A01-D01": {"status": "confirmed",
   "checks": {"category_names": true, "exact_counts": "not_applicable",
              "paper_page_facts": true, "supported_unambiguous": true}}}}
```

`status` is `confirmed`, `corrected` or `not_reviewed`. Every check must be `true` or `not_applicable`. The reviewer must appear in the set's `labelled_by`, and the digests and corpus must match the set as it is now, so a later edit makes the review stale.

Every A09 conversation carries `a09_case`: `missing_field`, `no_match` or `outage`. While the set has A09 cases but lacks one of the three, `--write-lock` refuses. The draft set has none tagged yet.

```powershell
python manage.py eval_conversations --set s.json --validate --label-review labels.json --write-lock s.lock.json
```

The lock now pins the corpus snapshot and `rubric_version` as well as each split, and records `locked_at` and the label review's digest. A changed question, label, corpus or rubric invalidates it. Locks written before IR-607 pinned neither, so they read as stale and must be rewritten.

## 2. Give each reviewer a packet

```powershell
python manage.py eval_review_packets --run run.json --reviewer reviewer@cit.edu --reviewer-name "Full Name" --out packets-name.json
```

A run holding held-out conversations is packaged only with `--lock`, and only when the run was stamped after `locked_at`, so held-out output is not opened before the freeze. The packet is issued to `--reviewer-name`, which is what reviews are signed with; the name is not tied to the login, so keep the email-to-name mapping with the packets. A packet holds each turn's question, rendered answer and citations (title, page, quoted text), checked against `Record.objects.visible_to(reviewer)` at the time of writing. If a turn cites a record the reviewer cannot read now, the whole turn is withheld, because its answer may quote that record. Packets never hold private diagnostics, usage, saved Turns or other reviewers' verdicts. Each conversation comes with a blank `review` template (`status: not_reviewed`, every judgment `null`).

## 3. Review independently, then adjudicate

A reviewer fills the template: `task_completion` (yes / partial / no), `pair_usefulness`, one entry per factual claim (`record_id`, `supported` and `citation_correct` as true/false, `page_correct` as true/false or `null` when no page applies), any other records consulted in `evidence_record_ids`, and explicit `true`/`false` for `unnecessary_clarification` and `access_breach`. Unfinished work stays `not_reviewed` and leaves every denominator.

Two people review on their own. When their verdicts agree, the conversation counts once. When they disagree, a finished third record with `"role": "adjudication"`, by someone other than the two reviewers, settles it. All original records stay in the score's `review_audit`. Only `reviewer_kind: "human"` is accepted; a model judge or automated trace cannot supply a verdict, and judge calibration stays separate (`--judge`).

## 4. Score

```powershell
python manage.py eval_conversations --set s.json --score --lock s.lock.json --runs controller=run.json --reviews reviews.json --label-review labels.json --packets packets-a.json --packets packets-b.json --counted
```

With `--packets`, a review citing a record outside its reviewer's packet is refused, as is a review from someone given no packet. Held-out reviews are scored only when the run was stamped after `locked_at` with the locked rubric version. Every score file states `counted` and `not_counted_reasons`. These keep a score uncounted: draft labels, a missing or fixture label review, no packets, fake providers, a run on a corpus other than the locked one, a conversation with only one review, or a review that does not state `reviewer_kind`. `--counted` turns any of them into a refusal. A label review that differs from the one recorded in the lock is always refused.

Not automated: the label checks themselves. The tool records what the named person confirmed; it does not compare category names or counts with the corpus.

Each arm also reports `diagnostics`: per-turn private stages from the run file (`candidates_then_no_results`, `no_candidates`, `provider_failure`, `answered`, `other`, `not_traced`). They show where a turn ended, for example a search that found papers but composed a no-sources answer. They never change a human verdict, and the reader's response is the same either way.

## Fixtures

`backend/apps/ai/evaluation/fixtures/review/` is a development fixture: a set with a fixture label review (`"fixture": true`), a fake-provider run, two independent reviews, an adjudication, a `not_reviewed` record, a partial answer, an unsupported claim and a wrong page. It exercises the workflow, and its score always reads `counted: false`. No person has approved it.
