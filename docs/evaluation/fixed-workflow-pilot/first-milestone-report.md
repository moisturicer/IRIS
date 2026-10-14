# First fixed-workflow milestone — evaluation report and pilot recommendation

**Ticket:** IR-550 (T9), a subtask of IR-551 under epic IR-146. **Status: prepared for owner review, 2026-10-14.** An AI agent wrote this, and it decides nothing. Every gate below stays **OPEN** until the named person records a decision (`CLAUDE.md` §What AI does not decide). Contract, populations, approvals and budget come from the [pilot README](README.md).

## Recommendation

**Do not enable the pilot.** Nothing here supports a claim about relevance, answer quality, capacity or cost on CIT-U data. What exists is a reproducible instrument, plus a control run that shows it counts correctly. The instrument is ready to measure once the gates in §6 are recorded. Even then, an automatic rollout is not part of the plan (§7).

| Question | Answer today | Why |
|---|---|---|
| Is relevance/answer quality known? | **No.** It is exploratory and inconclusive | There is no pilot-family question set on real or proxy data and no held-out split (README §3). No person has reviewed anything |
| Is coverage honest? | **Yes, by construction, on fakes.** The control run reports every unassessed and restricted Record separately and found no breach | Asserted by tests, not observed on real traffic |
| Is the capacity known? | **No.** It is unverified | No paid burst ran. Under the proposed campaign, a 100-submission uncached burst **cannot fit** at the per-run caps (§4) |
| Is the cost known? | **No.** | No paid call was made. Coding-agent usage is separate and not counted |

## 1. What was built

| Piece | What it does |
|---|---|
| `backend/apps/ai/evaluation/milestone.py` | Scores the metadata count, topic-match count and presence listing against pinned labels. Each measure has its own denominator and its own ground truth (§2). It also checks the held-out lock |
| `backend/apps/ai/evaluation/capacity.py` | Counts a burst. Every submission stays in the denominator. Latency runs from the original submission. Only a real, cold, simultaneous burst of at least 100 distinct questions can make a capacity claim. `plan_burst` refuses a burst that would reach the protected reserve |
| `backend/apps/ai/evaluation/http_driver.py` | Sends questions to a running Ask IRIS over `/api/v1/ai/ask/stream/`, all at once and on one clock. Classifies what each reader finally received. Sanitizes `done` events for publication |
| `backend/apps/ai/evaluation/campaign.py` | Reads the shared admission ledger (IR-545) and plans paid work against what is spendable. Refuses when admission is not enforcing |
| `manage.py eval_pilot_milestone` | Runs a milestone set against a server, or **rescores** a published run file with human review verdicts and judge scores added |
| `manage.py eval_pilot_capacity` | Runs a simultaneous burst. With `--providers real`, it plans against the campaign first and sends nothing if the burst does not fit |
| `backend/apps/ai/tests/test_pilot_milestone_http.py` | Runs snapshot S0 through the authenticated HTTP/SSE boundary with deterministic fakes, sanitizes the output, scores it and asserts the report |

## 2. Measures and their denominators (AC 2)

Every measure is reported on its own and never folded into a single score. A case with no observation counts as **missing**, never as correct.

| Measure | Numerator | Denominator (independent ground truth) |
|---|---|---|
| Metadata count correctness | Cases whose reported `count.total` equals the contract | Every metadata case. The contract count is checked against its population's record keys when the set loads, and a disagreement refuses the set |
| Retrieved-subset topic classification | Per case, the confusion of screener state against the human label | Assessed candidates only |
| Screening precision | Included ∩ labelled relevant | Included ∩ labelled `relevant`/`not_relevant` |
| Screening recall | Included ∩ labelled relevant | (Included + excluded) ∩ labelled relevant |
| Outside both screening denominators | Label uncertain, unlabelled, screener uncertain, not assessed | Reported as counts, never dropped |
| Candidate recall | Labelled-relevant Records among the candidates | **Every** labelled-relevant Record in the asker's metadata population, whether or not the workflow found it. Also reported over the AI-eligible subset |
| Unassessed / coverage | Unassessed candidates; restricted; inconclusive cases | Selected candidates |
| Topic-count consistency | Reported `topic_count.matches` against its own included candidates | Topic-count cases |
| Breaches | A listed Record outside the metadata population; an AI-restricted Record judged or named | Any non-zero is a defect |
| Answer correctness, claim support, citation/page support | The primary reviewer's verdicts | Reviewed cases, claims and citations. The reviewed fraction is shown against every scored case |
| Judge agreement | Judge equals human on the same case | Cases carrying both. **Never interpreted here** (§3) |
| Latency, usage | Observed per case; `listing.observed` model calls, estimated prompt tokens, cache hits | Cases that reported them. Missing ones are listed, never zeroed |
| Security and lifecycle scenarios | The eight named scenarios in `milestone.SCENARIOS` | Each is marked "asserted by tests, not observed in this run" |

**Standing.** A report is `exploratory_inconclusive` unless the tier is CIT-U, a held-out split exists and its lock verifies, and an independent second review exists. Only then does it become `eligible_for_owner_review`. That status is not approval. A public or synthetic sample can never become CIT-U reliability evidence.

