# ADR-054: Each person answers once whether AI may use their papers

## Status

**Accepted on merge** — 2026-11-02. The decisions are Hermoine Zozobrado's, from a design session under IR-836. Merging this PR records acceptance by Lee Jasmin Adolfo, the project lead, as relayed by Hermoine Zozobrado. Not built yet. No CIT-U data protection officer's review is recorded (IR-123).

It replaces [ADR-051](051-system-admin-account-deletion-and-consent.md)'s Submission consent: decision 14's per-paper half, the last sentence of decision 15, decision 16's submission notice and the first half of decision 18. Everything else in ADR-051 stands, including that withdrawing Signup consent means account deletion. It changes which fact supplies the consent input to [ADR-015](015-voyage-embedding-and-reranking.md)'s disclosure gate.

## Context

ADR-051 made consent to AI a per-paper act, withdrawable per paper. None of that is built. Observed on `main`, 2026-11-02:

- **The disclosure gate reads a per-paper stamp.** `apps/ai/policy/records.py` passes `Record.dpa_accepted`, which `POST /records/<id>/submit/` stamps from a checkbox on Publish's last step.
- **So the gate refuses every draft.** Consent arrives at the last step, but indexing and the AI Overview are queued right after the upload is read (`apps/ai/tasks.py`). They are refused today only because of that order.
- **AI that fills in fields at upload is planned.** It can't run while consent comes last.
- **Signup consent is all or nothing.** Registration refuses anyone who doesn't agree (`apps/accounts/serializers.py`), so today there is no way to have an account and refuse AI.
- **PDF reading is moving to a third party because of hardware constraints.** Docling (ADR-016) needs an 18.6 GB image and prefers a GPU. Its replacement gets its own ADR, written by Jive Tyler Revalde. It matters here because reading a paper will now send it outside IRIS.

## Decision

### What is asked

1. **One notice asks one question about AI.** The notice carries the data-privacy agreement, which having an account requires, and a required Yes or No on AI using the person's papers. This is **AI consent**. Publish no longer asks for consent per paper.
2. **It is asked at sign-up and after every new notice.** RDCO or the System Admin publishes a notice as ADR-051 decisions 16 and 17 describe. Everyone answers, office staff and the System Admin included.
3. **Nobody uses IRIS without answering.** Until they answer the current notice they can only answer, sign out or request deletion, and the server enforces this, as ADR-051 decision 15 does. Each answer is kept with its notice version and time.
4. **A person's last answer stands until they answer the new notice.** A graduate who never signs in again stays as they were.

### What each answer does

5. **Yes is the normal way.** AI may use their papers, subject to the embargo and the IP mark.
6. **No keeps the account normal and their papers away from AI.** They can still upload, search, read, publish and review. AI doesn't touch those papers at all: no third-party reading, indexing, AI Overview, Paper Chat, comparison, collaboration matching or filled-in fields. They fill in the details themselves.
7. **A person who said No can still use Ask IRIS** on papers whose owners said Yes. Their questions still go to AI companies, and the notice says so.
8. **Asking about a No paper says why nothing comes back.** Opening its AI Overview, or asking about that one paper, says the owner did not consent, so nothing is available for AI. This applies to the owner too. A general Ask IRIS question simply doesn't find it. This message is for consent only: an embargo is never named to a reader who may not see it (ADR-052).

### Which answer a paper follows

9. **The Contact person's answer carries the paper.** Co-owners' answers don't count.
10. **A paper keeps the answer it started with.** It takes the Contact person's answer when its draft is created. Changing that answer later, or changing the Contact person, doesn't change it, except as decision 13 allows. A paper with no answer stored, including one with no Contact person, is refused.

### Changing an answer

11. **Settings can change the answer at any time.** Waiting for a new notice could mean waiting indefinitely, and a person must be able to withdraw.
12. **Yes to No only affects papers from then on.** Earlier papers keep their Yes, and what was already processed stays and stays in use.
13. **No to Yes offers two choices, with neither preselected:** all my papers, or only papers from now on. "All" covers the papers they are Contact person of that hold a No, and says plainly that this text will be sent and can't be recalled. The same two choices appear wherever the answer changes to Yes, including the notice pop-up.

### Embargo and the third-party reader

14. **The embargo question still stands, for every paper,** whatever the person answered here. ADR-052 is unchanged.
15. **Reading a paper is an outside call, so the gate decides it.** A paper the gate refuses isn't sent to the third-party reader. While an embargo is active or hasn't been released, nothing goes to any third party and the author fills in the details. A release then sends the paper on, reading included (ADR-052 decision 10).
16. **When the gate allows it, everything runs at upload.** With Yes and no embargo, reading, indexing and the AI Overview start as soon as the file lands.

### Getting there

