# IRIS Privacy Policy — institutional review draft

**DRAFT FOR REVIEW — NOT EFFECTIVE.** Draft identifier: `privacy-review-2026-10-30-01`. No effective date or institutional approval has been assigned. This is proposed text for the CIT-U pilot, not a finding of compliance. Every **institutional decision required** marker blocks final publication. The existing interim notice remains in place.

## Operator, scope and contact

This draft covers personal information handled through registration, roles, research submissions, institutional reviews, publication, AI features and operation of the CIT-U IRIS pilot. It includes information about account holders and people whose information appears in submitted material.

**Institutional decision required — P1:** Confirm the controller/operator's full legal identity, address, DPO or privacy contact and verified request channel. CIT-U is the proposed institutional owner. Confirm the applicable arrangements for minors and others who cannot independently provide required consent. No contact or institutional authority is assumed by this draft.

## Data and sources

The code evidence identifies the following categories; the operating team must verify the actual pilot before publication:

| Category | Information handled and source |
| --- | --- |
| Accounts and roles | Names, institutional email, password hash, role, verification and account status, Student program or Adviser college/department, role requests and approvals; provided during registration or institutional account administration |
| Research and files | Titles, abstracts, author/owner/adviser details, affiliations, research/IP metadata, manuscripts, supplements, versions, consent stamps and extracted text; supplied by submitters or import operators, including information about other people in those materials |
| Review and workflow | Reviewer identities, decisions, comments, clearances, assignments, revisions, document requests and deadlines; created by users and the workflow |
| AI activity | Questions, rewritten questions, answers, citations, model-generated reasoning, summaries, conversation/research metadata and embeddings; supplied by readers or generated during processing |
| Operations and security | Notifications, download/deletion requests, audit events, session activity, account and IP-related authentication/lockout information; generated during use and administration |

**Institutional decision required — P2:** Validate this inventory, including actual hosting logs, backups, imported material and any sensitive or privileged information. Determine what users must supply, what is optional and the consequence of not supplying it. Do not characterize education or research-participant information as harmless merely because it appears in a research system.

## Purposes and grounds

Observed purposes include creating and verifying accounts, approving roles, managing research and files, routing institutional reviews, providing authorized catalogue access, supporting configured AI features, communicating workflow activity and maintaining security/accountability records.

**Institutional decision required — P3:** Approve a purpose-by-purpose processing-ground assessment, including sensitive information and information about coauthors, reviewers and research participants. Identify when consent is genuinely required, how it may be refused or withdrawn, and any other grounds that permit continued processing. Do not use Terms acceptance, a privacy acknowledgment or a submitter's consent as a blanket basis for processing everybody's information. Any evaluation, secondary research or training use needs its own explicit assessment and disclosure; none is authorized by this draft.

## Access, recipients and external processing

Registration details are handled by RDCO and system administrators. Approved Adviser details are exposed through the signed-in adviser directory; the exact fields must be checked against the deployed endpoint and IR-587 before the final notice is approved.

Research access is controlled by role, ownership, adviser assignment and publication state. Current code grants office roles broad access to nondeleted records. Signed-in users can see published catalogue records. This is not anonymous internet publication. Conversation APIs restrict access to the owner; operational administrators' privileged access must be documented separately rather than promising that no administrator could access stored information.

Implemented AI integrations can transmit questions, context and research passages to inference providers and transmit passages or queries for embedding/reranking. Code supports Groq/OpenRouter inference and Voyage embedding/reranking. The actual deployment may enable a different subset or configuration. Email delivery also uses a configurable external service. Conditional or evaluation-only integrations must not be described as universally active.

**Institutional decision required — P4:** Identify actual recipients/processors, hosting/email/storage/backup/logging providers and AI providers, their purposes, processing locations, transfer safeguards, contracts, training/data-use settings and retention. Verify authorized categories of research before sending them externally. A request setting that denies provider data collection is not proof of all vendor handling. No local-only or zero-retention promise is made.

## Browser storage

Current frontend code keeps an access token in memory and a refresh token in session storage. It also uses browser storage for login-attempt/lockout information and locally saved record/opportunity choices. Those choices do not currently synchronize between devices.

**Institutional decision required — P5:** Verify the production site's complete browser-storage inventory, purposes and lifetimes, including anything added by hosting or analytics. Approve any required user choices and final wording; do not claim that the code inventory establishes the absence of all tracking in deployment.

## Retention and deletion

**Current behavior, not an approved retention schedule:** Conversations store questions, answers, reasoning and associated data. The Conversation model does not define a general automatic retention expiry. Owner-initiated conversation deletion cascades to its turns. Research deletion generally marks a record deleted rather than erasing every underlying item; accepted research requires RDCO deletion review. Audit records are designed to survive deletion of referenced users or records.

These behaviors do not establish retention durations for institutional purposes, backups or external providers. Deleting a conversation through IRIS is not proof that every backup or provider-held copy has been erased.

**Institutional decision required — P6:** Approve retention periods or criteria separately for accounts, research/files/extractions/vectors, review history, conversations/reasoning, notifications, audit/security records and backups. Specify triggering events, exceptions/holds, disposal methods, accountable owners and provider-side handling. Review existing no-expiry conversation behavior before promising a duration. Retention changes that need automation require separate implementation and verification.

## Rights, requests and consent

The final notice must explain applicable rights and how to request information, access, correction, restriction/deletion or other available remedies. Where processing relies on consent, it must explain withdrawal and its effect. A request may require assessment against applicable rules and retention duties; the final notice must not promise unrestricted erasure.

**Institutional decision required — P7:** Establish the request and complaint channels, responsible office, proportionate identity verification, response arrangements, escalation and approved explanations of lawful exceptions. Include the appropriate NPC complaint route in the final notice. Rights exist independently of whether IRIS has a self-service button; no such tool is promised here. Refusal, withdrawal and privacy requests must remain distinguishable from accepting Terms.

## Security and policy changes

The code includes password hashing and access checks. These observations do not establish all production security controls. The operating team must verify privileged access, hosting/storage security, incident response and the accuracy of all final security statements.

**Institutional decision required — P8:** Approve incident/reporting arrangements and the procedure for notifying users of material policy changes. Assign the final version and effective date. Proposed future implementation records the user, action, document version and time; historical signup booleans are not evidence of acknowledgment or consent to this replacement policy. Approved text is intended for a public, versioned `/privacy` page; that route is not implemented by this draft.

Reviewer references: [NPC right-to-be-informed guidance](https://privacy.gov.ph/the-right-to-be-informed/), [Data Privacy Act](https://privacy.gov.ph/data-privacy-act/) and [NPC consent guidelines](https://privacy.gov.ph/wp-content/uploads/2023/11/NPC-Circular-No.-2023-04_Guidelines-on-Consent_07Nov2023.pdf), consulted 2026-10-30. These frame review questions, not a conclusion that the pilot is compliant.

Review companion: [review checklist and future development tasks](README.md).
