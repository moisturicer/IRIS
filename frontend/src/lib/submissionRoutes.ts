/**
 * Route bookends per record type, for the Submit Disclosure wizard.
 *
 * Only the parts of the route that are actually fixed by type. Under ADR-018
 * (Proposed), which of ITSO/IERC/KTTO review a Thesis/Research or Project
 * disclosure is no longer determined by type alone — the submitter requests
 * offices in step 2 based on what the disclosure actually involves, and RDCO
 * confirms at intake. Showing a fixed "IERC + KTTO" pill for every submission
 * of that type would misrepresent something that is now genuinely
 * conditional, so step 1 only shows what's actually certain: who does intake
 * and who signs off at the end.
 *
 * `docs/ui-ux/05-submission.md` explicitly allows a static client-side map
 * like this for the MVP.
 */
export interface SubmissionRoute {
  typeName: string;
  description: string;
  /** The office/stage that reviews first — named in the submit confirmation. */
  firstStage: string;
  /** The fixed bookend stages, for step 1's summary. Never the whole route. */
  bookends: string[];
  /** Whether this type has any conditional middle stage at all (Proposal doesn't). */
  hasConditionalOffices: boolean;
}

export const SUBMISSION_ROUTES: Record<string, SubmissionRoute> = {
  Proposal: {
    typeName: "Proposal",
    description: "Reviewed by your adviser.",
    firstStage: "your adviser",
    bookends: ["Adviser Review", "Approved"],
    hasConditionalOffices: false,
  },
  "Thesis / Research": {
    typeName: "Thesis / Research",
    description: "Reviewed by RDCO, then by whichever offices your disclosure needs.",
    firstStage: "RDCO",
    bookends: ["RDCO Intake", "RDCO Final", "Published"],
    hasConditionalOffices: true,
  },
  Project: {
    typeName: "Project",
    description: "Reviewed by RDCO, then by whichever offices your disclosure needs.",
    firstStage: "RDCO",
    bookends: ["RDCO Intake", "RDCO Final", "Published"],
    hasConditionalOffices: true,
  },
};

/** Look up a route by the RecordType name as returned by the API. Never fabricated for an unknown type. */
export function routeForTypeName(name: string | undefined): SubmissionRoute | null {
  if (!name) return null;
  return SUBMISSION_ROUTES[name] ?? null;
}
