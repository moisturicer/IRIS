# IR-598 conversational pilot report — skeleton for owner review

**Ticket:** IR-598, under the general-tools contract ([ADR-042](../../adr/042-general-tools-conversation-contract.md), [spec §9–§11](../../architecture-review/2026-10-15-askiris-general-tools-spec.md)). **Status: prepared for review, 2026-10-16.** An AI agent wrote this and decides nothing. Every gate below stays **OPEN** until a named person records a decision (`CLAUDE.md` §What AI does not decide).

## Recommendation

**Do not enable a pilot on the strength of this report.** What exists is a validated, locked set of draft conversations and a scorer that has only been unit-tested with fakes. No arm was run, no person reviewed a label or an answer, and no money or institutional content was spent or sent. Quality, preference, capacity and cost are all **not measured**.

| Question | Answer today | Why |
|---|---|---|
| Does the controller complete unambiguous supported tasks? | **Not measured** | No arm was run and no human review exists |
| Is claim and citation support known? | **Not measured** | The scorer needs named human reviews; there are none |
| Is there any access or disclosure breach? | **Not measured** | The adversarial families (A11, A12, A15) have labels but no run |
| Is capacity known? | **Capacity unverified** | No paid or burst run; the existing campaign cannot be assumed to fit |
| Is cost per successful task known? | **Not measured** | No paid call was made |
| Is the conversation set ready to score? | **No** | `label_status` is `draft_unreviewed`, `labelled_by` is empty |

## 1. What was measured

Only three things, all free and local, with no database, vendor or institutional content:

1. **Set validation.** `manage.py eval_conversations --validate` checks schema, per-turn fields, duplicate ids, family coverage, the 100-conversation minimum and split leakage by paper title and by topic.
2. **Locked digests.** The same command wrote `conversation_set_v1.lock.json` (one SHA-256 per split) and re-checked the set against it.
3. **Scorer unit tests with fakes.** `test_conversations.py`, `test_conversation_scoring.py` and `test_conversations_command.py`: 24 tests pass. They show the scorer counts and gates correctly on invented reviews. They say nothing about any model.

Run on 2026-10-16 from `backend/`:

```
set general-tools-conversations-v1 (draft_unreviewed): 105 conversations, 36 supported and unambiguous
development: A01=4 A02=4 ... A15=4
held_out:    A01=3 A02=3 ... A15=3
coverage gaps: none
shared across splits (allowed): 0
digests development=b703c23705a8514c held_out=65b4475aa32b2941
valid
```

Lock write and re-check both ended `valid`. Leakage: zero shared papers, zero shared topics, `shared_allowed` is empty. Package suite `python -m pytest apps/ai/evaluation`: 299 passed, 1 failed. The failure is the known Windows-only `test_the_proxy_audit_pins_the_proxy_set_it_audited` (CRLF checkout of `proxy_starter.json` changes its digest); it predates this ticket.

## 2. The set

`conversation_set_v1.json` holds **105 conversations** (2 turns: 70, 3 turns: 28, 4 turns: 7) over the 40-paper arXiv proxy corpus. It is a proxy, not CIT-U research, and nothing measured on it is a finding about CIT-U.

**Partition.** Papers and topics were split together. Six topic groups (23 papers) are development; five groups (17 papers) are held out. A paper appears in one split only, and so does a topic. Within a conversation every turn stays in one split. Nothing may move between splits after output is seen.

