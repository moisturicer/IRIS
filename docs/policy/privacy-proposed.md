# IRIS Privacy Policy

Proposed version 1.0 · Prepared 4 November 2026

Complete proposed wording for the CIT-U pilot. This version is awaiting institutional approval and is not yet effective. It describes the current software; the operating team must confirm the arrangements used by the live service.

## 1. Scope

This policy describes personal information handled by the Cebu Institute of Technology – University IRIS pilot for accounts, research submissions, institutional review, discovery and AI research assistance. It covers account holders and people whose information appears in research, comments or supporting documents.

## 2. Information IRIS handles

| Category | Examples and source |
| --- | --- |
| Account and affiliation | Your name, institutional email, password hash, requested and approved roles, college, program or department, verification status and profile information you provide |
| Research and files | Titles, abstracts, authors and owners, adviser, affiliations, keywords, research/IP details, manuscripts, supporting files, versions and extracted text supplied by users or import operators |
| Review and disclosure | Assignments, comments, decisions, clearances, revisions, deadlines, document requests, disclosure-consent records and embargo answers, including who acted and when |
| AI interactions | Questions, relevant conversation context, answers, citations, generated reasoning where stored, summaries, search vectors and associated processing metadata |
| Service activity | Notifications, download/deletion requests, authentication and session activity, audit events and security information generated during operation |

Research uploads may contain information about coauthors, reviewers, participants or other people. Submit only information necessary for the intended purpose and within your authority. An account holder's agreement cannot stand in for every other person's required permission.

## 3. Why information is used

IRIS uses information to create and verify accounts, assess requested roles, route research for review, manage files and versions, record decisions and clearances, provide authorized discovery and document access, support enabled AI features, issue workflow notifications, and maintain security and accountability.

Account details needed for registration and role assessment are required to complete those steps. Manuscripts, workflow information and submission-specific disclosure choices are needed for the corresponding features. Providing optional information or using AI does not remove the need to respect other people's information and research restrictions.

Terms acceptance, acknowledging this policy and giving consent for a particular processing purpose are distinct. Reading this policy does not grant blanket consent. Where processing depends on consent, its purpose and scope must be identified separately. Other institutional processing requires its own applicable authority; this policy does not declare consent to be the basis for every activity.

## 4. Who can access information

RDCO handles account and role-request administration. System administrators have privileged operational access. Approved advisers appear in a directory available to signed-in users so that a submitter can identify an adviser; the registration notice describes name, email, college and department.

Research access depends on ownership, assigned adviser, office role, publication state and document permissions. Office-role access may extend beyond individually assigned reviews. Published catalogue records are available to signed-in users; this is different from anonymous internet publication.

Conversation APIs limit ordinary access to the conversation owner. This does not mean database or system administrators are technically unable to access stored information. Authorized operational access must remain subject to institutional controls.

## 5. External services and AI processing

Enabled AI features can send questions, relevant conversation context and research text to external providers. Voyage AI integrations support embeddings and reranking. Configured language-model providers generate answers and summaries; the repository supports provider configurations including Groq and OpenRouter. A provider integration existing in the code does not establish that it is enabled in your deployment.

Text extraction and indexing can create additional representations of a manuscript. Summaries may use the whole manuscript, while answers may use selected passages and previous conversation context. Personal or confidential information embedded in that text can travel with it. Avoid putting restricted information into questions.

Hosting, email delivery and other operational services can also process data. The enabled providers, processing locations, retention arrangements and contractual safeguards depend on the actual deployment. Ask RDCO and the university DPO for the verified deployment information before submitting material whose restrictions depend on those arrangements. This proposal makes no local-only, zero-retention or universally enforced no-training claim.

## 6. Embargoes, IP and disclosure consent

The research disclosure check considers intellectual property status, embargo state and the submission's disclosure consent separately. It refuses IP-marked research, research with an unknown or active embargo, and research without the required disclosure consent. An answered “no embargo” or a recorded release clears only the embargo condition.

The review date never releases an embargo automatically. Publication does not clear it, and an embargo does not itself prevent publication or authorized human access. Embargo state and date are shown to owners, the assigned adviser and office staff rather than ordinary catalogue readers.

The adopted release design assigns embargo release to the adviser or RDCO and IP release to KTTO. Some associated controls and reminders may not yet be available. A planned release mechanism is not permission to bypass the current gate. Contact the responsible office about a restriction that needs review.

An embargo controls external AI disclosure of research content; it does not prevent all external processing associated with accounts, email or questions you type. Adding a restriction cannot retrieve information already sent to a provider or copied by an authorized reader. Report new restrictions promptly rather than relying on retroactive removal.

## 7. Browser storage

The frontend uses browser storage for session continuity and local interface choices, including saved choices and login-attempt information. Its authentication design keeps an access token in memory and a refresh token in session storage. Protect your device and end your session on shared devices. Clearing browser storage can remove local choices without deleting server-side records. A deployment must separately disclose any additional analytics or tracking it introduces.

## 8. Retention and deletion

The repository does not establish a complete, category-specific institutional retention schedule. In particular, conversations have no general automatic expiry: they persist until deleted through the applicable process. Stored conversation data can include questions, answers, citations and model-generated reasoning, even when reasoning is not displayed in full.

Deleting your conversation removes its associated questions and answers from the application database. Research deletion commonly marks a record deleted, and accepted research can require RDCO review. Audit records can survive removal of a referenced user or record. These actions do not guarantee erasure of every file, backup, log or provider-held copy.

An approved schedule must account for institutional records duties, research and IP obligations, security, disputes and applicable restrictions. Until that schedule and its disposal processes are established, no fixed automatic deletion period is promised. Keeping information indefinitely is not endorsed merely because automatic expiry is absent.

## 9. Privacy requests and consent withdrawal

You may raise requests concerning access, correction, objection, erasure or blocking, consent withdrawal and other applicable data-protection rights with the university DPO. The university must assess the request, verify identity proportionately and explain applicable restrictions or continuing obligations. A missing self-service control does not prevent you from raising a request.

For submission corrections, account concerns or disclosure restrictions, RDCO can help identify the responsible office. Consent withdrawal is not currently a complete self-service action and is distinct from changing an embargo or deleting a conversation. Do not assume that a request has already stopped queued or future processing until the responsible office confirms the action taken. Withdrawal does not recall earlier disclosures.

Use an established university contact or verified directory to reach RDCO or the DPO. Do not send passwords or unnecessary manuscript content with an initial inquiry. You can also raise a privacy concern with the National Privacy Commission through its published official channels.

## 10. Security and policy versions

IRIS implements password hashing, permission checks and security/audit records. These measures do not guarantee that unauthorized access or loss can never occur. Report suspected exposure or account compromise promptly through the university's established channels. Production safeguards and incident responsibilities must be verified before operating the pilot with real data.

Published revisions must state their version and effective date and explain material changes. Historical signup booleans are not evidence of acceptance of this proposed policy or consent to newly introduced purposes. Changes requiring a separate choice must not be treated as agreed merely because this text was updated.
