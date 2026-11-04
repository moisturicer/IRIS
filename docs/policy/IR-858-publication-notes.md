# IR-858 proposed policy package

Prepared 4 November 2026 against `main` at `c764c3c6`. User instruction: draft complete text from the current repository and embargo design, using editorial judgment as though preparing the final wording.

Read the [Terms](terms-proposed.md) and [Privacy Policy](privacy-proposed.md). They replace open-ended drafting questions with complete proposed prose. They are not institutionally approved policies. The existing interim notice remains live. No public routes, footer links, consent mechanisms or access controls change in this documentation task; IR-858's original implementation acceptance criteria remain outstanding.

## Editorial recommendations

Use the two short footer labels **Data privacy** and **Terms**, targeting public versioned pages after approval. Open each in a new tab with an accessible indication and appropriate opener protection, preserving the registration form. Reuse the shared frame for identical behavior. At 360 px, stack links before copyright; on wide screens align links left and copyright right. Complete IR-856 first and verify keyboard focus, zoom and form preservation in the browser.

Keep Terms agreement, privacy acknowledgment and any purpose-specific processing consent separate. Record the exact version, user and time for each required action; never backfill acceptance from the historical signup boolean. Preserve authorized access to existing records and privacy requests if a user declines a new optional purpose. These are implementation recommendations, not claims about current controls.

Use RDCO as the proposed initial service coordinator and the university DPO as the privacy escalation owner. Confirm that those offices accept these responsibilities and publish their verified contact details. Do not invent addresses. Before launch, publish a deployment-specific processor list covering hosting, email, storage/backups and enabled AI vendors, including destinations, contracts, training settings and retention arrangements.

Adopt a category-specific retention schedule rather than guessing a universal period. Recommend retaining research and review history under the university's approved records schedule, retaining conversations only for a stated user-facing research purpose, and defining security-log and backup periods separately. Assign disposal owners and implement the approved periods before promising automatic deletion. No numerical period is represented as approved or implemented here.

Do not publish a blanket liability waiver, new research licence, disciplinary power, lawful-processing conclusion or claim of statutory compliance. Confirm the institutional operator, authorized Terms approver, grounds for each purpose, handling of minors, research permissions, appeals, incident procedure, verified contacts and effective date with the responsible people. These are the remaining publication decisions; the proposed text is ready for their review, not a substitute for it.

## Embargo evidence and limits

| Statement | Repository authority |
| --- | --- |
| Unknown and Active refuse; None and Released pass only the embargo check; IP and disclosure consent remain independent | `backend/apps/ai/policy/disclosure.py`, `records.py` |
| Submission records the answer, actor and time; unanswered historical records remain Unknown | `backend/apps/records/embargo.py`, migration `0025_record_embargo.py` |
| A date never releases; publication and embargo are independent; adviser/RDCO release embargo, KTTO releases IP | [ADR-052](../adr/052-each-paper-states-its-embargo-and-a-person-ends-it.md), accepted project design, not proof every control has shipped |
| Ordinary catalogue readers do not receive embargo state/date | `backend/apps/records/test_embargo.py` and record serialization |
| No general automatic conversation expiry; deletion relationships cascade | `backend/apps/ai/models/conversation.py` |
| Interim registration notice; disclosure consent wording still pending DPO review | `frontend/src/features/auth/DataNotice.tsx`, `frontend/src/lib/dpaTerms.ts` |

The current gate still rejects every IP-marked record; do not describe the planned KTTO release as an already working exception. Release actions, reminders, consent withdrawal and complete outbound-call enforcement require their own implementation and deployment verification. The policy text deliberately distinguishes adopted release rules from available controls and does not certify end-to-end enforcement.

## Validation scope

Privacy framing was checked against the National Privacy Commission's [right-to-be-informed guidance](https://privacy.gov.ph/the-right-to-be-informed/) and [data-subject rights guidance](https://privacy.gov.ph/data-subject-rights/) on 4 November 2026. A privacy notice describes processing; it is not interchangeable with purpose-specific consent. These references support review and do not establish institutional approval or compliance.

Documentation-only change: inspect Markdown links and `git diff --check`, then review factual claims against source. No runtime behavior or requirement implementation is claimed, so application tests, typechecking, migrations and browser checks are not evidence for these drafts. No production configuration, institutional approval or legal opinion is inferred from source code. Policy publication and the original footer task remain pending.
