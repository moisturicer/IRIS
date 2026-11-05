# IR-606 — development conversation replay

`eval_replay_conversations` collects selected development cases through the authenticated Ask IRIS stream and Conversation endpoints. It creates a fresh saved Conversation for each execution, submits turns in order with the `public-1` protocol, and reopens the transcript after each turn. The run file keeps the public answer, citation and source IDs, saved Turn, final reopened transcript, outcome, latency and usage status. It is input for human review and the IR-598 scorer, not a quality score by itself.

The small smoke mode is a separate launch that runs the authenticated API in the command process with **deterministic providers injected explicitly**. From `backend/`, with `IRIS_EVAL_TOKEN` holding a development reader's JWT:

```powershell
python manage.py eval_replay_conversations --set ../docs/evaluation/general-tools/conversation_set_v1.json --lock ../docs/evaluation/general-tools/conversation_set_v1.lock.json --case A01-D01 --smoke
```

`--case` may be repeated for a larger development collection. Held-out cases are rejected unless `--held-out` is given, which needs a frozen lock and, for real providers, recorded approvals ([campaign.md](campaign.md)). The command checks the set lock before any request and writes a versioned file under `docs/evaluation/runs/`. Each run has a new run ID; repeating a case creates a different Conversation. A timeout, cancellation, missing answer, admission stop or failed request is retained as an attempted turn, including when no Turn was saved. Cost is `0` for a fake run and usage is explicitly `missing`; this says nothing about real model cost. Cache state defaults to `unknown`; use `--cache cold` or `--cache warm` only when that state was actually prepared. `IRIS_EVAL_TOKEN` enters only the Authorization header and is never written to the run file.

For a later approved real-provider campaign, use `--providers real`, `--approval-id`, `--data-policy`, `--case-cost-usd`, and `--case-attempts`. The command requires synchronous Ask IRIS, evidence shadow off, and admission enforcement with a **fresh dedicated campaign key** and all approved campaign and per-run limits. The API runs in the command process, so its engine, models and settings match the manifest. Each turn reserves the configured maximum run spend before it starts, so an insufficient case remainder ends in `cap_stop`. The shared admission ledger applies the campaign ceiling before physical calls. The collector reads reservations after each synchronous turn; retries and fallbacks remain separate attempt rows with model, run key, charged tokens, cost and whether usage was reported. The campaign must serve only this collection, or cursor-based attribution is invalid. A timed-out provider call can have missing usage; the ledger keeps its conservative reservation charge. An open reservation makes the case incomplete with `cost_final: false`; its saved charge is provisional and conservative.

Each turn also carries a private `diagnostics` stage read from the run's `ResearchRun` rows (IR-607): `candidates_then_no_results`, `no_candidates`, `provider_failure`, `answered`, `other`, or `not_traced` where no research run was written. Review packets leave it out; see [review.md](review.md).

The manifest records the set and split digests, code and controller versions, protocol and prompt versions, corpus snapshot digest, permission and data policy, model and fallback IDs, retrieval and cache switches, limits and physical attempts. No key, provider continuation artifact, raw reasoning or private paper text enters the manifest. The run file includes the **public reader answer and transcript**, which may contain authorized paper quotations; handle the whole run file with the same access controls as a reader transcript. A named human must review draft labels before scoring, and paid collection, institutional transfer and production use each require their separate recorded approvals.

## IR-740 — collecting the dedicated runtime

`--runtime-url https://<reader edge>` (with `IRIS_EVAL_TOKEN` as above) collects the same cases through the **dedicated AI runtime's** authenticated routes instead of this process: it submits each question to `/api/v1/ai/runtime/runs`, follows the run's status until it ends, and reopens the saved Conversation (`/api/v1/ai/runtime/conversations/<id>`). The edge fetches the grant and fixes the reader protocol exactly as it does for a browser; the token goes only into the `Authorization` header. A later question names the Conversation and the revision the reader saw. A run still active after `--run-deadline-seconds` is cancelled and kept as a `timeout`; a `503 busy` is kept as `cap_stop`; a cancelled or failed run is kept with its outcome. `--depth` is `deep` unless the case should run ordinary.

The run file is the same IR-606 file, with `arm: runtime` and its own identity. It is **never `controller-v1`** and the reader has no engine selector; the arm is a label of which collection this was.

| Manifest field | Value |
|---|---|
| `engine_version` | `ai-runtime-1` |
| `protocol_version` | `runs-reader-1` (the runtime's wire protocol, not `public-1`) |
| `identity` | `{engine: ai-runtime-1, transport: runs-reader-1, schema: runtime-rows-1}` |
| `runtime` | operator-declared facts: depth, `declared_by: operator` |

Rows have the shape IR-606 rows have, so review packets, independent human review, adjudication and scoring read them unchanged. The row keeps the runtime's citations in the order the runtime returned them (`citation_record_ids` equals the saved Turn's citations), the saved Turn, the final reopened transcript, and every public run state observed while following the run. A turn whose sources became unreadable is a `failure`, never an answer.

**What the command cannot see.** The service is not this process, so its provider mode and model are **declared by the operator** (`--providers fake|real`, `--runtime-model`) and recorded as declared. With `--providers real` the command needs the same approval, data policy, case cap and enforced admission as above, and reads each run's physical attempts from the shared ledger by the run's `airun:<run id>` key and `owner = 'ai'`: purpose, purpose version, model, state, reserved and charged cost, and whether usage was reported. The effective model identity used in comparisons comes from those attempts when there are any. No real collection through this path has been run.

**Every run file now says what it is evidence of** (`evidence`). A fake-provider file is `kind: contract`, `human_reviewed: false`, `quality_evidence: false`: it proves transport and contracts, and `eval_campaign --counted` already refuses it. A real file is `collected_unreviewed` until independent human review and scoring. Older run files have no `evidence` key and are read as before.
