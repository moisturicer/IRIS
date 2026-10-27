# IR-598 rollout runbook — cohort, rollback and monitoring (recommendation)

**Status: proposed, 2026-10-16. Nothing here is approved or enabled.** An AI agent wrote this. It binds to [spec §10–§11](../../architecture-review/2026-10-15-askiris-general-tools-spec.md) and [ADR-042](../../adr/042-general-tools-conversation-contract.md). Where the two disagree with the ticket wording, the ADR wins and the conflict is recorded in §1 for a person to settle.

## 1. Conflict recorded for a human

The ticket speaks of a controlled pilot **cohort**. Spec §10 says the controller becomes the default reader path "without an on/off switch or reader lane override". A cohort chosen by a flag or per-reader setting would be that switch, so this runbook does not propose one.

**Reading used here:** a cohort is a set of **accounts that can reach a particular deployment**, such as a pilot environment limited to named pilot accounts. It is not a feature flag and not a lane choice inside one deployment. Whether that reading is acceptable, or whether the owner wants an in-product cohort (which would need an ADR amendment), is **not decided here**. Owner: Jive Tyler Revalde. Until it is settled, no cohort mechanism should be built.

## 2. What a pilot would be

| Item | Proposal | Cost of the choice |
|---|---|---|
| Where | A separate pilot deployment of the release that makes the controller the default | Gain: no switch, rollback is a redeploy. Cost: a second environment to run and keep patched |
| Who | Named pilot accounts only, admitted by the deployment owner | Gain: small blast radius, known readers. Cost: slow to learn from; a small cohort cannot show capacity |
| Corpus | The corpus those accounts are already allowed to read, through the existing visibility predicate | Gain: no second permission path. Cost: results depend on what is indexed and disclosed there |
| Reader notice | The persistent mistake notice below both prompt boxes (A13) | Gain: sets expectations. Cost: none beyond UI |
| Optional public web | **Not required.** The institutional pilot does not wait for it | Gain: fewer approvals. Cost: no external literature |

## 3. Preconditions

None is met by this ticket. Each needs a separate record from a named person.

1. The conversation set has been reviewed by a named person, `labelled_by` is filled and the lock rewritten.
2. A review run has been scored with human reviews on a locked held-out split ([pilot report](pilot-report.md) §4).
3. No access or disclosure breach was observed. Any breach blocks enablement.
4. The owner has reviewed the proposed targets and either approved them as gates or replaced them. As written they are proposals.
5. Admission limits are set and approved. Admission fails closed, so unset limits refuse paid work (`CLAUDE.md` §Provider admission).
6. Capacity has been measured against the approved campaign, or the pilot is declared small enough that unverified capacity is accepted by name.

## 4. Separate approvals, each by a named person

**None is granted by this ticket.** Approving one never implies another.

| Approval | Why it is separate | Owner |
|---|---|---|
| Deployment of the pilot environment | Changes what readers can reach | Deployment owner (not named) |
| Vendor and data retention | Which vendors see content, retention, no-training terms (ADR-035 §11 for shadow work) | Not named |
| Transmitting institutional content to a vendor | Disclosure of Records outside the institution | Institutional authority (not named) |
| Paid evaluation campaign | Spend ceiling, per-run caps, protected reserve | Budget owner (not named) |
| Pilot account list | Who the readers are | Not named |

## 5. Rollback

Rollback is a **code or deployment rollback**, not a switch.

- Redeploy the previous release. Do not edit settings to bypass the controller; none exists for readers.
- Only **new** runs change. A run pins its controller, protocol and prompt versions when it starts, so a run already underway finishes or is cancelled under the version it started with.
- Old and new transcripts stay readable. Old Turns are shown through the safe projection, and the rollout migration deletes no schema.
- Queued runs that the older release cannot execute should be cancelled by the operator, using the existing cancel route, rather than left to fail. If a run has pinned a version the older release does not know, preparation refuses it before any paid work (IR-597).
- After rollback, read `provider_campaign` once to confirm that spend stopped, and record the time, the release and the reason.

**Triggers for rollback (proposed):** any access or disclosure breach; a presentation leak (tool, routing or raw reasoning text) reaching a reader; duplicate final Turns or paid calls after cancel; spend reaching the protected reserve; an unavailable rate above the level the owner sets. The owner sets that level; none is proposed because no data exists.

## 6. Monitoring

Read these while a pilot runs. Each item says what it can and cannot tell you.

| Watch | Source | Cadence (proposed) | Limit |
|---|---|---|---|
| Breach reports (access, disclosure, leaked private title) | Reader reports and sampled review, quoting `/ai/conversations/<id>` | Immediately on report; weekly sample | Zero reports does not prove zero breaches |
| Completion and support on sampled conversations | Human review of a sample, scored with `eval_conversations --score` | Weekly | Needs a named reviewer; small samples give wide intervals |
| Unavailable rate | `AskRun.end_reason` and Turn states (`unavailable`, `capacity_limited`, `run_failed`) | Daily | Says how often answers fail, not whether answers are right |
| Queue-inclusive latency | Submission to final Turn, cold and warm apart | Daily | Needs enough traffic to mean anything |
| Spend against the campaign | `manage.py provider_campaign` | At least daily | An upper bound; open reservations count in full |
| Duplicate Turns and paid calls after cancel | Turn and admission records | Weekly | A race shows only under load |

Reader feedback should go to the reviewer through the team's existing channel with the conversation URL. A reported failure may become a development-set case. It must never enter the held-out split.

## 7. What this runbook does not decide

- Whether the cohort reading in §1 is acceptable.
- Any numeric limit, threshold, cadence or unavailable-rate level.
- Who the reviewers, owners and pilot accounts are.
- Whether to enable anything. That is a human decision after the gates in the [pilot report](pilot-report.md) §7.
