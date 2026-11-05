# IR-753 long-context case pack — proxy-based review draft v2

**State: not ready / blocked.** This pack has no named human review, freeze lock or counted output. It is a review proposal, not approved ground truth. No paid provider was called.

The cases use the existing **40-paper arXiv proxy corpus** and its development/held-out paper split. The [`sources.json`](sources.json) references copy ten question/page/quote bindings from [`proxy_starter.json`](../proxy_starter.json), six development and four held out. The new questions and task expectations are unreviewed. The original, human-reviewed [`general-tools/conversation_set_v1.json`](../general-tools/conversation_set_v1.json) and its lock remain unchanged.

There are 70 proposed Conversations: ten distinct source-bound cases in each of L01 long Manuscript, L02 middle/late evidence, L03 repeated/manual compaction, L04 exact-detail recovery, L05 revocation, L06 partial outage and L07 interrupted research. Source titles do not cross splits. The `harness_setup` field specifies a condition to induce and record; a user prompt alone never proves a fault or compaction occurred.

## What the 40 papers can and cannot establish

They are the correct corpus for a matched comparison with the earlier IR-605 baseline. Their page/quote references can be checked against existing source labels. **Their length and the position of the selected evidence within a full Manuscript have not been verified here.** This draft therefore cannot claim that L01 exercised a long document or L02 reached middle/late evidence. Those scenarios need source-length inspection and, if the 40 papers do not contain suitable examples, a separate versioned set of genuinely long, permitted Manuscripts. Expanded-corpus results must be reported separately from matched 40-paper comparisons. Do not invent 100-page sources to fill this gap.

L03–L07 also need an executable harness that records compaction, access revocation, tool failure or worker interruption. IR-736 owns deterministic long-context continuity contracts; IR-753 owns the reviewed evaluation cases. Until the condition actually fires, its case remains unmeasured.

## Review and freeze sequence

1. A named **label reviewer** inspects every new prompt, intended task, page, quote and acceptable uncertainty against the permitted source. They check whether each source is genuinely long enough for L01/L02. Remove or replace unsupported cases, then sign an IR-605 label-review file against the final set digests. An agent cannot sign this step.
2. The **evaluation owner** confirms ten substantively distinct cases per proposed reporting family, source/topic split, executable scenario setup, corpus digest, rubric and thresholds. A family with fewer than ten reviewed cases is inconclusive. Save edits under a new set ID; retain this draft and the old baseline.
3. Only then run `eval_conversations --write-lock` with the named non-fixture label review. The freeze command rejects this draft while labels are unreviewed or corpus ingestion is unverified. Keep the signed lock and review digest in the campaign manifest before opening held-out outputs.
4. For counted outputs under IR-755, two **independent human reviewers** assess each Conversation. A separate **adjudicator** resolves disagreements. Record their actual names and verdicts. Three repetitions, funding/provider/data approvals, and real execution evidence remain separate gates.

## Free checks on this draft

From `backend/`:

```text
python manage.py eval_conversations --set ../docs/evaluation/long-context-draft/conversation_set_v1.json --validate --min-conversations 70
python -m pytest apps/ai/evaluation/tests/test_long_context_pack.py -q
```

These check schema, 10-per-family counts, split leakage, bindings against the existing proxy question references, rejection of a seven-case family, and refusal to freeze unreviewed labels. They do **not** establish that the source is long, the fault setup fired, or a human approved the labels. IR-605 campaign manifest preflight requires a frozen set and real run files; it must remain blocked here rather than be simulated with invented outputs.

The inherited proposed targets remain task completion ≥90% and claim, citation and applicable page support ≥95%. No result from this draft is a CIT-U research finding.
