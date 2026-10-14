# Fixed-workflow pilot — contract, labelled baseline and approval gates

**Ticket:** IR-542 (T0/T1), a subtask of IR-551 under epic IR-146. **Status: prepared for human review, 2026-10-12.** An AI agent wrote this. It decides nothing. Every row marked **OPEN** or **NOT APPROVED** stays that way until the named person records a decision. The implementing agent signs nothing (`CLAUDE.md` §What AI does not decide).

**What this pack is for.** The later tickets build fixed workflows: metadata counts (IR-543), a durable queue (IR-544, IR-545), candidate previews and screening (IR-546), topic-match counts (IR-547), owned run URLs (IR-548) and named comparison (IR-549). IR-550 then evaluates them. Before any of that is built, this pack does three things:

- it says what a correct answer looks like for each kind of question;
- it pins what IRIS returns today, as a test fixture, so each later change shows up as a diff;
- it lists the approvals that must exist before anything is switched on.

| File | What it holds |
|---|---|
| this README | The contract, the approval table, the gates and the campaign budget |
| [`proxy_audit.json`](proxy_audit.json) | Audit of the 113 public proxy questions: pinned SHA-256, development/held-out membership, pilot-family coverage |
| [`backend/apps/ai/evaluation/fixtures/fixed_workflow_baseline.json`](../../../backend/apps/ai/evaluation/fixtures/fixed_workflow_baseline.json) | Synthetic snapshot S0: six Records, two populations, relevance labels, seven cases. Each case has a target `contract` and today's `baseline` |
| `backend/apps/ai/tests/test_fixed_workflow_baseline_http.py` | Runs each baseline case through authenticated `POST /ai/ask/`, the `/ai/ask/stream/` `done` event and the reopened conversation. Vendors come from the composition override, and any outbound HTTP fails the test |
| `backend/apps/ai/evaluation/tests/test_fixed_workflow_fixture.py` | Checks that the fixture and the audit agree with themselves and with the pinned proxy file. Needs no database |

## 0. Sources, and a conflict recorded up front

The ticket names "the fixed-workflow specification and revised proposal dated 12 October 2026" as its source. **That document is not in this repository and was not found in Confluence** (CQL `text ~ "fixed workflow"` returned nothing for October 2026). This pack is built from:

1. **The IR-551 and IR-542 descriptions.** These are the nearest copy of the 12 October decisions. Under `CLAUDE.md` §Source-of-truth, Jira is **not** a requirements authority. Every figure below that comes only from Jira is marked **[Jira]**.
2. [Proposal 13](../../architecture-review/13-bounded-research-agent-proposal.md), including its owner decisions of 2026-10-11, and [ADR-038](../../adr/038-bounded-research-lane-for-ask-iris.md), which is **Proposed**, not accepted.
3. The code on `main` at `b43f826`.

**Needed from a person:** commit the 12 October specification, or an ADR amendment that carries it. Until that happens, the [Jira] figures have no repository authority. A later ticket that relies on them inherits the same gap.

## 1. Direction and limits (AC 1)

