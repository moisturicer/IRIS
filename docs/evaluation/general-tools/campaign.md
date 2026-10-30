# IR-609 — comparable campaigns and the evaluation report

`eval_campaign` turns collected run files, named human reviews and IR-608 safety evidence into one report. It is free: it reads files, calls no model and touches no database. **Running it, or reading a report from fake providers, authorizes no spending, deployment or release.**

## Order of work

1. **Development smoke.** Collect a few development cases with `eval_replay_conversations` (IR-606). Its `--smoke` flag is a fake-provider setup check only; a smoke that measures spend uses `--providers real` on two or three cases, without `--smoke`. Then measure it:

   ```powershell
   python manage.py eval_campaign --smoke ../docs/evaluation/runs/<smoke>.json --case-cost-usd 0.50 --campaign-cost-usd 50 --planned-cases 900
   ```

   It reports setup (conversations complete), turn outcomes, latency and physical spend per operation (`llm`, `embed`, `rerank`, `decision` for Jev). An operation appears only if the smoke executed it. Retries and fallbacks are separate attempt rows, so the dearest conversation already includes them. Unreported usage is counted at its reservation, never as zero. `--planned-cases` counts every case execution (cases × arms × repetitions). An attempt with no recorded cost counts as missing, not as zero. It says `ready` only for real providers, complete usage, at least one finished conversation, and proposed caps that cover the dearest observed conversation and the projected campaign. The caps are proposals for a person to approve; the command approves nothing.

2. **Development campaign.** Collect each arm at least **three times** (`MIN_REPETITIONS`) under one set of conditions. Reviews must carry the `run_id` they judged, because each repetition produced a different answer (always required in model mode). If the funding approval records `case_cost_usd`, every run's case cap must be within it.

3. **Held-out campaign, once.** `eval_replay_conversations --held-out` refuses unless the lock has `locked_at` and freezes the scorer's thresholds (`thresholds`, written by `--write-lock` from IR-609 on; older locks must be rewritten). With `--providers real` it also needs `--approvals` naming a reference and an approver for each of `funding`, `provider_data_policy` and `dataset_transmission`. The report applies the same freeze to any run with held-out cases, requires that output to postdate `locked_at`, and needs the approvals for real providers.

## The report

```powershell
python manage.py eval_campaign --report --set ../docs/evaluation/general-tools/conversation_set_v1.json --lock ../docs/evaluation/general-tools/conversation_set_v1.lock.json --runs controller=r1.json --runs controller=r2.json --runs controller=r3.json --reviews reviews.json --approvals approvals.json --scenarios ../docs/evaluation/runs/<IR-608-scenarios>.json
```

Repeat `--runs label=path` once per repetition. `--counted` adds the IR-607 checks (label review, review packets, real providers, locked corpus, a stated `reviewer_kind`, two reviews per conversation) and refuses `--min-examples` below the scorer's default of 10. `--exclude-run run_id=reason` lists a run that was left out and why. `--mode model` compares models under one architecture and is labelled separately; an architecture comparison never mixes models.

**Refused before anything is scored:** no lock or a stale one, incomplete manifests, a repeated `run_id`, a case run twice in one run, a saved Conversation reused, run digests that differ from the lock, and any difference in corpus, models, data policy, limits, rubric or set digests between arms. Each arm must run its own pinned engine (`controller-v1` for `controller`, `lanes-v1` for `current` and `fixed_synthesis`) through the authenticated `public-1` protocol. `fixed_synthesis` has no engine of its own in this codebase, so its manifest must name the `implementation_ref` of a pinned release. Two arms with the same engine, commit and release are the same code and are refused. Until such a release exists, `fixed_synthesis` stays `not_measured`. A model comparison must give each label different `model_ids`.

**What it writes** (`docs/evaluation/runs/<stamp>-IR-609-campaign-<set>.json` and `.md`):

- per arm, each repetition scored by the unchanged IR-598 scorer: completion, claim, citation and page support as separate fractions with their own denominators and Wilson intervals, plus the range across repetitions;
- per family, its status: `reported`, `INCONCLUSIVE` below the minimum, or `unreviewed` when any case it ran lacks a verdict;
- access breaches by run and conversation;
- cold and warm latency and spend apart, per operation and model, with the vendor price basis (flagged when runs priced differently); missing usage or cost makes spend `incomplete` and leaves cost per success undefined; a breached answer is never a success;
- private diagnostic stages, counted and never used as a verdict;
- real success and failure examples drawn from every repetition (ids, family, the set's question, verdict and stages; no answer text);
- excluded runs, unmeasured arms and scenarios (IR-608 access, durability, browser; A15 public research);
- approval references, the corpus statement and the notes below.

**Blocking.** Any access breach, any unreviewed family, and any IR-608 scenario that failed or was not measured set `enablement_blocked`. A strong average never clears it.

A proxy corpus result is not CIT-U research and the report says so. Targets are proposed owner-review targets, not approved gates.

## Status

Built and tested with hand-authored fixtures (`apps/ai/evaluation/tests/test_campaign_report.py`, `test_campaign_command.py`). **No campaign has been run**: the set is still draft-labelled, no person has reviewed an arm, no paid approval is recorded, and only the controller arm has a pinned implementation in this checkout.
