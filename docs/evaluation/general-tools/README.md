# IR-589 general-tools evaluation contract, version 1

**Product contract approved by Jive Tyler Revalde, 2026-10-15; implementation and measurements pending.** This protocol belongs to [ADR-042](../../adr/042-general-tools-conversation-contract.md) and the [A01–A15 fixture pack](../../../backend/apps/ai/evaluation/fixtures/general_tools_contract_v1.json). The fixture test validates consistency and source-inspected failure wording. A separate [current-system control](../../../backend/apps/ai/evaluation/tests/test_general_tools_current_http.py) submits all 15 conversations through HTTP, SSE and reopened history with deterministic providers. Its database cases skipped locally because Postgres was unavailable; it makes no claim that the new outcomes pass. See the [acceptance map](acceptance-map.md) and [manifest template](manifest.example.json). No vendor call, institutional transmission, independent human case review or production approval has occurred for this pack.

## Deterministic boundary and result recording

Implement each script with deterministic provider responses at the existing authenticated HTTP, SSE, AskRun and Conversation boundaries. The current-system control uses the existing generic path and one synthetic chunk per paper; it checks the boundary and replay, not the proposed operations, late pages or races. For A01/A09 it also forces the current fixed lane and asserts its failure text on response and replay. Downstream tickets must observe final answers, citations, public events, replay, persisted state and refusal shape at their owned seams. Use real Postgres/shared worker tests for cancellation, redelivery and concurrent revision races. Keep expected new behavior and observed current behavior in separate result columns; a `not_measured` current observation must not be scored as a pass or a failure. The literal current comparison-title and unavailable messages in A01/A09 are pinned to `routing/lanes.py` by the fixture validator; those HTTP assertions remain unexecuted locally without Postgres. Preserve the existing fixed-workflow baseline under its own version.

The fake corpus has three readable papers and one private draft. Reissue handles for each run; revoke or alter a source version where the script says so. Do not build a second retrieval or permission path to satisfy a fixture. A10 separates harmless list markers, an equation and a quoted phrase from an unsupported 37% factual claim. A02 resolves ordinals from the displayed order rather than retrieval order. A09 preserves three distinct outcomes: a paper does not report a field, search found no match, and the provider is unavailable.

## Development and held-out model set

Collect **at least 100 multi-turn conversations** across A01–A15 families, with a stated count per family and for unambiguous supported tasks. Human authors label intended task, useful comparison pair, required evidence, citation/page support, acceptable uncertainty and whether clarification was necessary before models are scored. Separate development and held-out sets by topic and paper where practical; group all turns of one conversation in one split. Do not move a case between splits after seeing model output. Record duplicates, coverage gaps and uncertainty intervals per family. The synthetic pack is a contract seed, not 100 independently labelled examples and not institutional reliability evidence.

Compare three architecture arms on the same permitted corpus snapshot, model, data policy and run budget: current system; improved fixed-lane synthesis; general-tools controller. Keep model comparisons as a separate axis so an architecture change is not credited for a stronger model. Run at least three repetitions for nondeterministic provider behavior, reporting variation rather than choosing the best. Keep development data for prompt/threshold tuning and open held-out results once. No test may tune on held-out topics or the earlier proxy set.

## Human review rubric and proposed targets

For each conversation a reviewer records: task completion (yes/partial/no), pair usefulness (useful/weak/wrong/not applicable), each factual claim's support (source and page or typed metadata fact), citation correctness, omitted relevant caveats, unnecessary clarification, presentation leaks, and access/disclosure violations. A second independent reviewer adjudicates disagreements before an institutional claim. Record reviewer identities and the rubric version in the run record; none is assigned here. Report denominators for each metric and every failure, including cases with no answer.

**Proposed owner-review targets, not approved release gates:** at least 90% completion of unambiguous supported tasks; at least 95% reviewed factual-claim and citation/page support; zero observed access or disclosure breaches in the adversarial suite; and blind human preference over the fixed baseline. A zero-observed breach result is limited by the suite size and does not prove absence of risk. Record queue-inclusive latency and cost per successful task, cold and warm separately, with uncertainty; retain existing load goals as goals until measured. Report capacity as unverified if the approved campaign cannot fit the set. No blended score hides a weak family.

## Reproducibility manifest

Every executed run writes a manifest containing: run ID and timestamp; contract and rubric versions; Git commit and controller/protocol/prompt versions; corpus snapshot ID and content digest (no paper text); source authorization/disclosure policy version; fixture and split digests; paper/topic partition method; model vendor/model IDs, fallbacks, reasoning and summary capabilities; embedding/rerank configuration; retrieval switches and limits; screening/brief/cache policy versions; answer and repair prompts; temperature/seed where supported; deadline, call/concurrency caps and admission/campaign configuration **names and numeric limits only**; worker/store topology; cold/warm cache state; per-attempt usage and cost; reviewer identities; and redacted failure codes. Never store API keys, raw credentials, private paper text or provider continuation artifacts in the manifest.

## Approval boundary

Fixture validation and local fake runs are free and authorized by IR-589. Paid model runs require a recorded funding/campaign owner approval, approved provider data retention and hosting policy, and authorization for the specific dataset before any request. Sending institutional content externally needs a separate explicit approval and disclosure check. Production limits, optional capability switches, thresholds, vendor choices, public web access and rollout require named decisions; this document supplies none. A passing fake suite cannot be used as a production-readiness claim. ADR-042 records the product approval; a human still reviews the implementation before a downstream ticket can be called ready.

## IR-598 conversation set, scorer and pilot documents

- [`conversation_set_v1.json`](conversation_set_v1.json): 105 draft conversations over the 40-paper arXiv proxy corpus (not CIT-U research), all of A01–A15, seven per family, split 62 development and 43 held out by paper and topic. **`label_status` is `draft_unreviewed` and `labelled_by` is empty**: an AI agent drafted every label and a named person must review them before any score counts.
- [`conversation_set_v1.lock.json`](conversation_set_v1.lock.json): one SHA-256 per split. Rewrite it after label review.
- Command: `python manage.py eval_conversations --set ../docs/evaluation/general-tools/conversation_set_v1.json --validate [--lock ...]` from `backend/`. It is free. `--score` reads collected runs and human reviews and calls no model; it requires `--lock`, refuses draft labels without `--allow-draft` and needs run manifests (see the pilot report §3).
- [`pilot-report.md`](pilot-report.md): what was and was not measured, denominators, proposed (unapproved) targets and open gates.
- [`rollout-runbook.md`](rollout-runbook.md): cohort reading, rollback, monitoring and the separate approvals. It records one conflict with the ticket wording for a human to settle.

Nothing in this section is a quality result. No arm was run and no person has reviewed anything.

## IR-606 development replay

The [development replay command](replay.md) collects a selected case through the authenticated public reader protocol, saves its Conversation and reopened Turns, and writes a versioned scorer-readable run file. It records incomplete attempts and explicit missing usage. The local smoke mode uses a deterministic-provider server; it does not run a paid campaign or score draft labels.

## IR-607 review and counted scoring

[Label review, reviewer packets, double review with adjudication, and counted scoring](review.md). The draft set is not yet reviewed, its A09 cases are untagged, and its lock predates corpus and rubric pinning, so it cannot be locked or counted yet.