| Item | Recorded value | Source |
|---|---|---|
| Direction | **Fixed workflows first.** Application code decides which Records are candidates, how they are counted and what completeness label applies. A planner (ADR-038's research lane) is not used for these question shapes | Proposal 13 §1 "A now, B later"; IR-551 [Jira] |
| Ordinary candidate limit | **At most twenty distinct candidate Records** are screened for presence, listing and topic-match questions. "Distinct" means distinct `Record.id`, not chunks, versions or owners | IR-551 [Jira] |
| Early preview | Candidates may be shown **before screening finishes**, each marked **relevance pending**. A pending candidate is never described as a match | IR-542 [Jira] |
| Subset language | Every topic answer says it covers **the candidates assessed, of the Records you can see**. No answer claims a topic is absent from the repository. "No assessed match among N candidates" is allowed; "there are no papers on X" is not | IR-551 [Jira]; consistent with `routing/lanes.py` `LIST_WORDING` |
| Latency goal | **95 successful final answers under 10 s per 100 submissions**, measured at 100 simultaneous distinct uncached questions. This is a **soft goal**, not an observed capacity. Nothing has measured it | IR-551 [Jira] |
| Ordinary deadline | **30 s end to end**, counted from the original submission. It keeps any authorized partial result, and the queue is bounded and fair. A retry or fallback does not restart the clock | IR-551 [Jira] |

**Where `main` differs from this contract today.** These were found by reading the code. The cases marked as pinned have a test in the baseline fixture.

- **Changed by IR-547.** `research/workflows.py::topic_count` screened every visible Record up to `AI_SCREEN_MAX_RECORDS` (500) and fell back to the top 10 beyond that. It is deleted. A topic count now selects at most twenty distinct candidates through the same workflow as a listing (§12). b02's baseline is changed deliberately; its diff is the evidence.
- **Changed by IR-543.** With the research lane on, "How many papers are in the repository?" matches the fixed `count` rule (`routing/router.py::_fixed_lane`), and `research/metadata_count.py` now answers it from `COUNT(DISTINCT id)` before topic screening is considered. b01's `count` baseline pins it (5 records, no model call). Before IR-543 it went to topic screening and no database count ran.
- With the lane off, which is the default, no count or listing is returned at all. The question gets a passage answer (b01, b02 lane-off).
- A disclosure-refused Record is reported only as "could not be assessed". The wording does not separate *not eligible for AI* from *the screener was unsure* (b02: "2 could not be assessed" merges `rainfall-note` and `flood-warning`).

## 2. Populations, identity and labels (AC 2)

There are two populations. They are kept separate on purpose: a metadata count must not change because AI may not read a paper.

| Population | Predicate | Used by |
|---|---|---|
| **Metadata count** | `Record.objects.visible_to(asker)` limited to `PUBLICLY_VISIBLE_STATUSES` (the catalogue the asker can browse), counted as `COUNT(DISTINCT id)` | IR-543. Uses no AI at all |
| **AI assessment eligible** | The metadata population **and** the disclosure gate permits the content to reach a vendor (`CompositionRoot.vendor_permits()`) | IR-546/IR-547 screening |

- **Identity.** A Record is its `id`. Two versions, two owners or three chunks are still one Record, which IR-510's `count_records` already tests.
- **Snapshots.** Each count names its snapshot: the asker, the visibility predicate and the moment it was read. A Record that changes during a run is re-checked before it is shown. `_count` already returns "The readable papers changed during counting" when they disagree. The fixture's snapshot is **S0**.
- **Relevance labels** are made per Record and per written criterion: `relevant`, `not_relevant` or `uncertain`. They are given for every Record, including ones the asker cannot see and ones AI may not read, so a population mistake shows up as a wrong count rather than a missing label. In S0, the human-relevant `flood-warning` Record is not AI-eligible. A correct workflow therefore reports it as **unassessed**, not as excluded.
- **Citation labels** are Record + page + verbatim quote, the [ADR-023 format](../README.md#the-label-format). They are never chunk ids.
- **Outcome states each case must land in:**

| State | Meaning |
|---|---|
| `exact_metadata_count` | A database count over the metadata population. No AI |
| `subset_topic_count` | Assessed matches among at most twenty candidates, with exclusions, uncertain and unassessed counts shown separately |
| `relevance_pending_preview_then_assessed_subset` | The listing equivalent of the above |
| `scoped_passage_answer` | Paper Chat answers from its own Record only |
| `cited_answer` | A passage answer whose citations meet the citation labels |
| `explicit_unavailable_with_sources` | The answer model is down. No substitute text is generated; sources are still returned (ADR-008) |
| `partial_with_all_unassessed` | The screening model is down. Every candidate is unassessed, and no zero is claimed |

**Labeller:** the S0 relevance labels were written by the IR-542 author, an AI agent, on synthetic text. **No person has confirmed them**, and they are not human labels until someone does. That review is the first item for the exploratory quality reviewer (§5).

## 3. Proxy question audit (AC 3)

Full detail is in [`proxy_audit.json`](proxy_audit.json). In summary:

- **Pinned source:** `docs/evaluation/proxy_starter.json`, SHA-256 `222a3871…862b`, last changed by `4418b1a` (IR-467), on the 40-paper arXiv proxy corpus. A test fails if the file changes without a re-audit.
- **113 questions, 73 with passage labels,** in nine kinds (mechanism 33; ten each of the other eight).
- **Pilot-family coverage: zero.** No question carries a metadata count, a topic-match count, per-Record relevance labels, a Paper Chat scope or a named two-Record comparison.
- **15 questions can be adapted:**
  - ten "which work…?" cross-paper questions, for presence and listing;
  - five "which paper in the repository…?" decline questions, for the no-assessed-match wording.
  
  Each needs Record-level relevance labels before it can score a workflow.
- **Split:** all 113 are **development**, and **held-out is empty**. Every question has already been read while tuning (IR-133, IR-394, IR-463–467, IR-481–486), so none of them can serve as held-out evidence.
- **The 60-question design** (six per family, a 30/30 development/held-out split) **stays an exploratory proposal**. Six examples per family cannot show category reliability. The evidence-decision runs found the same thing at two per category (`eval_evidence`, 2026-10-06: "every category inconclusive"). Writing those questions is not part of this ticket.

## 4. Deterministic baseline (AC 4)

The fixture holds seven cases: b01–b07. They cover the metadata count, topic-match count, presence listing, Paper Chat scope, passage citation, answer-model failure and screening-model failure.

Each case runs on both endpoints. Every run checks four things:

- the routing lane;
- the listing rows and completeness label, with each Record appearing once;
- the coverage wording, and that every citation or source is within the allowed Records;
- that the invisible and refused Records never appear anywhere in the response.

The reopened conversation must then return the same listing.

**No paid provider calls.** Vendors come from `use_composition_root`. Jev is replaced by `ScriptedDecisionModel`. Any `httpx` send fails the test; every vendor adapter and the `openai` SDK go through it.

**Execution status.** The fixture-integrity tests pass locally. The database-backed HTTP tests could not run in the authoring environment: no Postgres role was available, and creating one was not permitted. They run in CI's pgvector job. Their result is reported on the PR, not here.

## 5. Approval table (AC 5) and reviewers (AC 6)

**Nothing in this table is approved by this pack.** "Recorded" means a statement exists in the repository. It does not mean a person approved this pilot's use.

| Endpoint | Pilot purpose | Data sent | Retention | No-training | Fallback | Approval for **this pilot** |
|---|---|---|---|---|---|---|
| Voyage contextualized embeddings + rerank (ADR-015, Accepted 2026-09-02) | Query embedding, candidate ranking | Query text; chunk text for reranking | **Not recorded** (ADR-035 notes ADR-015's terms "cover training, not retention") | Training happens unless the account opts out. The opt-out toggle is **not confirmed flipped** (ADR-015 §2026-09-20 note) | Full-text retrieval (`DegradableRetriever`) | **OPEN.** The opt-out must be confirmed first |
| OpenAI-compatible endpoint, `screen` task (ADR-036, Accepted 2026-09-15) | Title/abstract screening | Criterion, titles, abstracts | OpenRouter: "as long as reasonably necessary"; Groq: not recorded | OpenRouter `data_collection: deny`; **Groq: none recorded** | Every candidate unassessed (b07) | **NOT APPROVED.** The vendor and model for `screen` are not named |
| Same endpoint, `answer` task | Grounded answer, comparison | Question, selected passages | As above | As above | Explicit unavailable state with sources (b06) | Existing ADR-036 approval; **endpoint approval for pilot traffic is OPEN** |
| Jev via OpenRouter Decisions (`typesafe/jev-1.13`) | Routing, question screening | Question, ≤5 prior questions, corpus description | Unstated | No training (owner, IR-485) | `route` backup, then the passage lane | **Proposed** in ADR-038 §9 and not accepted in the document |
| Docling-serve (self-hosted, ADR-016) | Extraction | PDF bytes, on premises | n/a | n/a | None (no flat-text fallback) | Not a vendor transmission |

**Source conflicts, recorded and not resolved here:**

1. **Jev approval.** ADR-038 is Proposed and awaiting a named approver. ADR-035 says the no-training term was "accepted by the owner (IR-485)". TRACEABILITY.md says IR-499 is "marked Done" while "the ADR document's named approval … not reconciled".
2. **Retention.** ADR-035 requires retention to be "verified and approved first" before shadowing. ADR-035's later section and ADR-036 (2026-10-10) say retention is acceptable if no training happens. IR-551 [Jira] says CIT-U permits retention. **Retention permission does not grant training permission or endpoint approval.**
3. **External transmission.** `docs/security/SECURITY.md` §8 says permission is "UNCONFIRMED. Do not assume it". ADR-015 (2026-09-04) says embedding is "no longer gated on an external governance sign-off". ADR-036 calls SECURITY.md §8 stale, but no change has been made to it.
4. **Voyage opt-out.** ADR-015 requires the toggle to be flipped before any content is sent. Its 2026-09-20 note says real content was sent with the opt-out unverified, and no confirmation has been recorded since.
5. **Groq.** ADR-036 names it a sanctioned vendor. ADR-035 and ADR-038 record no no-training terms for it, and it is not approved for `route`.

**Reviewers and owners:**

| Role | Person | Status |
|---|---|---|
| Exploratory quality reviewer | **Jive Tyler Revalde** | Recorded by IR-542/IR-551 [Jira]. Exploratory only; this role cannot support institutional quality claims |
| Independent second reviewer | **OPEN** | Must be named before any institutional quality claim |
| Institutional authority (data transmission, retention) | **OPEN** | Needed for conflicts 2–3 |
| Budget and deployment owner | **OPEN** | Needed before any campaign spend or enablement |

## 6. Pilot metrics and gates (AC 7)

All metrics are **declared before measurement**. They are reported separately and never folded into a single score. Every report states its sample size, its failures and any usage that is unknown.

| Metric | Definition | Threshold |
|---|---|---|
| Metadata count correctness | Exact match to the database predicate at the named snapshot | Must be exact; any miss blocks |
| Topic-match precision / recall | Over assessed candidates, against human relevance labels | **Owner sets** the trade-off between missed matches and false matches. **OPEN** |
| Uncertainty rate | Uncertain + unassessed, divided by candidates | **Owner sets. OPEN** |
| Citation support | Each cited page contains the labelled quote (ADR-023 matching) | **Owner sets. OPEN** |
| Latency | Share of successful final answers under 10 s, at stated concurrency | Soft goal 95/100; the 30 s deadline is a hard limit |
| Error rate | Failed, unavailable or deadline-exceeded runs divided by submissions | **Owner sets. OPEN** |
| Cost | Physical attempts, input/output tokens and US$, per stage and per run | Within the stage values below |

**Gates. Each one blocks only the enablement it names.**

| Gate | Blocks | Status |
|---|---|---|
| Per-stage and per-run values: physical attempts, output tokens, cost | IR-545 enablement and any paid run | **OPEN.** Proposed values need owner approval. The enforcing mechanism exists (§10); every value is an unset, required setting |
| Queue sizing (depth, per-user fairness, worker count) | IR-544/IR-545 enablement | **OPEN.** Depth and per-user caps are enforced once set (§10); no value is approved and no sizing for 100 simultaneous submissions has been done |
| Shared provider quotas across workers, retries and fallbacks | Any concurrent pilot run | **Mechanism built** by IR-545 in a shared store, not per worker (§10, ADR-041 Proposed). **Values OPEN** |
| Endpoint approval per §5 row | Traffic to that endpoint | **OPEN** for every row |
| Quality/error trade-offs above | IR-550's verdict | **OPEN** |

**Draft approval text, for a person to adopt or change. Not signed:**

> *I, [name], approve [endpoint] for [purpose] in the IR-551 pilot, sending [data], on the recorded terms [retention / no-training], with fallback [x]. This does not approve training on CIT-U data, other endpoints, or deployment. Date: [ ]. Recorded in: [ADR/section].*

## 7. Campaign budget and deferred scope (AC 8)

There is **one proposed evaluation campaign** across every IR-551 subtask and fix [Jira]. It is not approved. Paid evaluation, institutional transmission and deployment each still need their own approval.

| Limit | Total | Protected 25 % reserve | Spendable before reserve |
|---|---|---|---|
| Physical attempts | 480 | 120 | 360 |
| Input tokens | 500,000 | 125,000 | 375,000 |
| Output tokens | 80,000 | 20,000 | 60,000 |
| Cost | US$15.00 | US$3.75 | US$11.25 |
| Active minutes | 60 | 15 | 45 |

A retry, fallback or re-run counts against the same campaign as a physical attempt. Coding-agent usage is separate and is not counted. Spending into the reserve needs the budget owner's approval.

**Deferred, and not delivered by IR-551:** screening uploads or extractions for instructions, scoring, quarantine and evaluating a classifier.

- **IR-505's unfulfilled scope.** ADR-038 §10 defers *chunk* injection screening to IR-505. Upload and extraction screening is not recorded anywhere as anyone's scope.
- **Residual risk.** Passage text and abstracts reach the screening and answer models without being screened. A planted instruction in a paper can skew how that paper is screened or worded inside the asker's own visible Records. It cannot widen visibility, change counts that come from the database, or cite a Record outside the run. Those limits are enforced in code: `visible_to`, the disclosure gate and code-owned identity (`_rows`).
- **Also out of scope:** bulk deletion of historical reasoning, and any automatic deployment.

## 8. Metadata counts as built (IR-543)

IR-543 implements the **Metadata count** population of §2 inside the existing `count` lane. It is reachable only where the research lane already is (`AI_RESEARCH_LANE=on`, development only until IR-504); nothing here widens that switch.

- **Code.** `apps/ai/research/metadata_count.py`, called first by `routing/lanes.py::_count`. A question with a topic left in it ("about flooding") is not a metadata count and still goes to topic screening (IR-547's scope).
- **No model.** A closed rule set reads the question, one `COUNT(DISTINCT id)` counts, and the sentence is assembled in code. The `answer`, `screen` and `resolve` models are never called for the count.
- **Supported predicates**, all stored on `Record`: classification, PSCED area, record type, completion year (a year, a range, `since`/`after`/`before`) and the IP flag. Names are read from the taxonomy tables, so nothing is invented.
- **Declined by name, with no count:** a publication year (IRIS stores completion year and the two are never equated), relative dates ("last year", "recent"), fields it does not store (author, adviser, department, keywords, budget, ...) and a question naming two values of one field.
- **Population.** `visible_to(asker)` and Paper Chat scope, narrowed to `PUBLICLY_VISIBLE_STATUSES`. Staff, owners and a student therefore get the same number, and a draft is never counted.
- **Reader-visible parts.** The count, the stated predicate, the snapshot time, the unit ("distinct IRIS records, not unique scholarly works"), titles that appear on more than one counted Record (flagged, still counted separately), records with no completion year when a year was asked, and AI eligibility, described separately and only over the asker's own counted Records. `listing.count` carries the same facts as structured data and is stored on the Turn, so a reopened transcript keeps the original snapshot.
- **Not done here:** grouping ("by classification"), topic-match counts, a metadata question asked inside Paper Chat without widening (it stays a passage answer), and any run with the research lane off.

## 9. Durable queued questions as built (IR-544)

IR-544 lets a reader leave and come back to a question. It ships **off** (`AI_DURABLE_ASK=False`). The §6 queue-sizing and shared-quota gates still block switching it on; IR-545 is where they are built. The design is [ADR-040](../../adr/040-durable-queued-ask-iris-questions.md), which is **Proposed**.

- **Same transport.** With the switch on, a question asked over `POST /ask/stream/` inside a Conversation is queued. The response streams the run's journal: `run_queued`, `run_started`, the existing events, then `done` (or `run_failed`). Every event has an SSE `id:`. `GET /ask/runs/<uuid>/stream/?after=N` replays from that cursor and tails. Older clients ignore the new names. One-off questions and `/ask/` JSON are unchanged.
- **One run, one Turn.** `AskRun` holds the owner, the original deadline (30 s, [Jira], never moved by a retry), its attempts and one terminal outcome. Each Celery delivery claims a new `AskRunAttempt`. Only the current attempt can write, so a redelivery or a restarted worker cannot add a second Turn. The run's `turn` is one-to-one.
- **Deletion wins.** Writing the Turn locks the Conversation first, and deleting a Conversation locks it too. A deleted conversation is never written back.
- **Leaving unsubscribes.** Closing the stream stops reading the journal and nothing else.
- **Public only.** The journal never holds reasoning or the router's probabilities. Replay re-checks ownership, re-filters citations and sources to the Records visible now, and rebuilds `done` from the Turn the way a reopened transcript is. `Turn.reasoning` is still written (IR-381). No policy to stop that has been recorded, and nothing historical is deleted.
- **Measured with fakes only.** `apps/ai/tests/test_durable_ask_http.py` drives submission, disconnect, the worker, reconnect, redelivery, a superseded attempt, deletion before and during the answer, both deadline paths, a foreign run and changed visibility, all with deterministic providers. No claim is made about real-provider throughput or queue behaviour under load.

## 10. Shared capacity and spend controls as built (IR-545)

IR-545 builds the mechanism that §6's quota and queue gates need. **It approves no number.** The design is [ADR-041](../../adr/041-shared-provider-admission.md), which is **Proposed**. It ships **off** (`AI_PROVIDER_ADMISSION=off`). `AI_DURABLE_ASK` now refuses to start without `AI_PROVIDER_ADMISSION=enforce`.

- **Fail closed.** Every limit is a required setting with no default. Under `enforce`, any unset limit refuses every paid attempt. The §7 figures appear in `backend/.env.example` as an illustration only, marked not approved.
- **One shared ledger.** Postgres, through its own `admission` connection, with the campaign row locked for every admission. Two independent processes contending for one lane limit of 3 admit exactly 3. With the lock removed, the same test admits 4.
- **Every physical attempt.** The first try, a retry and each fallback model each reserve separately. The SDK's hidden retries are off under enforcement. Covered paths: chat completions, tool calls, Voyage embedding and rerank, and Jev decisions.
- **Worst case before sending.** A reservation holds input bounded by bytes, the completion cap (always sent, tool calls included), the cost at the dearest model that may answer, and active time. It is then settled to what the vendor reported. Unreported usage stays at its reservation, never zero. An unsent attempt is released.
- **Leases.** A dead worker's reservation holds its slot until its lease (its own timeout plus grace) ends. It is then abandoned and charged in full. A stream renews its lease, and a refused renewal stops it.
- **Campaign.** The §7 ceiling's five limits are enforced. The protected 25% stays closed until `AI_ADMISSION_RESERVE_RELEASED` records the budget owner's release. Paid load, probes and debugging go through the same adapters and share it. `manage.py provider_campaign` prints spend against both ceilings.
- **Queue.** A submission is refused as `503 busy` (`queue_full`, `user_queue_full` or `not_configured`) before anything is created, so one asker cannot fill the queue. The original 30 s deadline bounds every vendor call a worker makes, and retries do not reset it. A run whose refusals cost it its answer journals `capacity_limited` before `done`. Its answer is the explicit unavailable state with its sources. No client renders `capacity_limited` yet.
- **Measured with fakes and real Postgres only.** No vendor was called and nothing was billed. The `MeteredAdapter` fake stands where the vendor adapter stands. No throughput or latency claim is made.


## 11. Candidate previews and the screened listing as built (IR-546)

IR-546 builds the **presence/listing** half of the fixed workflow inside the existing `listing` lane. It is reachable only where the research lane already is (`AI_RESEARCH_LANE`); nothing here widens that switch. It adds no screening-model approval: §5 still lists the `screen` endpoint as **NOT APPROVED**.

- **Code.** `apps/ai/research/listing.py` (selection, screening, wording), called by `routing/lanes.py::lane_events`. The reader-facing events are `candidates_selected` and `candidates_updated`. They are journalled and replayed like every other public event (§9).
- **Candidates.** One ranked list from the approved word, meaning and passage signals, merged by Record (`rank_record_candidates`). At most **twenty distinct Records** are selected. Twenty is a code constant, not a setting: changing it needs measured screening recall, latency and cost on human-labelled pilot data. A failed, uncertain or AI-restricted candidate stays in the twenty and nothing replaces it, so a retry cannot widen the list.
- **Preview.** As soon as the candidates are selected, each is announced as `pending` with its title. A pending candidate is never described, counted or listed as a match. Updates carry a state by record id and nothing else, so a repeat or a replay cannot add a card.
- **Screening.** Candidates are sent in batches of `AI_SCREEN_BATCH_SIZE`, with at most `AI_SCREEN_CONCURRENCY` batches in flight, each on a worker thread that carries the question's deadline, workload and admission run. A model may answer include, exclude or uncertain for a handle it was issued, with a quote copied from that paper. Anything else, and every failure, leaves the paper `unassessed`, never excluded. Spend is charged on the request thread.
- **Uncertain papers.** If limits allow (`AI_SCREEN_RECHECK_MAX_RECORDS`, `AI_SCREEN_RECHECK_PASSAGES`, and time left of at least one screening timeout), a few passages are read for an uncertain paper and it is asked once more. A failed recheck leaves it uncertain. The decision records where its quote came from: title, abstract, or a passage and page.
- **A paper AI may not read** is counted as a candidate and as unassessed, never sent to a model and never named in the preview, the list or the transcript. This keeps the README §1 rule that a disclosure-refused Record is reported only as "could not be assessed".
- **Access is read again** before every send, before every update the reader sees, and before the final list. A paper that became unreadable disappears without a count; one whose text changed since it was sent loses its decision. On a reopened conversation and on replay the reader sees only the Records they can see now, the wording is rebuilt from what remains, and a quote that no longer appears in its source reads as unassessed.
- **Wording** is written in code. It states the matched, not-matched, uncertain and could-not-be-assessed totals, "These are matches found, not a complete list of the papers you can see", whether more candidates were found than screened, and whether search ran on word matching only. Zero matches among assessed candidates says "other relevant papers may exist". When no candidate could be assessed the result is `inconclusive`. No candidates is "a search result, not proof that none exist".
- **Deadline.** The listing stops at `AI_ORDINARY_WORKFLOW_DEADLINE_SECONDS` (30), counted from the start of its workflow, or at the queued run's original deadline when that is sooner. Decisions already made are kept and the rest are unassessed.
- **Not done here.** Owned run URLs (IR-548), named comparison (IR-549), any measurement of screening quality, latency or cost, and any real-provider run. Topic-match counts and the screening cache are §12 (IR-547). The `selected`, `included`, `excluded`, `uncertain` and `unassessed` figures describe a screened subset, not the repository.
- **Measured with fakes only.** `apps/ai/tests/test_listing_workflow_http.py` drives the HTTP, SSE, queued-replay and reopened-conversation boundaries with deterministic providers. The 10 s soft goal is not measured: no vendor was called and nothing was billed.

## 12. Topic-match counts and the screening cache as built (IR-547)

IR-547 extends §11's workflow to **"how many papers match a topic"** in the `count` lane, and adds a per-reader screening cache that both workflows use. It is reachable only where the research lane already is, and approves no screening model, no cache enablement and no cross-reader sharing.

- **Same candidates, same decisions.** A topic count is `screen_listing(..., count=True)`: at most twenty distinct Records, previewed `pending`, screened, access read again before every send, update and output. The count is the number of `included` candidates, computed in code. A model never writes or extrapolates a number, and a reply carrying anything but `decisions` is rejected whole. A metadata question ("How many papers are in the repository?") is still answered first by IR-543's database count, with no model.
- **Wording.** "7 matches among 16 assessed of 20 selected candidate papers, with 4 not assessed." Uncertain papers are assessed and never matches ("…, 3 of them uncertain"). The sentence then names the criterion, the method (`title_and_abstract_screening`) and the version (`screen-` and a digest of the prompt and reply schema), and says the figure counts topic classifications among the selected candidates only, is not a catalogue metadata count, and that other relevant papers may exist. `done.listing.topic_count` carries the same figures as data.
- **Inconclusive, zero and pending.** Nothing assessed is `inconclusive` and never "0 matches". Zero matches among assessed papers is a subset statement. A pending candidate contributes nothing. No candidates is "a search result, not proof that none exist".
- **Replay.** A Turn stores only the run's criterion, method and version. Every figure and the sentence are rebuilt from the candidates the reader may still see, so revoked access, a changed title or a quote that no longer holds lowers the count on reopen and on queued replay.
- **Cache.** `AI_SCREEN_CACHE` (**off by default**) remembers a reader's include, exclude and uncertain verdicts in `ScreeningJudgment` (migration 0025): a decision, its verbatim quote and where it was found, with no title, abstract or passage. A paper that could not be assessed is never remembered. The key digests the Record's title and abstract, its active extraction, the criterion, the vendor, model, fallbacks and data policy, the prompt and reply schema, and `AI_SCREEN_CACHE_POLICY`. Any change is a different key. Listing and count share rows when their criterion text is identical.
- **A hit grants nothing.** The cache is consulted only for already-selected candidates that are readable and disclosable at that moment. The quote must still be in the Record as it is now, and the final list re-checks access and content as for a fresh verdict. A cached uncertain paper is rechecked like any other. A hit can neither add a candidate beyond the twenty nor skip distinct-Record accounting.
- **Per reader only.** Another reader's verdicts are never read. A cross-reader cache is a count channel (ADR-027 §3, ADR-038) and **needs a named person's approval before anything shares it**; nothing here does. Enabling the per-reader cache also needs the policy label set (`AI_SCREEN_CACHE_POLICY`), which makes earlier verdicts misses when it changes.
- **Races.** Writers update a row by key or lose the insert to the row already there; both are decisions about the same content, so either is kept. A cache that cannot be read or written never fails a count.
- **Observed, not claimed.** `done.listing.observed` reports cache hits and misses, model calls, estimated prompt tokens and select/screen/finish/total milliseconds for that run, with a note that a warm run does not show fresh-model capacity. These are this run's observations, not a measure of the 10 s goal or of capacity.
- **Not added.** No automatic full-catalogue topic scan, no scholarly-work de-duplication (a record is still the unit), and no real-provider run.
- **Measured with fakes only.** `apps/ai/tests/test_topic_count_http.py` drives cold, warm, changed content, extraction, model, policy, criterion and prompt, revoked access (before, during and after), concurrent writers, zero, inconclusive, malformed, timed-out and unavailable screens, the queued journal and the reopened transcript with deterministic providers and real Postgres.
