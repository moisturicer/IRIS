/**
 * What each role can actually do, in plain language.
 *
 * Derived from `backend/core/permissions.py` and the viewsets that use it --
 * NOT aspirational. Every line here corresponds to a permission class that is
 * enforced server-side today:
 *
 *   IsStudent / IsAdviser / IsKTTO / IsRDCO / IsITSO / IsIERC  — single role
 *   IsReviewer  = Adviser, KTTO, RDCO, ITSO, IERC
 *   IsStaff     = KTTO, RDCO, ITSO, IERC
 *   IsAdmin     = KTTO, RDCO (plus Django staff/superusers)
 *
 * If a permission changes there, change it here. A settings screen that
 * overstates what a role can do is worse than one that says nothing, because a
 * user will plan around it and then hit a 403.
 */
export const ROLE_CAPABILITIES: Record<string, string[]> = {
  Student: [
    "Submit research disclosures and track them through review.",
    "Browse published research across the university, and ask IRIS about it.",
    "Request deletion of your own disclosure, subject to RDCO approval.",
  ],

  Adviser: [
    "Everything a student can do.",
    "Review disclosures on which you are named as adviser, and approve or return them.",
  ],

  RDCO: [
    "Review disclosures at the RDCO stage and approve, decline or return them.",
    "Mark an approved proposal complete once the research concludes.",
    "Approve or decline deletion requests from record owners.",
    "Manage the tags and classifications applied to records.",
  ],

  KTTO: [
    "Record the KTTO clearance decision on disclosures routed to your office.",
    "Return a disclosure for revision without resetting the clearances other offices have already given.",
  ],

  ITSO: [
    "Record the ITSO clearance decision on disclosures routed to your office.",
    "Return a disclosure for revision without resetting the clearances other offices have already given.",
  ],

  IERC: [
    "Record the IERC ethics clearance on disclosures that require ethics review.",
    "Return a disclosure for revision without resetting the clearances other offices have already given.",
  ],
};