| Family | Scenario | Development | Held out | Total | Supported and unambiguous |
|---|---|---|---|---|---|
| A01 | Multi-turn discovery, pair, compare, simplify | 4 | 3 | 7 | 7 |
| A02 | Ordinals follow the displayed order | 4 | 3 | 7 | 7 |
| A03 | Exclusions and honest insufficient results | 4 | 3 | 7 | 5 |
| A04 | Ambiguous alias, exact title, unknown title | 4 | 3 | 7 | 0 |
| A05 | Long paper, late section | 4 | 3 | 7 | 7 |
| A06 | Exact metadata count vs classified topic count | 4 | 3 | 7 | 0 |
| A07 | Different datasets or metrics, no winner | 4 | 3 | 7 | 0 |
| A08 | More detail or simpler wording | 4 | 3 | 7 | 7 |
| A09 | Missing field, no match, outage | 4 | 3 | 7 | 0 |
| A10 | Harmless formatting vs unsupported number | 4 | 3 | 7 | 0 |
| A11 | Access: revocation, stale brief, foreign handle, Paper Chat scope | 4 | 3 | 7 | 0 |
| A12 | Cancel, redelivery, reconnect, concurrency | 4 | 3 | 7 | 0 |
| A13 | Public surfaces and the prompt notice | 4 | 3 | 7 | 0 |
| A14 | Missing summary capability, reasoning-only | 4 | 3 | 7 | 3 |
| A15 | Injection and optional public egress | 4 | 3 | 7 | 0 |
| **All** | | **60** | **45** | **105** | **36** |

**Labels are drafts.** `label_status` is `draft_unreviewed` and `labelled_by` is `[]`: an AI agent drafted every label. 82 evidence entries carry a page and quote copied unchanged from `docs/evaluation/proxy_starter.json`; the drafting script asserted each one exists there. Everywhere else `page` and `quote` are `null`, meaning "some passage of this paper; a reviewer must locate it". No page or quote was invented. Some labels depend on a fact only a reviewer can check, such as "this paper reports no compute budget"; those say so in `acceptable_uncertainty`.

**Limits of the set.**

- Seven conversations per family (four development, three held out). With the default `--min-examples 10`, every family is **INCONCLUSIVE**, and an interval on seven cases is very wide. Splitting results in half is worse. The set meets the spec's "at least 100" and nothing more.
- A04, A11, A12, A13, A14 and A15 test behaviour the harness injects (a seeded private record, a revoked source, a killed worker, a planted document, a provider with no summary support). The conversation text alone does not exercise them. The proxy corpus contains no private record, no injection and no outage.
- A12 outcomes need real Postgres and independent worker processes, not fakes.
- 36 supported-unambiguous conversations is the denominator for the 90% completion target, so that target has at most 36 cases across both splits.
- The set was not checked against a running retrieval stack. Whether each labelled paper can actually be retrieved is unknown.

## 3. Metrics and denominators

The scorer (`conversation_scoring.py`) reports each measure with its own denominator and a 95% Wilson interval, per arm and per family. It does not blend them. A conversation with no answer counts as a failure, never as missing.

| Measure | Numerator | Denominator |
|---|---|---|
| Task completion | Reviews marked `yes` | Reviewed conversations flagged supported and unambiguous |
| Partial completion | Reviews marked `partial` | Same |
| Pair usefulness | Reviews marked `useful` | Reviews where a pair applies (not `na`) |
| Unnecessary clarification | Reviews flagged | All reviewed conversations |
| Claim support | Claims marked supported | Every reviewed factual claim |
| Citation support | Claims whose citation is correct | Every reviewed factual claim |
| Page support | Claims whose page is correct | Claims where a page was judged |
| Presentation leaks, no-answer count, access breaches | Counts | Reported with the number of reviewed conversations |
| Blind preference | Candidate wins, baseline wins, ties | Judged pairs; ties are not dropped |
| Judge calibration | Agreement with adjudicated human verdicts | Items carrying a human verdict |
| Latency and cost | Queue-inclusive latency and cost per successful task | Successful tasks, cold and warm separately |

Architecture arms are `current`, `fixed_synthesis` and `controller`. The scorer refuses to compare arms whose corpus digest, model ids, data policy or limits differ. Model comparison is a separate `--mode model` axis. Fake-provider runs are labelled "contract check only".

**Proposed owner-review targets. These are not approved release gates; no named person has approved any threshold.**

| Target | Value | Denominator |
|---|---|---|
| Completion of unambiguous supported tasks | at least 90% | Supported conversations (36 in the draft set) |
| Reviewed factual-claim support | at least 95% | Reviewed claims |
| Citation and page support | at least 95% | Reviewed claims |
| Access or disclosure breaches in the adversarial suite | zero observed | Adversarial conversations reviewed |
| Blind human preference over the fixed baseline | wins over baseline | Judged pairs |

