# IR-123: disclosure notice and external AI processing review

Prepared 2026-10-30 against task baseline `9f52887`. **Pending CIT-U DPO / legal
review.** This is an engineering inventory for review, not institutional approval
or a claim that existing consent covers the processing below.

## Finding and correction

`frontend/src/lib/dpaTerms.ts` said that data was not shared outside CIT-U.
External embedding, reranking and generation paths now exist. The notice now
describes those paths and manuscript extraction, and exposes the pending review
status. Its checkbox explicitly mentions external AI processing. The clipboard
export is generated from the displayed sections so the two cannot drift.

Consumers are `DpaConsentInline` (submission), `DpaConsentModal` (read and copy),
and `SettingsPage`. Signup's separate interim data notice and university policy
documents remain tracked in IR-214; this change does not replace them.

## Processing inventory from code

| Processing | Data and destination | Repository evidence |
| --- | --- | --- |
| Manuscript extraction | PDF bytes and filename go to the configured Docling-serve instance. The documented deployment runs this within the deployment, not at an external AI vendor. | `backend/apps/ai/extraction/docling_client.py`; ADR-016 |
| Embedding | Manuscript text and search queries go to Voyage AI's contextualized-embeddings endpoint. Manuscripts are split into passages for indexing. | `backend/apps/ai/providers/voyage.py`; ADR-015 |
| Reranking | Query text and candidate passages go to Voyage AI to order results. | `backend/apps/ai/providers/voyage.py` |
| Answers and research assistance | Questions, relevant conversation context and selected manuscript content go to the configured language-model endpoints. These may include intermediary providers and model hosts. This is not a guarantee of de-identification: text may contain personal or confidential information. | `backend/apps/ai/providers/openai_compatible.py`; `backend/apps/ai/inference/profiles.py`; `backend/apps/ai/research/`; ADR-036, ADR-038 |
| AI Overview | The configured summary model receives a page-organized prompt assembled from the active manuscript's chunks, potentially the whole paper. | `backend/apps/ai/overview/service.py::_generate`; `backend/apps/ai/overview/pages.py::build_page_prompt` |
| Disclosure checks | Record eligibility is evaluated by the disclosure policy before permitted vendor processing. This policy is an engineering control; it does not establish that the notice has been institutionally approved. | `backend/apps/ai/policy/`; `backend/apps/ai/research/context.py`; `backend/apps/ai/overview/service.py` |

This inventory establishes implemented capabilities, not the production providers
or actual historical transmissions. Deployment credentials and real research
data were not read. Provider retention, training settings, processing countries,
subprocessors and contractual protections have not been verified by this task.
ADR-015 removed its old governance-signoff implementation precondition; this
change does not silently reinstate it as a new runtime rule. IR-123's outstanding
DPO review of the notice remains a separate requirement.

## Institutional decisions and evidence still required

- [ ] CIT-U's DPO / legal reviewer approves or revises the complete notice,
  including purpose, recipients, lawful basis and rights wording. Record the
  reviewer, role, date and exact approved revision on IR-123.
- [ ] The deployment owner supplies the actual provider and model-host list,
  including intermediary services, processing countries, retention and training
  settings, and applicable agreements. Review every configured fallback too.
- [ ] CIT-U decides whether the current RDCO contact process is the accepted
  pilot mechanism for withdrawal, and supplies an actionable contact route.
- [ ] Agree the revised notice's effective date and re-collection procedure for
  existing authors, including records already indexed under the older wording.
  IR-123 expressly requires consent to be re-collected when embedding/parsing is
  implemented. Editing a notice does not perform that step.
- [ ] Decide how affected records are handled before renewed consent and how
  refusal/withdrawal affects indexes, AI outputs and provider-held data. Confirm
  deletion/retention wording against current soft deletion and backup behavior.
- [ ] Record completed re-collection evidence and a deployment decision before
  claiming the full issue is resolved or collecting real pilot consent.

No new consent version, forced re-consent flow, backend transmission gate,
withdrawal workflow or data migration is implemented here. Existing
`dpa_accepted_at` / `dpa_accepted_by` stamps are untouched and are not evidence of
acceptance of this revised notice. Those controls need the institutional
decisions above; this PR must not be presented as completing IR-123.

## Verification

`frontend/src/components/compliance/DpaConsent.test.tsx` exercises the expanded
submission notice and the modal's real Copy content action. It checks external
processing disclosure, pending review status, unchecked consent, and that every
displayed modal heading and paragraph is included in the clipboard output.
The original notice fails both regression cases. Final suite, typecheck,
lint/build and review evidence are recorded on the PR and Jira issue.