**Held-out lock (AC 1).** A set may carry `split: {development, held_out, lock}`. `lock` is the SHA-256 over the held-out cases, their topic's labels and the populations, taken from parsed JSON, so a line-ending change does not alter it. A changed label, a case in both halves or a wrong lock refuses the set. Today, **held-out is empty** (README §3), so no run can be anything but development.

## 3. Human review and model judges (AC 3, AC 4)

- **Exploratory reviewer:** Jive Tyler Revalde (README §5). **Nothing has been reviewed yet.** The control run's `answer_quality.status` is `not_reviewed` and its reviewed fraction is 0/3.
- **How a review is recorded.** A JSON list, one row per case and reviewer: `{case, reviewer, rubric, independent, answer_correct, claims: {supported, total}, citations: {supported, total}}`. `eval_pilot_milestone --from-run <run> --reviews <file>` rescores without asking anything again. The report discloses the reviewers, rubric versions, reviewed fraction and every disagreement between reviewers.
- **Proposed rubric `pilot-rubric-v1`, for the reviewer to adopt or change:**
  - *answer correct*: the answer's figure or list matches what the labelled Records support, with subset wording intact;
  - *claim supported*: each factual sentence is backed by a cited passage of a readable Record;
  - *citation supported*: the cited page contains the quoted text (ADR-023 matching).
- **Independent second reviewer: OPEN.** None is invented. Until one is named, `institutional_quality_claim` is `false` in every report.
- **Model judges.** None was run. If judge scores are supplied, agreement with the primary reviewer is reported on the shared cases, and `interpretable` stays `false`, because the agreement threshold is the owner's decision and is not recorded.
- **Jev calibration: inconclusive.** No suitable development data exists for an approved purpose, and that is recorded here as the finding. Upload/extraction classifier evaluation stays excluded (IR-505).

## 4. Capacity and cost (AC 5, AC 6, AC 7)

**Not measured.** `eval_pilot_capacity` is the instrument. Its accounting is pinned by `test_capacity.py`:

- **Denominator.** Every submission counts: rejected (`503 busy`), failed, timeout (`run_failed` with `deadline_exceeded`), cancelled, unfinished. Preview-only, unavailable, partial, no-results and inconclusive outcomes are **not** successful generated completions.
- **Soft goal.** At least 95 of 100 submissions produce a generated final response within 10 s of the original submission, queue time included. Any final response after 30 s is listed as a deadline violation.
- **Claims.**
  - `measured_goal_met` or `measured_goal_missed` requires real providers, a cold cache, a simultaneous burst and at least 100 distinct questions.
  - A fake-provider or warm-cache burst is `control_only`.
  - Anything smaller or sequential is `unverified`.
- **Budget fit, found by this ticket.** README §7 proposes a campaign but no per-run caps. The only per-run figures in the repository are the illustrative ones the admission tests use (`admission/tests/support.py`: 12 attempts, 60,000 input tokens, 8,000 output tokens, US$0.50).
  - At those caps, a worst-case 100-submission burst needs 1,200 attempts and US$50. That is **more than the spendable 360 attempts and US$11.25 before the reserve**.
  - No per-run active-time cap exists, so active minutes cannot be bounded either.
  - `test_the_proposed_campaign_cannot_fit_a_hundred_uncached_submissions` pins this.
  - More generally, a 100-submission burst fits the proposed campaign only if **each run** is capped at no more than 3 attempts, 3,750 input tokens, 600 output tokens, US$0.1125 and 27 active seconds.

  **Capacity therefore remains unverified.** To change that, the budget owner must set per-run caps, change the campaign or change the burst size. Any of those is a decision, not a measurement.
- **Shared ceiling.** Paid evaluation questions, load submissions, retries, fallbacks, probes and debugging all go through the same admission ledger (IR-545). `eval_pilot_milestone --providers real` and `eval_pilot_capacity --providers real` refuse to start unless `AI_PROVIDER_ADMISSION=enforce` and the work fits before the reserve.

## 5. Control run: snapshot S0, fake providers

Run file: [`../runs/20261014-pilot-milestone-s0-fake-control.json`](../runs/20261014-pilot-milestone-s0-fake-control.json), written by `IRIS_PILOT_RUN_OUT=<path> python -m pytest apps/ai/tests/test_pilot_milestone_http.py`. **Tier: synthetic.** Screening came from a fake that decides from S0's own labels, so precision and recall of 1.0 show that the arithmetic is correct. They say **nothing** about screening quality.

