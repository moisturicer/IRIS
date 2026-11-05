# IR-753 long-context case pack — review draft v1

**State: not ready / blocked.** This is an agent-authored proposal. No person has reviewed its labels, no fixture Manuscript has been ingested, and no counted or paid output has been opened. There is no freeze lock. Do not use it for a counted campaign or treat its synthetic facts as institutional findings.

The pack extends the IR-605 Conversation schema without changing the frozen [`general-tools/conversation_set_v1.json`](../general-tools/conversation_set_v1.json) or its lock. Its seven scenario families are L01 long Manuscript, L02 middle/late evidence, L03 repeated and manual compaction, L04 original-detail recovery, L05 revocation, L06 partial outage, and L07 interrupted research. Each has ten distinct Conversation IDs: six development and four held out. Cases share no source across splits. The 70 planned 100-page Manuscripts and planted facts are in [`sources.json`](sources.json); their `planned_not_ingested` state is deliberate. The `harness_setup` field names conditions the collection harness must actually induce and record. A case with an unfired condition is not evidence for that condition.

## Review before freezing

1. A named **label reviewer** checks every prompt, expected task, source title, page and quote against an ingested, versioned source fixture. They resolve the planned fixture status, edit incorrect cases, and sign an IR-605 `label_review.json` against the final set digests. An agent cannot sign this step.
2. The **evaluation owner** checks that each family still has at least ten distinct cases, development and held-out sources are disjoint, the IR-605 rubric version and thresholds are approved, and the scenario conditions can be induced. The owner records the fixture/corpus digest and freezes the final pack with `eval_conversations --write-lock` **only after** the named review. Keep this draft version for audit; publish any edited version under a new set ID.
3. Two **independent output reviewers** assess each counted Conversation using IR-605 packets and the same rubric. A separate **adjudicator** resolves disagreements. Record their names and decisions in the campaign review artifacts. None is assigned or impersonated here.
4. The evaluation owner records the signed lock path, label-review digest, source snapshot, rubric, thresholds and freeze time in the campaign manifest. Counted outputs must postdate that lock. Keep the source fixture and the old baseline set immutable.

## Free preflight performed on this draft

From `backend/`, run:

```text
python manage.py eval_conversations --set ../docs/evaluation/long-context-draft/conversation_set_v1.json --validate --min-conversations 70
python -m pytest apps/ai/evaluation/tests/test_long_context_pack.py -q
```

The first command reports 70 cases, ten per family, no split leakage and no coverage gap. The test checks every proposed page/quote against `sources.json`, refuses a seven-case family and confirms the original baseline lock still matches. These are structural checks of a draft, not source verification or human approval. IR-605 scoring and campaign preflight remain blocked until the fixtures, named review, signed freeze and real run manifests exist. The existing `--counted` gates must remain in force; never pass `--allow-draft` to describe a quality result.

## Rubric for human label review

For every turn, confirm that its intended task is supported by the source and that the prompt does not reveal the planted answer. Check whether the specified page is truly middle/late in the actual Manuscript, whether a partial read is reported honestly, whether a compaction preserves goal/order/selection and recovers originals, and whether revocation removes derived content. For outage and interruption, verify the recorded fault fired and the final answer uses only committed, still authorized evidence. Mark an unsupported or uninducible case for correction; never silently count it as a pass.

IR-605's proposed quality targets remain task completion ≥90%, claim support ≥95%, citation support ≥95%, and applicable page support ≥95%. A family with fewer than ten distinct reviewed cases is **inconclusive** even if all its observed cases pass. Three repeated real-provider runs and independent reviews are separate campaign requirements under IR-755.