17. **Existing accounts start unanswered** and answer at next sign-in. Today's per-paper stamps stop counting. IRIS isn't deployed, so no real paper is affected.
18. **Test data answers Yes.** `seed_demo` and `load_corpus` give every account and paper a Yes (IR-815).

## Alternatives Considered

**Consent per paper, on Publish's last step (ADR-051).** A person decides for each paper, knowing what it is. Rejected: the answer arrives after the upload, so AI that runs at upload could never run.

**Consent per paper, as Publish's first screen.** It keeps the per-paper choice and comes before the file. Rejected: one more screen on every submission, for a choice most people answer the same way each time.

**No means no account.** It is the simplest, and matches today's registration. Rejected: refusing AI shouldn't cost someone access to their university's repository.

**Any owner's No blocks the paper (ADR-051 decision 18).** Nobody's refusal can be overruled. Rejected: one person could take a paper out of AI for all its owners. The Contact person answers for it instead.

**No removes what was already processed (ADR-051 decision 18).** It takes full effect at once. Rejected: those papers were processed under a Yes, and each switch would remove and re-index whole papers at a cost.

**No to Yes silently brings every paper in.** It needs no extra choice. Rejected: it sends text the person uploaded while saying No without asking about those papers, and that can't be recalled.

**A paper that switched to No can never come back.** It needs no extra choice either. Rejected: it locks a changed mind out for good.

**Changing the answer only when a new notice appears.** No Settings control to build. Rejected: someone who clicked Yes by mistake could wait indefinitely, and the National Privacy Commission says people can withdraw consent after giving it.

**Indexing waits until submission.** A wrong file or abandoned draft would send nothing. Rejected: it needs its own rule, and uploads already start indexing.

**Read every paper with the third party, then gate only the AI.** Every paper would have its passages ready. Rejected: an embargoed paper would leave IRIS at upload, which is exactly what its embargo is for.

## Decision Rationale

A person answers once, in one place, and can change it. Asking before any upload lets AI that runs at upload work at all, and asking per person saves a question on every submission. Changes only reach forward unless the person chooses otherwise, because text sent to a vendor can't be recalled.

## Consequences

**Positive:**

- AI that fills in fields at upload can run for a person who said Yes.
- A person can refuse AI and keep using IRIS.
- Publish loses a checkbox on its last step.
- One gate still decides every outside call, the third-party reader included.

**Negative:**

- **Withdrawal only reaches forward, and this is the main legal risk.** After a switch to No, earlier papers keep going to AI companies every time someone asks a question, and the person can't stop that. The National Privacy Commission says people can withdraw consent, so CIT-U's data protection officer may object. This needs IR-123's review before real papers are collected.
- **A co-owner's No can be overruled.** If the Contact person said Yes, a co-owner who said No still has that paper's text sent.
- **A wrong file or abandoned draft goes out** for a person who said Yes with no embargo, as soon as it lands, and it is billed.
- **The IP mark comes too late for what runs at upload.** It is set in Details, after the file lands, so a paper later marked as IP has already been sent, unless its owner also answered Yes to the embargo.
- **A No is visible.** Any reader opening a No paper's AI Overview learns that its owner did not consent.
- **Everyone is interrupted by each new notice,** even for a typo, as ADR-051 decision 17 already accepts.
- **A graduate's papers stay under the notice they last answered,** indefinitely.

## MVP Impact

Required before deployment, with ADR-052. Without an answer every paper stays refused. The consent screen, the Settings control and the two choices are new frontend work.

## SaaS Impact

The rules are the same per deployment, and each institution publishes its own notice.

## Security Impact

The gate stays fail-closed: no stored answer is refused. The sign-in block is enforced by the server, not the screen. The new act of changing an answer joins the authorization matrix (`apps/tests/access/`) and is audited. Reading is now an outside call, so a paper the gate refuses must not reach the third-party reader.

## Deployment Impact

One migration for the person's answers and the paper's stored answer. Real papers imported later stay out of AI until they have a Contact person who answered. The notice must name every third party, including the new reader.

## Research Impact

The evaluation's proxy papers keep working once they answer Yes. A No paper is absent from retrieval, so a corpus with No papers measures only what AI may use. No finding about CIT-U research changes, because no real paper has been indexed.

## Related Requirements

`FR-M6-02` and `FR-M6-06` (stable labels).

## Related Tasks

IR-836 (records this) · IR-779 (its spec) · IR-789, IR-790, IR-791, IR-792, IR-793 and IR-800 (consent tickets written for ADR-051, to be rewritten) · IR-123 (the data protection officer's review) · IR-250, IR-811, IR-812, IR-815 and IR-816 (the embargo work) · IR-830 and IR-833 (autofill, which still names local Docling)
