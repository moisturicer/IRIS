/** RA 10173 consent copy — align with legal / SRS FR-M6-02 (OD-06). */
export const DPA_REGISTRY_TITLE =
  "DPA Consent Registry (RA 10173)";

export const DPA_REGISTRY_SUBTITLE =
  "Cebu Institute of Technology - University Technology Transfer Office";

export const DPA_TERMS_PLAIN_TEXT = `${DPA_REGISTRY_TITLE}
${DPA_REGISTRY_SUBTITLE}

Republic Act No. 10173 (Data Privacy Act of 2012) Terms

In compliance with the Data Privacy Act of 2012 (RA No. 10173) and Cebu Institute of Technology - University TLO Ingestion Policies, the Submitter hereby consents and agrees to the collection, hosting, vector embedding, and automated algorithmic parsing of all submitted intellectual property disclosures, abstracts, and full-text manuscripts.

1. Collection Scope and Log Parameters
We log concrete digital audit fingerprints including:

Author Credentials: Full legal name, unique university ID (Student/Faculty card numbers), authenticated email coordinate, course, section, and branch of study.
Metadata Attributes: Disclosure title, semantic research keywords, adviser names, submission timestamp logs, and college of origin.
Raw Files Verification hashes: Unique SHA-256 binary values, MIME types, filesize strings, and internal layout tokens during high-performance chunk extractions.

2. System Purposes and Algorithmic Vectors
Retrieval-Augmented Generation (RAG): Text chunks are loaded securely as vector coordinates inside our local Qdrant memory grid to allow student/faculty thesis lookup queries.
Verification Analysis: The pipeline automatically processes files to verify semantic duplications or overlapping intellectual files against regional indexes.
Audit Consistency: Immutable submission logs are written to safe university directories for secure validation and IP processing history tracking.

3. Your Enforceable Legal Rights
Under RA 10173, submitters possess complete active authority to:

Withdraw Consent: Instantly decline terms initially to prevent entry or block future document parsing.
Request Erasure: File official technical support requests to scrub existing vector points from all active server indexes.
Query Record History: Access active directories to explore full lists of currently registered research papers under your credentials.

Consent Confirmation

Checking the consent checkbox on Step 3 confirms you have carefully reviewed these official terms and grant Cebu Institute of Technology - University deep consent permission records.`;

export const DPA_SECTIONS = [
  {
    title: "Republic Act No. 10173 (Data Privacy Act of 2012) Terms",
    body: "In compliance with the Data Privacy Act of 2012 (RA No. 10173) and Cebu Institute of Technology - University TLO Ingestion Policies, the Submitter hereby consents and agrees to the collection, hosting, vector embedding, and automated algorithmic parsing of all submitted intellectual property disclosures, abstracts, and full-text manuscripts.",
  },
  {
    title: "1. Collection Scope and Log Parameters",
    body: "We log concrete digital audit fingerprints including:",
    list: [
      "Author Credentials: Full legal name, unique university ID (Student/Faculty card numbers), authenticated email coordinate, course, section, and branch of study.",
      "Metadata Attributes: Disclosure title, semantic research keywords, adviser names, submission timestamp logs, and college of origin.",
      "Raw Files Verification hashes: Unique SHA-256 binary values, MIME types, filesize strings, and internal layout tokens during high-performance chunk extractions.",
    ],
  },
  {
    title: "2. System Purposes and Algorithmic Vectors",
    list: [
      "Retrieval-Augmented Generation (RAG): Text chunks are loaded securely as vector coordinates inside our local Qdrant memory grid to allow student/faculty thesis lookup queries.",
      "Verification Analysis: The pipeline automatically processes files to verify semantic duplications or overlapping intellectual files against regional indexes.",
      "Audit Consistency: Immutable submission logs are written to safe university directories for secure validation and IP processing history tracking.",
    ],
  },
  {
    title: "3. Your Enforceable Legal Rights",
    body: "Under RA 10173, submitters possess complete active authority to:",
    list: [
      "Withdraw Consent: Instantly decline terms initially to prevent entry or block future document parsing.",
      "Request Erasure: File official technical support requests to scrub existing vector points from all active server indexes.",
      "Query Record History: Access active directories to explore full lists of currently registered research papers under your credentials.",
    ],
  },
  {
    title: "Consent Confirmation",
    body: "Checking the consent checkbox on Step 3 confirms you have carefully reviewed these official terms and grant Cebu Institute of Technology - University deep consent permission records.",
  },
] as const;

export const DPA_CHECKBOX_LABEL =
  "I have read and agree to the Data Privacy Act (RA 10173) terms and grant CIT-U consent to process my disclosure as described above.";
