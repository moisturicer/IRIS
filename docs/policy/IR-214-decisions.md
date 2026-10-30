# IR-214 policy drafting decisions

Status: shared understanding confirmed by Lee on 2026-10-30; review drafts prepared. These are drafting instructions, not institutional policy approval. No product behavior changes are authorized by this record.

## Confirmed direction

- Prepare Terms of Service and a Privacy Policy as drafts for institutional review. Keep the existing interim data notice until the replacement documents are approved.
- CIT-U is the proposed institutional policy owner. The team prepares drafts; Lee coordinates review; the university DPO reviews privacy commitments. Institutional confirmation and the Terms approver remain outstanding.
- Cover the CIT-U institutional pilot only. Commercial customers and other institutions require separate terms later.
- Cover the whole service: accounts, role approval, research submissions, review and publication, AI processing and conversations, and operational records.
- Mark unresolved retention periods, deletion exceptions, privacy contact and request-handling arrangements as **institutional decision required**. Unresolved placeholders block publication of final policies.
- Deliver review drafts, a verified data inventory and gaps requiring follow-up. Product changes are separate work; gaps affecting publication remain explicit blockers.
- Intended destination after approval: public, versioned pages inside IRIS, readable before sign-in. Signup must open them without losing entered information. This is a future implementation requirement, not an implemented capability.
- Proposed signup design distinguishes Terms acceptance, Privacy Policy acknowledgment and any specific processing consent the DPO determines is needed. Acknowledgment must not be represented as blanket processing consent.
- The Terms draft must not propose new ownership rights in submitted research for CIT-U or the developers. Propose only permissions needed for storage, processing, review and display under approved institutional rules. Existing university IP rules and authority to submit coauthored work require institutional confirmation.
- Future acceptance evidence should record document version, user, action and time. Preserve historical signup booleans without representing them as acceptance of replacement policies. Implementation and the existing-user rollout are separate decisions.
- Proposed rollout: existing users review and accept approved Terms before new research submissions or new AI questions. Preserve access to existing information and the privacy contact process. Requires institutional review and separate implementation; no access change is made during drafting.
- Drafts disclose that enabled AI features may send questions and research passages to external providers, retain conversations and model-generated reasoning, and produce answers users must verify. Verify deployed providers, processing locations, retention terms and authority to send particular research before publication. Make no blanket local-processing or zero-retention promise.
- Terms propose authorized submissions, respect for confidentiality and applicable research/IP restrictions, account protection and no bypassing access controls. Uploading does not prove ownership or coauthor permission. Reporting, suspension, enforcement authority, appeals and treatment of existing submissions require institutional approval.

## Existing evidence

- IR-214 comments dated 2026-10-12 and 2026-10-14 record the interim-notice decision and implementation in IR-540, PR #273. The original issue title describes the earlier defect.
- `frontend/src/features/auth/DataNotice.tsx` contains the interim notice; `SignupPage.tsx` associates signup consent with it.
- Signup acceptance and consent for an individual research disclosure are separate facts. Current signup storage is a boolean; it does not identify a policy version.

## Open decisions

Lee confirmed the shared-understanding summary and supplied seven proposed future development tasks, now captured in [the review package](README.md). They follow institutional decisions and approval; they are not completed features. Institutional approval is separate from completion of these drafts. Code inspection and provider verification must distinguish implemented behavior from proposed or disabled features.

Institutional review must settle the policy owner's authority and Terms approver, processing grounds and specific consent requirements, retention/deletion rules and exceptions, privacy contact and request handling, research/IP permissions, operational AI/vendor details, and reporting/suspension/appeal arrangements. Draft completion must not be represented as resolution of these matters.

## Research basis

NPC Circular 2023-04, Guidelines on Consent, distinguishes provision of a privacy notice from obtaining consent for processing. Used to frame the proposed acceptance design; the DPO must determine appropriate processing grounds and consent requirements for the actual pilot.

Source: https://privacy.gov.ph/wp-content/uploads/2023/11/NPC-Circular-No.-2023-04_Guidelines-on-Consent_07Nov2023.pdf (consulted 2026-10-30).