| Measure | S0 result | Reads as |
|---|---|---|
| Metadata count | 1/1 exact (5 records) | Population plumbing is correct |
| Screening precision / recall | 4/4, 4/4 | The oracle was counted correctly, and nothing more |
| Candidate recall | 6/6 (3 owed per case; `flood-draft`, invisible to the asker, is not owed) | Distinct-Record selection reached every labelled-relevant visible Record |
| Unassessed | 2/10 (the AI-restricted `flood-warning` in each topic case) | Restricted Records are counted as unassessed and never named |
| Breaches | 0 | No invisible Record listed; no restricted Record judged or named |
| Topic-count consistency | 0 inconsistent | The reported count equals its own included candidates |
| Answer quality | `not_reviewed`, 0/3 | No person has reviewed |
| Latency | p50 335 ms, p95 514 ms over 3 cases, in-process | Fake providers and the test client. **Not a latency observation** |
| Usage | 4 model calls, about 956 estimated prompt tokens; b01 reported none (no model, by design) | Fake providers |
| Standing | `exploratory_inconclusive` | Synthetic; no held-out cases; no independent review |

**Not run:**

- the proxy corpus, which has no pilot-family labels (README §3);
- CIT-U data;
- any paid call;
- any capacity burst.

## 6. Gates (AC 8): separate, and all OPEN

| Gate | Owner | Status | Blocks |
|---|---|---|---|
| Endpoint approval for each README §5 row | Institutional authority | **OPEN** | Traffic to that endpoint |
| Campaign and per-run values; reserve release | Budget and deployment owner | **OPEN**. No per-run cap is proposed; the illustrative test caps cannot fit a 100-submission burst (§4) | Every paid run, including this evaluation |
| Pilot-family labelled set with a locked held-out split | A labeller who does not tune on it | **OPEN** | Any non-exploratory quality figure |
| Exploratory quality review | Jive Tyler Revalde | **Not started** | The exploratory quality section |
| Independent second review | **Not named** | **OPEN** | Any institutional quality claim |
| Quality and error trade-offs (README §6) | Owner | **OPEN** | A pilot verdict |
| Institutional pilot enablement | Institutional authority | **OPEN** | Switching anything on for readers |

## 7. Operation, reader feedback and rollback (proposed)

**Enablement is manual.** Each switch is changed by a person after its gate is recorded: `AI_RESEARCH_LANE`, `AI_DURABLE_ASK`, `AI_PROVIDER_ADMISSION=enforce`, `AI_SCREEN_CACHE` with `AI_SCREEN_CACHE_POLICY`. No automatic rollout, percentage ramp or scheduled enablement exists, and none is proposed.

**While a pilot runs:**

- `manage.py provider_campaign` is read at least daily against the campaign;
- spend stops before the reserve unless the budget owner releases it;
- run outcomes (`AskRun.end_reason`, `capacity_limited`, `run_failed`) are reviewed weekly.

**Reader feedback (proposed; not built).** Readers in the pilot cohort report wrong counts, missing papers or unsupported citations to the exploratory reviewer through the team's existing channel, quoting the conversation URL (`/ai/conversations/<id>`, IR-548). Each report becomes a labelled case for the development half only. Feedback must never enter the held-out half, because that would contaminate it.

**Rollback.** Set the switch back. Each one fails safe:

- with the research lane off, questions get passage answers;
- with durable ask off, they are answered inline;
- with the screening cache off, verdicts are recomputed.

Rollback deletes no Turn, AskRun, ScreeningJudgment or reasoning history. Bulk historical deletion is out of scope. **Triggers that should prompt a rollback decision:**

- any breach;
- a metadata count that disagrees with its database predicate;
- the campaign reaching its reserve;
- an endpoint approval being withdrawn.

## 8. Deferred, and kept intact (AC 9, AC 10)

- **Comparison quality** (IR-549, "ticket 08") is evaluated only after IR-549 is complete and its comparison limits and data approvals exist. It is not part of this milestone and does not gate it. `milestone.MILESTONE_FAMILIES` scores only metadata count, topic-match count and presence listing; every other case is named as `out_of_milestone`.
- **Adaptive comparison: deferred.** No fixed-workflow weakness was predeclared, so nothing triggers it.
- **IR-505's ingestion screening and quarantine stay unfulfilled.** IR-504's history is unchanged.

## 9. Reproducing

```bash
# Control: snapshot S0, fakes, no network (needs Postgres)
IRIS_PILOT_RUN_OUT=../docs/evaluation/runs/<stamp>-pilot-milestone-s0-fake-control.json \
  python -m pytest apps/ai/tests/test_pilot_milestone_http.py

# Against a running server, as the user whose JWT is in IRIS_EVAL_TOKEN
python manage.py eval_pilot_milestone --set <labels.json> --base-url <url> --tier proxy --providers fake

# Add a reviewer's verdicts later without asking again
python manage.py eval_pilot_milestone --set <labels.json> --from-run <run.json> --tier proxy --reviews <reviews.json>

# Burst control (fakes on the server), then the real burst once its gates are recorded
python manage.py eval_pilot_capacity --base-url <url> --questions <100 distinct.json> --providers fake --cache cold
```

**Local note.** On a Windows checkout with `core.autocrlf=true`, `test_the_proxy_audit_pins_the_proxy_set_it_audited` fails, because CRLF conversion changes `proxy_starter.json`'s bytes. The committed bytes match the pin, and the failure predates this ticket. This report's held-out lock hashes parsed JSON, so it does not have the same problem.