A target is shown as met only when the interval's lower bound clears it, not-met only when the upper bound falls below it, and otherwise inconclusive. A zero-breach result is limited by the suite size and does not prove the risk is absent.

**Any access or disclosure breach blocks enablement**, whatever the other numbers say. The scorer sets `enablement_blocked` on the first one.

## 4. Not measured

| Item | Status | What it needs |
|---|---|---|
| Arm runs (current, fixed synthesis, controller) | **Not run** | A funding and campaign approval, vendor retention terms, a dataset authorisation |
| Human review of labels | **Not done** | A named reviewer; `labelled_by` filled; a new lock |
| Human review of answers, claims and citations | **Not done** | A named reviewer and a recorded rubric version |
| Independent second review and adjudication | **Not done** | A second named person |
| Blind preference | **Not measured** | Reviewed pairs |
| LLM judge calibration | **Not measured** | Human-adjudicated items; the judge is never a substitute for review |
| Repetition variance (three or more runs) | **Not measured** | Paid or fake-provider runs |
| Cold and warm latency, cost per successful task | **Not measured** | A run on a real provider |
| Capacity | **Capacity unverified** | A 100-plus burst that fits the approved campaign |
| Real shared-store race behaviour (A12) | **Not measured against this set** | Independent worker processes on Postgres |
| UI, accessibility and prompt-notice behaviour (A13) | **Not measured against this set** | Browser checks |
| Optional public web (A15) | **Not built** | A separate policy decision |

## 5. A01–A15 evidence map

"Exists" means a repository artefact is present now; it does not mean the new behaviour passes. See also the [acceptance map](acceptance-map.md).

| ID | Evidence that exists | Evidence pending |
|---|---|---|
| A01 | Seven conversations; contract script; source-pinned current failure text | Controller run, human review |
| A02 | Seven conversations that fix a user-given display order | Controller run, review |
| A03 | Seven conversations, two of them exhausted-topic cases | Run, review |
| A04 | Seven conversations; the third title is deliberately absent | Run with a seeded private record, review |
| A05 | Seven conversations using labelled pages 4 to 10 | Run, review; the control corpus has one page per paper |
| A06 | Seven conversations; two count bases kept apart | Run, review |
| A07 | Seven conversations; reviewer must confirm no shared measure | Run, review |
| A08 | Seven conversations, reusing labelled passages | Run with a provider-call record, review |
| A09 | Seven conversations; outage injected by the harness | Run, review |
| A10 | Seven conversations; the number in turn 2 is a trap, not from a paper | Run, review |
| A11 | Seven conversations; scenario variants in `intended_task` | Run with seeded accounts, review |
| A12 | Seven conversations; harness action named in each turn | Real-Postgres worker run |
| A13 | Seven conversations; surface named in each turn | Browser and serializer checks |
| A14 | Seven conversations; provider mode named | Provider adapter run |
| A15 | Seven conversations; planted text lives in the harness | Run, review; public adapter not built |

## 6. Failures and limits

- One pre-existing Windows-only test failure, described in §1. It was left alone.
- The set is small per family, draft-labelled and proxy-only (§2).
- The lock pins the **draft** content. Any review that edits a label changes the digests; rewrite the lock after review and record who did.
- The scorer has run on invented data only. Its correctness on real review files is untested.
- Nothing here has been shown to a CIT-U reader.

## 7. Gates (all OPEN)

| Gate | Owner | Status |
|---|---|---|
| Label review of the set | A named reviewer | **OPEN** |
| Independent second reviewer | **Not named** | **OPEN** |
| Funding and campaign approval, with per-run caps | Budget owner | **OPEN** |
| Provider data retention and hosting terms | Named person | **OPEN** |
| Sending institutional content to a vendor | Institutional authority | **OPEN** |
| Review of the targets as release gates | Jive Tyler Revalde or delegate | **OPEN** |
| Deployment and enablement | Deployment owner | **OPEN**; see the [rollout runbook](rollout-runbook.md) |
