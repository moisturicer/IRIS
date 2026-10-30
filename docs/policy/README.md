# IR-214 institutional policy review package

**Status: DRAFT FOR INSTITUTIONAL REVIEW, 2026-10-30.** Lee confirmed the drafting direction and shared understanding. This is not institutional approval, legal sign-off, an effective policy or authorization to deploy changes. The existing interim data notice remains in place. IR-214 remains `not-ready` for final policy publication and implementation.

## Read this package

| File | Purpose |
| --- | --- |
| [Terms draft](terms-review-draft.md) | Proposed pilot Terms with decisions T1–T9 explicitly unresolved |
| [Privacy Policy draft](privacy-review-draft.md) | Current processing evidence, proposed disclosures and unresolved decisions P1–P8 |
| [Confirmed decisions](IR-214-decisions.md) | The interview outcomes and their approval boundary |
| [Data inventory](IR-214-data-inventory.md) | Code evidence and operational verification still needed |

The pilot's original dead-link defect was addressed through the interim notice in IR-540 / PR #273. IR-214's title and original acceptance criteria describe an earlier state; its comments retain the interim decision. Draft documents do not fulfill the requirement for approved, readable product policies. No application routes, database changes or enforcement behavior are delivered in this package.

## Review responsibilities and publication gates

The team prepares the material. Lee coordinates review. CIT-U is the proposed institutional policy owner, subject to confirmation. The university DPO reviews privacy commitments; an authorized Terms approver must still be identified. Engineering review or merging these files does not count as approval of the policies.

| Decision | Reviewer to establish or confirm | Evidence required before publication |
| --- | --- | --- |
| Owner, authority, eligible users and any minor-user arrangements | Authorized institution representative; DPO as applicable | Confirmed identity, scope and sign-off authority; T1/P1 resolved |
| Processing purposes, grounds and any required consent | DPO and responsible institutional offices | Purpose/data/ground assessment; P2/P3 resolved, including third-party and sensitive information |
| Research ownership and permissions | Authorized IP/research policy owner and Terms approver | Applicable rules and approved permission wording; T3/T4 resolved |
| Real deployment and external recipients | Operating team, DPO and institutional owner | Enabled features/providers, destinations, contracts, safeguards and authorized research categories; T5/P4 resolved |
| Retention and deletion | Records owners, operating team and DPO | Category-specific schedule, exceptions, disposal and backup/vendor handling; P6 resolved and implementation gaps addressed |
| Privacy, support and incident channels | Offices that will actually handle requests | Verified contacts, request/complaint procedure and incident responsibility; T6/P7/P8 resolved |
| Restrictions, appeals and service terms | Authorized Terms approver | Enforcement/appeal authority, availability, closure and any legal provisions; T7/T8 resolved |
| Acceptance and policy changes | Terms approver, DPO and engineering | Approved rollout, wording, versions, dates and tested behavior; T2/T9/P5/P8 resolved |

Every **institutional decision required** marker is a blocker for final publication. Record reviewer identity, authority, date, exact document version and conditions. Recheck the documents against the deployment after implementation; code defaults alone are insufficient. Do not remove draft warnings or publish these files as effective policies merely because a documentation PR merges.

## Proposed future development tasks

These are proposals confirmed by Lee, **not completed features or newly created Jira issues**. Create and scope implementation tickets after institutional decisions and approval. Each task needs a real Jira key; the numbers below are list items, not issue identifiers. Preserve the current interim notice until its approved replacement is ready.

1. **Public, versioned policy pages.** Create `/terms` and `/privacy`, readable without sign-in, with approved version/effective date and a way to read the applicable historical text. Opening from signup must preserve entered information. Verify keyboard access, link destinations and readable rendering.
2. **Distinct registration actions.** Present the relevant Terms agreement and Privacy Policy acknowledgment distinctly. Identify any purpose-specific consent separately, using approved wording. Preserve accessible labels, error association and form state when a user reads a document.
3. **Versioned acceptance/acknowledgment records.** Record the user, action type, document version and timestamp for applicable actions. Retain historical signup booleans as historical evidence without backfilling acceptance of documents that did not exist. Define handling of obsolete versions, repeated requests and audit evidence. Any migration must be verified against a realistic database copy.
4. **Separate purpose-specific consent.** Record consent only for purposes determined to require it, including the relevant purpose/text version and events needed to establish grant or withdrawal. Specify refusal/withdrawal effects under approved policy and distinguish these from Terms acceptance and per-disclosure consent. Do not invent a lawful processing ground or assume that one user's consent covers other people.
5. **Existing-user review.** Prompt users to review relevant approved policies before new submissions or Ask IRIS questions. Preserve authorized access to existing information and the privacy contact process. Define revision rollout, refusal and any renewed acceptance/consent with institutional reviewers before building the gate.
6. **Backend enforcement.** Enforce applicable approved requirements at the API/service boundary, including direct requests and any queued Ask IRIS paths that are enabled. Define the applicable version and time at which a requirement is checked. Do not rely on disabled frontend buttons. Preserve existing authorization checks and do not turn the policy gate into new record-access authority.
7. **Behavioral verification.** Test refusal, withdrawal, version changes and access preservation. Include direct-API bypass attempts, historical accounts, independently required actions, obsolete versions and replayed requests; verify no submission/question is created when an applicable requirement is unmet. Show that withdrawal stops the applicable consent-dependent processing without asserting universal erasure or loss of access to existing information. Test genuine workflow outcomes and record executed evidence in traceability.

Retaining or expiring conversations is an additional implementation decision if the approved schedule differs from current behavior. The Conversation model stores questions, answers, reasoning and associated data and has no general automatic retention expiry. Establish the institutional rule before promising a duration; do not silently add a schedule while implementing acceptance records.

## Validation and handoff

This package changes documentation only. Check Markdown integrity, local links and factual statements against code. No frontend lint/build, backend tests or migration runs are claimed for these drafts; product checks belong to the implementation tasks. Record any documentation CI result separately from policy approval.

Handoff sequence: team draft review → Lee coordinates institutional review → DPO/privacy and authorized Terms decisions → finalize approved versioned text → implement and verify follow-up tasks → confirm operational readiness → publish/replace the interim notice through the authorized release process. No messages have been sent to prospective reviewers by preparing this package.
