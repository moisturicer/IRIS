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
 * IR-123: extraction and external embedding, reranking and generation now
 * exist. The old blanket assurance of no sharing outside CIT-U was false.
 * See docs/compliance/IR-123-processing-review.md for code evidence and the
 * institutional decisions still outstanding, including re-collection of consent.
 * Editing this copy does not renew existing consent or approve a deployment.
 */
export const DPA_REGISTRY_TITLE =
  "DPA Consent Registry (RA 10173)";

export const DPA_REGISTRY_SUBTITLE =
  "Cebu Institute of Technology - University Technology Transfer Office";

export const DPA_SECTIONS = [
  {
    title: "Notice review status",
    body: "This notice is pending CIT-U Data Protection Officer (DPO) / legal review before the pilot collects real consent.",
  },
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
      "Manuscript processing: IRIS extracts text from uploaded manuscripts and builds a search index to find relevant passages and support AI responses.",
      "Review workflow: your disclosure is routed to the offices you select or that your submission type requires, so they can record a clearance decision.",
      "Audit logging: security-relevant events such as sign-in, document access and document download are recorded so that access to your work can be accounted for.",
    ],
  },
  {
    title: "3. External AI processing",
    body: "When AI features are enabled, IRIS sends data to external AI providers outside CIT-U to support search and AI responses. Personal or confidential information included in that text may also be sent.",
    list: [
      "Voyage AI receives manuscript text for embedding (building the search index), and search questions and candidate passages for reranking (ordering search results).",
      "The configured language-model providers receive questions, relevant conversation context and manuscript text to generate answers and summaries. A summary may use text from the whole manuscript. The providers used depend on the deployment configuration; contact the Research and Development Coordinating Office for the current provider details.",
      "Provider retention, processing locations and use of submitted data are subject to the configured providers' terms and account settings. These arrangements require institutional review; this notice does not promise that providers retain no data or that processing stays within CIT-U.",
    ],
  },
  {
    title: "4. Your rights under RA 10173",
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

// Copy content must carry the same notice as the inline, modal and Settings views.
export const DPA_TERMS_PLAIN_TEXT = [
  DPA_REGISTRY_TITLE,
  DPA_REGISTRY_SUBTITLE,
  ...DPA_SECTIONS.map((section) => [
    section.title,
    ...("body" in section ? [section.body] : []),
    ...("list" in section ? section.list : []),
  ].join("\n")),
].join("\n\n");

export const DPA_CHECKBOX_LABEL =
  "I have read and agree to the Data Privacy Act (RA 10173) terms, including the external AI processing described above, and grant CIT-U consent to process my disclosure as described above.";
