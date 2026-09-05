/**
 * RA 10173 consent copy.
 *
 * ---------------------------------------------------------------------------
 * PENDING LEGAL / DPO REVIEW. This is a privacy notice for a real institution.
 * The revision below was made to remove statements that described processing
 * IRIS does not perform; it is not a lawyer's draft and must be reviewed by
 * CIT-U's Data Protection Officer before the pilot collects real consent.
 * ---------------------------------------------------------------------------
 *
 * Why it was rewritten: the previous version asked users to consent to
 * processing that does not exist, which under RA 10173 is worse than asking for
 * too little. Specifically it claimed:
 *
 *   - "Text chunks are loaded ... inside our local Qdrant memory grid".
 *     Qdrant is **explicitly rejected** by ADR-007, which selects pgvector --
 *     and pgvector is not implemented either (the service classes are `pass`
 *     bodies). Nothing in IRIS embeds anything today.
 *   - "vector embedding", "automated algorithmic parsing", "internal layout
 *     tokens during high-performance chunk extractions". Docling is not
 *     implemented; ADR-006 defers it. No document parsing pipeline runs.
 *   - "verify semantic duplications ... against regional indexes". There are no
 *     regional indexes and no cross-institution comparison of any kind.
 *   - "scrub existing vector points from all active server indexes" as the
 *     erasure right. There is no vector store to scrub. The real mechanism is
 *     the delete-request workflow (`records.DeleteRequest`), which is what this
 *     now describes.
 *   - "unique university ID (Student/Faculty card numbers) ... section".
 *     IRIS collects none of these -- see accounts.User / StudentProfile.
 *
 * What IRIS actually does today: PostgreSQL full-text search over a weighted
 * `search_vector` (this works), retrieval-only Ask IRIS answers built from that
 * same index, file storage, and an audit log. If embedding or automated parsing
 * is later implemented, this notice must be updated **and consent re-collected**
 * -- consent obtained for one purpose does not extend to a new one.
 */
export const DPA_REGISTRY_TITLE =
  "DPA Consent Registry (RA 10173)";

export const DPA_REGISTRY_SUBTITLE =
  "Cebu Institute of Technology - University Technology Transfer Office";

export const DPA_TERMS_PLAIN_TEXT = `${DPA_REGISTRY_TITLE}
${DPA_REGISTRY_SUBTITLE}

Republic Act No. 10173 (Data Privacy Act of 2012) Terms

In compliance with the Data Privacy Act of 2012 (RA No. 10173), you consent to Cebu Institute of Technology - University collecting, storing and indexing the intellectual property disclosures, abstracts and manuscripts you submit, for the purposes described below.

1. What we collect
Account details: your name, your CIT-U email address, your assigned role, and your course, department or college as recorded by the university.
Disclosure details: the title, abstract, keywords and classification of each submission, the adviser you nominate, the college of origin, and submission and review timestamps.
Uploaded files: the manuscripts and supporting documents you upload, together with their file type and size.

2. How your submission is used
Institutional search: submitted titles, abstracts and keywords are indexed so that CIT-U students and staff can find research across the university.
Review workflow: your disclosure is routed to the offices you select or that your submission type requires, so they can record a clearance decision.
Audit logging: security-relevant events such as sign-in, document access and document download are recorded so that access to your work can be accounted for.

We do not sell your data, share it outside CIT-U, or compare it against any external or third-party database.

3. Your rights under RA 10173
Access: you may view every disclosure recorded under your account at any time, from My Workspace.
Correction: you may correct your own name and profile details from Settings, and may ask the Research and Development Coordinating Office to correct any submission detail.
Erasure: you may request deletion of a disclosure. The request is reviewed and, once approved, the record and its uploaded files are removed.
Withdraw consent: you may withdraw consent by contacting the Research and Development Coordinating Office. Withdrawal cannot be completed from this system yet, and it does not undo review decisions already recorded.
Complain: you may raise a concern with CIT-U's Data Protection Officer, and with the National Privacy Commission.

Consent Confirmation

Ticking the consent box confirms that you have read these terms and agree to CIT-U processing your disclosure as described above.`;

export const DPA_SECTIONS = [
  {
    title: "Republic Act No. 10173 (Data Privacy Act of 2012) Terms",
    body: "In compliance with the Data Privacy Act of 2012 (RA No. 10173), you consent to Cebu Institute of Technology - University collecting, storing and indexing the intellectual property disclosures, abstracts and manuscripts you submit, for the purposes described below.",
  },
  {
    title: "1. What we collect",
    list: [
      "Account details: your name, your CIT-U email address, your assigned role, and your course, department or college as recorded by the university.",
      "Disclosure details: the title, abstract, keywords and classification of each submission, the adviser you nominate, the college of origin, and submission and review timestamps.",
      "Uploaded files: the manuscripts and supporting documents you upload, together with their file type and size.",
    ],
  },
  {
    title: "2. How your submission is used",
    list: [
      "Institutional search: submitted titles, abstracts and keywords are indexed so that CIT-U students and staff can find research across the university.",
      "Review workflow: your disclosure is routed to the offices you select or that your submission type requires, so they can record a clearance decision.",
      "Audit logging: security-relevant events such as sign-in, document access and document download are recorded so that access to your work can be accounted for.",
      "We do not sell your data, share it outside CIT-U, or compare it against any external or third-party database.",
    ],
  },
  {
    title: "3. Your rights under RA 10173",
    body: "Under RA 10173 you may:",
    list: [
      "Access: view every disclosure recorded under your account at any time, from My Workspace.",
      "Correction: correct your own name and profile details from Settings, and ask the Research and Development Coordinating Office to correct any submission detail.",
      "Erasure: request deletion of a disclosure. The request is reviewed and, once approved, the record and its uploaded files are removed.",
      "Withdraw consent: contact the Research and Development Coordinating Office. Withdrawal cannot be completed from this system yet, and it does not undo review decisions already recorded.",
      "Complain: raise a concern with CIT-U's Data Protection Officer, and with the National Privacy Commission.",
    ],
  },
  {
    title: "Consent Confirmation",
    body: "Ticking the consent box confirms that you have read these terms and agree to CIT-U processing your disclosure as described above.",
  },
] as const;

export const DPA_CHECKBOX_LABEL =
  "I have read and agree to the Data Privacy Act (RA 10173) terms and grant CIT-U consent to process my disclosure as described above.";
