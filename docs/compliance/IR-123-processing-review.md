# IR-123: disclosure notice and external AI processing review

Prepared 2026-10-30 against task baseline `9f52887`. **Pending CIT-U DPO / legal
review.** This is an engineering inventory for review, not institutional approval
or a claim that existing consent covers the processing below.

Updated 2026-10-31: [Planned processing](#planned-processing-designed-not-yet-built)
adds features designed on 2026-10-30 and 2026-10-31 that will process personal
data once built.

## Finding and correction

`frontend/src/lib/dpaTerms.ts` said that data was not shared outside CIT-U.
External embedding, reranking and generation paths now exist. The notice now
describes those paths and manuscript extraction, and exposes the pending review
status. Its checkbox explicitly mentions external AI processing. The clipboard
export is generated from the displayed sections so the two cannot drift.

Consumers are `DpaConsentInline` (submission), `DpaConsentModal` (read and copy),
and `SettingsPage`. Signup's separate interim data notice and university policy
documents remain tracked in IR-214; this change does not replace them.
Settings labels this as the current disclosure notice and explicitly says that
the historical account consent record does not prove acceptance of this revision.

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

## Planned processing (designed, not yet built)

These features are specified in Jira but have no code yet, except where a row
says so. They add personal-data processing that the notice above does not
describe. The notice is **not** changed now, because it describes what IRIS does
today. Each feature updates `dpaTerms.ts` and this inventory when it ships, and
the DPO review should cover them.

| Feature | Personal data, and who sees it | Jira |
| --- | --- | --- |
| Public profiles and people search | For every approved account: name, affiliation (college, department, course) and a role label, shown to every signed-in user and searchable by name, interests, college, department and role. Optional, entered by the person: a photo (JPEG or PNG, up to 2 MB), a bio (up to 500 characters), up to 10 research interests, and a self-declared ORCID iD. Derived: the published papers the person owns or advised, and the accounts that shared a published paper with them. The email address is never shown. A suspended account's profile is hidden. | IR-694 |
| Account suspension | RDCO's reason for suspending an account, emailed to the person and kept in the audit event; a second email when the suspension is lifted. | Same spec |
| View counting | A server-side record of which accounts opened which published paper, kept only to count each account once and never shown or exposed by any API, deleted with the account or the paper; and at most one `ACCESS` audit event per account, paper and 24 hours. **Already in production today:** an `ACCESS` audit event naming the account on every opening of a paper (`RecordViewSet.increment_access`), which the inventory above does not list. | IR-369 |
| Comments on published papers | The comment, the writer's name and an Author badge, shown to every signed-in user. A deleted or removed comment's text is kept and shown to no one. A report keeps a copy of the reported text, the reporter and the reason, visible to RDCO only. A removal reason is sent to the writer. | IR-420 |
| Download requests | The reader's note on each request, RDCO's decline and revocation notes, the grant's dates, and an audit event per download naming the downloader. Once IR-676 lands, each downloaded copy carries the downloader's name and email in its footer and metadata. A request flow already exists without notes or grants. | IR-672, IR-676 |

Decisions these features add:

- [ ] The DPO confirms the lawful basis and notice wording for showing every
  account's name, affiliation and role to all signed-in users, and for making
  them searchable.
- [ ] Decide whether a profile photo needs separate consent, and how it is
  removed on request or when the account is deleted.
- [ ] Set retention for deleted and removed comment text, comment reports,
  per-account view records, download notes and download audit events. None is
  set yet.
- [ ] Confirm that printing a downloader's name and email in each copy (IR-676)
  is acceptable.
- [ ] Update `dpaTerms.ts` and this inventory as each feature ships. As above,
  editing the notice does not re-collect consent.

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
`frontend/src/features/settings/SettingsPage.test.tsx` also verifies that an
existing account's consent is not presented as acceptance of the revised notice.
