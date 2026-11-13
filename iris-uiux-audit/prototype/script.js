/* IRIS redesign prototype. Static data, hash routing, no network calls.
   Every screen here exists in the live app; see ../page-inventory.md. */
"use strict";

/* ------------------------------------------------------------------ helpers */
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const ic = (n, cls = "") => `<svg class="icon ${cls}" aria-hidden="true"><use href="#i-${n}"/></svg>`;
const mark = (cls = "") => `<svg class="brand b-mark ${cls}" viewBox="6.87 -0.93 212.93 212.93" aria-hidden="true"><use href="#b-mark"/></svg>`;
const askMark = (cls = "") => `<svg class="brand b-ask ${cls}" viewBox="1.60 1.70 20.80 20.80" aria-hidden="true"><use href="#b-ask"/></svg>`;
const store = {
  get(k, d) { try { const v = localStorage.getItem("iris-proto-" + k); return v == null ? d : v; } catch { return d; } },
  set(k, v) { try { localStorage.setItem("iris-proto-" + k, v); } catch { /* private mode */ } },
};

/* --------------------------------------------------------------------- data */
const ROLES = {
  student: { name: "Sam Student", initials: "SS", email: "student@cit.edu", label: "Student", unit: "College of Computer Studies", program: "BS Computer Science" },
  adviser: { name: "Ana Adviser", initials: "AA", email: "adviser@cit.edu", label: "Adviser", unit: "College of Computer Studies", reviews: true },
  office: { name: "Irene Villanueva", initials: "IV", email: "itso.coordinator@cit.edu", label: "ITSO coordinator", unit: "Intellectual Property and Technology Support Office", office: "ITSO", coordinator: true, reviews: true },
  rdco: { name: "Rita Cruz", initials: "RC", email: "rdco.coordinator@cit.edu", label: "RDCO coordinator", unit: "Research, Development and Coordination Office", office: "RDCO", coordinator: true, reviews: true, rdco: true },
  admin: { name: "Noel Abarquez", initials: "NA", email: "admin@cit.edu", label: "System Admin", unit: "Management Information Systems Office", admin: true },
};

const ABS_101 = "Chronic absenteeism lowers achievement and raises the risk of dropping out, yet schools usually act only after a student has already missed many days. This study built and compared models that predict which senior high school students are likely to become chronically absent, using attendance logs, grades and enrolment records from a private school in Cebu City over three school years. Random forest, gradient boosting and logistic regression models were trained on 2,184 student records and evaluated with stratified cross-validation. Gradient boosting performed best (F1 = 0.81), and prior-term absences, first-quarter grades and commuting distance were the strongest predictors. The study recommends a monthly early-warning list that advisers review with guidance counselors.";

const RECORDS = [
  { id: 101, title: "Predicting Student Absenteeism", authors: ["Hermoine Joyce Zozobrado", "Ashlee Sean Abac"], adviser: "Ana Adviser", type: "Thesis / Research", unit: "College of Computer Studies", program: "BS Computer Science", area: "Computer Science", psced: "Computing", year: 2025, published: "14 Oct 2025", sortKey: 20251014, views: 35, status: "published", keywords: ["absenteeism", "early warning", "gradient boosting", "senior high school"], abstract: ABS_101 },
  { id: 107, title: "Forecasting Dengue Incidence in Cebu City from Weather and Mobility Data", authors: ["Paolo Ybañez", "Rhea Mae Lim"], adviser: "Ana Adviser", type: "Thesis / Research", unit: "College of Computer Studies", program: "BS Computer Science", area: "Computer Science", psced: "Computing", year: 2026, published: "21 Aug 2026", sortKey: 20260821, views: 58, status: "published", keywords: ["dengue", "time series", "public health"], abstract: "Dengue cases in Cebu City rise every rainy season, but barangay health offices receive warnings only when hospital admissions are already climbing. This study combines weekly rainfall, temperature and anonymised mobility indices with city health office case counts from 2016 to 2025 to forecast incidence four weeks ahead. A seasonal ARIMA model with weather covariates was compared against a gradient-boosted regressor; the regressor reduced mean absolute error by 18 percent. The forecasts are presented as a weekly bulletin format tested with two barangay health workers." },
  { id: 108, title: "A Low-Cost IoT Monitor for Water Quality in Mactan Fish Pens", authors: ["Kyle Dela Peña", "Jonas Uy"], adviser: "Engr. Marco Lim", type: "Thesis / Research", unit: "College of Engineering and Architecture", program: "BS Computer Engineering", area: "Engineering", psced: "Engineering and engineering trades", year: 2026, published: "5 Jul 2026", sortKey: 20260705, views: 41, status: "published", keywords: ["IoT", "aquaculture", "dissolved oxygen"], abstract: "Fish kills in Mactan's pens are often traced to sudden drops in dissolved oxygen at night. This project designed a solar-powered monitor that measures dissolved oxygen, temperature and pH every ten minutes and sends an SMS alert when readings cross a threshold. Over a six-week deployment the device stayed within 4 percent of a laboratory meter and cost under PHP 3,500 to build." },
  { id: 102, title: "Toward a Theory of Fixative Accommodation: Explaining How Bounded Change Preserves the Conditions of Recurring Difficulty", authors: ["Hermoine Joyce Zozobrado"], adviser: "Dr. Liza Fernandez", type: "Thesis / Research", unit: "College of Arts and Sciences", program: "AB Psychology", area: "Social Sciences", psced: "Social and behavioural science", year: 2026, published: "2 Feb 2026", sortKey: 20260202, views: 23, status: "published", keywords: ["grounded theory", "accommodation", "coping"], abstract: "Why do people who adapt successfully to a difficulty keep meeting it again? Drawing on interviews with 24 working students, this grounded-theory study proposes fixative accommodation: adjustments that make a recurring problem bearable without changing the conditions that produce it. The theory describes three bounded changes and the ways each preserves the original difficulty." },
  { id: 109, title: "Perceived Usability of the CIT-U Learning Management System Among First-Year Students", authors: ["Maria Clara Santos"], adviser: "Ana Adviser", type: "Thesis / Research", unit: "College of Computer Studies", program: "BS Information Technology", area: "Computer Science", psced: "Computing", year: 2026, published: "18 Mar 2026", sortKey: 20260318, views: 17, status: "published", keywords: ["usability", "SUS", "learning management system"], abstract: "First-year students rated the university learning management system with the System Usability Scale and completed five common tasks. The mean SUS score was 61.4, below the commonly cited benchmark of 68. Submitting an assignment and finding grades caused the most errors." },
  { id: 103, title: "Complementary Roles of Brand Familiarity and Brand Differentiability in BIM Software Purchase Decisions Among Selected Architectural and Construction Firms", authors: ["Sam Student", "Kyle Dela Peña"], adviser: "Ana Adviser", type: "Thesis / Research", unit: "College of Computer Studies", program: "BS Computer Science", area: "Business", psced: "Business and administration", year: 2026, status: "review", version: 2, submitted: "6 Oct 2026", owners: ["student"], keywords: ["BIM", "brand equity", "purchase decision"], abstract: "Architectural and construction firms choose building information modelling (BIM) software under heavy switching costs. Surveying 63 firms in Metro Cebu, this study tests whether brand familiarity and brand differentiability act as substitutes or complements in purchase decisions. Structural equation modelling shows the two are complementary: differentiability matters most for firms already familiar with a brand." },
  { id: 104, title: "Activity Preference and Level of Physical Activity Participation of CIT University Administrative Employees", authors: ["Sam Student"], adviser: "Ana Adviser", type: "Thesis / Research", unit: "College of Computer Studies", program: "BS Computer Science", area: "Health", psced: "Health", year: 2026, status: "review", version: 1, submitted: "6 Nov 2026", owners: ["student"], keywords: ["physical activity", "workplace wellness"], abstract: "This descriptive-correlational study surveyed 142 administrative employees on their preferred physical activities and weekly participation, using the International Physical Activity Questionnaire short form." },
  { id: 105, title: "Quantitative Forecasting of Land Suitability in Metro Cebu", authors: ["Sam Student"], adviser: "Ana Adviser", type: "Thesis / Research", unit: "College of Computer Studies", program: "BS Computer Science", area: "Environmental Science", psced: "Environment", year: 2026, status: "draft", saved: "11 Nov 2026", owners: ["student"], keywords: [], abstract: "" },
  { id: 110, title: "Sentiment of Cebuano Posts on Public Utility Jeepney Modernization", authors: ["Paolo Ybañez"], adviser: "Ana Adviser", type: "Thesis / Research", unit: "College of Computer Studies", program: "BS Computer Science", area: "Computer Science", psced: "Computing", year: 2026, status: "review", version: 1, submitted: "10 Nov 2026", keywords: ["sentiment analysis", "Cebuano", "transport policy"], abstract: "A Cebuano sentiment lexicon was built from 9,800 public posts about the jeepney modernization program and used to track sentiment before and after three policy announcements." },
  { id: 111, title: "Design of a Solar-Powered Cold Storage Box for Small Fish Vendors", authors: ["Jonas Uy"], adviser: "Engr. Marco Lim", type: "Thesis / Research", unit: "College of Engineering and Architecture", program: "BS Mechanical Engineering", area: "Engineering", psced: "Engineering and engineering trades", year: 2026, status: "review", version: 1, submitted: "28 Oct 2026", keywords: ["cold chain", "solar"], abstract: "A 60-litre insulated box with a solar-charged Peltier module kept fish below 4 °C for 9 hours in field tests at Carbon Market." },
  { id: 112, title: "Gamified Vocabulary Practice for Grade 4 Learners", authors: ["Maria Clara Santos"], adviser: "Ana Adviser", type: "Thesis / Research", unit: "College of Computer Studies", program: "BS Information Technology", area: "Education", psced: "Education", year: 2026, status: "review", version: 1, submitted: "2 Oct 2026", keywords: ["gamification", "vocabulary"], abstract: "A quasi-experiment with two Grade 4 sections compared a points-and-streaks vocabulary app against printed drills over eight weeks." },
];
const REC = Object.fromEntries(RECORDS.map((r) => [r.id, r]));
/* Embargo (ADR-052): a paper stays out of Discover and Ask IRIS until its Adviser or RDCO releases it. */
const EMBARGO = { 103: { released: "Released by Ana Adviser on 12 Sep 2026" }, 104: {}, 110: {}, 111: { released: "Released by Engr. Marco Lim on 30 Oct 2026" }, 112: { until: "2 Dec 2026" } };
const COMMENTS = { 101: [
  { id: 1, who: "Maria Clara Santos", d: "2026-11-03", text: "Did you try the model on the second semester only? Our school's absences spike after the December break." },
  { id: 2, to: 1, who: "Hermoine Joyce Zozobrado", d: "2026-11-04", author: true, text: "Not separately. Prior-term absences already carry some of that, but it would be a good follow-up." },
  { id: 3, to: 2, who: "Maria Clara Santos", d: "2026-11-05", text: "Thanks! I'd like to try it on our Grade 11 data next term." },
  { id: 4, who: "Paolo Ybañez", d: "2026-11-06", text: "Which attendance threshold did you use for “chronic”? DepEd counts 10% of school days." },
  { id: 5, to: 4, who: "Ashlee Sean Abac", d: "2026-11-07", author: true, text: "10% as well, so it lines up with DepEd. Section 3.1 explains how we counted half-days." },
  { id: 6, to: 4, who: "Rhea Mae Lim", d: "2026-11-08", text: "Same question here, thanks for asking it." },
  { id: 7, to: 5, who: "Jonas Uy", d: "2026-11-09", text: "Did half-days count as one absence or half?" },
  { id: 8, who: "Kyle Dela Peña", d: "2026-11-10", edited: true, text: "Would the model still work for Grade 10? The predictors look like they would carry over." },
] };
const PUBLISHED = RECORDS.filter((r) => r.status === "published");

/* Clearance per record: who has acted, and whether a clearance was kept across a resubmission. */
const CLEARANCE = {
  103: [
    { party: "Adviser", who: "Ana Adviser", state: "kept", text: "Cleared on v1 · kept", date: "12 Sep 2026" },
    { party: "ITSO", who: "Irene Villanueva", state: "kept", text: "Cleared on v1 · kept", date: "19 Sep 2026" },
    { party: "IERC", who: "Dr. Marco Lim", state: "reviewing", text: "Reviewing v2", date: "Since 7 Oct 2026", was: "Requested revision on v1, 30 Sep" },
    { party: "KTTO", who: "Joanna Reyes", state: "kept", text: "Cleared on v1 · kept", date: "24 Sep 2026" },
    { party: "RDCO", who: "", state: "waiting", text: "Publishes after every office clears", date: "" },
  ],
  104: [
    { party: "Adviser", who: "Ana Adviser", state: "cleared", text: "Cleared", date: "8 Nov 2026" },
    { party: "ITSO", who: "", state: "unclaimed", text: "Nobody has claimed this yet", date: "Routed 8 Nov 2026" },
    { party: "IERC", who: "Dr. Marco Lim", state: "revising", text: "Asked for a revision", date: "11 Nov 2026" },
    { party: "KTTO", who: "", state: "unclaimed", text: "Nobody has claimed this yet", date: "Routed 8 Nov 2026" },
    { party: "RDCO", who: "", state: "waiting", text: "Publishes after every office clears", date: "" },
  ],
  110: [
    { party: "Adviser", who: "Ana Adviser", state: "reviewing", text: "Your review", date: "Since 10 Nov 2026" },
    { party: "ITSO", state: "waiting", text: "Not asked yet", who: "", date: "" },
    { party: "IERC", state: "waiting", text: "Not asked yet", who: "", date: "" },
    { party: "KTTO", state: "waiting", text: "Not asked yet", who: "", date: "" },
    { party: "RDCO", state: "waiting", text: "Publishes after every office clears", who: "", date: "" },
  ],
  111: [
    { party: "Adviser", who: "Engr. Marco Lim", state: "cleared", text: "Cleared", date: "30 Oct 2026" },
    { party: "ITSO", who: "Irene Villanueva", state: "reviewing", text: "Reviewing", date: "Due 15 Nov 2026" },
    { party: "IERC", who: "Dr. Marco Lim", state: "cleared", text: "Cleared", date: "6 Nov 2026" },
    { party: "KTTO", who: "Joanna Reyes", state: "reviewing", text: "Reviewing", date: "Due 18 Nov 2026" },
    { party: "RDCO", state: "waiting", text: "Publishes after every office clears", who: "", date: "" },
  ],
  112: [
    { party: "Adviser", who: "Ana Adviser", state: "cleared", text: "Cleared", date: "4 Oct 2026" },
    { party: "ITSO", who: "Irene Villanueva", state: "cleared", text: "Cleared", date: "20 Oct 2026" },
    { party: "IERC", who: "Dr. Marco Lim", state: "cleared", text: "Cleared", date: "22 Oct 2026" },
    { party: "KTTO", who: "Joanna Reyes", state: "cleared", text: "Cleared", date: "29 Oct 2026" },
    { party: "RDCO", who: "Rita Cruz", state: "reviewing", text: "Ready to publish", date: "Since 29 Oct 2026" },
  ],
};
const HISTORY = {
  103: [
    ["upload", "Sam Student sent version 2", "7 Oct 2026", true],
    ["rotate", "IERC requested a revision on v1. Only IERC's clearance was reset.", "30 Sep 2026", true],
    ["check", "KTTO cleared v1", "24 Sep 2026"],
    ["check", "ITSO cleared v1", "19 Sep 2026"],
    ["route", "Ana Adviser cleared and routed to ITSO, IERC and KTTO", "12 Sep 2026"],
    ["file-up", "Sam Student submitted v1", "5 Sep 2026"],
  ],
  104: [["rotate", "IERC asked for a revision on v1. Only IERC's clearance resets; Ana Adviser's stays.", "11 Nov 2026", true], ["route", "Ana Adviser cleared and routed to ITSO, IERC and KTTO", "8 Nov 2026"], ["file-up", "Sam Student submitted v1", "6 Nov 2026"]],
  110: [["file-up", "Paolo Ybañez submitted v1", "10 Nov 2026", true]],
  111: [["check", "IERC cleared v1", "6 Nov 2026"], ["route", "Engr. Marco Lim cleared and routed to ITSO, IERC and KTTO", "30 Oct 2026"], ["file-up", "Jonas Uy submitted v1", "28 Oct 2026"]],
  112: [["check", "KTTO cleared v1 · every office has cleared", "29 Oct 2026", true], ["check", "IERC cleared v1", "22 Oct 2026"], ["check", "ITSO cleared v1", "20 Oct 2026"], ["route", "Ana Adviser cleared and routed", "4 Oct 2026"]],
};

const REVIEWQ = {
  adviser: {
    todo: [{ id: 110, due: "Due 17 Nov", dn: 17, w: 3, note: "Waiting for your review" }],
    progress: [{ id: 104, note: "IERC asked Sam for a revision · ITSO and KTTO not claimed yet" }, { id: 103, note: "IERC is reviewing v2" }],
    done: [{ id: 101, note: "Published 14 Oct 2025", out: "Published" }, { id: 109, note: "Published 18 Mar 2026", out: "Published" }, { id: 112, note: "Cleared 4 Oct 2026", out: "Cleared" }],
  },
  office: {
    todo: [{ id: 111, due: "Due 15 Nov", dn: 15, w: 16, note: "Assigned to you", mine: true }, { id: 104, due: "Due 22 Nov", dn: 22, w: 5, note: "Nobody has claimed this yet" }],
    progress: [{ id: 103, note: "Your clearance on v1 is kept · IERC is reviewing v2", mine: true }],
    done: [{ id: 112, note: "Cleared 20 Oct 2026", mine: true, out: "Cleared" }, { id: 101, note: "Cleared 2 Oct 2025", mine: true, out: "Cleared" }],
  },
  rdco: {
    todo: [{ id: 112, due: "Ready since 29 Oct", w: 15, note: "Every office has cleared", mine: true }],
    progress: [{ id: 103, note: "Waiting for IERC" }, { id: 111, note: "Waiting for ITSO and KTTO" }, { id: 104, note: "Waiting for Sam's revision, then ITSO, IERC and KTTO" }],
    done: [{ id: 107, note: "Published 21 Aug 2026", mine: true, out: "Published" }, { id: 108, note: "Published 5 Jul 2026", mine: true, out: "Published" }],
  },
};

/* Review workspace: versions, conversation, threads on passages, and what changed between versions. */
const VERSIONS = {
  103: [{ v: 1, kind: "Submission", date: "5 Sep 2026", pages: 46 }, { v: 2, kind: "Revision", date: "7 Oct 2026", pages: 48 }],
  104: [{ v: 1, kind: "Submission", date: "6 Nov 2026", pages: 10 }],
  110: [{ v: 1, kind: "Submission", date: "10 Nov 2026", pages: 38 }],
  111: [{ v: 1, kind: "Submission", date: "28 Oct 2026", pages: 52 }],
  112: [{ v: 1, kind: "Submission", date: "2 Oct 2026", pages: 41 }],
};
/* Conversation: events (icon, text, date) and comments (who, role, text, quote, replies). Newest last, like the live timeline. */
const CONVO = {
  103: [
    { ev: "file-up", text: "Sam Student submitted v1 to Ana Adviser", date: "5 Sep 2026" },
    { who: "Ana Adviser", role: "Adviser", date: "10 Sep 2026", v: 1, text: "The survey instrument is solid. Before I clear it, add the response rate per firm size to Table 4.", mention: "Sam Student", replies: [{ who: "Sam Student", role: "Author", date: "11 Sep 2026", text: "Added on p. 22. Thank you, ma'am." }] },
    { ev: "route", text: "Ana Adviser cleared v1 and routed it to ITSO, IERC and KTTO", date: "12 Sep 2026" },
    { ev: "check", text: "ITSO cleared v1", who: "Irene Villanueva", date: "19 Sep 2026" },
    { ev: "check", text: "KTTO cleared v1", who: "Joanna Reyes", date: "24 Sep 2026" },
    { ev: "rotate", text: "IERC asked for a revision on v1", who: "Dr. Marco Lim", date: "30 Sep 2026", note: "Only IERC's clearance resets. Adviser, ITSO and KTTO keep theirs." },
    { ev: "upload", text: "Sam Student sent v2 · answers IERC's request", date: "7 Oct 2026", mark: true },
    { ev: "eye", text: "IERC started reviewing v2", who: "Dr. Marco Lim", date: "7 Oct 2026", mark: true },
  ],
  104: [
    { ev: "file-up", text: "Sam Student submitted v1 to Ana Adviser", date: "6 Nov 2026" },
    { ev: "route", text: "Ana Adviser cleared v1 and routed it to ITSO, IERC and KTTO", date: "8 Nov 2026" },
    { who: "Dr. Marco Lim", role: "IERC", date: "11 Nov 2026", v: 1, quote: "Respondents were invited through the HR mailing list and answered anonymously.", text: "Please attach the signed informed consent form and say how anonymity was kept when the HR office sent the invitation.", replies: [] },
    { ev: "rotate", text: "IERC asked for a revision on v1", who: "Dr. Marco Lim", date: "11 Nov 2026", mark: true, note: "Only IERC's clearance resets. Ana Adviser's clearance stays." },
  ],
};
const THREADS = {
  103: [
    { id: 1, sev: "must", party: "IERC", who: "Dr. Marco Lim", v: 1, page: 18, quote: "Firms were contacted by phone and asked to name the person who decides software purchases.", text: "State how consent was obtained from these respondents, and attach the consent script.", state: "addressed", answer: "Consent script added as Appendix C; the procedure is on p. 18 of v2." },
    { id: 2, sev: "suggest", party: "IERC", who: "Dr. Marco Lim", v: 1, page: 31, quote: "Firm names are listed in Table 7.", text: "Consider replacing firm names with codes.", state: "addressed", answer: "" },
    { id: 3, sev: "suggest", party: "Adviser", who: "Ana Adviser", v: 1, page: 22, quote: "Response rate was 63 percent.", text: "Break the response rate down by firm size.", state: "resolved", answer: "Done in Table 4." },
  ],
  104: [
    { id: 4, sev: "must", party: "IERC", who: "Dr. Marco Lim", v: 1, page: 4, quote: "Respondents were invited through the HR mailing list and answered anonymously.", text: "Attach the signed informed consent form and explain how anonymity was kept when HR sent the invitation.", state: "open", answer: "" },
    { id: 5, sev: "suggest", party: "IERC", who: "Dr. Marco Lim", v: 1, page: 7, quote: "IPAQ short form (Craig et al., 2003)", text: "Say which language version of the IPAQ you used.", state: "open", answer: "" },
  ],
  111: [{ id: 6, sev: "suggest", party: "IERC", who: "Dr. Marco Lim", v: 1, page: 12, quote: "Fish were bought at Carbon Market each morning.", text: "Fine as is. Noting it for ITSO: no human participants.", state: "resolved", answer: "" }],
};
const CHANGES = {
  103: { from: 1, to: 2, changed: 3, added: 29, removed: 22, unchanged: 8, names: ["Abstract", "1. Introduction", "2. Review of related literature", "2.1 Brand familiarity", "2.2 Brand differentiability", "5. Discussion", "6. Conclusion", "Appendix A. Survey"], sections: [
    { name: "3. Methodology", page: 18, changed: 2, added: 14, removed: 6, items: [
      { kind: "Removed", text: "Firms were contacted by phone and asked to name the person who decides software purchases.", page: 18 },
      { kind: "Added", text: "Firms were contacted by phone. The caller read the consent script in Appendix C, and only respondents who agreed were asked to name the person who decides software purchases.", page: 18 },
    ] },
    { name: "4. Results", page: 31, changed: 1, added: 9, removed: 12, items: [
      { kind: "Removed", text: "Table 7 lists each firm by name with its BIM platform.", page: 31 },
      { kind: "Added", text: "Table 7 lists each firm by code (F01 to F63) with its BIM platform.", page: 31 },
    ] },
    { name: "Appendix C. Consent script", page: 47, changed: 0, added: 6, removed: 0, items: [{ kind: "Added", text: "A two-page consent script read to every respondent before the survey.", page: 47 }] },
    { name: "References", page: 44, changed: 0, added: 0, removed: 4, items: [{ kind: "Removed", text: "Four duplicate references.", page: 44 }] },
  ] },
};
const DOCS = {
  manuscript: (r) => ({ name: `${slug(r.title).slice(0, 28)}-v${r.version || 1}.pdf`, size: "2.4 MB", pages: (VERSIONS[r.id] || [{ pages: 48 }]).slice(-1)[0].pages }),
  supporting: { 103: [["Consent script (Appendix C)", "consent-script.pdf", "180 KB"], ["Survey instrument", "survey-instrument.pdf", "310 KB"]], 104: [["IPAQ short form", "ipaq-short.pdf", "96 KB"]] },
  supplementary: { 103: [["Survey responses (anonymised)", "responses.xlsx", "64 KB"]] },
};

const NOTIFS = {
  student: [
    { g: "Today", unread: true, text: "IERC started reviewing version 2 of <b>Complementary Roles of Brand Familiarity…</b>. Your Adviser, ITSO and KTTO clearances from version 1 are kept.", when: "2 hours ago", href: "#/records/103?tab=review" },
    { g: "This week", unread: true, text: "IERC asked for a revision of <b>Activity Preference and Level of Physical Activity Participation…</b>. Ana Adviser's clearance is kept; send version 2 when you're ready.", when: "11 Nov", href: "#/records/104?tab=review" },
    { g: "This week", text: "Ana Adviser cleared <b>Activity Preference and Level of Physical Activity Participation…</b> and sent it to ITSO, IERC and KTTO.", when: "8 Nov", href: "#/records/104?tab=review" },
    { g: "Earlier", text: "IERC requested a revision on <b>Complementary Roles of Brand Familiarity…</b>.", when: "30 Sep", resolved: "You sent version 2 on 7 Oct", href: "#/records/103?tab=review" },
    { g: "Earlier", text: "KTTO cleared <b>Complementary Roles of Brand Familiarity…</b>.", when: "24 Sep", href: "#/records/103?tab=review" },
  ],
  adviser: [
    { g: "Today", unread: true, text: "Paolo Ybañez submitted <b>Sentiment of Cebuano Posts on Public Utility Jeepney Modernization</b> for your review. Due 17 Nov.", when: "3 hours ago", href: "#/records/110?tab=review" },
    { g: "This week", unread: true, text: "Sam Student sent version 2 of <b>Complementary Roles of Brand Familiarity…</b>. Your clearance from version 1 is kept; only IERC reviews again.", when: "7 Oct", href: "#/records/103?tab=review" },
    { g: "Earlier", text: "<b>Predicting Student Absenteeism</b> was published.", when: "14 Oct 2025", href: "#/records/101" },
  ],
  office: [
    { g: "Today", unread: true, text: "<b>Design of a Solar-Powered Cold Storage Box…</b> is due for your ITSO review in 2 days.", when: "1 hour ago", href: "#/records/111?tab=review" },
    { g: "This week", unread: true, text: "<b>Activity Preference and Level of Physical Activity Participation…</b> was routed to ITSO. Nobody has claimed it yet.", when: "8 Nov", href: "#/records/104?tab=review" },
    { g: "This week", text: "<b>Gamified Vocabulary Practice for Grade 4 Learners</b> was routed to ITSO.", when: "4 Oct", resolved: "Cleared by you on 20 Oct", href: "#/records/112?tab=review" },
  ],
  rdco: [
    { g: "This week", unread: true, text: "Every office cleared <b>Gamified Vocabulary Practice for Grade 4 Learners</b>. It is ready for you to publish.", when: "29 Oct", href: "#/records/112?tab=review" },
    { g: "This week", unread: true, text: "Kyle Dela Peña asked to delete the record <b>A Low-Cost IoT Monitor for Water Quality in Mactan Fish Pens</b>.", when: "12 Nov", href: "#/rdco/delete-requests" },
    { g: "Earlier", text: "Jonas Uy asked to delete the record <b>Solar Dryer for Dried Fish</b>.", when: "26 Oct", resolved: "Declined by Rita Cruz on 27 Oct", href: "#/rdco/delete-requests?view=declined" },
  ],
  admin: [
    { g: "This week", unread: true, text: "Paolo Ybañez asked to delete their account.", when: "10 Nov", href: "#/admin/account-deletion-requests" },
    { g: "Earlier", text: "The retention run removed 14 Ask IRIS conversations older than 180 days.", when: "1 Nov", href: "#/admin/retention" },
  ],
};

const CONVOS = [
  { id: 1, g: "Today", title: "What predicts chronic absenteeism?", when: "10:24" },
  { id: 2, g: "This week", title: "Dengue forecasting methods used at CIT-U", when: "Tue" },
  { id: 3, g: "This week", title: "Papers on usability testing", when: "Mon" },
  { id: 4, g: "Earlier", title: "IoT projects in aquaculture", when: "28 Oct" },
];

/* Conversations deleted in this session (the prototype saves nothing). */
const CONVO_GONE = new Set();

const USERS = [
  { name: "Rita Cruz", email: "rdco.coordinator@cit.edu", role: "RDCO coordinator", unit: "RDCO", status: "Active", last: "Now" },
  { name: "Noel Abarquez", email: "admin@cit.edu", role: "System Admin", unit: "MIS Office", status: "Active", last: "Today" },
  { name: "Irene Villanueva", email: "itso.coordinator@cit.edu", role: "ITSO coordinator", unit: "ITSO", status: "Active", last: "Today" },
  { name: "Dr. Marco Lim", email: "ierc.coordinator@cit.edu", role: "IERC coordinator", unit: "IERC", status: "Active", last: "Today" },
  { name: "Joanna Reyes", email: "ktto.coordinator@cit.edu", role: "KTTO coordinator", unit: "KTTO", status: "Active", last: "Yesterday" },
  { name: "Ana Adviser", email: "adviser@cit.edu", role: "Adviser", unit: "College of Computer Studies", status: "Active", last: "Today" },
  { name: "Sam Student", email: "student@cit.edu", role: "Student", unit: "College of Computer Studies", status: "Active", last: "Today" },
  { name: "Paolo Ybañez", email: "paolo.ybanez@cit.edu", role: "Student", unit: "College of Computer Studies", status: "Active", last: "3 days ago" },
  { name: "Mark Abellana", email: "mark.abellana@cit.edu", role: "ITSO reviewer", unit: "ITSO", status: "Locked", last: "2 Oct 2026" },
];

/* -------------------------------------------------------------------- state */
const S = {
  navRail: store.get("nav-rail", "0") === "1", readingRail: null,
  role: ROLES[store.get("role", "student")] ? store.get("role", "student") : "student",
  saved: new Set([102, 107]),
  read: new Set(),
  claimed: new Set(),
  disc: { view: "papers", feed: "latest", q: "", filters: false, sort: "newest", area: "", year: "", unit: "", busy: false },
  ask: { open: false, scope: "paper", msgs: [], startedAll: false },
  chat: { depth: "Standard", msgs: [] },
  revScope: "mine",
  revSort: "due",
  doneFilter: "All",
  comSort: "oldest",
  cmt: { open: {}, replyTo: null, drafts: {}, editing: null, hl: null },
  notesOpen: false,
  notes: {},
  ws: { ver: {}, tab: "conversation", filter: "all", drafts: {}, anno: null, paneOpen: false, viewed: new Set(), diff: "inline", showUnchanged: false, side: store.get("ws-side", "") || null, mode: "wide", roomy: true, tourOffer: store.get("tour-offer", "1") === "1" },
  finished: {},
  sentV2: new Set(),
};
const me = () => ROLES[S.role];

/* ------------------------------------------------------------------- router */
function parse() {
  const h = location.hash.slice(1) || "/discover";
  const [path, qs] = h.split("?");
  return { path, q: new URLSearchParams(qs || "") };
}
const ROUTES = [
  [/^\/login$/, viewLogin, { bare: true }],
  [/^\/signup$/, viewSignup, { bare: true }],
  [/^\/discover$/, viewDiscover],
  [/^\/records\/(\d+)$/, viewRecord],
  [/^\/library$/, viewLibrary],
  [/^\/ai$/, viewAsk],
  [/^\/ai\/c\/(\d+)$/, viewAsk],
  [/^\/reviews$/, viewReviews, { need: "reviews" }],
  [/^\/reviews\/console$/, viewConsole, { need: "coordinator" }],
  [/^\/reviews\/analytics$/, viewAnalytics, { need: "coordinator" }],
  [/^\/notifications$/, viewNotifications],
  [/^\/calls$/, viewCalls],
  [/^\/profile$/, viewProfile],
  [/^\/people\/([\w-]+)$/, viewPerson],
  [/^\/settings$/, viewSettings],
  [/^\/help$/, viewHelp],
  [/^\/rdco\/import$/, viewImport, { need: "rdco" }],
  [/^\/rdco\/users$/, viewUsers, { need: "rdco" }],
  [/^\/rdco\/role-requests$/, viewRoleRequests, { need: "rdco" }],
  [/^\/rdco\/download-requests$/, viewDownloadRequests, { need: "rdco" }],
  [/^\/rdco\/delete-requests$/, viewDeleteRequests, { need: "rdco" }],
  [/^\/rdco\/notices$/, viewNotices, { need: "rdco" }],
  [/^\/admin\/users$/, viewAdminUsers, { need: "admin" }],
  [/^\/admin\/audit$/, viewAudit, { need: "admin" }],
  [/^\/admin\/account-deletion-requests$/, viewAccountDeletions, { need: "admin" }],
  [/^\/admin\/retention$/, viewRetention, { need: "admin" }],
  [/^\/admin\/notices$/, viewNotices, { need: "admin" }],
  [/^\/profile\/edit$/, viewProfileEdit],
  [/^\/password\/forgot$/, viewForgot, { bare: true }],
];

let firstRender = true;
function render() {
  const { path, q } = parse();
  let match = null, opts = {}, fn = viewNotFound;
  for (const [re, f, o] of ROUTES) { const m = path.match(re); if (m) { match = m; fn = f; opts = o || {}; break; } }
  if (opts.need && !me()[opts.need]) { fn = viewNoAccess; viewNoAccess.need = opts.need; }
  const fk = document.activeElement && document.activeElement.dataset ? document.activeElement.dataset.fk : null;
  const v = fn(match || [], q);
  document.title = `${v.title} · IRIS`;
  const root = $("#root");
  const ks = render.keepScroll ? $$("[data-ks]").map((e) => [e.id, e.scrollTop]) : [];
  /* Paper (live IRIS, IR-569) and Review (prototype: the paper is open there too) collapse the
     sidebar to its rail for the visit; the IRIS mark opens it again. */
  const reading = /^\/records\/\d+$/.test(path) && ["paper", "review"].includes(q.get("tab"));
  if (!reading) S.readingRail = null; else if (S.readingRail === null) S.readingRail = true;
  if (opts.bare) {
    root.innerHTML = `<main id="view" tabindex="-1">${v.html}</main>`;
  } else {
    root.innerHTML = `<div class="app ${railOn() ? "is-rail" : ""}">${sidebar(path)}<div class="main">${topbar()}<main id="view" tabindex="-1" class="${v.full ? "full" : ""}">${v.full ? v.html : `<div class="page ${v.wide ? "wide" : ""}">${v.html}</div>`}</main></div></div>${v.fab === false ? "" : `<a class="ask-fab" href="#/ai" aria-label="Ask IRIS">${askMark()}</a>`}`;
  }
  $$(".proto-roles button").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.role === S.role)));
  closePopover();
  if (v.after) v.after();
  ks.forEach(([id, top]) => { const e = document.getElementById(id); if (e) e.scrollTop = top; });
  if (fk && $(`[data-fk="${fk}"]`)) $(`[data-fk="${fk}"]`).focus();
  else if (!firstRender && !render.keepScroll) { const h1 = $("#view h1"); if (h1) { h1.setAttribute("tabindex", "-1"); h1.focus({ preventScroll: true }); } window.scrollTo(0, 0); }
  render.keepScroll = false;
  firstRender = false;
}
const rerender = () => { render.keepScroll = true; render(); };
window.addEventListener("hashchange", render);

/* -------------------------------------------------------------------- shell */
function navItem(href, icon, label, path, extra = "") {
  const cur = path === href.slice(1).split("?")[0] || (href === "#/discover" && path.startsWith("/records") && !path.endsWith("mine"));
  return `<a class="nav-item" href="${href}" data-tip="${label}" ${cur ? 'aria-current="page"' : ""}>${ic(icon)}<span class="label">${label}</span>${extra}</a>`;
}
function unreadCount() { return (NOTIFS[S.role] || []).filter((n, i) => n.unread && !S.read.has(S.role + i)).length; }
function sidebar(path) {
  const r = me();
  const todo = r.reviews ? REVIEWQ[S.role].todo.length : 0;
  const n = unreadCount();
  let reviews = "";
  if (r.reviews) {
    reviews = navItem("#/reviews", "clipboard", "My Reviews", path, todo ? `<span class="count num" aria-label="${todo} to review">${todo}</span>` : "");
    if (r.coordinator) reviews += `<div class="nav-sub">${navItem("#/reviews/console", "dashboard", "Office console", path)}${navItem("#/reviews/analytics", "chart", "Workflow analytics", path)}</div><span class="nav-divider" aria-hidden="true"></span>${railOnly(navItem("#/reviews/console", "dashboard", "Office console", path))}${railOnly(navItem("#/reviews/analytics", "chart", "Workflow analytics", path))}`;
  }
  const rdco = r.rdco ? `<p class="nav-label">RDCO tools</p><span class="nav-divider" aria-hidden="true"></span><nav class="nav-group" aria-label="RDCO tools">
      ${navItem("#/rdco/import", "file-up", "Import records", path)}
      ${navItem("#/rdco/users", "users", "Users", path)}
      ${navItem("#/rdco/role-requests", "user-plus", "Role requests", path)}
      ${navItem("#/rdco/download-requests", "file-down", "Download requests", path, '<span class="count num" aria-label="2 pending">2</span>')}
      ${navItem("#/rdco/delete-requests", "file-x", "Delete requests", path, '<span class="count num" aria-label="1 pending">1</span>')}
      ${navItem("#/rdco/notices", "scroll", "Notices", path)}
    </nav>` : "";
  const admin = r.admin ? `<p class="nav-label">Administration</p><span class="nav-divider" aria-hidden="true"></span><nav class="nav-group" aria-label="Administration">
      ${navItem("#/admin/users", "users", "Users", path)}
      ${navItem("#/admin/audit", "history", "Audit log", path)}
      ${navItem("#/admin/account-deletion-requests", "user-x", "Account deletions", path, '<span class="count num" aria-label="1 pending">1</span>')}
      ${navItem("#/admin/retention", "calendar", "Retention", path)}
      ${navItem("#/admin/notices", "scroll", "Notices", path)}
    </nav>` : "";
  return `<aside class="sidebar" id="sidebar" aria-label="Main">
    <div class="brand-row">
      <button class="rail-toggle" type="button" data-action="nav-rail" aria-label="${railOn() ? "Open sidebar" : "Collapse sidebar"}" title="${railOn() ? "Open sidebar" : "Collapse sidebar"}" aria-controls="sidebar" aria-expanded="${!railOn()}">${mark()}</button>
      <a class="side-brand" href="#/discover" aria-label="IRIS, go to Discover">${mark()}<svg class="brand b-word" viewBox="-4.31 -3.82 230.33 66.87" aria-hidden="true"><use href="#b-word"/></svg></a>
      <button class="icon-btn bell-side" type="button" data-notif aria-label="Notifications, ${n} unread" aria-haspopup="dialog">${ic("bell", "icon-20")}${n ? `<span class="dot num">${n}</span>` : ""}</button>
      <button class="icon-btn drawer-close" type="button" data-close-drawer aria-label="Close menu">${ic("x", "icon-20")}</button>
    </div>
    <nav class="nav-group" aria-label="Main">
      ${navItem("#/discover", "compass", "Discover", path)}
      ${r.admin ? "" : navItem("#/ai", "msg", "Ask IRIS", path.startsWith("/ai") ? "/ai" : path)}
      ${r.admin ? "" : navItem("#/library", "library", "My Library", path)}
      ${reviews}
      ${navItem("#/calls", "megaphone", "Calls & Conferences", path)}
    </nav>
    ${rdco}${admin}
    <div class="side-foot">
      ${navItem("#/help", "help", "Help", path)}
      <button class="account-btn" type="button" data-acct aria-haspopup="menu" aria-expanded="false"><span class="avatar">${r.initials}</span><span class="who"><b>${r.name}</b><span>${r.label}</span></span></button>
    </div>
  </aside><div class="drawer-scrim" hidden data-close-drawer></div>`;
}
const railOn = () => (S.readingRail ?? S.navRail);
const railOnly = (html) => html.replace('class="nav-item"', 'class="nav-item rail-only"');
function topbar() {
  const n = unreadCount();
  return `<header class="topbar">
    <button class="icon-btn" type="button" data-open-drawer aria-label="Open menu" aria-controls="sidebar" aria-expanded="false">${ic("menu", "icon-20")}</button>
    <a class="lock" href="#/discover" aria-label="IRIS, go to Discover">${mark()}<span class="wordmark">IRIS</span></a>
    ${canAuthor() ? `<button class="btn btn-primary" type="button" data-publish>${ic("plus")}Publish</button>` : '<span class="spacer"></span>'}
    <button class="icon-btn" type="button" data-notif aria-label="Notifications, ${n} unread">${ic("bell", "icon-20")}${n ? `<span class="dot num">${n}</span>` : ""}</button>
  </header>`;
}
function head({ title, desc = "", crumbs = null, actions = "" }) {
  const c = crumbs ? `<nav aria-label="Breadcrumb"><ol class="crumbs">${crumbs.map(([t, h]) => `<li>${h ? `<a href="${h}">${t}</a>` : `<span aria-current="page">${t}</span>`}</li>`).join("")}</ol></nav>` : "";
  return `<header class="page-head"><div class="titles">${c}<h1 class="page-title">${title}</h1>${desc ? `<p class="page-desc">${desc}</p>` : ""}</div>${actions ? `<div class="head-actions">${actions}</div>` : ""}</header>`;
}

/* -------------------------------------------------------- shared components */
const STATUS_ICON = { quiet: "clock", active: "eye", attention: "alert", settled: "check", kept: "shield" };
const status = (tone, word, icon) => `<span class="status ${tone}">${ic(icon || STATUS_ICON[tone])}${word}</span>`;
function officeChip(c) {
  const map = { cleared: ["cleared", "check"], kept: ["kept", "shield"], reviewing: ["reviewing", "eye"], revising: ["revising", "rotate"], unclaimed: ["", "hand"], waiting: ["", "clock"] };
  const [cls, icon] = map[c.state] || ["", "clock"];
  const word = { cleared: "cleared", kept: "kept from v1", reviewing: "reviewing", revising: "asked for revision", unclaimed: "unclaimed", waiting: c.party === "RDCO" ? "publishes last" : "not asked" }[c.state];
  return `<span class="office ${cls}">${ic(icon)}${c.party} <span class="sr-only">:</span>${word}</span>`;
}
const clearStrip = (id) => (CLEARANCE[id] ? `<div class="clear-strip" aria-label="Clearance">${CLEARANCE[id].map(officeChip).join("")}</div>` : "");
const thumb = () => `<div class="thumb" aria-hidden="true"><span class="seal"></span><i class="t"></i><i></i><i class="s"></i><i></i><i></i><i class="s"></i></div>`;
function recStatus(r) {
  if (r.status === "draft") return status("quiet", "Draft", "pencil");
  if (r.status === "review") return status("active", r.version > 1 ? `In review · v${r.version}` : "In review");
  return "";
}
/* Search is by keyword. When the words look like a question, offer Ask IRIS once, above the
   results; an ordinary title or keyword search never shows it. A guess: a title that starts
   "How…" shows it too, which costs one line above correct results. */
const looksLikeQuestion = (q) => !!q && (/\?\s*$/.test(q) || /^\s*(who|whom|whose|what|when|where|why|how|which|does|do|did|is|are|can|could|should|was|were)\b/i.test(q));
/* Keyword search, as in live IRIS: every word must appear; common words and punctuation are ignored. */
const STOP = new Set("a an and are as at be by can could did do does for from has have how i in is it of on or should the this to was were what when where which who whom whose why with".split(" "));
const terms = (q) => (q || "").toLowerCase().replace(/[^\p{L}\p{N}\s-]/gu, " ").split(/\s+/).filter((w) => w && !STOP.has(w));
function recRow(r, { q = "", foot = "" } = {}) {
  const ts = terms(q);
  const hi = (t) => (ts.length ? esc(t).replace(new RegExp(`(${ts.map((w) => w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|")})`, "ig"), "<mark>$1</mark>") : esc(t));
  const saved = S.saved.has(r.id);
  return `<article class="rec">
    <div>
      <div class="rec-kicker"><span>${r.type}</span><span class="sep">·</span><span>${r.unit}</span><span class="sep">·</span><span class="num">${r.year}</span>${r.status !== "published" ? `<span class="sep">·</span>${recStatus(r)}` : ""}</div>
      <h2 class="rec-title"><a href="#/records/${r.id}">${hi(r.title)}</a></h2>
      <p class="byline">${r.authors.map((a) => `<a href="#/people/${slug(a)}">${a}</a>`).join(", ")}</p>
      ${r.abstract ? `<p class="rec-abs">${hi(r.abstract)}</p>` : ""}
      ${foot || `<div class="rec-foot"><span class="views">${ic("eye", "icon-16")}<span class="num">${r.views}</span> views · Published ${r.published}</span>
        <button class="btn btn-secondary btn-sm" type="button" data-action="save" data-id="${r.id}" aria-pressed="${saved}">${ic("bookmark", "icon-16")}${saved ? "Saved" : "Save"}</button></div>`}
    </div>${thumb()}
  </article>`;
}
const slug = (name) => name.toLowerCase().replace(/[^a-z]+/g, "-").replace(/^-|-$/g, "");
const empty = (icon, title, text, action = "") => `<div class="empty"><span class="ico">${ic(icon, "icon-20")}</span><h3>${title}</h3><p>${text}</p>${action ? `<div style="margin-top:8px">${action}</div>` : ""}</div>`;

/* ------------------------------------------------------------- Sign in / up */
function entryFrame(tab, inner, lede = ["Your research has", "a place."]) {
  return `<div class="entry">
    <header class="masthead"><a class="lock" href="#/login" aria-label="IRIS">${mark()}<svg class="brand b-word" viewBox="-4.31 -3.82 230.33 66.87" aria-hidden="true" style="height:20px;width:69px"><use href="#b-word"/></svg></a><span class="vr" aria-hidden="true"></span><img class="cit" src="assets/cit-logo.png" alt="Cebu Institute of Technology – University"></header>
    <div class="entry-main">
      <div class="lede">
        <h1>${lede[0]} <em>${lede[1]}</em></h1>
        <p>Submit your research, follow its review across offices, and find what others have already found.</p>
        <ul>
          <li>${ic("route")}Your adviser and each office review in one place, and you see who has cleared it.</li>
          <li>${ic("shield")}When one office asks for changes, the others' clearances are kept.</li>
          <li>${ic("msg")}Ask IRIS answers from the papers in IRIS and cites the page.</li>
        </ul>
      </div>
      <div class="folder"><span class="folder-tab">${tab}</span><div class="sheet">${inner}</div></div>
    </div>
    <footer class="entry-foot"><span>© 2026 IRIS · Research and IP disclosure</span><a href="#/help">Help</a><a href="#/help#privacy">Privacy notice</a></footer>
  </div>`;
}
function viewLogin() {
  return {
    title: "Sign in", fab: false,
    html: entryFrame("Sign in", `
      <h2>Welcome back</h2>
      <form class="stack" data-form="login" novalidate>
        <div class="field"><label for="li-email">Email address</label><input class="input" id="li-email" type="email" autocomplete="username" required><span class="err" id="li-email-err" hidden></span></div>
        <div class="field"><div class="row" style="justify-content:space-between"><label for="li-pw">Password</label><a class="small" href="#/password/forgot">Forgot password?</a></div>
          <div class="input-wrap"><input class="input" id="li-pw" type="password" autocomplete="current-password" required><button class="btn btn-ghost btn-sm reveal" type="button" data-action="reveal" aria-controls="li-pw" aria-pressed="false">Show</button></div><span class="err" id="li-pw-err" hidden></span></div>
        <label class="check"><input type="checkbox" checked> Keep me signed in on this device</label>
        <button class="btn btn-primary" type="submit" style="width:100%;min-height:44px">Sign in</button>
      </form>
      <p class="small muted" style="text-align:center">New to IRIS? <a href="#/signup">Create an account</a></p>`),
  };
}
function viewSignup() {
  return {
    title: "Create an account", fab: false,
    html: entryFrame("Create an account", `
      <ol class="stepper" aria-label="Step 1 of 3"><li aria-current="step">Your name</li><li>Affiliation</li><li>Password</li></ol>
      <h2>Who are you?</h2>
      <form class="stack" data-form="signup" novalidate>
        <div class="row" style="gap:12px;align-items:start;flex-wrap:nowrap">
          <div class="field" style="flex:1"><label for="su-first">First name</label><input class="input" id="su-first" autocomplete="given-name" required><span class="err" hidden></span></div>
          <div class="field" style="flex:1"><label for="su-last">Last name</label><input class="input" id="su-last" autocomplete="family-name" required><span class="err" hidden></span></div>
        </div>
        <div class="field"><label for="su-email">Institutional email</label><input class="input" id="su-email" type="email" autocomplete="email" required aria-describedby="su-email-hint"><span class="hint" id="su-email-hint">Use the email your institution gave you. We send a confirmation link to it.</span><span class="err" hidden></span></div>
        <button class="btn btn-primary" type="submit" style="width:100%;min-height:44px">Continue</button>
      </form>
      <p class="small muted" style="text-align:center">Already have an account? <a href="#/login">Sign in</a></p>`, ["Begin with your", "research identity."]),
  };
}

/* ----------------------------------------------------------------- Discover */
function viewDiscover(_, q) {
  const d = S.disc;
  if (q.get("q") != null && q.get("q") !== d.q) d.q = q.get("q");
  let list = PUBLISHED.slice();
  if (d.q) { const ts = terms(d.q); list = list.filter((r) => { const h = (r.title + " " + r.abstract + " " + r.authors.join(" ") + " " + r.keywords.join(" ")).toLowerCase(); return ts.every((t) => h.includes(t)); }); }
  if (d.area) list = list.filter((r) => r.area === d.area);
  if (d.unit) list = list.filter((r) => r.unit === d.unit);
  if (d.year) list = list.filter((r) => String(r.year) === d.year);
  if (d.feed === "trending" || d.sort === "views") list.sort((a, b) => b.views - a.views);
  else if (d.sort === "oldest") list.sort((a, b) => a.sortKey - b.sortKey);
  else list.sort((a, b) => b.sortKey - a.sortKey);
  if (d.feed === "foryou") list = list.filter((r) => r.area === "Computer Science" || S.saved.has(r.id));
  const active = [d.area, d.unit, d.year].filter(Boolean).length;
  const areas = [...new Set(PUBLISHED.map((r) => r.area))].sort();
  const units = [...new Set(PUBLISHED.map((r) => r.unit))].sort();
  const people = [
    ["Hermoine Joyce Zozobrado", "Student · College of Computer Studies", 2],
    ["Ana Adviser", "Adviser · College of Computer Studies", 0],
    ["Paolo Ybañez", "Student · College of Computer Studies", 1],
    ["Kyle Dela Peña", "Student · College of Engineering and Architecture", 1],
    ["Maria Clara Santos", "Student · College of Computer Studies", 1],
  ];
  const body = d.view === "people"
    ? `<p class="people-hint">${ic("info", "icon-16")}People are the authors, advisers and reviewers of papers in IRIS. Search by name.</p>
       <div class="result-list">${people.filter(([n]) => !d.q || n.toLowerCase().includes(d.q.toLowerCase())).map(([n, role, c]) => `<div class="person-row"><span class="avatar">${n.split(" ").map((x) => x[0]).slice(0, 2).join("")}</span><div style="flex:1;min-width:0"><a class="strong" href="#/people/${slug(n)}" style="color:var(--ink)">${n}</a><div class="small muted">${role}</div></div><span class="small muted num">${c ? `${c} paper${c > 1 ? "s" : ""}` : "No papers yet"}</span></div>`).join("") || empty("users", "Nobody by that name", `No one in IRIS matches “${esc(d.q)}”.`)}</div>`
    : d.busy
      ? `<div class="result-list" aria-busy="true">${[1, 2, 3].map(() => `<div class="rec" style="min-height:150px"><div class="stack-sm"><i style="display:block;height:12px;width:40%;background:var(--desk);border-radius:6px"></i><i style="display:block;height:22px;width:85%;background:var(--desk);border-radius:6px"></i><i style="display:block;height:12px;width:60%;background:var(--bar);border-radius:6px"></i></div>${thumb()}</div>`).join("")}</div>`
      : list.length
        ? `${looksLikeQuestion(d.q) ? `<p class="ask-suggest">${askMark()}<span>This looks like a question. <a href="#/ai?q=${encodeURIComponent(d.q)}">Ask IRIS</a> answers it from the papers, with page numbers.</span></p>` : ""}<div class="result-list">${list.map((r) => recRow(r, { q: d.q })).join("")}</div>`
        : empty("search", d.q ? `No papers match “${esc(d.q)}”` : "No papers match these filters", d.q ? "Try fewer words, or ask IRIS in a sentence. It reads the papers, not only their titles." : "Clear a filter to see more papers.", d.q ? `<div class="row" style="justify-content:center"><a class="btn btn-primary" href="#/ai?q=${encodeURIComponent(d.q)}">${askMark()}Ask IRIS instead</a><button class="btn btn-secondary" type="button" data-action="clear-search">Clear search</button></div>` : `<button class="btn btn-secondary" type="button" data-action="clear-filters">Clear filters</button>`);
  return {
    title: d.q ? `“${d.q}” · Discover` : "Discover",
    html: `${head({ title: "Discover", desc: "Research, projects and reference papers in IRIS.", actions: canAuthor() ? `<button class="btn btn-primary" type="button" data-publish>${ic("plus")}Publish a paper</button>` : "" })}
      <form role="search" data-form="search">
        <label class="sr-only" for="disc-q">Search ${d.view === "people" ? "people" : "papers"}</label>
        <div class="search-xl">${ic("search", "b-search")}<input id="disc-q" data-fk="disc-q" type="search" value="${esc(d.q)}" placeholder="${d.view === "people" ? "Search people by name" : innerWidth < 400 ? "Search papers" : innerWidth < 480 ? "Titles, authors, keywords" : "Search titles, authors and keywords"}" autocomplete="off"><button class="btn btn-primary" type="submit">Search</button></div>
      </form>
      <div class="toolbar" role="toolbar" aria-label="Browse options">
        <div class="seg" role="group" aria-label="Show">${[["papers", "Papers"], ["people", "People"]].map(([k, l]) => `<button type="button" data-action="disc-view" data-v="${k}" aria-pressed="${d.view === k}">${l}</button>`).join("")}</div>
        ${d.view === "papers" ? `<span class="divider" aria-hidden="true"></span>
        <div class="seg" role="group" aria-label="Feed">${[["latest", "Latest"], ["foryou", "For you"], ["trending", "Most viewed"]].map(([k, l]) => `<button type="button" data-action="disc-feed" data-v="${k}" aria-pressed="${d.feed === k}">${l}</button>`).join("")}</div>
        <button class="chip" type="button" data-action="toggle-filters" aria-expanded="${d.filters}" aria-controls="filters" aria-pressed="${d.filters || active > 0}">${ic("sliders", "icon-16")}Filters${active ? `<span class="badge num">${active}</span>` : ""}</button>
        <button class="chip" type="button" data-action="feeds-menu" aria-haspopup="menu">${ic("bookmark", "icon-16")}My feeds${ic("chev-down", "icon-16")}</button>` : ""}
      </div>
      ${d.view === "papers" && d.filters ? `<div class="filter-panel" id="filters" role="group" aria-label="Filters">
        <div class="field"><label for="f-area">Area</label><select class="select" id="f-area" data-filter="area"><option value="">Any area</option>${areas.map((a) => `<option ${a === d.area ? "selected" : ""}>${a}</option>`).join("")}</select></div>
        <div class="field"><label for="f-unit">College or office</label><select class="select" id="f-unit" data-filter="unit"><option value="">Any</option>${units.map((a) => `<option ${a === d.unit ? "selected" : ""}>${a}</option>`).join("")}</select></div>
        <div class="field"><label for="f-year">Year completed</label><select class="select" id="f-year" data-filter="year"><option value="">Any year</option>${["2026", "2025"].map((y) => `<option ${y === d.year ? "selected" : ""}>${y}</option>`).join("")}</select></div>
        <div class="field"><label for="f-type">Record type</label><select class="select" id="f-type"><option>Thesis / Research</option></select></div>
        <div class="actions"><button class="btn btn-ghost" type="button" data-action="clear-filters">Clear all</button><button class="btn btn-secondary" type="button" data-action="toggle-filters">Done</button></div>
      </div>` : ""}
      ${d.view === "papers" ? `<div class="results-head"><span aria-live="polite"><b class="num" style="color:var(--ink)">${d.busy ? "…" : list.length}</b> ${list.length === 1 ? "paper" : "papers"}${d.q ? ` for “${esc(d.q)}”` : ""}</span><span class="spacer"></span>
        <label class="small" for="sort">Sort</label><select class="select" id="sort" data-fk="sort" data-action-change="sort"><option value="newest" ${d.sort === "newest" ? "selected" : ""}>Newest first</option><option value="oldest" ${d.sort === "oldest" ? "selected" : ""}>Oldest first</option><option value="views" ${d.sort === "views" ? "selected" : ""}>Most viewed</option></select></div>` : ""}
      ${body}`,
  };
}

/* ------------------------------------------------------------------- Record */
function relation(r) {
  if (r.owners && r.owners.includes(S.role)) return "owner";
  if (S.role === "adviser" && r.adviser === "Ana Adviser" && r.status !== "published") return "adviser";
  if ((S.role === "office" || S.role === "rdco") && CLEARANCE[r.id]) return "office";
  return "reader";
}
function viewRecord(m, q) {
  const r = REC[m[1]];
  if (!r || (r.status !== "published" && relation(r) === "reader")) return viewNotFound();
  const rel = relation(r);
  const tabs = [["overview", "Overview", "file"], ["paper", "Paper", "book"]];
  if (rel !== "reader" && r.status !== "draft") tabs.push(["review", "Review", "clipboard"]);
  let tab = q.get("tab") || "overview";
  if (!tabs.some(([k]) => k === tab)) tab = "overview";
  const body = tab === "paper" ? recordPaper(r) : tab === "review" ? recordReview(r, rel) : recordOverview(r, rel);
  const tabTitle = { overview: "", paper: "Paper · ", review: "Review · " }[tab];
  return {
    title: `${tabTitle}${r.title.length > 60 ? r.title.slice(0, 57) + "…" : r.title}`,
    full: true, fab: false,
    html: `<div class="record-bar ${tab !== "overview" ? "always" : ""}" id="record-bar">
        <button class="back" type="button" data-action="back" aria-label="Back">${ic("arrow-left")}<span>Back</span></button>
        <span class="vr" aria-hidden="true"></span>
        <p class="bar-title" aria-hidden="${tab === "overview"}">${esc(r.title)}</p>
        ${VERSIONS[r.id] && VERSIONS[r.id].length > 1 && rel !== "reader" ? `<label class="sr-only" for="ver-pick">Version</label><select class="select sel-sm ver-pick" id="ver-pick" data-action-change="version">${VERSIONS[r.id].slice().reverse().map((v, i) => `<option value="${v.v}" ${(S.ws.ver[r.id] || VERSIONS[r.id].length) === v.v ? "selected" : ""}>v${v.v} · ${v.kind} · ${v.date}${i === 0 ? " (current)" : ""}</option>`).join("")}</select>` : ""}
        <div class="seg" role="tablist" aria-label="Record sections">${tabs.filter(([k]) => !(tab === "review" && k === "paper")).map(([k, l, i]) => `<button type="button" role="tab" aria-selected="${k === tab}" data-action="rec-tab" data-v="${k}" data-id="${r.id}">${ic(i, "icon-16")}${l}</button>`).join("")}</div>
        ${tab === "review" ? `<button class="btn ${S.ask.open ? "btn-primary" : "btn-secondary"} ask-toggle" type="button" data-action="toggle-ask" aria-label="Ask IRIS" aria-expanded="${S.ask.open}" aria-controls="ask-panel">${askMark("icon")}<span class="label">Ask IRIS</span></button>` : ""}
      </div>
      <div class="record-layout ${tab === "review" ? "is-ws" : ""}"><div class="record-main ${tab !== "review" ? "has-fabs" : ""}">${body}</div>${askPanel(r)}${notesPanel(r)}</div>${fabStack(tab)}`,
    after() {
      const bar = $("#record-bar");
      if (bar && tab === "overview") {
        const t = $(".display-title");
        const io = new IntersectionObserver(([e]) => { bar.classList.toggle("scrolled", !e.isIntersecting); $(".bar-title", bar).setAttribute("aria-hidden", String(e.isIntersecting)); }, { rootMargin: "-120px 0px 0px 0px" });
        if (t) io.observe(t);
      }
      if (tab === "review") wsLayout();
    },
  };
}
function recordOverview(r, rel) {
  const saved = S.saved.has(r.id);
  const stateNotice = r.status === "draft"
    ? `<div class="notice warn" style="margin-top:20px">${ic("pencil")}<div><b>Draft, saved ${r.saved}.</b> Only you can see it. Add the details and your manuscript, then submit it to your adviser.<div style="margin-top:10px"><button class="btn btn-primary btn-sm" type="button" data-publish data-resume="105">Continue draft</button></div></div></div>`
    : r.status === "review" && rel !== "reader"
      ? `<div class="notice" style="margin-top:20px">${ic("info")}<div><b>Not published yet.</b> Only you, the adviser and the reviewing offices can open this paper. <a href="#/records/${r.id}?tab=review">See where it is in review</a>.</div></div>`
      : "";
  const overview = r.id === 101 ? `<section class="reading-sec" aria-labelledby="sec-ai">
      <div class="sec-head"><h2 id="sec-ai">${askMark()}AI overview</h2><span class="ai-tag">Generated</span></div>
      <div class="prose">
        <p class="lead">The study predicts chronic absenteeism among senior high school students from records the school already keeps, early enough for advisers to act.</p>
        <h3>What they did</h3>
        <ul><li>Trained random forest, gradient boosting and logistic regression models on 2,184 student records from three school years <span class="cites"><a class="cite" href="#/records/101?tab=paper" aria-label="Page 14">p. 14</a></span></li>
        <li>Measured each with stratified five-fold cross-validation, reporting F1 because chronic absentees are only 11% of students <span class="cites"><a class="cite" href="#/records/101?tab=paper" aria-label="Page 19">p. 19</a></span></li></ul>
        <h3>What they found</h3>
        <ul><li>Gradient boosting did best, with an F1 of 0.81 <span class="cites"><a class="cite" href="#/records/101?tab=paper" aria-label="Page 27">p. 27</a></span></li>
        <li>Absences in the previous term, first-quarter grades and commuting distance were the strongest predictors <span class="cites"><a class="cite" href="#/records/101?tab=paper" aria-label="Page 29">p. 29</a><a class="cite" href="#/records/101?tab=paper" aria-label="Page 30">p. 30</a></span></li></ul>
        <h3>Limits the authors name</h3>
        <ul><li>Data from a single private school, so results may not transfer to public schools <span class="cites"><a class="cite" href="#/records/101?tab=paper" aria-label="Page 41">p. 41</a></span></li></ul>
      </div>
      <p class="small muted" style="margin-top:12px">Written by Ask IRIS from this paper. Check the cited page before you quote it.</p>
    </section>` : "";
  return `<div class="overview">
    <article>
      <div class="rec-meta-line"><span>${r.type}</span><span class="sep">·</span><span>${r.unit}</span><span class="sep">·</span><span>Completed <span class="num">${r.year}</span></span>${r.status !== "published" ? `<span class="sep">·</span>${recStatus(r)}` : ""}</div>
      <h1 class="display-title">${esc(r.title)}</h1>
      <div class="authors">${r.authors.map((a) => `<a class="author" href="#/people/${slug(a)}"><span class="avatar">${a.split(" ").map((x) => x[0]).slice(0, 2).join("")}</span>${a}</a>`).join("")}
        <span class="author"><span class="role">Adviser</span>&nbsp;<a href="#/people/${slug(r.adviser)}" style="font-weight:600;text-decoration:none">${r.adviser}</a></span></div>
      <p class="affil">${r.program} · Cebu Institute of Technology – University</p>
      ${stateNotice}
      <div class="actions-row">
        <a class="btn btn-primary" href="#/records/${r.id}?tab=paper">${ic("book")}Read paper</a>
        ${r.status === "published" ? `<button class="btn btn-secondary" type="button" data-action="save" data-id="${r.id}" aria-pressed="${saved}">${ic("bookmark")}${saved ? "Saved" : "Save"}</button>
        <button class="btn btn-secondary" type="button" data-action="cite" data-id="${r.id}">${ic("quote")}Cite</button>
        <button class="btn btn-secondary" type="button" data-action="share">${ic("link")}Copy link</button>` : ""}
        ${rel === "owner" ? `<button class="btn btn-secondary" type="button" data-action="edit-details" data-id="${r.id}">${ic("pencil")}Edit details</button>` : ""}
        ${rel !== "reader" && r.status !== "draft" ? `<button class="btn btn-secondary" type="button" data-action="docs" data-id="${r.id}">${ic("file")}Documents</button>` : ""}
        ${S.role === "rdco" ? `<button class="icon-btn" type="button" data-action="manage-record" data-id="${r.id}" aria-label="Manage this record" aria-haspopup="menu" aria-expanded="false">${ic("more")}</button>` : ""}
      </div>
      <section class="reading-sec" aria-labelledby="sec-abs">
        <div class="sec-head"><h2 id="sec-abs">Abstract</h2></div>
        ${r.abstract ? `<div class="prose"><p>${esc(r.abstract)}</p></div>` : `<p class="closed-field">No abstract yet. You add it in step 2 of your draft.</p>`}
        ${r.keywords.length ? `<div class="row" style="gap:6px;margin-top:16px">${r.keywords.map((k) => `<span class="meta-chip">${k}</span>`).join("")}</div>` : ""}
      </section>
      ${overview}
      ${r.status === "published" ? relatedHtml(r) : ""}
      ${r.status === "published" ? commentsHtml(r) : ""}
    </article>
    <aside class="details" aria-labelledby="det-h">
      <div class="card">
        <h2 id="det-h">Record details</h2>
        <dl class="kv">
          <dt>Type</dt><dd>${r.type}</dd>
          <dt>Program</dt><dd>${r.program}</dd>
          <dt>Area</dt><dd>${r.area}</dd>
          <dt>PSCED field</dt><dd>${r.psced}</dd>
          <dt>Completed</dt><dd class="num">${r.year}</dd>
          ${r.published ? `<dt>Published</dt><dd class="num">${r.published}</dd><dt>Views</dt><dd class="num">${r.views}</dd><dt>Contact</dt><dd><a href="#/people/${slug(r.authors[0])}">${r.authors[0]}</a></dd>` : ""}
          ${r.submitted ? `<dt>Submitted</dt><dd class="num">${r.submitted}</dd><dt>Version</dt><dd class="num">v${r.version}</dd>` : ""}
        </dl>
      </div>
      ${EMBARGO[r.id] && rel !== "reader" ? embargoCard(r, rel) : ""}
      ${r.status === "published" ? `<div class="card"><h2 style="font-size:16px;font-family:var(--sans)">Full text</h2><p class="small muted" style="margin:4px 0 12px">Reading is open to every IRIS account. A PDF copy needs RDCO's approval.</p><button class="btn btn-secondary btn-sm" type="button" data-action="request-download" data-id="${r.id}">${ic("download", "icon-16")}Request a PDF copy</button></div>` : ""}
    </aside>
  </div>`;
}
function embargoCard(r, rel) {
  const e = EMBARGO[r.id];
  const can = rel === "adviser" || S.role === "rdco";
  if (e.released) return `<div class="card stack-sm"><h2 class="card-title">Embargo</h2><div>${status("settled", "Released", "check")}</div><p class="small muted">${e.released}. Ask IRIS can read it once it's published.</p></div>`;
  return `<div class="card stack-sm"><h2 class="card-title">Embargo</h2><div>${status("quiet", "Under embargo", "lock")}</div>
    <p class="small muted">Ask IRIS can't read or cite it, and it stays out of Discover, until it's released.${e.until ? ` Review date: <span class="num">${e.until}</span>.` : " No review date set."}</p>
    ${can ? `<div class="row" style="gap:6px"><button class="btn btn-secondary btn-sm" type="button" data-action="release" data-id="${r.id}">Release…</button><button class="btn btn-ghost btn-sm" type="button" data-action="embargo-date" data-id="${r.id}">${e.until ? "Change review date…" : "Add review date…"}</button></div>` : `<p class="small muted">Your adviser or RDCO releases it.</p>`}</div>`;
}
function relatedHtml(r) {
  const rel = PUBLISHED.filter((x) => x.id !== r.id).sort((a, b) => (b.area === r.area) - (a.area === r.area) || b.sortKey - a.sortKey).slice(0, 3);
  return `<section class="reading-sec" aria-labelledby="sec-rel"><div class="sec-head"><h2 id="sec-rel">Related works</h2><a class="sec-link" href="#/discover">Explore all papers ${ic("arrow-right", "icon-16")}</a></div>
    <ul class="rel-cards">${rel.map((x) => `<li><a class="rel-card" href="#/records/${x.id}"><span class="rel-t">${esc(x.title)}</span><span class="rel-m"><span class="num">${x.year}</span> · ${x.area}</span></a></li>`).join("")}</ul></section>`;
}
/* Public comments as threads (IR-1024): a top-level comment with its replies under it. */
const TODAY = Date.UTC(2026, 10, 13);
function ago(iso) {
  const d = Math.round((TODAY - Date.parse(iso + "T00:00:00Z")) / 864e5);
  return d <= 0 ? ["Just now", "just now"] : d < 7 ? [`${d}d`, `${d} day${d > 1 ? "s" : ""} ago`] : [`${Math.floor(d / 7)}w`, `${Math.floor(d / 7)} week${d >= 14 ? "s" : ""} ago`];
}
function cmtThreads(list) {
  const byId = Object.fromEntries(list.map((c) => [c.id, c]));
  const rootOf = (c) => (c.to ? rootOf(byId[c.to]) : c);
  const roots = list.filter((c) => !c.to).map((root) => ({ root, replies: list.filter((c) => c.to && rootOf(c).id === root.id) }));
  return { byId, threads: S.comSort === "newest" ? roots.slice().reverse() : roots };
}
function cmtItem(c, size, byId, rail) {
  const mine = c.who === me().name;
  const [short, long] = ago(c.d);
  /* "@name" only when a reply answers another reply, not the thread's first comment. */
  const at = size === "reply" && c.to && byId[c.to] && byId[c.to].to ? byId[c.to] : null;
  if (c.deleted) return `<article class="cmt-it ${size}" id="cmt-${c.id}"><div class="cmt-av"><span class="avatar" aria-hidden="true">?</span>${rail ? '<span class="cmt-rail" aria-hidden="true"></span>' : ""}</div><div><p class="cmt-bub gone">[deleted]</p></div></article>`;
  const body = S.cmt.editing === c.id
    ? `<form class="cmt-edit" data-form="cmt-edit" data-id="${c.id}"><label class="sr-only" for="ce-${c.id}">Edit your comment</label><textarea class="textarea" id="ce-${c.id}" data-fk="ce-${c.id}" rows="2">${esc(c.text)}</textarea><div class="row" style="gap:6px;justify-content:flex-end"><button class="btn btn-ghost btn-sm" type="button" data-action="cmt-edit-cancel">Cancel</button><button class="btn btn-secondary btn-sm" type="submit">Save</button></div></form>`
    : `<div class="cmt-line"><div class="cmt-bub ${S.cmt.hl === c.id ? "hl" : ""}"><p class="cmt-who"><a href="#/people/${slug(c.who)}">${c.who}</a>${c.author ? '<span class="cmt-author">Author</span>' : ""}</p><p class="cmt-text">${at ? `<a class="cmt-at" href="#cmt-${at.id}" data-action="cmt-jump" data-id="${at.id}">@${at.deleted ? "[deleted comment]" : at.who}</a> ` : ""}${esc(c.text)}</p></div>
      <button class="icon-btn cmt-more" type="button" data-action="cmt-more" data-id="${c.id}" data-who="${c.who}" aria-label="More actions for ${mine ? "your" : c.who + "'s"} comment" aria-haspopup="menu" aria-expanded="false">${ic("more")}</button></div>
      <p class="cmt-acts"><button type="button" data-action="cmt-reply" data-id="${c.id}" id="reply-btn-${c.id}" aria-label="Reply to ${c.who}">Reply</button><span aria-hidden="true">·</span><time title="${c.d}" aria-label="${long}">${short}</time>${c.edited ? '<span aria-hidden="true">·</span><span>Edited</span>' : ""}</p>`;
  return `<article class="cmt-it ${size}" id="cmt-${c.id}"><div class="cmt-av"><span class="avatar" aria-hidden="true">${initials(c.who)}</span>${rail ? '<span class="cmt-rail" aria-hidden="true"></span>' : ""}</div><div class="cmt-main">${body}</div></article>`;
}
function commentsHtml(r) {
  const list = COMMENTS[r.id];
  if (!list) return `<section class="reading-sec" aria-labelledby="sec-com"><div class="sec-head"><h2 id="sec-com">Comments</h2></div><p class="closed-field">The authors have closed comments on this paper.</p></section>`;
  const { byId, threads } = cmtThreads(list);
  const count = list.filter((c) => !c.deleted).length;
  const reply = S.cmt.replyTo && byId[S.cmt.replyTo];
  const composerFor = (rootId) => reply && (reply.to ? cmtThreads(list).threads.find((t) => t.replies.includes(reply)) : { root: reply }).root.id === rootId;
  const replyBox = () => `<li class="cmt-rep"><form class="cmt-compose sm" data-form="cmt-reply" data-id="${r.id}"><span class="avatar" aria-hidden="true">${initials(me().name)}</span><div><label class="sr-only" for="cr-in">Reply to ${reply.who}</label><textarea class="textarea" id="cr-in" data-fk="cr-in" rows="1" placeholder="Reply to ${reply.who}…">${esc(S.cmt.drafts[reply.id] || "")}</textarea>
      <p class="cmt-hint">Replying to <b>${reply.who}</b><span aria-hidden="true">·</span><button type="button" data-action="cmt-cancel">Cancel reply</button><span aria-hidden="true">·</span><span>Ctrl+Enter to post</span></p></div><button class="btn btn-secondary btn-sm" type="submit">Post reply</button></form></li>`;
  return `<section class="reading-sec comments-sec" aria-labelledby="sec-com"><div class="sec-head"><h2 id="sec-com">Comments (${count})</h2>${threads.length > 1 ? `<label class="inline-sel"><span>Sort by</span><select class="select sel-sm" id="com-sort" data-action-change="com-sort"><option value="oldest" ${S.comSort === "oldest" ? "selected" : ""}>Oldest</option><option value="newest" ${S.comSort === "newest" ? "selected" : ""}>Newest</option></select></label>` : ""}</div>
    <form class="cmt-compose" data-form="post-comment" data-id="${r.id}"><span class="avatar" aria-hidden="true">${initials(me().name)}</span><div><label class="sr-only" for="com-in">Add a comment</label><textarea class="textarea" id="com-in" data-fk="com-in" rows="1" placeholder="Write a comment…"></textarea><p class="cmt-hint">Everyone who can read this paper sees your comment and your name.</p></div><button class="btn btn-secondary btn-sm" type="submit">Post comment</button></form>
    ${threads.length ? `<ol class="cmt-list" aria-label="Comments">${threads.map(({ root, replies }) => {
      const composing = composerFor(root.id);
      const open = composing || (S.cmt.open[root.id] ?? replies.length <= 2);
      const below = replies.length > 0 || composing;
      return `<li>${cmtItem(root, "root", byId, below)}${below ? `<ol class="cmt-replies" aria-label="Replies to ${root.deleted ? "a deleted comment" : root.who}">
        ${replies.length ? (open ? replies.map((x) => `<li class="cmt-rep">${cmtItem(x, "reply", byId, false)}</li>`).join("") : `<li class="cmt-rep"><button class="cmt-toggle" type="button" data-action="cmt-toggle" data-id="${root.id}" aria-expanded="false">View ${replies.length} ${replies.length === 1 ? "reply" : "replies"}</button></li>`) : ""}
        ${open && replies.length > 2 && !composing ? `<li class="cmt-rep"><button class="cmt-toggle" type="button" data-action="cmt-toggle" data-id="${root.id}" aria-expanded="true">Hide replies</button></li>` : ""}
        ${composing ? replyBox() : ""}</ol>` : ""}</li>`;
    }).join("")}</ol>` : `<p class="small muted">No comments yet. Start the discussion.</p>`}</section>`;
}
/* Notes (IR-580): private to the reader, in the same panel place as Ask IRIS. */
function notesPanel(r) {
  return `<aside class="ask-panel notes-panel" id="notes-panel" aria-labelledby="notes-h" ${S.notesOpen ? "" : "hidden"}>
    <div class="ask-head"><h2 id="notes-h">${ic("sticky")}Notes</h2>
      <button class="icon-btn" type="button" data-action="toggle-ask" aria-label="Ask IRIS" title="Ask IRIS about this paper">${askMark()}</button>
      <button class="icon-btn" type="button" data-action="close-notes" aria-label="Close Notes">${ic("x")}</button></div>
    <div class="notes-meta"><p class="small strong notes-title">${esc(r.title)}</p><p class="small muted">${ic("lock", "icon-16")}Private: only you can read your notes. Not staff, the paper's authors or Ask IRIS.</p></div>
    <div class="notes-body"><label class="sr-only" for="notes-t">Your notes on this paper</label><textarea class="textarea" id="notes-t" data-fk="notes-t" data-id="${r.id}" placeholder="What do you want to remember about this paper? A question, a page, a thought.">${esc(S.notes[r.id] || "")}</textarea>
      <p class="small muted" id="notes-status" aria-live="polite">${S.notes[r.id] ? "Saved" : "Saved as you type"}</p></div>
  </aside>`;
}
function fabStack(tab) {
  if (tab === "review" || S.ask.open || S.notesOpen) return "";
  return `<div class="fab-stack"><button class="notes-fab" type="button" data-action="notes" aria-label="Notes" title="Your private notes on this paper">${ic("sticky")}</button><button class="ask-fab" type="button" data-action="toggle-ask" aria-label="Ask IRIS" title="Ask IRIS about this paper">${askMark()}</button></div>`;
}
function recordPaper(r) {
  return `<div class="reader">${readerTools(r)}<div class="find-bar" id="find-bar" hidden></div><div class="pages" id="pages">${paperPages(r)}</div></div>`;
}
/* ---------------------------------------------------------- Review workspace
   Paper | review pane. People & details lives in the Details tab only; a second tab can be
   opened in a right column on wide screens. Three further changes from the live workspace:
   each column scrolls on its own, status is tone + word + icon, and the clearances kept
   across a revision are visible in the pane head, not only in the sidebar. */
const initials = (n) => n.replace(/^(Dr\.|Engr\.) /, "").split(" ").map((x) => x[0]).slice(0, 2).join("");
const holders = (r) => (CLEARANCE[r.id] || []).filter((c) => ["reviewing", "unclaimed"].includes(c.state) || (c.state === "revising" && S.sentV2.has(r.id))).map((c) => c.party);
function wherePill(r) {
  const rows = CLEARANCE[r.id] || [];
  const rev = rows.find((c) => c.state === "revising");
  if (rev && !S.sentV2.has(r.id)) return status("attention", `With the authors · ${rev.party} asked for changes`, "rotate");
  const h = holders(r);
  if (!h.length && rows.length && rows.every((c) => c.party === "RDCO" || c.state === "cleared" || c.state === "kept")) return status("active", "With RDCO to publish", "eye");
  return h.length ? status("active", `With ${h.join(", ")}`, "eye") : status("quiet", "Not in review", "clock");
}
function keptNote(r) {
  const rows = CLEARANCE[r.id] || [];
  const kept = rows.filter((c) => c.state === "kept" || (c.state === "cleared" && rows.some((x) => x.state === "revising")));
  const rev = rows.find((c) => c.state === "revising" || c.was);
  if (!kept.length || !rev) return "";
  return `<p class="kept-note">${ic("shield", "icon-16")}<span>${kept.map((c) => c.party).join(", ")} ${kept.length > 1 ? "keep their" : "keeps its"} clearance. Only ${rev.party} reviews ${rev.state === "revising" ? "the next version" : `v${r.version}`}.</span></p>`;
}
function myParty(r) {
  if (S.role === "adviser") return "Adviser";
  if (S.role === "office") return "ITSO";
  if (S.role === "rdco") return "RDCO";
  return "";
}
/* What this person can do now, shaped like GitHub's merge box: a status icon, a heading and
   one line under it, then one primary action, at most two others, the rest in a menu. */
function footFor(r, rel) {
  const id = r.id, done = S.finished[id];
  const more = (items) => `<button class="icon-btn" type="button" data-action="foot-more" data-id="${id}" data-items="${items}" aria-label="More review actions" aria-haspopup="menu" aria-expanded="false">${ic("more")}</button>`;
  const F = (tone, icon, h, sub, acts = "") => ({ tone, icon, h, sub, acts });
  if (done) return F("settled", "check", `Your review: ${done}`, "Sent today. Everyone on this review was notified.");
  if (rel === "owner") {
    const rev = (CLEARANCE[id] || []).find((c) => c.state === "revising");
    if (rev && !S.sentV2.has(id)) {
      const open = (THREADS[id] || []).filter((t) => t.state === "open").length;
      return F("attention", "rotate", `${rev.party} asked for changes`, `Send version 2 for ${rev.party}. ${open} open thread${open === 1 ? "" : "s"} to answer.`, `<button class="btn btn-primary" type="button" data-action="send-version" data-id="${id}">${ic("upload")}Send version 2…</button>`);
    }
    return F("quiet", "clock", "Nothing for you to do right now", "You're notified when a reviewer asks for something.");
  }
  if (S.role === "office" && id === 104 && !S.claimed.has(id)) return F("quiet", "hand", "Nobody has claimed this for ITSO", "Due 22 Nov 2026", `<a class="btn btn-secondary" href="#/reviews/console">Assign…</a><button class="btn btn-primary" type="button" data-action="claim" data-id="${id}">${ic("hand")}Claim review</button>`);
  if (S.role === "office" && (id === 111 || id === 104)) {
    const n = (S.ws.drafts[id] || []).length;
    return F("active", "eye", "Your ITSO review is in progress", `${n ? `${n} draft comment${n > 1 ? "s" : ""}, held until you finish · ` : ""}${id === 111 ? "due 15 Nov" : "due 22 Nov"}`, `${more("docs,colleague")}<button class="btn btn-primary" type="button" data-action="finish" data-id="${id}">Finish review…</button>`);
  }
  if (S.role === "adviser" && id === 110) {
    const n = (S.ws.drafts[id] || []).length;
    return F("active", "eye", "Your review isn't sent yet", `${n ? `${n} draft comment${n > 1 ? "s" : ""}, held until you finish · ` : ""}due 17 Nov`, `${more("docs")}<button class="btn btn-primary" type="button" data-action="finish" data-id="${id}">Finish review…</button>`);
  }
  if (S.role === "rdco" && id === 112) return F("settled", "check", "Every office has cleared v1", "Publish it to the catalogue, or keep it unlisted.", `${more("revise,reject")}<button class="btn btn-secondary" type="button" data-action="keep-unlisted" data-id="${id}">Keep unlisted…</button><button class="btn btn-primary" type="button" data-action="publish-rec" data-id="${id}">Accept & publish…</button>`);
  const mine = (CLEARANCE[id] || []).find((c) => c.party === myParty(r));
  if (mine && mine.state === "kept") return F("kept", "shield", "You cleared v1, and it is kept", "Nothing to do. Only the office that asked for changes reviews again.");
  if (mine && mine.state === "cleared") return F("settled", "check", "You cleared this", "Nothing to do.");
  return F("quiet", "clock", "Nothing for you to do right now", S.role === "rdco" ? "RDCO publishes after every office clears." : "You're notified if this needs you again.");
}
const convoOf = (r) => CONVO[r.id] || (HISTORY[r.id] || []).slice().reverse().map(([i, t, d, m]) => ({ ev: i, text: t, date: d, mark: m }));
function wsTabs(r) {
  const th = THREADS[r.id] || [];
  const open = th.filter((t) => t.state === "open").length;
  const cmts = convoOf(r).filter((x) => !x.ev).reduce((n, x) => n + 1 + (x.replies || []).length, 0);
  const n = (v, label) => `<span class="n num" aria-label="${label}">${v}</span>`;
  const tabs = [["conversation", "Conversation", cmts ? n(cmts, `${cmts} comment${cmts > 1 ? "s" : ""}`) : ""], ["threads", "Threads", th.length ? n(th.length, `${th.length} threads, ${open} open`) : ""]];
  { const c = CHANGES[r.id]; tabs.push(["changes", "Changes", c ? n(c.sections.length, `${c.sections.length} sections changed`) : ""]); }
  tabs.push(["details", "Details", ""]);
  return tabs;
}
/* Who sent the version under review, as GitHub says who opened a pull request. */
function paneMeta(r) {
  const vs = VERSIONS[r.id] || [];
  const last = vs.slice(-1)[0] || { v: r.version, date: r.submitted };
  const by = r.authors[0];
  return `<span class="pane-meta"><a href="#/people/${slug(by)}">${by}</a> ${last.v > 1 ? `sent v${last.v}` : "submitted v1"} · ${last.date}</span>`;
}
const TAB_NAMES = { conversation: "Conversation", threads: "Threads", changes: "Changes", details: "Details" };
function wsBody(k, r, rel) { return k === "threads" ? wsThreads(r, rel) : k === "changes" ? wsChanges(r) : k === "details" ? wsDetails(r, rel) : wsConversation(r, rel); }
function recordReview(r, rel) {
  const tabs = wsTabs(r);
  const side = S.ws.mode === "wide" && S.ws.roomy && S.ws.side && TAB_NAMES[S.ws.side] ? S.ws.side : null;
  let tab = S.ws.tab;
  if (!tabs.some(([k]) => k === tab) || tab === side) tab = tabs.find(([k]) => k !== side)[0];
  const foot = footFor(r, rel);
  return `<div class="ws ${side ? "has-side-tab" : ""}" id="ws" data-mode="${S.ws.mode}" data-pane="${S.ws.paneOpen}">
    <section class="ws-paper" id="ws-paper" data-ks aria-label="Paper" data-tour="paper">
      ${readerTools(r, true)}
      <div class="find-bar" id="find-bar" hidden></div>
      <div class="pages" id="pages">${paperPages(r, true)}</div>
      <div class="ws-paperbar"><span class="small">${wherePill(r)}</span><span class="spacer"></span><button class="btn btn-ghost btn-sm" type="button" data-action="tour-start">Take a tour</button><button class="btn btn-secondary btn-sm" type="button" data-action="pane-open" aria-controls="ws-pane" aria-expanded="${S.ws.paneOpen}">${ic("panel", "icon-16")}Open review pane</button></div>
    </section>
    <div class="ws-sep" role="separator" tabindex="0" aria-orientation="vertical" aria-label="Resize the review pane" aria-controls="ws-pane" data-sep="mid"></div>
    <section class="ws-pane" id="ws-pane" aria-labelledby="pane-h" data-tour="pane">
      <header class="pane-head">
        <div class="pane-top"><h2 id="pane-h">Review</h2><span class="spacer"></span>
          <button class="btn btn-ghost btn-sm" type="button" data-action="tour-start">${ic("help", "icon-16")}Tour</button>
          <button class="btn btn-ghost btn-sm pane-back" type="button" data-action="pane-close">${ic("arrow-left", "icon-16")}Back to paper</button></div>
        <p class="pane-where">${wherePill(r)}${paneMeta(r)}</p>
        ${keptNote(r)}
        ${S.ws.tourOffer ? `<div class="tour-offer"><p class="small">New to the review workspace? A four-step tour shows where everything is.</p><div class="row" style="gap:6px"><button class="btn btn-ghost btn-sm" type="button" data-action="tour-dismiss">Not now</button><button class="btn btn-secondary btn-sm" type="button" data-action="tour-start">Start tour</button></div></div>` : ""}
        <div class="pane-tabrow" data-tour="tabs"><div class="tabs pane-tabs" role="tablist" aria-label="Review pane">${tabs.filter(([k]) => k !== side).map(([k, l, n]) => `<button type="button" role="tab" id="wst-${k}" aria-controls="wsp" aria-selected="${k === tab}" data-action="ws-tab" data-v="${k}">${l}${n}</button>`).join("")}</div><button class="icon-btn tabs-split" type="button" data-action="split-menu" aria-haspopup="menu" aria-expanded="false" aria-label="Open a tab beside this one" title="Open a tab beside this one">${ic("columns", "icon-16")}</button></div>
      </header>
      <div class="pane-body" id="wsp" data-ks role="tabpanel" aria-labelledby="wst-${tab}" tabindex="0">${wsBody(tab, r, rel)}</div>
      <footer class="pane-foot" data-tour="footer"><span class="mb-ic ${foot.tone}" aria-hidden="true">${ic(foot.icon)}</span><p class="foot-line"><b>${foot.h}</b><span>${foot.sub}</span></p>${foot.acts ? `<div class="foot-acts">${foot.acts}</div>` : ""}</footer>
    </section>
    ${side ? `<div class="ws-sep side-sep" role="separator" tabindex="0" aria-orientation="vertical" aria-label="Resize the right column" data-sep="side"></div>
    <aside class="ws-side is-tab" id="ws-side" data-ks aria-labelledby="side-h"><div class="side-top"><h2 id="side-h" class="side-h">${TAB_NAMES[side]}</h2><button class="icon-btn" type="button" data-action="split-close" aria-label="Close ${TAB_NAMES[side]} on the right" title="Close">${ic("x", "icon-16")}</button></div><div class="side-tab">${wsBody(side, r, rel)}</div></aside>` : ""}
    <div class="ws-scrim" data-action="pane-close" hidden></div>
  </div>`;
}
/* Clearances, summarised like the box at the end of a pull request: one line on where things
   stand, the list of offices folded under it (the sidebar already lists them). */
function clearBox(r) {
  const rows = CLEARANCE[r.id] || []; if (!rows.length) return "";
  const offices = rows.filter((c) => c.party !== "RDCO");
  const ok = offices.filter((c) => c.state === "cleared" || c.state === "kept");
  const rev = rows.find((c) => c.state === "revising");
  let tone, icon, h, sub;
  if (rev && !S.sentV2.has(r.id)) { tone = "attention"; icon = "rotate"; h = `${rev.party} asked for changes`; sub = `The authors send a new version for ${rev.party}.${ok.length ? ` ${ok.map((c) => c.party).join(", ")} keep${ok.length > 1 ? "" : "s"} ${ok.length > 1 ? "their" : "its"} clearance.` : ""}`; }
  else if (ok.length === offices.length) { tone = "settled"; icon = "check"; h = "Every office has cleared"; sub = "RDCO publishes it next."; }
  else { const h2 = holders(r); tone = "active"; icon = "eye"; h = `${ok.length} of ${offices.length} cleared`; sub = h2.length ? `Waiting for ${h2.join(", ")}.` : "Waiting for the offices."; }
  const t = { kept: "kept", cleared: "settled", reviewing: "active", revising: "attention", unclaimed: "quiet", waiting: "quiet" };
  const ico = { kept: "shield", cleared: "check", reviewing: "eye", revising: "rotate", unclaimed: "hand", waiting: "clock" };
  return `<section class="mbox" aria-labelledby="mb-h">
    <div class="mbox-head"><span class="mb-ic ${tone}" aria-hidden="true">${ic(icon)}</span><div><h3 id="mb-h">${h}</h3><p class="small">${sub}</p></div></div>
    <details class="mbox-list"><summary>${ic("chev-right", "icon-16")}Show all clearances</summary><ul>${rows.map((c) => `<li><span class="rv-st ${t[c.state]}">${ic(ico[c.state])}</span><b>${c.party === "RDCO" ? "RDCO final" : c.party}</b><span class="muted">${c.text}${c.who ? ` · ${c.who}` : ""}</span></li>`).join("")}</ul></details>
  </section>`;
}
function wsConversation(r, rel) {
  let items = convoOf(r);
  const vs = VERSIONS[r.id] || [];
  const first = items[0] && items[0].ev === "file-up" ? items.shift() : null;
  const by = r.authors[0];
  const av = (n) => `<a class="avatar tl-av" href="#/people/${slug(n)}" aria-hidden="true" tabindex="-1">${initials(n)}</a>`;
  return `<ol class="tl" aria-label="Timeline">
    <li class="tl-cmt">${av(by)}<article class="gh-box" aria-label="Submission by ${by}">
      <header class="gh-head"><p><b><a href="#/people/${slug(by)}">${by}</a></b> <span class="muted">${first ? first.text.replace(by + " ", "") : "submitted v1"} · ${first ? first.date : vs.length ? vs[0].date : r.submitted}</span></p><span class="gh-label">Author</span></header>
      <div class="gh-body"><p class="gh-abs">${esc(r.abstract || "")}</p><a class="small" href="#/records/${r.id}">Read the abstract on Overview</a></div>
    </article></li>
    ${items.map((x) => x.ev
    ? `<li class="tl-ev ${x.mark ? "m" : ""}"><span class="tl-badge" aria-hidden="true">${ic(x.ev)}</span><div><p>${x.text}${x.who ? ` <span class="muted">· ${x.who}</span>` : ""} <time class="muted">${x.date}</time></p>${x.note ? `<p class="cv-note">${ic("shield", "icon-16")}${x.note}</p>` : ""}</div></li>`
    : `<li class="tl-cmt">${av(x.who)}<article class="gh-box" aria-label="Comment by ${x.who}">
        <header class="gh-head"><p><b><a href="#/people/${slug(x.who)}">${x.who}</a></b> <span class="muted">commented ${x.date}${x.v ? ` · on v${x.v}` : ""}</span></p><span class="gh-label">${x.role}</span></header>
        <div class="gh-body">${x.quote ? `<blockquote class="cmt-quote">${esc(x.quote)}</blockquote>` : ""}<p>${esc(x.text)}</p>${x.mention ? `<p class="small muted">Mentioned ${x.mention}</p>` : ""}</div>
        ${(x.replies || []).map((y) => `<div class="gh-rep"><span class="avatar sm" aria-hidden="true">${initials(y.who)}</span><div><p class="gh-rh"><b>${y.who}</b> <span class="gh-label">${y.role}</span> <span class="muted">${y.date}</span></p><p>${esc(y.text)}</p></div></div>`).join("")}
        <div class="gh-foot"><button class="gh-reply" type="button" data-action="reply" data-who="${x.who}">Reply to ${x.who.split(" ")[0] === "Dr." ? x.who : x.who.split(" ")[0]}…</button></div>
      </article></li>`).join("")}
  </ol>
  ${clearBox(r)}
  <form class="ws-composer" data-form="ws-comment" data-id="${r.id}">
    <span class="avatar tl-av" aria-hidden="true">${initials(me().name)}</span>
    <div class="gh-box">
      <header class="gh-head"><label for="ws-c"><b>Add a comment</b> <span class="muted">· the authors and every reviewer can read it</span></label></header>
      <div class="gh-body"><textarea class="textarea" id="ws-c" data-fk="ws-c" rows="3" placeholder="Leave a comment"></textarea></div>
      <div class="gh-foot row"><button class="icon-btn" type="button" data-action="saved-replies" aria-label="Saved replies" title="Saved replies" aria-haspopup="menu" aria-expanded="false">${ic("copy")}</button><button class="icon-btn" type="button" data-action="mention" data-id="${r.id}" aria-label="Mention someone" title="Mention someone" aria-haspopup="menu" aria-expanded="false">${ic("user")}</button><span class="spacer"></span><button class="btn btn-primary btn-sm" type="submit">Comment</button></div>
    </div>
  </form>`;
}
const SEV = { must: ["attention", "Must fix", "alert"], suggest: ["quiet", "Suggestion", "msg"] };
const TSTATE = { open: ["active", "Open", "eye"], addressed: ["settled", "Addressed", "check"], resolved: ["kept", "Resolved", "check"], declined: ["quiet", "Declined", "x"] };
function wsThreads(r, rel) {
  const all = THREADS[r.id] || [];
  const mine = (t) => t.party === myParty(r) || t.who === me().name;
  const groups = { open: all.filter((t) => t.state === "open"), yours: all.filter(mine), resolved: all.filter((t) => t.state !== "open"), all };
  const f = groups[S.ws.filter] ? S.ws.filter : "all";
  const list = groups[f];
  const drafts = S.ws.drafts[r.id] || [];
  const reviewer = rel === "office" || rel === "adviser";
  const answered = all.filter((t) => t.answer && t.v < r.version);
  return `${answered.length ? `<section class="resp" aria-labelledby="resp-h"><h3 id="resp-h">Response to reviewers · v${r.version}</h3>${answered.map((t) => `<p class="small"><b class="strong">${t.party}, p. ${t.page}:</b> ${esc(t.answer)}</p>`).join("")}</section>` : ""}
    <div class="row th-tools"><div class="seg" role="group" aria-label="Show threads">${[["open", "Open"], ["yours", "Yours"], ["resolved", "Resolved"], ["all", "All"]].map(([k, l]) => `<button type="button" data-action="th-filter" data-v="${k}" aria-pressed="${k === f}">${l} <span class="n num">${groups[k].length}</span></button>`).join("")}</div>
      ${reviewer ? `<button class="btn btn-secondary btn-sm" type="button" data-action="new-comment" data-id="${r.id}">${ic("msg-plus", "icon-16")}New comment</button>` : ""}</div>
    ${reviewer ? `<p class="small muted">Select a passage in the paper and press <kbd class="kbd">C</kbd>, or use New comment.</p>` : ""}
    ${drafts.length ? `<section class="drafts" aria-labelledby="dr-h"><h3 id="dr-h">Your drafts <span class="muted small">· held until you finish your review</span></h3>${drafts.map((d) => threadCard(d, r, rel, true)).join("")}</section>` : ""}
    ${list.length ? list.map((t) => threadCard(t, r, rel)).join("") : `<p class="th-empty">${f === "open" ? "No open threads. Everything raised so far has an answer." : "No threads here."}</p>`}`;
}
function threadCard(t, r, rel, draft = false) {
  const owner = rel === "owner";
  const mineT = t.party === myParty(r);
  let acts = "";
  if (draft) acts = `<button class="btn btn-ghost btn-sm" type="button" data-action="draft-remove" data-id="${r.id}" data-t="${t.id}">${ic("trash", "icon-16")}Remove draft</button>`;
  else if (owner && t.state === "open") acts = `<button class="btn btn-ghost btn-sm" type="button" data-action="th-decline" data-id="${r.id}" data-t="${t.id}">Decline…</button><button class="btn btn-secondary btn-sm" type="button" data-action="th-address" data-id="${r.id}" data-t="${t.id}">Mark addressed…</button>`;
  else if (mineT && t.state === "addressed") acts = `<button class="btn btn-ghost btn-sm" type="button" data-action="th-reopen" data-id="${r.id}" data-t="${t.id}">Reopen</button><button class="btn btn-secondary btn-sm" type="button" data-action="th-resolve" data-id="${r.id}" data-t="${t.id}">Resolve</button>`;
  if (!draft) acts = `<button class="btn btn-ghost btn-sm" type="button" data-action="reply" data-who="${t.who}">${ic("msg", "icon-16")}Reply</button>${acts}`;
  return `<article class="gh-box th-box ${draft ? "draft" : ""} ${S.ws.anno === t.id ? "is-now" : ""}" id="th-${t.id}" aria-label="${draft ? "Your draft" : `Thread by ${t.who}`} on page ${t.page}">
    <header class="gh-head"><p><b>${t.who}</b> <span class="muted">· ${t.party}</span></p><a class="th-pg" href="#/records/${r.id}?tab=review" data-action="goto-page" data-p="${t.page}" data-t="${t.id}">p. ${t.page} · v${t.v}</a></header>
    <div class="gh-body"><p class="th-head">${status(...SEV[t.sev])}${draft ? status("quiet", "Draft", "pencil") : status(...TSTATE[t.state])}</p>
      <blockquote class="cmt-quote">${esc(t.quote)}</blockquote>
      <p>${esc(t.text)}</p>
      ${draft ? "" : t.answer ? `<div class="th-answer"><p class="small"><b class="strong">Authors' answer:</b> ${esc(t.answer)}</p></div>` : t.state !== "open" ? `<p class="small muted">No answer given.</p>` : ""}</div>
    <div class="gh-foot th-acts">${acts}</div>
  </article>`;
}
function wsChanges(r) {
  const c = CHANGES[r.id];
  if (!c) return `<div class="th-empty"><p class="strong">Only one version so far</p><p class="small muted">When the authors send version 2, what changed shows here section by section.</p></div>`;
  const vs = VERSIONS[r.id];
  const side = S.ws.diff === "side";
  return `<div class="chg-tools">
      <div class="chg-vs"><label class="sr-only" for="chg-a">Compare</label><select class="select sel-sm" id="chg-a">${vs.map((v) => `<option ${v.v === c.from ? "selected" : ""}>v${v.v} · ${v.kind}</option>`).join("")}</select>${ic("arrow-right", "icon-16")}<label class="sr-only" for="chg-b">with</label><select class="select sel-sm" id="chg-b">${vs.map((v) => `<option ${v.v === c.to ? "selected" : ""}>v${v.v} · ${v.kind}</option>`).join("")}</select></div>
      <div class="chg-bar"><p class="small chg-sum"><span class="num">${c.changed}</span> changed <span class="num add">+${c.added}</span> <span class="num del">−${c.removed}</span></p>
        <div class="seg seg-sm" role="group" aria-label="Layout"><button type="button" data-action="diff" data-v="inline" aria-pressed="${!side}">Inline</button><button type="button" data-action="diff" data-v="side" aria-pressed="${side}">Side by side</button></div></div>
    </div>
    <div class="chg-list">${c.sections.map((s, i) => { const seen = S.ws.viewed.has(r.id + ":" + i); return `<details class="chg-sec ${seen ? "seen" : ""}" ${i === 0 ? "open" : ""}>
      <summary><span class="chg-name">${s.name}</span><span class="small muted num">${[s.changed && `${s.changed} changed`, s.added && `+${s.added}`, s.removed && `−${s.removed}`].filter(Boolean).join(" · ")}</span>${seen ? status("settled", "Viewed", "check") : ""}</summary>
      <div class="chg-body ${side ? "side" : ""}">${s.items.map((it) => `<div class="chg-item ${it.kind.toLowerCase()}"><p class="chg-k">${ic(it.kind === "Added" ? "plus" : "x", "icon-16")}${it.kind} <span class="muted">· ${it.kind === "Added" ? `v${c.to}` : `v${c.from}`}</span></p><p class="chg-t">${it.kind === "Added" ? `<ins>${esc(it.text)}</ins>` : `<del>${esc(it.text)}</del>`}</p><a class="small" href="#/records/${r.id}?tab=review" data-action="goto-page" data-p="${it.page}">Show in v${it.kind === "Added" ? c.to : c.from}, p. ${it.page}</a></div>`).join("")}
        <label class="check small chg-viewed"><input type="checkbox" data-action="chg-viewed" data-k="${r.id}:${i}" ${seen ? "checked" : ""}> Viewed</label></div>
    </details>`; }).join("")}</div>
    <button class="btn btn-ghost btn-sm" type="button" data-action="show-unchanged" aria-expanded="${S.ws.showUnchanged}">${S.ws.showUnchanged ? "Hide" : "Show"} ${c.unchanged} unchanged sections</button>
    ${S.ws.showUnchanged ? `<ul class="small muted unchanged">${c.names.map((n) => `<li>${n}</li>`).join("")}</ul>` : ""}`;
}
/* People & details, laid out like GitHub's sidebar: small headed sections divided by rules,
   a gear only where this person can change something, and rarer links at the bottom. */
function wsDetails(r, rel) {
  const rows = CLEARANCE[r.id] || [];
  const tone = { kept: "kept", cleared: "settled", reviewing: "active", revising: "attention", unclaimed: "quiet", waiting: "quiet" };
  const icon = { kept: "shield", cleared: "check", reviewing: "eye", revising: "rotate", unclaimed: "hand", waiting: "clock" };
  const word = { kept: "Kept", cleared: "Cleared", reviewing: "Reviewing", revising: "Changes asked", unclaimed: "Unclaimed", waiting: "Waiting" };
  const vs = VERSIONS[r.id] || [];
  const cur = vs.length ? vs[vs.length - 1] : { v: r.version, kind: "Submission", date: r.submitted };
  const people = [...new Set([...r.authors, r.adviser, ...rows.map((c) => c.who).filter(Boolean)])];
  const due = rows.filter((c) => /^Due/.test(c.date));
  const gear = (action, label, extra = "") => `<button class="icon-btn side-gear" type="button" data-action="${action}" ${extra} aria-label="${label}" title="${label}">${ic("settings", "icon-16")}</button>`;
  const head = (id, t, g = "") => `<div class="side-sh"><h3 id="${id}">${t}</h3>${g}</div>`;
  const person = (n, sub = "") => `<li class="pp"><span class="avatar sm" aria-hidden="true">${initials(n)}</span><a href="#/people/${slug(n)}">${n}</a>${sub ? `<span class="muted">${sub}</span>` : ""}</li>`;
  const sup = DOCS.supporting[r.id] || [];
  return `<div class="side-body">
    <section class="side-sec" aria-labelledby="sd-rv">${head("sd-rv", "Reviewers", S.role === "adviser" || S.role === "rdco" ? gear("request-review", "Request a review", `data-id="${r.id}"`) : S.role === "office" ? gear("add-colleague", "Add a colleague") : "")}
      <ul class="rv-list">${rows.map((c) => { const claimed = c.party === "ITSO" && S.claimed.has(r.id); const st = claimed ? "reviewing" : c.state; const who = c.who || (claimed ? me().name : ""); const w = c.party === "RDCO" && st === "reviewing" ? "Ready" : word[st];
        const sub = [who ? (c.party === "RDCO" ? "RDCO final" : c.party) : c.party === "RDCO" ? "Publishes after every office clears" : "", c.date].filter(Boolean).join(" · ");
        return `<li class="rv"><span class="avatar sm ${who ? "" : "vacant"}" aria-hidden="true">${who ? initials(who) : ""}</span><p class="rv-n">${who ? `<a href="#/people/${slug(who)}">${who}</a>` : c.party}</p><span class="rv-st ${tone[st]}">${ic(icon[st])}<span>${w}</span></span>${sub ? `<p class="rv-p">${sub}</p>` : ""}${c.was ? `<p class="rv-p">${c.was}</p>` : ""}</li>`; }).join("")}</ul>
    </section>
    <section class="side-sec" aria-labelledby="sd-au">${head("sd-au", r.authors.length > 1 ? "Researchers" : "Researcher")}<ul class="pp-list">${r.authors.map((a) => person(a)).join("")}</ul></section>
    <section class="side-sec" aria-labelledby="sd-ad">${head("sd-ad", "Adviser")}<ul class="pp-list">${person(r.adviser)}</ul></section>
    <section class="side-sec" aria-labelledby="sd-cl">${head("sd-cl", "Classification")}
      <div class="lbls"><span class="meta-chip">${r.type}</span><span class="meta-chip">${r.area}</span>${r.keywords.map((k) => `<span class="meta-chip lbl-k">${k}</span>`).join("")}</div>
      <p class="small muted">${r.program} · ${r.unit}</p>
    </section>
    <section class="side-sec" aria-labelledby="sd-vs">${head("sd-vs", "Version")}
      <p class="small"><b class="strong">v${cur.v}</b> · ${cur.kind} · ${cur.date}</p>
      ${vs.length > 1 ? `<p class="small muted">First sent ${vs[0].date}</p><button class="side-link" type="button" data-action="ws-tab" data-v="changes">${ic("history", "icon-16")}Compare ${vs.length} versions</button>` : ""}
    </section>
    ${due.length ? `<section class="side-sec" aria-labelledby="sd-dd">${head("sd-dd", "Due dates")}<ul class="pp-list">${due.map((c) => `<li class="pp">${ic("calendar", "icon-16")}<span>${c.party}</span><span class="muted num">${c.date.replace("Due ", "")}</span></li>`).join("")}</ul></section>` : ""}
    <section class="side-sec" aria-labelledby="sd-dc">${head("sd-dc", "Documents")}
      <ul class="pp-list"><li class="pp">${ic("file", "icon-16")}<a href="#/records/${r.id}?tab=review" data-action="goto-page" data-p="1">Manuscript · v${cur.v}</a></li>${sup.map(([t]) => `<li class="pp">${ic("file", "icon-16")}<span>${t}</span></li>`).join("")}</ul>
      <button class="side-link" type="button" data-action="docs" data-id="${r.id}">All documents</button>
    </section>
    <section class="side-sec" aria-labelledby="sd-pt">${head("sd-pt", `<span class="num">${people.length}</span> participants`)}
      <div class="av-stack">${people.map((p) => `<a class="avatar sm" href="#/people/${slug(p)}" title="${p}" aria-label="${p}">${initials(p)}</a>`).join("")}</div>
    </section>
    <section class="side-sec side-foot" aria-label="More">
      <button class="side-link" type="button" data-toast="Link copied. Only people who can see this review can open it.">${ic("link", "icon-16")}Copy link to this review</button>
      ${rel === "owner" && r.status === "review" ? `<button class="side-link danger" type="button" data-action="withdraw-paper" data-id="${r.id}">${ic("file-x", "icon-16")}Withdraw paper…</button>` : ""}
    </section>
  </div>`;
}
/* Paper toolbar shared by the Paper tab and the workspace. */
function readerTools(r, ws = false) {
  const vs = VERSIONS[r.id] || [];
  const pages = vs.length ? vs[vs.length - 1].pages : 48;
  const canDownload = ws || r.status !== "published";
  return `<div class="reader-tools" role="toolbar" aria-label="Paper">
      <button class="icon-btn" type="button" aria-label="Previous page" disabled>${ic("chev-left")}</button>
      <span class="num pg-l">Page 1 / ${pages}</span>
      ${S.ws.ver[r.id] && S.ws.ver[r.id] < vs.length ? status("quiet", `Reading v${S.ws.ver[r.id]} · not current`, "history") : ""}
      <button class="icon-btn" type="button" aria-label="Next page" data-action="goto-page" data-p="2">${ic("chev-right")}</button>
      <span class="tsep" aria-hidden="true"></span>
      <button class="icon-btn" type="button" aria-label="Zoom out" data-action="zoom" data-v="-1">${ic("zoom-out")}</button>
      <span class="num zoom-l" id="zoom-l">100%</span>
      <button class="icon-btn" type="button" aria-label="Zoom in" data-action="zoom" data-v="1">${ic("zoom-in")}</button>
      <button class="icon-btn" type="button" aria-label="Fit to width" data-action="zoom" data-v="fit">${ic("panel")}</button>
      <span class="spacer"></span>
      <button class="icon-btn" type="button" aria-label="Contents" data-action="outline" aria-haspopup="menu" aria-expanded="false">${ic("scroll")}</button>
      <button class="icon-btn" type="button" aria-label="Find in this paper" data-action="find" aria-controls="find-bar" aria-expanded="false">${ic("search")}</button>
      ${ws && (S.role === "office" || S.role === "adviser") ? `<button class="btn btn-secondary btn-sm" type="button" data-action="new-comment" data-id="${r.id}" aria-label="Comment on a passage">${ic("msg-plus", "icon-16")}<span class="t-label" aria-hidden="true">Comment</span></button>` : ""}
      ${canDownload ? `<button class="icon-btn" type="button" aria-label="Download the manuscript" data-toast="Prototype: the manuscript PDF would download.">${ic("download")}</button>` : `<button class="btn btn-secondary btn-sm" type="button" data-action="request-download" data-id="${r.id}" aria-label="Request a PDF copy">${ic("download", "icon-16")}<span class="t-label" aria-hidden="true">Request PDF</span></button>`}
    </div>`;
}
function paperPages(r, marks = false) {
  return `<div class="pdf-page" role="img" aria-label="Page 1: title page" id="pg-1">
        <img class="logo" src="assets/cit-logo.png" alt="">
        <div class="code">${r.unit.replace("College of ", "").split(" ").map((w) => w[0]).join("")} ${r.year}-0${r.id - 90}</div>
        <hr><div class="pt">${esc(r.title.toUpperCase())}</div><hr>
        <div class="mem">${r.authors.join("<br>")}<br><br>${r.program}<br>${r.year}</div>
      </div>
      <div class="pdf-page" role="img" aria-label="Page 2: abstract" id="pg-2" style="align-items:stretch;text-align:left">
        <div class="pt" style="text-align:center;margin-bottom:6%">ABSTRACT</div>
        ${Array.from({ length: 14 }, (_, i) => `<i style="display:block;height:6px;margin:7px 0;background:#e7e5e4;border-radius:3px;width:${i % 5 === 4 ? 62 : 100}%"></i>`).join("")}
      </div>${marks ? annoPages(r) : ""}`;
}
/* A page for each passage a reviewer commented on. The passage is the one real text on it:
   a pen mark (wash + underline) with the thread's number. Open threads are filled; answered
   and resolved ones keep only the underline. Clicking a mark opens its thread. */
const bars = (n, short = 4) => Array.from({ length: n }, (_, i) => `<i class="pg-bar" style="width:${i % short === short - 1 ? 58 : 100}%"></i>`).join("");
function annoPages(r) {
  const ts = (THREADS[r.id] || []).slice().sort((a, b) => a.page - b.page);
  return ts.map((t, i) => `<div class="pdf-page pg-text" role="group" aria-label="Page ${t.page}" id="pg-${t.page}">
        ${bars(6)}
        <p class="pg-p"><a href="#th-${t.id}" class="anno ${t.state === "open" ? "is-open" : "is-done"} ${S.ws.anno === t.id ? "is-now" : ""}" data-action="anno" data-t="${t.id}" aria-label="Passage on page ${t.page}, thread ${i + 1} by ${t.who}${t.state === "open" ? "" : ", " + TSTATE[t.state][1].toLowerCase()}: open the thread"><span class="anno-pin num" aria-hidden="true">${i + 1}</span>${esc(t.quote)}</a></p>
        ${bars(9, 5)}
        <span class="pg-no num" aria-hidden="true">${t.page}</span>
      </div>`).join("");
}
/* Width decides the layout, not the viewport: the Ask IRIS panel or the icon rail can narrow it. */
function wsLayout() {
  const ws = $("#ws"); if (!ws) return;
  const set = () => {
    if (!ws.isConnected) return;
    const w = ws.clientWidth;
    const mode = w >= 1100 ? "wide" : w >= 740 ? "folded" : "drawer";
    const roomy = w >= 1180; /* a right column needs room for the paper too */
    ws.dataset.roomy = roomy;
    if (roomy !== S.ws.roomy) { S.ws.roomy = roomy; if (S.ws.side && ws.dataset.mode === mode) { rerender(); return; } }
    if (ws.dataset.mode !== mode) {
      ws.dataset.mode = mode;
      const was = S.ws.mode; S.ws.mode = mode;
      if (S.ws.side && (was === "wide") !== (mode === "wide")) { rerender(); return; }
    }
    const scrim = $(".ws-scrim", ws), pane = $(".ws-pane", ws); if (!scrim || !pane) return;
    scrim.hidden = !(mode === "drawer" && S.ws.paneOpen);
    pane.inert = mode === "drawer" && !S.ws.paneOpen;
  };
  try { const c = JSON.parse(store.get("ws-cols", "{}")); if (c.mid) ws.style.setProperty("--mid-w", c.mid + "px"); if (c.side) ws.style.setProperty("--side-w", c.side + "px"); } catch { /* ignore */ }
  set();
  new ResizeObserver(set).observe(ws);
  $$(".ws-sep", ws).forEach((sep) => {
    const key = sep.dataset.sep, v = key === "mid" ? "--mid-w" : "--side-w", lim = key === "mid" ? [340, 640] : [300, 520];
    const cur = () => parseFloat(getComputedStyle(ws).getPropertyValue(v)) || (key === "mid" ? 520 : 380);
    const apply = (px) => { px = Math.round(Math.max(lim[0], Math.min(lim[1], px))); ws.style.setProperty(v, px + "px"); sep.setAttribute("aria-valuenow", px); let c = {}; try { c = JSON.parse(store.get("ws-cols", "{}")); } catch { /* ignore */ } c[key] = px; store.set("ws-cols", JSON.stringify(c)); };
    sep.setAttribute("aria-valuemin", lim[0]); sep.setAttribute("aria-valuemax", lim[1]); sep.setAttribute("aria-valuenow", Math.round(cur()));
    sep.addEventListener("keydown", (e) => { if (e.key === "ArrowLeft" || e.key === "ArrowRight") { e.preventDefault(); apply(cur() + (e.key === "ArrowLeft" ? 24 : -24)); } });
    sep.addEventListener("pointerdown", (e) => {
      e.preventDefault(); sep.setPointerCapture(e.pointerId); const x0 = e.clientX, w0 = cur(); ws.classList.add("dragging");
      const mv = (ev) => apply(w0 + (x0 - ev.clientX));
      const up = () => { sep.removeEventListener("pointermove", mv); sep.removeEventListener("pointerup", up); ws.classList.remove("dragging"); };
      sep.addEventListener("pointermove", mv); sep.addEventListener("pointerup", up);
    });
  });
}
/* Tour: five steps over the real regions. */
/* Open a review tab in a right column, which exists only while a tab is open there. One button at the end of
   the tab row; right-clicking a tab opens the same menu for that tab. Wide layout only. */
function splitMenu(anchor, only) {
  const ws = $("#ws");
  if (!ws || ws.dataset.mode !== "wide" || !S.ws.roomy) { toast("Widen the window to open a tab beside this one"); return; }
  const keys = (only ? [only] : Object.keys(TAB_NAMES)).filter((k) => k !== S.ws.side);
  const items = keys.map((k) => mi(`${TAB_NAMES[k]} on the right`, `data-sp="${k}"`, "columns")).join("")
    + (S.ws.side ? `<div class="menu-sep"></div>${mi(`Close ${TAB_NAMES[S.ws.side]} on the right`, 'data-sp=""', "x")}` : "");
  popover(anchor, `<p class="menu-head">Open beside this one</p>${items}<p class="menu-note">Read one tab while you write in another.</p>`, { align: "end", width: 260, label: "Open beside" });
  pop?.el.addEventListener("click", (e) => {
    const b = e.target.closest("[data-sp]"); if (!b) return; closePopover();
    const was = S.ws.side; S.ws.side = b.dataset.sp || null; store.set("ws-side", S.ws.side || ""); rerender();
    const h = $("#side-h"); if (h) { h.setAttribute("tabindex", "-1"); h.focus(); } else { const t = $(".tabs-split"); if (t) t.focus(); }
    toast(S.ws.side ? `${TAB_NAMES[S.ws.side]} is open on the right` : `Closed ${TAB_NAMES[was]} on the right`);
  });
}
document.addEventListener("contextmenu", (e) => {
  const t = e.target.closest(".pane-tabs [role=tab]"); if (!t || !TAB_NAMES[t.dataset.v]) return;
  e.preventDefault(); splitMenu(t, t.dataset.v);
});
const TOUR = [
  ["paper", "The paper", "Read the manuscript here. Select a passage and press C to comment on it, or use Find and Contents in the toolbar."],
  ["pane", "The review pane", "Where the paper is, who has cleared it and whose clearances are kept, and the conversation with the authors."],
  ["tabs", "Review pane sections", "Conversation is the timeline, Threads the comments on passages, Changes what changed between versions, and Details the people, dates and documents (a gear means you can change that part). The columns button at the end of the row opens a tab on the right."],
  ["footer", "Your part", "Where your part stands, and the one action that moves the paper on. Rarer actions are under More."],
];
let tourEl = null;
function tourEnd() { if (!tourEl) return; tourEl.remove(); tourEl = null; $$(".tour-hl").forEach((x) => x.classList.remove("tour-hl")); document.removeEventListener("keydown", tourKey, true); }
function tourKey(e) { if (e.key === "Escape") { e.stopPropagation(); tourEnd(); } }
function tourStep(i) {
  const ws = $("#ws"); if (!ws) return;
  if (i >= TOUR.length) { tourEnd(); toast("Tour finished. Take a tour is in the review pane whenever you need it."); return; }
  const [k, t, d] = TOUR[i];
  if (ws.dataset.mode === "drawer" && k !== "paper" && !S.ws.paneOpen) { S.ws.paneOpen = true; ws.dataset.pane = "true"; $("#ws-pane").inert = false; $(".ws-scrim", ws).hidden = false; }
  if (ws.dataset.mode === "drawer" && k === "paper" && S.ws.paneOpen) { S.ws.paneOpen = false; ws.dataset.pane = "false"; $("#ws-pane").inert = true; $(".ws-scrim", ws).hidden = true; }
  let target = $(`[data-tour="${k}"]`, ws);
  $$(".tour-hl").forEach((x) => x.classList.remove("tour-hl"));
  target.classList.add("tour-hl");
  if (!tourEl) { tourEl = document.createElement("div"); tourEl.className = "tour"; tourEl.setAttribute("role", "dialog"); tourEl.setAttribute("aria-labelledby", "tour-t"); $("#layer").append(tourEl); document.addEventListener("keydown", tourKey, true); }
  tourEl.innerHTML = `<p class="small muted">Step ${i + 1} of ${TOUR.length}</p><h2 id="tour-t">${t}</h2><p class="small">${d}</p><div class="row" style="gap:6px;justify-content:flex-end"><button class="btn btn-ghost btn-sm" type="button" data-t="end">Skip tour</button>${i ? `<button class="btn btn-secondary btn-sm" type="button" data-t="${i - 1}">Back</button>` : ""}<button class="btn btn-primary btn-sm" type="button" data-t="${i + 1}">${i === TOUR.length - 1 ? "Done" : "Next"}</button></div>`;
  tourEl.onclick = (e) => { const b = e.target.closest("[data-t]"); if (!b) return; if (b.dataset.t === "end") tourEnd(); else tourStep(Number(b.dataset.t)); };
  requestAnimationFrame(() => {
    const rc = target.getBoundingClientRect(), w = tourEl.offsetWidth, h = tourEl.offsetHeight;
    let left = rc.left + 16, top = rc.top + 16;
    if (rc.width > w + 32 && k !== "paper") left = rc.left + (rc.width - w) / 2;
    if (k === "pane" && rc.left - w - 12 >= 12) left = rc.left - w - 12;
    if (k === "footer" || k === "tabs") top = k === "footer" ? rc.top - h - 12 : rc.bottom + 12;
    tourEl.style.left = Math.max(12, Math.min(left, innerWidth - w - 12)) + "px";
    tourEl.style.top = Math.max(12, Math.min(top, innerHeight - h - 12)) + "px";
    $(".btn-primary", tourEl).focus();
  });
}
const STARTERS = {
  paper: ["What did the study find?", "How was the data collected?", "What limits do the authors name?"],
  all: ["Which other papers study this?", "What methods do similar studies use?", "Who else here researches this?"],
};
function askPanel(r) {
  const msgs = S.ask.msgs, all = S.ask.scope === "all";
  /* As in IRIS today: a chat that began on all papers cannot narrow to this one. */
  const locked = msgs.length > 0 && S.ask.startedAll;
  return `<aside class="ask-panel" id="ask-panel" aria-labelledby="ask-h" ${S.ask.open ? "" : "hidden"}>
    <div class="ask-head"><h2 id="ask-h">${askMark()}Ask IRIS</h2>
      ${msgs.length ? `<button class="icon-btn" type="button" data-action="ask-new" aria-label="New chat" title="New chat">${ic("msg-plus")}</button>` : ""}
      <button class="icon-btn" type="button" data-action="notes" aria-label="Notes" title="Your private notes">${ic("sticky")}</button>
      <button class="icon-btn" type="button" data-action="toggle-ask" aria-label="Close Ask IRIS">${ic("x")}</button></div>
    <div class="ask-scroll" id="ask-scroll" aria-live="polite">
      ${msgs.length ? msgs.map(msgHtml).join("") : `<p class="scope">${all ? "Answers can cite any paper in IRIS you can read." : `Answers come from <b>${esc(r.title)}</b> and cite its pages.`}</p>
      ${r.id === 101 && !all ? `<div class="recent-chats"><p class="small strong">Your recent chats about this paper</p><a href="#/ai/c/1">${ic("msg", "icon-16")}What predicts chronic absenteeism?<span class="small muted">Today</span></a></div>` : ""}
      <div class="starters">${STARTERS[S.ask.scope].map((t) => `<button type="button" data-action="ask-starter" data-v="${t}">${ic("arrow-right", "icon-16")}${t}</button>`).join("")}</div>`}
    </div>
    <form class="composer" data-form="ask">
      ${locked ? `<p class="scope-lock" id="scope-lock">${ic("info", "icon-16")}<span>This chat covers all papers.</span><button type="button" data-action="ask-new" data-v="paper">New chat on this paper</button></p>` : ""}
      <div class="composer-box"><label class="sr-only" for="ask-in">${all ? "Ask across all papers" : "Ask about this paper"}</label><textarea id="ask-in" data-fk="ask-in" rows="1" placeholder="${all ? "Ask across all papers" : "Ask about this paper"}"></textarea>
        <div class="composer-row"><button class="scope-btn ${all ? "is-all" : ""}" type="button" data-action="ask-scope-menu" aria-haspopup="menu" aria-expanded="false" aria-label="Answers from: ${all ? "all papers" : "this paper"}" ${locked ? 'disabled aria-describedby="scope-lock"' : ""}>${ic(all ? "layers" : "file", "icon-16")}${all ? "All papers" : "This paper"}${locked ? "" : ic("chev-down", "icon-16")}</button><button class="send" type="submit" aria-label="Send">${ic("arrow-up", "icon-16")}</button></div></div>
      <p class="disclaimer">Ask IRIS can be wrong. Check the cited page.</p>
    </form>
  </aside>`;
}
function msgHtml(m) {
  if (m.divider) return `<p class="scope-div"><span>${m.divider === "all" ? "All papers from here" : "This paper from here"}</span></p>`;
  if (m.q) return `<p class="msg-q">${esc(m.q)}</p>`;
  if (m.typing) return `<p class="msg-a muted">${ic("book", "icon-16")} Reading the papers. This can take a few seconds…</p>`;
  const src = m.all ? SRC_ALL : SRC_PAPER;
  return `<div class="msg-a">${m.all ? CANNED_ALL : CANNED}<button class="sources-btn" type="button" data-action="toggle-sources" aria-expanded="false">${ic("file", "icon-16")}${src.length} sources</button>
    <div class="sources" hidden>${src.map(([id, t, sec, pg], i) => `<a class="source" href="#/records/${id}?tab=paper"><span class="no">${i + 1}</span><span><b>${t}</b>${sec}</span><span class="pg">p. ${pg}</span></a>`).join("")}</div></div>`;
}
const SRC_PAPER = [[101, "Predicting Student Absenteeism", "Results and discussion", 27], [101, "Predicting Student Absenteeism", "Feature importance", 29]];
const SRC_ALL = [[101, "Predicting Student Absenteeism", "Results and discussion", 27], [109, "Perceived Usability of the CIT-U Learning Management System Among First-Year Students", "Discussion", 18]];
const CANNED_ALL = `<p>This paper finds that previous-term absences predict chronic absenteeism best <a class="cite" href="#/records/101?tab=paper">p. 27</a>.</p><p>One other paper touches on it: first-year students who rarely used the learning system also missed more classes <a class="cite other" href="#/records/109?tab=paper">Perceived Usability…, p. 18</a>.</p>`;
const CANNED = `<p>Gradient boosting predicted chronic absenteeism best, with an F1 of 0.81 <a class="cite" href="#/records/101?tab=paper">p. 27</a>.</p><ul><li><b>Previous-term absences</b> were the strongest single predictor.</li><li><b>First-quarter grades</b> and <b>commuting distance</b> came next <a class="cite" href="#/records/101?tab=paper">p. 29</a>.</li></ul><p>The authors suggest a monthly early-warning list that advisers review with guidance counselors.</p>`;

/* ------------------------------------------------------------------ Library */
/* Only a paper's authors publish: Student and Adviser (live IRIS, lib/access.ts AUTHORS). Offices
   clear what others submit and RDCO files through Import records, so neither authors. */
const canAuthor = () => S.role === "student" || S.role === "adviser";
function viewLibrary(_, q) {
  const author = canAuthor();
  let tab = q.get("tab") || (author ? "overview" : "saved");
  const mine = RECORDS.filter((r) => r.owners && r.owners.includes(S.role));
  const saved = RECORDS.filter((r) => S.saved.has(r.id));
  const dls = S.role === "student" ? [["Forecasting Dengue Incidence in Cebu City…", "12 Nov 2026", "Pending", "quiet"], ["A Low-Cost IoT Monitor for Water Quality…", "2 Nov 2026", "Approved · expires 16 Nov", "settled"]] : [];
  const tabs = [["overview", "Overview"], ["research", "My research", mine.length], ["saved", "Saved papers", saved.length], ["downloads", "Download requests", dls.length]].filter(([k]) => author || k === "saved" || k === "downloads");
  if (!tabs.some(([k]) => k === tab)) tab = tabs[0][0];
  let body = "";
  if (tab === "overview") {
    const steps = mine.length ? `
      <div class="step-row urgent"><span class="ico">${ic("pencil", "icon-20")}</span><div><h3><a href="#/records/105" style="color:inherit;text-decoration:none">Quantitative Forecasting of Land Suitability in Metro Cebu</a></h3><p class="what">Draft · step 2 of 3, Details. Saved 11 Nov.</p></div><button class="btn btn-primary" type="button" data-publish data-resume="105">Continue draft</button></div>
      <div class="step-row"><span class="ico">${ic("eye", "icon-20")}</span><div><h3><a href="#/records/103?tab=review" style="color:inherit;text-decoration:none">Complementary Roles of Brand Familiarity and Brand Differentiability…</a></h3><p class="what">IERC is reviewing your version 2. Nothing to do yet.</p>${clearStrip(103)}</div><a class="btn btn-secondary" href="#/records/103?tab=review">Open review</a></div>
      <div class="step-row"><span class="ico">${ic("clock", "icon-20")}</span><div><h3><a href="#/records/104?tab=review" style="color:inherit;text-decoration:none">Activity Preference and Level of Physical Activity Participation…</a></h3><p class="what">With ITSO, IERC and KTTO since 8 Nov. Nothing to do yet.</p>${clearStrip(104)}</div><a class="btn btn-secondary" href="#/records/104?tab=review">Open review</a></div>`
      : empty("file-up", "You haven't published anything", "Papers you publish, or are named as an author on, appear here with where each one is in review.", `<button class="btn btn-primary" type="button" data-publish>${ic("plus")}Publish a paper</button>`);
    body = `<h2 class="section-title" style="margin-bottom:12px">Your papers</h2><div class="next-steps">${steps}</div>
      <h2 class="section-title" style="margin:32px 0 12px">Saved recently</h2><div class="result-list">${saved.slice(0, 2).map((r) => recRow(r)).join("") || empty("bookmark", "Nothing saved yet", "Save a paper from Discover to keep it here.")}</div>`;
  } else if (tab === "research") {
    body = mine.length ? `<div class="result-list">${mine.map((r) => recRow(r, { foot: `<div class="rec-foot"><span class="views">${r.status === "draft" ? `Saved ${r.saved}` : `Submitted ${r.submitted}`}</span>${r.status === "draft" ? `<button class="btn btn-ghost btn-sm" type="button" data-action="delete-draft" data-id="${r.id}">${ic("trash", "icon-16")}Delete draft</button><button class="btn btn-primary btn-sm" type="button" data-publish data-resume="${r.id}">Continue draft</button>` : `<a class="btn btn-secondary btn-sm" href="#/records/${r.id}?tab=review">Open review</a>`}</div>${r.status === "review" ? clearStrip(r.id) : ""}` })).join("")}</div>` : empty("file-up", "No research yet", "Papers you publish appear here.");
  } else if (tab === "saved") {
    body = saved.length ? `<div class="result-list">${saved.map((r) => recRow(r)).join("")}</div>` : empty("bookmark", "Nothing saved yet", "Save a paper from Discover to keep it here.", `<a class="btn btn-secondary" href="#/discover">Go to Discover</a>`);
  } else {
    body = dls.length ? `<div class="table-wrap"><table class="stack-sm-table"><caption class="sr-only">Your download requests</caption><thead><tr><th scope="col">Paper</th><th scope="col">Requested</th><th scope="col">Status</th><th scope="col"><span class="sr-only">Action</span></th></tr></thead><tbody>${dls.map(([t, d, s, tone]) => `<tr><td class="strong">${t}</td><td data-label="Requested" class="num">${d}</td><td data-label="Status">${status(tone, s)}</td><td class="act" style="text-align:right">${tone === "settled" ? `<button class="btn btn-secondary btn-sm" type="button" data-toast="Prototype: the PDF would download here.">${ic("download", "icon-16")}Download PDF</button>` : ""}</td></tr>`).join("")}</tbody></table></div>`
      : empty("file-down", "No download requests", "When you ask RDCO for a PDF copy of a paper, the request and its answer appear here.");
  }
  return {
    title: tab === "overview" ? "My Library" : `${tabs.find((t) => t[0] === tab)[1]} · My Library`,
    html: `${head({ title: "My Library", desc: author ? "Your papers, the papers you saved, and your PDF requests." : "Papers you saved, and your PDF requests.", actions: author ? `<button class="btn btn-primary" type="button" data-publish>${ic("plus")}Publish a paper</button>` : "" })}
      <div class="tabs" role="tablist" aria-label="My Library">${tabs.map(([k, l, n]) => `<a role="tab" href="#/library?tab=${k}" aria-selected="${k === tab}">${l}${n != null ? `<span class="n num">${n}</span>` : ""}</a>`).join("")}</div>${body}`,
  };
}

/* ------------------------------------------------------------------ Ask IRIS */
function viewAsk(m, q) {
  const cid = m[1] ? Number(m[1]) : null;
  const seed = q.get("q");
  if (seed && S.chat.seeded !== seed) { S.chat.seeded = seed; S.chat.msgs = [{ q: seed }, { typing: true }]; setTimeout(() => { S.chat.msgs = [{ q: seed }, { a: CANNED }]; if (location.hash.startsWith("#/ai")) rerender(); }, 900); }
  const msgs = cid === 1 ? [{ q: "What predicts chronic absenteeism among senior high school students?" }, { a: CANNED }] : S.chat.msgs;
  const conv = CONVOS.find((c) => c.id === cid);
  let lastG = "";
  const shown = CONVOS.filter((c) => !CONVO_GONE.has(c.id));
  /* As in live IRIS: a delete button on each conversation, shown on hover or focus (always on touch). */
  const list = shown.length ? shown.map((c) => { const g = c.g !== lastG ? `<p class="convo-group">${c.g}</p>` : ""; lastG = c.g; return `${g}<div class="convo-row"><a class="convo" href="#/ai/c/${c.id}" ${c.id === cid ? 'aria-current="true"' : ""}><b>${c.title}</b><span>${c.when}</span></a><button class="icon-btn convo-del" type="button" data-action="convo-del" data-id="${c.id}" aria-label="Delete ${esc(c.title)}" title="Delete conversation">${ic("trash", "icon-16")}</button></div>`; }).join("")
    : `<p class="small muted convo-none">No conversations yet. Ask a question to start one.</p>`;
  return {
    title: conv ? `${conv.title} · Ask IRIS` : "Ask IRIS",
    full: true, fab: false,
    html: `<div class="chat-layout" id="chat-layout">
      <nav class="convos" aria-label="Conversations"><div class="convos-head"><a class="btn btn-primary" href="#/ai" data-action="new-chat">${ic("msg-plus")}New conversation</a></div><div class="convos-list">${list}</div></nav>
      <section class="thread" aria-labelledby="thread-h">
        <div class="thread-head"><button class="icon-btn show-convos" type="button" data-action="show-convos" aria-label="Show conversations">${ic("history")}</button><h1 id="thread-h">${conv ? conv.title : "New conversation"}</h1></div>
        <div class="thread-body" id="thread-body"><div class="thread-col" aria-live="polite">
          ${msgs.length ? msgs.map(msgHtml).join("") : `<div class="chat-empty">${askMark()}<h2>Ask about research in IRIS</h2><p class="muted" style="max-width:52ch">IRIS answers from papers you are allowed to read and cites the page each claim comes from.</p>
            <div class="starters">${["What predicts chronic absenteeism among senior high students?", "Which theses used IoT sensors, and what did they measure?", "Compare the methods of the dengue forecasting papers"].map((s) => `<button type="button" data-action="chat-starter" data-v="${s}">${ic("arrow-right", "icon-16")}${s}</button>`).join("")}</div></div>`}
        </div></div>
        <form class="composer" data-form="chat"><div class="composer-box"><label class="sr-only" for="chat-in">Ask IRIS a question</label><textarea id="chat-in" data-fk="chat-in" rows="1" placeholder="Ask a question about research in IRIS"></textarea>
          <div class="composer-row"><button class="depth" type="button" data-action="depth" aria-haspopup="menu">${ic(S.chat.depth === "Standard" ? "search" : "book", "icon-16")}${S.chat.depth}${ic("chev-down", "icon-16")}</button><button class="send" type="submit" aria-label="Send">${ic("arrow-up", "icon-16")}</button></div></div>
          <p class="disclaimer">Ask IRIS can be wrong. Check the cited page.</p></form>
      </section></div>`,
  };
}

/* ------------------------------------------------------------------ Reviews */
function viewReviews(_, q) {
  const r = me();
  const tab = q.get("tab") || "todo";
  const Q = REVIEWQ[S.role];
  const scoped = (arr) => (r.office && S.revScope === "mine" ? arr.filter((x) => x.mine || S.role === "adviser") : arr);
  const tabs = [["todo", "To review"], ["progress", "In review"], ["done", "Done"]];
  let rows = scoped(Q[tab]);
  const OUT = ["All", "Cleared", "Finding recorded", "Accepted", "Rejected", "Published"];
  let tools = "";
  if (tab === "done") {
    const f = OUT.includes(S.doneFilter) ? S.doneFilter : "All";
    tools = `<div class="row chip-row" role="group" aria-label="Outcome">${OUT.map((o) => `<button class="chip" type="button" data-action="done-filter" data-v="${o}" aria-pressed="${o === f}">${o}<span class="num muted">${o === "All" ? rows.length : rows.filter((x) => x.out === o).length}</span></button>`).join("")}</div>`;
    if (f !== "All") rows = rows.filter((x) => x.out === f);
  } else {
    const so = S.revSort;
    tools = `<div class="row chip-row" role="group" aria-label="Sort and filter">${[["due", "Soonest due"], ["wait", "Longest waiting"], ["overdue", "Overdue only"]].map(([k, l]) => `<button class="chip" type="button" data-action="rev-sort" data-v="${k}" aria-pressed="${k === so}">${l}</button>`).join("")}</div>`;
    rows = so === "overdue" ? rows.filter((x) => x.overdue) : rows.slice().sort((a, b) => (so === "wait" ? (b.w || 0) - (a.w || 0) : (a.dn || 99) - (b.dn || 99)));
  }
  const desc = r.office ? `Papers routed to ${r.office}. Claim one, or let your coordinator assign it.` : "Papers where you are named as adviser.";
  const emptyMsg = tab === "todo" && S.revSort === "overdue" ? ["check", "Nothing overdue", "Every review waiting for you is still within its due date."]
    : tab === "todo" ? ["inbox", "Nothing waiting for you", "When a paper needs your review, it appears here and in your notifications."]
      : tab === "done" && S.doneFilter !== "All" ? ["clipboard", `No reviews ended “${S.doneFilter}”`, "Choose All to see every finished review."]
        : ["clipboard", "Nothing here", S.revScope === "mine" && r.office ? `Switch to “All of ${r.office}” to see the office's reviews.` : "Reviews move here as they progress."];
  return {
    title: "My Reviews",
    html: `${head({ title: "My Reviews", desc, actions: r.coordinator ? `<a class="btn btn-secondary" href="#/reviews/console">${ic("dashboard")}Office console</a><a class="btn btn-secondary" href="#/reviews/analytics">${ic("chart")}Workflow analytics</a>` : "" })}
      <div class="tabs" role="tablist" aria-label="Review status" style="margin-bottom:16px">${tabs.map(([k, l]) => `<a role="tab" href="#/reviews?tab=${k}" aria-selected="${k === tab}">${l}<span class="n num">${scoped(Q[k]).length}</span></a>`).join("")}</div>
      <div class="row" style="justify-content:space-between;margin-bottom:16px;gap:12px">${tools}${r.office ? `<div class="seg" role="group" aria-label="Whose reviews"><button type="button" data-action="rev-scope" data-v="mine" aria-pressed="${S.revScope === "mine"}">Mine</button><button type="button" data-action="rev-scope" data-v="all" aria-pressed="${S.revScope === "all"}">All of ${r.office}</button></div>` : ""}</div>
      <div class="result-list">${rows.length ? rows.map((x) => { const rec = REC[x.id]; const go = `#/records/${rec.id}?tab=${rec.status === "published" ? "overview" : "review"}`; return `<article class="rec" style="grid-template-columns:minmax(0,1fr)"><div>
          <div class="rec-kicker"><span>${rec.authors.join(", ")}</span><span class="sep">·</span><span>${rec.unit}</span>${rec.version ? `<span class="sep">·</span><span>v${rec.version}</span>` : ""}${x.due ? `<span class="sep">·</span>${status(tab === "todo" && x.dn && x.dn <= 15 ? "attention" : "quiet", x.due, "calendar")}` : ""}${x.out ? `<span class="sep">·</span>${status(x.out === "Published" ? "settled" : "kept", x.out, "check")}` : ""}</div>
          <h2 class="rec-title"><a href="${go}">${rec.title}</a></h2>
          <p class="byline">${x.note}${x.w ? ` · <span class="num">waiting ${x.w} days</span>` : ""}</p>
          ${clearStrip(rec.id)}
          <div class="rec-foot"><span class="views"></span><a class="btn ${tab === "todo" ? "btn-primary" : "btn-secondary"} btn-sm" href="${go}">${tab === "todo" ? "Start review" : "Open"}</a></div>
        </div></article>`; }).join("") : empty(...emptyMsg)}</div>`,
  };
}
function viewConsole() {
  const r = me();
  const rows = [
    { id: 104, who: "", due: "22 Nov 2026", st: ["quiet", "Unassigned", "hand"] },
    { id: 111, who: "Irene Villanueva", due: "15 Nov 2026", st: ["attention", "Due in 2 days", "alert"] },
    { id: 113, title: "Biochar Amendment Effects on Lettuce Yield in Talisay Upland Farms", who: "Mark Abellana", due: "12 Nov 2026", st: ["attention", "Overdue by 1 day", "alert"] },
    { id: 103, who: "Irene Villanueva", due: "—", st: ["kept", "Cleared on v1 · kept", "shield"] },
  ];
  return {
    title: `${r.office} office console`,
    html: `${head({ title: `${r.office} office console`, crumbs: [["My Reviews", "#/reviews"], ["Office console"]], desc: `Assign ${r.office}'s reviews, and move due dates when a reviewer needs more time.` })}
      <div class="table-wrap"><div class="table-scroll"><table class="stack-sm-table"><caption class="sr-only">Reviews routed to ${r.office}</caption>
        <thead><tr><th scope="col">Paper</th><th scope="col">Reviewer</th><th scope="col">Due</th><th scope="col">Status</th><th scope="col"><span class="sr-only">Actions</span></th></tr></thead>
        <tbody>${rows.map((x) => { const rec = REC[x.id] || { title: x.title, authors: ["Bea Gonzales"], version: 1 }; return `<tr>
          <td><a class="strong" href="${REC[x.id] ? `#/records/${x.id}?tab=review` : "#/reviews/console"}" style="color:var(--ink)">${rec.title.length > 70 ? rec.title.slice(0, 68) + "…" : rec.title}</a><span class="cell-sub">${rec.authors.join(", ")} · v${rec.version}</span></td>
          <td data-label="Reviewer">${x.who || '<span class="muted">Nobody yet</span>'}</td>
          <td data-label="Due" class="num">${x.due}</td>
          <td data-label="Status">${status(...x.st)}</td>
          <td class="act" style="text-align:right;white-space:nowrap">${x.id === 103 ? "" : x.who ? `<button class="icon-btn" type="button" data-action="row-more" data-who="${x.who}" aria-label="More actions for this review" aria-haspopup="menu">${ic("more")}</button>` : `<button class="btn btn-secondary btn-sm" type="button" data-action="assign">Assign…</button>`}</td></tr>`; }).join("")}</tbody></table></div></div>`,
  };
}
function viewAnalytics() {
  const r = me();
  const rows = [["Adviser", 38, 34, 3, 4.5, 0], ["ITSO", 31, 26, 2, 6.0, 1], ["IERC", 31, 22, 6, 9.5, 2], ["KTTO", 31, 27, 1, 5.0, 0], ["RDCO", 24, 21, 0, 2.0, 0]];
  return {
    title: "Workflow analytics",
    html: `${head({ title: "Workflow analytics", crumbs: [["My Reviews", "#/reviews"], ["Analytics"]], desc: "How long each party takes to review, 1 Jun to 13 Nov 2026.", actions: `<label class="sr-only" for="period">Period</label><select class="select" id="period" style="width:auto;min-height:40px"><option>1 Jun – 13 Nov 2026</option><option>This semester</option><option>Last 30 days</option></select>` })}
      <div class="steps3" style="margin-bottom:24px">
        <div class="card"><p class="small muted">Papers submitted</p><p class="num" style="font:600 32px/40px var(--serif);color:var(--ink)">38</p><p class="small muted">24 published, 11 in review, 3 drafts returned</p></div>
        <div class="card"><p class="small muted">Median days, submission to publication</p><p class="num" style="font:600 32px/40px var(--serif);color:var(--ink)">27</p><p class="small muted">Slowest step: IERC, 9.5 days</p></div>
        <div class="card"><p class="small muted">Clearances kept across a revision</p><p class="num" style="font:600 32px/40px var(--serif);color:var(--ink)">19</p><p class="small muted">Reviews nobody had to repeat</p></div>
      </div>
      <div class="table-wrap"><div class="table-scroll"><table><caption>By party</caption>
        <thead><tr><th scope="col">Party</th><th scope="col" class="n">Received</th><th scope="col" class="n">Cleared</th><th scope="col" class="n">Revisions asked</th><th scope="col" class="n">Median days</th><th scope="col" class="n">Overdue now</th></tr></thead>
        <tbody>${rows.map(([p, a, b, c, d, e]) => `<tr ${p === r.office ? 'style="font-weight:600"' : ""}><th scope="row" style="background:none;color:var(--ink);font-size:14px;border-bottom:1px solid var(--desk)">${p}${p === r.office ? ' <span class="meta-chip">You</span>' : ""}</th><td class="n">${a}</td><td class="n">${b}</td><td class="n">${c}</td><td class="n">${d.toFixed(1)}</td><td class="n">${e ? `<b style="color:var(--maroon)">${e}</b>` : e}</td></tr>`).join("")}</tbody></table></div></div>
      <details class="card" style="margin-top:16px"><summary class="strong" style="cursor:pointer">How these numbers are counted</summary><div class="prose small" style="margin-top:8px;font-size:14px"><p>Days run from when a party is asked to when it clears or asks for a revision, counting weekends. A clearance kept across a revision is not counted again. Papers still in review count as received but not cleared.</p></div></details>`,
  };
}

/* --------------------------------------------------------- Notifications etc. */
function notifItems(limit, onlyUnread = false, compact = false) {
  const list = (NOTIFS[S.role] || []).slice(0, limit || 99);
  let g = "";
  return list.map((n, i) => {
    const unread = n.unread && !S.read.has(S.role + i);
    if (onlyUnread && !unread) return "";
    const grp = n.g !== g ? `<div class="notif-group">${n.g}</div>` : ""; g = n.g;
    const inner = `<span class="ud" aria-hidden="true"></span><div><p class="text">${unread ? '<span class="sr-only">Unread. </span>' : ""}${n.text}</p><p class="when"><span>${n.when}</span>${n.resolved ? `${status("settled", n.resolved, "check")}` : ""}</p></div>`;
    if (compact) return `${grp}<a class="notif compact ${unread ? "unread" : ""} ${n.resolved ? "resolved" : ""}" href="${n.href}" data-read="${i}">${inner}</a>`;
    return `${grp}<div class="notif ${unread ? "unread" : ""} ${n.resolved ? "resolved" : ""}">${inner}<a class="btn btn-secondary btn-sm" href="${n.href}" data-read="${i}">Open</a></div>`;
  }).join("");
}
function viewNotifications(_, q) {
  const f = q.get("show") || "all";
  return {
    title: "Notifications",
    html: `${head({ title: "Notifications", actions: `<button class="btn btn-secondary" type="button" data-action="mark-all">${ic("check")}Mark all as read</button>` })}
      <div class="row" style="margin-bottom:16px"><div class="seg" role="group" aria-label="Show"><button type="button" data-action="notif-filter" data-v="all" aria-pressed="${f === "all"}">All</button><button type="button" data-action="notif-filter" data-v="unread" aria-pressed="${f === "unread"}">Unread <span class="n num">${unreadCount()}</span></button></div></div>
      <div class="notif-list">${f === "unread" && !unreadCount() ? `<div style="padding:24px">${empty("check", "You're up to date", "New review activity on your papers appears here.")}</div>` : notifItems(0, f === "unread")}</div>`,
  };
}
function viewCalls() {
  return {
    title: "Calls & Conferences",
    html: `${head({ title: "Calls & Conferences", desc: "Calls for papers, grants and conferences that RDCO shares." })}
      <div class="row" style="margin-bottom:16px"><div class="seg" role="group" aria-label="Show"><button type="button" aria-pressed="true">Open</button><button type="button" aria-pressed="false" data-toast="Prototype: past calls would list here.">Past</button></div></div>
      ${empty("megaphone", "No calls are open right now", "When RDCO posts a call for papers or a conference, it appears here and you get a notification.", me().rdco ? `<button class="btn btn-primary" type="button" data-toast="Prototype: the post-a-call form would open here.">${ic("plus")}Post a call</button>` : "")}`,
  };
}
function viewProfile() { return profileView(me().name, me().label + " · " + me().unit, true); }
function viewPerson(m) {
  const all = new Set(RECORDS.flatMap((r) => [...r.authors, r.adviser]));
  const name = [...all].find((n) => slug(n) === m[1]) || "Unknown person";
  return profileView(name, name.includes("Adviser") || name.startsWith("Dr.") || name.startsWith("Engr.") ? "Adviser" : "Student", false);
}
function profileView(name, role, self) {
  const papers = PUBLISHED.filter((r) => r.authors.includes(name));
  const advised = PUBLISHED.filter((r) => r.adviser === name);
  return {
    title: self ? "Your profile" : name,
    html: `${self ? `<div class="profile-note">${ic("eye", "icon-16")}<span style="flex:1">This is how other IRIS accounts see your profile.</span><a class="btn btn-secondary btn-sm" href="#/profile/edit">${ic("pencil", "icon-16")}Edit profile</a></div>` : `<nav aria-label="Breadcrumb"><ol class="crumbs"><li><a href="#/discover">Discover</a></li><li><span aria-current="page">People</span></li></ol></nav>`}
      <div class="profile-head"><span class="avatar lg" aria-hidden="true">${name.replace(/^(Dr\.|Engr\.) /, "").split(" ").map((x) => x[0]).slice(0, 2).join("")}</span><div><h1>${name}</h1><p class="muted">${role}</p><p class="small muted" style="margin-top:6px">Cebu Institute of Technology – University</p></div></div>
      <hr class="hr">
      <h2 class="section-title" style="margin-bottom:12px">Papers <span class="muted num" style="font:500 15px var(--sans)">${papers.length}</span></h2>
      <div class="result-list">${papers.map((r) => recRow(r)).join("") || empty("file", self ? "You have no published papers yet" : `${name.split(" ")[0]} has no published papers yet`, self ? "Papers appear here once RDCO publishes them." : "Published papers they wrote appear here.")}</div>
      ${advised.length ? `<h2 class="section-title" style="margin:32px 0 12px">Advised <span class="muted num" style="font:500 15px var(--sans)">${advised.length}</span></h2><div class="result-list">${advised.map((r) => recRow(r)).join("")}</div>` : ""}`,
  };
}
function viewSettings(_, q) {
  const tab = q.get("tab") || "account";
  const r = me();
  const tabs = [["account", "Account & security", "user"], ["privacy", "Data privacy & consent", "shield"], ["role", "Role & access", "users"]];
  const panes = {
    account: `<section class="card stack" aria-labelledby="s1"><h2 id="s1" class="section-title">Account</h2>
        <div class="form-grid"><div class="field"><label for="st-name">Full name</label><input class="input" id="st-name" value="${r.name}" autocomplete="name"></div>
        <div class="field"><label for="st-email">Institutional email</label><input class="input" id="st-email" value="${r.email}" readonly aria-describedby="st-email-h"><span class="hint" id="st-email-h">Your sign-in address. RDCO can change it if it is wrong.</span></div>
        <div><button class="btn btn-primary" type="button" data-toast="Prototype: nothing was saved.">Save changes</button></div></div></section>
      <section class="card stack" aria-labelledby="s2" style="margin-top:16px"><h2 id="s2" class="section-title">Password</h2>
        <form class="form-grid" data-form="password" novalidate><div class="field"><label for="pw0">Current password</label><input class="input" id="pw0" type="password" autocomplete="current-password" required><span class="err" hidden></span></div>
        <div class="field"><label for="pw1">New password</label><input class="input" id="pw1" type="password" autocomplete="new-password" aria-describedby="pw1-h" required><span class="hint" id="pw1-h">At least 12 characters. A short sentence works well.</span><span class="err" hidden></span></div>
        <div><button class="btn btn-primary" type="submit">Change password</button></div></form></section>`,
    privacy: `<section class="card stack" aria-labelledby="s3"><h2 id="s3" class="section-title">How IRIS uses your data</h2>
        <label class="check"><input type="checkbox" checked disabled> <span><b class="strong">Required to use IRIS.</b> Your name, email and the papers you submit or review. <a href="#/help#privacy">Read the privacy notice</a></span></label>
        <label class="check"><input type="checkbox" checked> <span>Let Ask IRIS read papers I wrote once they are published, so others can ask about them.</span></label>
        <label class="check"><input type="checkbox"> <span>Email me a weekly summary of review activity.</span></label>
        <div><button class="btn btn-primary" type="button" data-toast="Prototype: preferences not saved.">Save preferences</button></div></section>
      <section class="card stack" aria-labelledby="s4" style="margin-top:16px"><h2 id="s4" class="section-title">Your data</h2>
        <p class="small">Download a copy of everything IRIS holds about you, including the papers you viewed.</p>
        <div><button class="btn btn-secondary" type="button" data-toast="Prototype: your data export would start here.">${ic("download")}Download my data</button></div>
        <hr class="hr" style="margin:8px 0">
        <p class="small"><b class="strong">Delete account.</b> A System Admin reviews each request. Published papers stay in the repository with your name.</p>
        <div><button class="btn btn-ghost" type="button" data-action="delete-account" style="color:var(--maroon)">${ic("trash")}Ask to delete my account…</button></div></section>`,
    role: `<section class="card stack" aria-labelledby="s5"><h2 id="s5" class="section-title">Your role</h2>
        <dl class="kv" style="max-width:420px"><dt>Role</dt><dd>${r.label}</dd><dt>Unit</dt><dd>${r.unit}</dd></dl>
        <p class="small muted">Need a different role, for example to review for an office? Ask RDCO. Your current access stays until they decide.</p>
        <div><button class="btn btn-secondary" type="button" data-action="role-request">${ic("user-plus")}Request a role change…</button></div></section>`,
  };
  return {
    title: `${tabs.find((t) => t[0] === tab)[1]} · Settings`,
    html: `${head({ title: "Settings" })}<div class="settings-layout"><nav class="vtabs" aria-label="Settings sections">${tabs.map(([k, l, i]) => `<a href="#/settings?tab=${k}" ${k === tab ? 'aria-current="page"' : ""}>${ic(i)}${l}</a>`).join("")}</nav><div>${panes[tab]}</div></div>`,
  };
}
function viewHelp() {
  const secs = [
    ["publish", "Publishing a paper", "<p>Choose <b>Publish a paper</b> in Discover or My Library. You upload the manuscript, check the details IRIS reads from it, and submit it to your adviser. Your draft saves as you go, and you can come back to it from My Library.</p>"],
    ["review", "How review works", "<p>Your adviser reviews first, then sends the paper to the offices it needs: ITSO, IERC and KTTO review at the same time. RDCO publishes it once every office has cleared.</p><p>If one office asks for a revision, only that office reviews your next version. The clearances you already have are kept, and the Review tab marks them <b>kept</b>.</p>"],
    ["ask", "Asking IRIS", "<p>Ask IRIS answers questions from the papers you are allowed to read and cites the page each claim comes from. Choose <b>Thorough research</b> when you want it to read more before answering. It can be wrong, so check the cited page.</p>"],
    ["privacy", "Your data and privacy", "<p>Settings › Data privacy &amp; consent lists what IRIS keeps and lets you download it or ask to delete your account.</p>"],
    ["contact", "Contact RDCO", "<p>For access, roles or a problem with a paper, email the Research, Development and Coordination Office.</p>"],
  ];
  return {
    title: "Help",
    html: `${head({ title: "Help", desc: "How publishing, review and Ask IRIS work." })}
      <div class="help-layout"><nav class="toc" aria-label="On this page">${secs.map(([id, t]) => `<a href="#/help" data-action="jump" data-v="${id}">${t}</a>`).join("")}</nav>
      <div>${secs.map(([id, t, b]) => `<section class="help-sec" id="${id}" aria-labelledby="h-${id}"><h2 id="h-${id}">${t}</h2><div class="prose">${b}</div></section>`).join("")}</div></div>`,
  };
}

/* --------------------------------------------------------------------- RDCO */
function viewImport() {
  return {
    title: "Import records",
    html: `${head({ title: "Import records", desc: "Add papers that were finished before IRIS, in one batch. They arrive embargoed until you release them." })}
      <div class="steps3">
        <div class="card"><h3><span class="num-badge">1</span>Get the template</h3><p class="small muted">One row per paper: title, authors, adviser, program, year and the PDF's file name.</p><button class="btn btn-secondary btn-sm" type="button" style="margin-top:12px" data-toast="Prototype: the CSV template would download.">${ic("download", "icon-16")}Download template (CSV)</button></div>
        <div class="card"><h3><span class="num-badge">2</span>Fill it in</h3><p class="small muted">Keep the column names. Authors are separated by semicolons. Leave the abstract empty if you don't have it; IRIS reads it from the PDF.</p></div>
        <div class="card"><h3><span class="num-badge">3</span>Upload</h3><p class="small muted">Upload the CSV and the PDFs together. IRIS checks every row before anything is added.</p></div>
      </div>
      <div class="drop" style="margin-top:24px" id="drop">${ic("upload")}<b class="strong">Drop the CSV and PDFs here</b><span class="small muted">or</span><button class="btn btn-secondary btn-sm" type="button" data-action="fake-import">Choose files</button></div>
      <div id="import-check"></div>
      <div class="row" style="justify-content:flex-end;margin-top:16px"><button class="btn btn-primary" type="button" id="import-go" disabled data-toast="Prototype: 12 records would be imported, embargoed.">Import records</button></div>`,
  };
}
function viewUsers() {
  return {
    title: "Users",
    html: `${head({ title: "Users", desc: "Everyone with an IRIS account." })}
      <div class="row" style="margin-bottom:16px"><div class="search-xl" style="min-height:44px;flex:1 1 280px">${ic("search", "b-search")}<label class="sr-only" for="u-q">Search users</label><input id="u-q" type="search" placeholder="Search by name or email" style="height:42px;font-size:15px"></div>
        <label class="sr-only" for="u-role">Role</label><select class="select" id="u-role" style="width:auto"><option>All roles</option><option>Students</option><option>Advisers</option><option>Office staff</option></select></div>
      <div class="table-wrap"><div class="table-scroll"><table class="stack-sm-table"><caption class="sr-only">Users</caption>
        <thead><tr><th scope="col">Name</th><th scope="col">Role</th><th scope="col">Unit</th><th scope="col">Status</th><th scope="col">Last active</th><th scope="col"><span class="sr-only">Actions</span></th></tr></thead>
        <tbody>${USERS.map((u) => `<tr><td><span class="strong">${u.name}</span>${u.email === me().email ? ' <span class="meta-chip">You</span>' : ""}<span class="cell-sub">${u.email}</span></td><td data-label="Role">${u.role}</td><td data-label="Unit">${u.unit}</td><td data-label="Status">${u.status === "Locked" ? status("attention", "Locked", "lock") : status("settled", "Active", "check")}</td><td data-label="Last active">${u.last}</td><td class="act" style="text-align:right">${u.email === me().email ? "" : `<button class="icon-btn" type="button" data-action="user-more" data-name="${u.name}" data-locked="${u.status === "Locked"}" aria-label="Actions for ${u.name}" aria-haspopup="menu">${ic("more")}</button>`}</td></tr>`).join("")}</tbody></table></div></div>`,
  };
}
function viewRoleRequests() {
  return { title: "Role requests", html: `${head({ title: "Role requests", desc: "People asking for a different role, such as office reviewer." })}${empty("user-plus", "No role requests", "When someone asks for a new role from their Settings, the request appears here for you to approve or decline.")}` };
}
function viewDownloadRequests() {
  const rows = [["Sam Student", "Forecasting Dengue Incidence in Cebu City…", "Comparing methods for my own thesis", "12 Nov 2026"], ["Kyle Dela Peña", "Perceived Usability of the CIT-U Learning Management System…", "Related literature", "11 Nov 2026"]];
  return {
    title: "Download requests",
    html: `${head({ title: "Download requests", desc: "Requests for a PDF copy of a paper. Reading in IRIS needs no approval." })}
      <div class="table-wrap"><div class="table-scroll"><table class="stack-sm-table"><caption class="sr-only">Pending download requests</caption>
      <thead><tr><th scope="col">Requested by</th><th scope="col">Paper</th><th scope="col">Reason</th><th scope="col">Date</th><th scope="col"><span class="sr-only">Actions</span></th></tr></thead>
      <tbody>${rows.map(([who, p, why, d]) => `<tr><td class="strong">${who}</td><td data-label="Paper">${p}</td><td data-label="Reason">${why}</td><td data-label="Date" class="num">${d}</td><td class="act" style="white-space:nowrap;text-align:right"><button class="btn btn-ghost btn-sm" type="button" data-action="decide" data-v="decline" data-who="${who}">Decline…</button><button class="btn btn-primary btn-sm" type="button" data-action="decide" data-v="approve" data-who="${who}">Approve</button></td></tr>`).join("")}</tbody></table></div></div>`,
  };
}
/* ----------------------------------------------------------- System Admin */
function viewAdminUsers() {
  const v = viewUsers();
  return { title: "Users", html: v.html.replace("Everyone with an IRIS account.", "Everyone with an IRIS account. You can change any role, including System Admin.") };
}
function viewAudit(_, q) {
  const kind = q.get("type") || "all";
  const rows = [
    ["13 Nov 2026, 09:42", "Irene Villanueva", "Review", "Cleared v1 of Design of a Solar-Powered Cold Storage Box… for ITSO", "review"],
    ["13 Nov 2026, 09:10", "Rita Cruz", "Access", "Approved Sam Student's PDF request for Forecasting Dengue Incidence…", "access"],
    ["12 Nov 2026, 16:05", "Kyle Dela Peña", "Record", "Asked to delete A Low-Cost IoT Monitor for Water Quality…", "record"],
    ["11 Nov 2026, 14:30", "Dr. Marco Lim", "Review", "Asked for a revision of v1 of Activity Preference and Level…; IERC clearance reset", "review"],
    ["10 Nov 2026, 08:15", "Paolo Ybañez", "Account", "Asked to delete their account", "account"],
    ["1 Nov 2026, 02:00", "IRIS", "Retention", "Removed 14 Ask IRIS conversations older than 180 days", "retention"],
  ];
  const list = kind === "all" ? rows : rows.filter((r) => r[4] === kind);
  return {
    title: "Audit log",
    html: `${head({ title: "Audit log", desc: "Every workflow act, access decision and account change, newest first. Entries can't be edited or deleted.", actions: `<button class="btn btn-secondary" type="button" data-toast="Prototype: the filtered log would download as CSV.">${ic("download")}Export CSV</button>` })}
      <div class="row" style="margin-bottom:16px"><div class="search-xl" style="min-height:44px;flex:1 1 260px">${ic("search", "b-search")}<label class="sr-only" for="au-q">Search the log</label><input id="au-q" type="search" placeholder="Search by person or paper" style="height:42px;font-size:15px"></div>
        <label class="sr-only" for="au-t">Event type</label><select class="select" id="au-t" style="width:auto" data-action-change="audit-type">${[["all", "All events"], ["review", "Review"], ["record", "Record"], ["access", "Access"], ["account", "Account"], ["retention", "Retention"]].map(([k, l]) => `<option value="${k}" ${k === kind ? "selected" : ""}>${l}</option>`).join("")}</select>
        <label class="sr-only" for="au-d">Period</label><select class="select" id="au-d" style="width:auto"><option>Last 30 days</option><option>This semester</option><option>All time</option></select></div>
      <div class="table-wrap"><div class="table-scroll"><table class="stack-sm-table"><caption class="sr-only">Audit events</caption>
        <thead><tr><th scope="col">When</th><th scope="col">Who</th><th scope="col">Type</th><th scope="col">What happened</th></tr></thead>
        <tbody>${list.map(([w, who, t, what]) => `<tr><td class="num" style="white-space:nowrap">${w}</td><td data-label="Who" class="strong">${who}</td><td data-label="Type"><span class="meta-chip">${t}</span></td><td data-label="What">${what}</td></tr>`).join("")}</tbody></table></div></div>
      <p class="small muted" style="margin-top:12px">Acts from before the audit log was switched on have no entries.</p>`,
  };
}
function viewAccountDeletions(_, q) {
  const v = q.get("view") || "pending";
  const all = [
    { n: "Paolo Ybañez", e: "paolo.ybanez@cit.edu", why: "Graduated; no longer needs an account", d: "10 Nov 2026", st: "pending" },
    { n: "Joanna Reyes", e: "ktto.coordinator@cit.edu", why: "Changed departments", d: "26 Oct 2026", st: "declined", note: "Still the KTTO coordinator. Reassign first." },
    { n: "Bea Gonzales", e: "bea.gonzales@cit.edu", why: "Transferred to another school", d: "2 Oct 2026", st: "approved", note: "Deleted 1 Nov 2026" },
  ];
  const rows = v === "all" ? all : all.filter((x) => x.st === v);
  const tabs = [["pending", "Pending"], ["approved", "Approved"], ["declined", "Declined"], ["all", "All"]];
  return {
    title: "Account deletions",
    html: `${head({ title: "Account deletion requests", desc: "People who asked to delete their account. Their published papers stay in the repository either way." })}
      <div class="row" style="margin-bottom:16px"><div class="seg" role="group" aria-label="Show">${tabs.map(([k, l]) => `<button type="button" data-action="go" data-v="#/admin/account-deletion-requests${k === "pending" ? "" : "?view=" + k}" aria-pressed="${v === k}">${l} <span class="n num">${k === "all" ? all.length : all.filter((x) => x.st === k).length}</span></button>`).join("")}</div></div>
      ${rows.length ? `<div class="table-wrap"><div class="table-scroll"><table class="stack-sm-table"><caption class="sr-only">${tabs.find((t) => t[0] === v)[1]} account deletion requests</caption>
      <thead><tr><th scope="col">Person</th><th scope="col">Reason given</th><th scope="col">Asked</th><th scope="col">Status</th><th scope="col"><span class="sr-only">Actions</span></th></tr></thead>
      <tbody>${rows.map((x) => `<tr><td><span class="strong">${x.n}</span><span class="cell-sub">${x.e}</span></td><td data-label="Reason">${x.why}</td><td data-label="Asked" class="num">${x.d}</td><td data-label="Status">${decidedStatus(x.st)}${x.note ? `<span class="cell-sub" style="margin-top:4px">${x.note}</span>` : ""}</td><td class="act" style="text-align:right">${x.st === "pending" ? `<button class="btn btn-secondary btn-sm" type="button" data-action="review-delete" data-who="${x.n}">Review…</button>` : ""}</td></tr>`).join("")}</tbody></table></div></div>` : empty("check", "Nothing here", "Requests move here once they're decided.")}`,
  };
}
const decidedStatus = (st) => (st === "approved" ? status("settled", "Approved", "check") : st === "declined" ? status("quiet", "Declined", "x") : status("active", "Pending", "clock"));
function viewRetention() {
  const rows = [["Ask IRIS conversations", "180 days after the last message", "1 Nov 2026 · 14 removed"], ["Deleted accounts", "30 days after a deletion is approved", "1 Nov 2026 · 1 removed"], ["Declined PDF requests", "1 year", "1 Oct 2026 · 0 removed"], ["Audit log", "5 years", "Never removed early"], ["Published papers", "Kept permanently", "Not part of the run"]];
  return {
    title: "Retention",
    html: `${head({ title: "Retention", desc: "How long IRIS keeps each kind of data. The run removes what is past its period on the 1st of each month." })}
      <div class="table-wrap"><div class="table-scroll"><table class="stack-sm-table"><caption class="sr-only">Retention periods</caption>
        <thead><tr><th scope="col">Data</th><th scope="col">Kept for</th><th scope="col">Last run</th><th scope="col"><span class="sr-only">Actions</span></th></tr></thead>
        <tbody>${rows.map(([d, k, l], i) => `<tr><td class="strong">${d}</td><td data-label="Kept for">${k}</td><td data-label="Last run">${l}</td><td class="act" style="text-align:right">${i < 3 ? `<button class="btn btn-ghost btn-sm" type="button" data-action="edit-retention" data-v="${d}">Change…</button>` : ""}</td></tr>`).join("")}</tbody></table></div></div>
      <div class="notice" style="margin-top:16px">${ic("calendar")}<div><b>Next run: 1 Dec 2026, 02:00.</b> It will remove an estimated 9 conversations. <a href="#/admin/audit?type=retention">See past runs in the audit log</a>.</div></div>`,
  };
}
/* Record deletion requests (RDCO). Shows the decided ones under their own filter (WF-02). */
function viewDeleteRequests(_, q) {
  const v = q.get("view") || "pending";
  const all = [
    { t: "A Low-Cost IoT Monitor for Water Quality in Mactan Fish Pens", id: 108, by: "Kyle Dela Peña", why: "Published by mistake before the patent filing", d: "12 Nov 2026", st: "pending" },
    { t: "Solar Dryer for Dried Fish", by: "Jonas Uy", why: "Duplicate of a record I submitted again", d: "26 Oct 2026", st: "declined", note: "Not a duplicate; the other record is a different study" },
    { t: "Survey of Jeepney Drivers' Income (draft import)", by: "Rita Cruz", why: "Imported twice", d: "4 Oct 2026", st: "approved", note: "Deleted 4 Oct 2026" },
  ];
  const rows = v === "all" ? all : all.filter((x) => x.st === v);
  const tabs = [["pending", "Pending"], ["approved", "Approved"], ["declined", "Declined"], ["all", "All"]];
  return {
    title: "Delete requests",
    html: `${head({ title: "Record deletion requests", desc: "Authors asking RDCO to remove a published record. Approving removes it from Discover and Ask IRIS; the audit log keeps the decision." })}
      <div class="row" style="margin-bottom:16px"><div class="seg" role="group" aria-label="Show">${tabs.map(([k, l]) => `<button type="button" data-action="go" data-v="#/rdco/delete-requests${k === "pending" ? "" : "?view=" + k}" aria-pressed="${v === k}">${l} <span class="n num">${k === "all" ? all.length : all.filter((x) => x.st === k).length}</span></button>`).join("")}</div></div>
      ${rows.length ? `<div class="table-wrap"><div class="table-scroll"><table class="stack-sm-table"><caption class="sr-only">${tabs.find((t) => t[0] === v)[1]} record deletion requests</caption>
      <thead><tr><th scope="col">Record</th><th scope="col">Reason given</th><th scope="col">Asked</th><th scope="col">Status</th><th scope="col"><span class="sr-only">Actions</span></th></tr></thead>
      <tbody>${rows.map((x) => `<tr><td>${x.id ? `<a class="strong" href="#/records/${x.id}" style="color:var(--ink)">${x.t}</a>` : `<span class="strong">${x.t}</span>`}<span class="cell-sub">Asked by ${x.by}</span></td><td data-label="Reason">${x.why}</td><td data-label="Asked" class="num">${x.d}</td><td data-label="Status">${decidedStatus(x.st)}${x.note ? `<span class="cell-sub" style="margin-top:4px">${x.note}</span>` : ""}</td><td class="act" style="text-align:right;white-space:nowrap">${x.st === "pending" ? `<button class="btn btn-ghost btn-sm" type="button" data-action="decide-record-delete" data-v="decline" data-t="${x.t}">Decline…</button><button class="btn btn-secondary btn-sm" type="button" data-action="decide-record-delete" data-v="approve" data-t="${x.t}">Approve…</button>` : ""}</td></tr>`).join("")}</tbody></table></div></div>` : empty("check", v === "pending" ? "No requests waiting" : "Nothing here", v === "pending" ? "When an author asks to remove a record, it appears here." : "Requests move here once they're decided.")}`,
  };
}
function viewProfileEdit() {
  const r = me();
  return {
    title: "Edit profile",
    html: `${head({ title: "Edit profile", crumbs: [["Your profile", "#/profile"], ["Edit"]], desc: "What other IRIS accounts see on your profile." })}
      <form class="card stack" data-form="profile" style="max-width:640px" novalidate>
        <div class="row" style="gap:16px"><span class="avatar lg" aria-hidden="true" style="width:72px;height:72px;font-size:26px">${r.initials}</span><div class="stack-sm"><button class="btn btn-secondary btn-sm" type="button" data-toast="Prototype: the photo picker would open.">${ic("upload", "icon-16")}Upload a photo</button><span class="hint">JPG or PNG, square, up to 2 MB.</span></div></div>
        <div class="field"><label for="pe-n">Display name</label><input class="input" id="pe-n" value="${r.name}" required><span class="err" hidden></span></div>
        <div class="field"><label for="pe-b">About you <span class="opt">(optional)</span></label><textarea class="textarea" id="pe-b" rows="4" placeholder="Your research interests, in a sentence or two"></textarea></div>
        <div class="field"><label for="pe-l">Links <span class="opt">(optional)</span></label><input class="input" id="pe-l" type="url" placeholder="https://orcid.org/…"><span class="hint">ORCID, Google Scholar or a personal page.</span></div>
        <label class="check"><input type="checkbox" checked> <span>Show my email on my profile</span></label>
        <div class="row" style="justify-content:flex-end"><a class="btn btn-ghost" href="#/profile">Cancel</a><button class="btn btn-primary" type="submit">Save profile</button></div>
      </form>`,
  };
}
function viewForgot() {
  return {
    title: "Reset your password", fab: false,
    html: entryFrame("Reset password", `
      <h2>Forgot your password?</h2>
      <p class="small">Enter your email address. If it has an IRIS account, we send a link to set a new password. The link works for one hour.</p>
      <form class="stack" data-form="forgot" novalidate>
        <div class="field"><label for="fp-email">Email address</label><input class="input" id="fp-email" type="email" autocomplete="username" required><span class="err" hidden></span></div>
        <button class="btn btn-primary" type="submit" style="width:100%;min-height:44px">Send reset link</button>
      </form>
      <p class="small muted" style="text-align:center"><a href="#/login">Back to sign in</a></p>`),
  };
}
function viewNotices() {
  return {
    title: "Notices",
    html: `${head({ title: "Data notice", desc: "The privacy notice every account accepts. Publishing a new version asks everyone to read it at their next sign-in." })}
      <div class="two-col">
        <form class="card stack" data-form="notice" novalidate>
          <div class="field"><label for="n-title">Title</label><input class="input" id="n-title" value="IRIS data privacy notice"></div>
          <div class="field"><label for="n-body">Notice text</label><textarea class="textarea" id="n-body" rows="10">IRIS keeps your name, institutional email and the papers you submit, review or read so that the review workflow and Ask IRIS can work. Published papers stay in the repository after you graduate.</textarea></div>
          <div class="field"><label for="n-ver">Version</label><input class="input" id="n-ver" value="Version 4" style="max-width:200px"></div>
          <div class="row"><button class="btn btn-secondary" type="button" data-toast="Prototype: draft saved locally only.">Save draft</button><button class="btn btn-primary" type="submit">Publish version 4…</button></div>
        </form>
        <aside class="card"><h2 class="card-title">Live now</h2><p class="small muted" style="margin:4px 0 12px">Version 3 · published 1 Aug 2026 · accepted by every active account</p><div class="prose small" style="font-size:14px"><p>IRIS keeps your name, institutional email and the papers you submit or review…</p></div></aside>
      </div>`,
  };
}
function viewNotFound() { return { title: "Page not found", html: `${head({ title: "We can't find that page" })}${empty("compass", "This page doesn't exist, or you don't have access to it", "Check the link, or go back to Discover.", `<a class="btn btn-primary" href="#/discover">Go to Discover</a>`)}` }; }
function viewNoAccess() {
  const need = { reviews: "an adviser or office reviewer", coordinator: "an office coordinator", rdco: "RDCO or System Admin", admin: "System Admin" }[viewNoAccess.need] || "a different role";
  return { title: "No access", html: `${head({ title: "You can't open this page" })}${empty("lock", `It's for ${need}. You're signed in as ${me().label}.`, "If you need it for your work, ask RDCO for a role change in Settings › Role & access. In this prototype, switch roles in the bar above.", `<a class="btn btn-secondary" href="#/discover">Go to Discover</a>`)}` };
}

/* ------------------------------------------------------- dialogs and menus */
function dialog({ title, body, foot = "", size = "" }) {
  const prev = document.activeElement;
  const scrim = document.createElement("div");
  scrim.className = "scrim";
  scrim.innerHTML = `<div class="dialog ${size}" role="dialog" aria-modal="true" aria-labelledby="dlg-t"><div class="dialog-head"><h2 id="dlg-t">${title}</h2><button class="icon-btn" type="button" data-x aria-label="Close">${ic("x")}</button></div><div class="dialog-body">${body}</div>${foot ? `<div class="dialog-foot">${foot}</div>` : ""}</div>`;
  $("#layer").append(scrim);
  const el = scrim.firstElementChild;
  const onKey = (e) => {
    if (e.key === "Escape") { e.stopPropagation(); close(); }
    if (e.key === "Tab") {
      const f = $$("a[href],button:not([disabled]),input:not([disabled]),select,textarea", el).filter((x) => x.offsetParent !== null);
      if (!f.length) return;
      if (e.shiftKey && document.activeElement === f[0]) { e.preventDefault(); f[f.length - 1].focus(); }
      else if (!e.shiftKey && document.activeElement === f[f.length - 1]) { e.preventDefault(); f[0].focus(); }
    }
  };
  function close() { scrim.remove(); document.removeEventListener("keydown", onKey, true); if (prev && prev.isConnected) prev.focus(); }
  scrim.addEventListener("mousedown", (e) => { if (e.target === scrim) close(); });
  el.addEventListener("click", (e) => { if (e.target.closest("[data-x]")) close(); });
  document.addEventListener("keydown", onKey, true);
  const focusFirst = () => (el.querySelector("[autofocus]") || el.querySelector(".dialog-body input, .dialog-body select, .dialog-body textarea") || el.querySelector(".dialog-foot .btn-primary") || el).focus();
  setTimeout(focusFirst, 30);
  return {
    el, close,
    update(t, b, f) { $("#dlg-t", el).innerHTML = t; $(".dialog-body", el).innerHTML = b; let ft = $(".dialog-foot", el); if (!ft) { ft = document.createElement("div"); ft.className = "dialog-foot"; el.append(ft); } ft.innerHTML = f; ft.hidden = !f; setTimeout(focusFirst, 30); },
  };
}
function confirmDialog({ title, body, label, danger = false, done }) {
  const d = dialog({ title, body: `<div class="prose" style="font-size:15px">${body}</div>`, foot: `<button class="btn btn-ghost" type="button" data-x>Cancel</button><button class="btn ${danger ? "btn-danger" : "btn-primary"}" type="button" data-ok>${label}</button>` });
  $("[data-ok]", d.el).addEventListener("click", () => { d.close(); toast(done); });
  return d;
}
function toast(msg) {
  const t = document.createElement("div");
  t.className = "toast";
  t.innerHTML = `${ic("check")}<span>${msg}</span>`;
  $("#toasts").append(t);
  setTimeout(() => t.remove(), 3600);
}
let pop = null;
function closePopover() { if (pop) { const { el, trigger } = pop; el.remove(); trigger && trigger.setAttribute("aria-expanded", "false"); pop = null; } }
function popover(trigger, html, { align = "start", width = 260, role = "menu", label = "" } = {}) {
  if (pop && pop.trigger === trigger) { closePopover(); return; }
  closePopover();
  const el = document.createElement("div");
  el.className = "menu";
  el.setAttribute("role", role);
  if (label) el.setAttribute("aria-label", label);
  el.style.position = "fixed";
  el.style.width = `min(${width}px, calc(100vw - 24px))`;
  el.innerHTML = html;
  $("#layer").append(el);
  const r = trigger.getBoundingClientRect();
  const w = el.offsetWidth, h = el.offsetHeight;
  let left = align === "end" ? r.right - w : r.left;
  left = Math.max(12, Math.min(left, innerWidth - w - 12));
  let top = r.bottom + 6;
  if (top + h > innerHeight - 12) top = Math.max(12, r.top - h - 6);
  el.style.left = left + "px"; el.style.top = top + "px";
  trigger.setAttribute("aria-expanded", "true");
  pop = { el, trigger };
  const first = el.querySelector("[role=menuitem],[role=menuitemradio],a,button");
  if (first) first.focus();
}
document.addEventListener("mousedown", (e) => { if (pop && !pop.el.contains(e.target) && !pop.trigger.contains(e.target)) closePopover(); });
document.addEventListener("keydown", (e) => {
  if (!pop) return;
  if (e.key === "Escape") { const t = pop.trigger; closePopover(); t.focus(); }
  if (e.key === "ArrowDown" || e.key === "ArrowUp") {
    const items = $$("[role^=menuitem]", pop.el); if (!items.length) return;
    e.preventDefault();
    const i = items.indexOf(document.activeElement);
    items[(i + (e.key === "ArrowDown" ? 1 : -1) + items.length) % items.length].focus();
  }
});
const mi = (label, attrs = "", icon = "", extra = "") => `<button class="menu-item ${extra}" type="button" role="menuitem" ${attrs}>${icon ? ic(icon) : ""}${label}</button>`;

/* ----------------------------------------------------------------- Publish */
function openPublish(resume) {
  const st = { step: resume ? 2 : 1, file: !!resume, title: resume ? "Quantitative Forecasting of Land Suitability in Metro Cebu" : "", abstract: "", adviser: resume ? "Ana Adviser" : "", year: "2026", type: "Thesis / Research", coauthors: "" };
  const steps = ["Your manuscript", "Details", "Review & submit"];
  const stepper = () => `<ol class="stepper" aria-label="Step ${st.step} of 3: ${steps[st.step - 1]}">${steps.map((s, i) => `<li ${i + 1 === st.step ? 'aria-current="step"' : ""} class="${i + 1 < st.step ? "done" : ""}">${s}</li>`).join("")}</ol>`;
  const d = dialog({ title: "Publish a paper", body: "", size: "lg" });
  const draw = () => {
    let b = "", f = "";
    if (st.step === 1) {
      b = `${stepper()}
        <div class="field"><label for="p-type">Record type</label><select class="select" id="p-type"><option>Thesis / Research</option></select><span class="hint">Decides who reviews it. A thesis goes to your adviser first, then ITSO, IERC and KTTO.</span></div>
        <div class="field"><span class="label" id="p-file-l">Manuscript</span>${st.file ? `<div class="file-chip">${ic("file", "icon-20")}<div style="flex:1;min-width:0"><b class="strong">Mobile_Learning_Readiness_Final.pdf</b><div class="small muted">2.4 MB · 64 pages · uploaded</div></div><button class="btn btn-ghost btn-sm" type="button" data-p="remove">Replace</button></div>`
          : `<div class="drop" aria-labelledby="p-file-l">${ic("upload")}<b class="strong">Drop your PDF here</b><span class="small muted">PDF up to 50 MB. IRIS reads the title, authors and abstract from it.</span><button class="btn btn-secondary btn-sm" type="button" data-p="file" style="margin-top:6px">Choose PDF</button></div>`}<span class="err" id="p-file-err" hidden>${ic("alert")}Add your manuscript to continue.</span></div>`;
      f = `<span class="note">Your draft saves as you go.</span><button class="btn btn-ghost" type="button" data-x>Cancel</button><button class="btn btn-primary" type="button" data-p="next">Continue</button>`;
    } else if (st.step === 2) {
      b = `${stepper()}
        ${st.title && !resume ? `<div class="notice">${ic("info")}<div>IRIS filled the title and abstract from your PDF. Check them before you continue. <button class="linkish" type="button" data-p="undo">Undo</button></div></div>` : ""}
        <div class="field"><label for="p-title">Title</label><input class="input" id="p-title" value="${esc(st.title)}" required><span class="err" hidden>${ic("alert")}Add a title.</span></div>
        <div class="field"><label for="p-abs">Abstract</label><textarea class="textarea" id="p-abs" rows="5">${esc(st.abstract)}</textarea></div>
        <div class="row" style="gap:16px;align-items:start">
          <div class="field" style="flex:1 1 220px"><label for="p-adv">Adviser</label><select class="select" id="p-adv" required><option value="">Choose your adviser</option>${["Ana Adviser", "Engr. Marco Lim", "Dr. Liza Fernandez"].map((a) => `<option ${a === st.adviser ? "selected" : ""}>${a}</option>`).join("")}</select><span class="err" hidden>${ic("alert")}Choose the adviser who reviews it first.</span></div>
          <div class="field" style="flex:0 1 160px"><label for="p-year">Year completed</label><input class="input num" id="p-year" inputmode="numeric" value="${st.year}"></div>
        </div>
        <div class="field"><label for="p-co">Co-authors <span class="opt">(optional)</span></label><input class="input" id="p-co" value="${esc(st.coauthors)}" placeholder="Search IRIS accounts by name"><span class="hint">You are listed as the first author.</span></div>`;
      f = `<span class="note">Saved just now</span><button class="btn btn-ghost" type="button" data-p="back">Back</button><button class="btn btn-primary" type="button" data-p="next">Continue</button>`;
    } else if (st.step === 3) {
      b = `${stepper()}
        <dl class="review-list"><dt>Type</dt><dd>${st.type}</dd><dt>Title</dt><dd>${esc(st.title)}</dd><dt>Authors</dt><dd>${me().name}${st.coauthors ? ", " + esc(st.coauthors) : ""}</dd><dt>Adviser</dt><dd>${esc(st.adviser)}</dd><dt>Year completed</dt><dd class="num">${esc(st.year)}</dd><dt>Manuscript</dt><dd>Mobile_Learning_Readiness_Final.pdf</dd></dl>
        <div class="notice">${ic("route")}<div><b>What happens next.</b> ${esc(st.adviser)} reviews it first and sends it to ITSO, IERC and KTTO. You can follow each clearance in My Library. Nobody outside review sees it until RDCO publishes it.</div></div>`;
      f = `<button class="btn btn-ghost" type="button" data-p="back">Back</button><button class="btn btn-primary" type="button" data-p="submit">Submit to ${esc(st.adviser.split(" ")[0] === "Engr." || st.adviser.startsWith("Dr.") ? st.adviser : st.adviser.split(" ")[0])}</button>`;
    } else {
      b = `<div class="empty" style="border-style:solid"><span class="ico" style="background:var(--maroon);color:#fff">${ic("check", "icon-20")}</span><h3>Submitted to ${esc(st.adviser)}</h3><p>You'll get a notification when they clear it or ask for changes. In this prototype nothing was sent.</p></div>`;
      f = `<button class="btn btn-secondary" type="button" data-x>Close</button><a class="btn btn-primary" href="#/library" data-x>Go to My Library</a>`;
    }
    d.update(st.step === 4 ? "Paper submitted" : "Publish a paper", b, f);
  };
  d.el.addEventListener("click", (e) => {
    const t = e.target.closest("[data-p]"); if (!t) return;
    const a = t.dataset.p;
    const val = (id) => { const x = $("#" + id, d.el); return x ? x.value.trim() : ""; };
    if (a === "file") { st.file = true; st.title = "Mobile Learning Readiness of Senior High School Teachers in Cebu City"; st.abstract = "This study measured the readiness of 118 senior high school teachers in Cebu City to teach with mobile devices, across access, skills and attitudes."; draw(); }
    if (a === "remove") { st.file = false; st.title = ""; st.abstract = ""; draw(); }
    if (a === "undo") { st.title = ""; st.abstract = ""; draw(); }
    if (a === "back") { if (st.step === 2) { st.title = val("p-title"); st.abstract = val("p-abs"); st.adviser = val("p-adv"); st.year = val("p-year"); st.coauthors = val("p-co"); } st.step--; draw(); }
    if (a === "next") {
      if (st.step === 1) { if (!st.file) { const er = $("#p-file-err", d.el); er.hidden = false; return; } st.step = 2; draw(); return; }
      st.title = val("p-title"); st.abstract = val("p-abs"); st.adviser = val("p-adv"); st.year = val("p-year"); st.coauthors = val("p-co");
      let ok = true;
      [["p-title", st.title], ["p-adv", st.adviser]].forEach(([id, v]) => { const inp = $("#" + id, d.el); const er = inp.parentElement.querySelector(".err"); inp.setAttribute("aria-invalid", String(!v)); er.hidden = !!v; if (!v && ok) { inp.focus(); ok = false; } });
      if (ok) { st.step = 3; draw(); }
    }
    if (a === "submit") { st.step = 4; draw(); }
  });
  draw();
}

/* ------------------------------------------------------------ interactions */
const ACTIONS = {
  save(el) { const id = Number(el.dataset.id); if (S.saved.has(id)) { S.saved.delete(id); toast("Removed from Saved papers"); } else { S.saved.add(id); toast("Saved to My Library"); } rerender(); },
  "disc-view"(el) { S.disc.view = el.dataset.v; rerender(); },
  "disc-feed"(el) { S.disc.feed = el.dataset.v; rerender(); },
  "toggle-filters"() { S.disc.filters = !S.disc.filters; rerender(); if (S.disc.filters) setTimeout(() => $("#f-area") && $("#f-area").focus(), 0); },
  "clear-filters"() { Object.assign(S.disc, { area: "", unit: "", year: "" }); rerender(); },
  "clear-search"() { S.disc.q = ""; location.hash = "#/discover"; },
  "feeds-menu"(el) { popover(el, `<p class="menu-head">My feeds</p>${mi("Computer Science", "", "bookmark")}${mi("Papers advised by Ana Adviser", "", "bookmark")}<div class="menu-sep"></div>${mi("Save current filters as a feed…", 'data-toast="Prototype: the feed would be saved."', "plus")}<p class="menu-note">A feed is a saved set of filters. New papers that match appear under For you.</p>`, { width: 300, label: "My feeds" }); },
  "rec-tab"(el) { location.hash = `#/records/${el.dataset.id}${el.dataset.v === "overview" ? "" : "?tab=" + el.dataset.v}`; },
  back() { if (history.length > 1) history.back(); else location.hash = "#/discover"; },
  "toggle-ask"() { S.notesOpen = false; S.ask.open = !S.ask.open; rerender(); if (S.ask.open) setTimeout(() => $("#ask-in") && $("#ask-in").focus(), 0); else ($(".ask-fab") || $(".ask-toggle")) && ($(".ask-fab") || $(".ask-toggle")).focus(); },
  "close-notes"() { S.notesOpen = false; rerender(); $(".notes-fab") && $(".notes-fab").focus(); },
  "cmt-reply"(el) { S.cmt.replyTo = Number(el.dataset.id); S.cmt.editing = null; rerender(); $("#cr-in") && $("#cr-in").focus(); },
  "cmt-cancel"() { const id = S.cmt.replyTo; S.cmt.replyTo = null; rerender(); $(`#reply-btn-${id}`) && $(`#reply-btn-${id}`).focus(); },
  "cmt-toggle"(el) { const id = el.dataset.id; const opening = el.getAttribute("aria-expanded") === "false"; S.cmt.open[id] = opening; rerender(); $(`[data-action="cmt-toggle"][data-id="${id}"]`) ? $(`[data-action="cmt-toggle"][data-id="${id}"]`).focus() : $(`#cmt-${id} [data-action="cmt-reply"]`).focus(); },
  "cmt-jump"(el, e) { e && e.preventDefault(); const id = Number(el.dataset.id); S.cmt.hl = id; rerender(); const t = $(`#cmt-${id}`); if (t) { t.scrollIntoView({ block: "center", behavior: "smooth" }); ($("[data-action=cmt-reply]", t) || t).focus({ preventScroll: true }); } setTimeout(() => { S.cmt.hl = null; const b = $(`#cmt-${id} .cmt-bub`); if (b) b.classList.remove("hl"); }, 1600); },
  "cmt-edit-cancel"() { const id = S.cmt.editing; S.cmt.editing = null; rerender(); $(`#cmt-${id} .cmt-more`) && $(`#cmt-${id} .cmt-more`).focus(); },
  "cmt-more"(el) {
    const id = Number(el.dataset.id), rid = Number(parse().path.split("/")[2]);
    if (el.dataset.who !== me().name) { ACTIONS["comment-more"](el); return; }
    popover(el, mi("Edit", 'data-cm="edit"', "pencil") + mi("Delete", 'data-cm="delete"', "trash", "danger"), { align: "start", width: 180, label: "Comment actions" });
    pop?.el.addEventListener("click", (e) => {
      const b = e.target.closest("[data-cm]"); if (!b) return; closePopover();
      if (b.dataset.cm === "edit") { S.cmt.editing = id; S.cmt.replyTo = null; rerender(); const t = $(`#ce-${id}`); if (t) { t.focus(); t.setSelectionRange(t.value.length, t.value.length); } return; }
      const d = dialog({ title: "Delete your comment?", body: "<p class=\"small\">It is removed for everyone. Replies to it stay, under \u201c[deleted]\u201d.</p>", foot: `<button class="btn btn-ghost" type="button" data-x>Cancel</button><button class="btn btn-danger" type="button" data-ok>Delete comment</button>` });
      $("[data-ok]", d.el).addEventListener("click", () => { const list = COMMENTS[rid]; const c = list.find((x) => x.id === id); if (list.some((x) => x.to === id)) c.deleted = true; else list.splice(list.indexOf(c), 1); d.close(); toast("Comment deleted"); rerender(); });
    });
  },
  "ask-scope"(el) { S.ask.scope = el.dataset.v; rerender(); },
  "ask-new"(el) { S.ask.msgs = []; S.ask.startedAll = false; if (el.dataset.v) S.ask.scope = el.dataset.v; rerender(); $("#ask-in") && $("#ask-in").focus(); },
  "ask-scope-menu"(el) {
    const opt = (v, icon, label, note) => `<button class="menu-item scope-opt" type="button" role="menuitemradio" aria-checked="${S.ask.scope === v}" data-sv="${v}">${ic(icon)}<span><b>${label}</b><span class="small muted">${note}</span></span>${S.ask.scope === v ? ic("check", "icon-16") : ""}</button>`;
    popover(el, opt("paper", "file", "This paper", "Only this paper, with pages") + opt("all", "layers", "All papers", "Can cite other papers in IRIS"), { align: "start", width: 270, label: "Answers from" });
    pop?.el.addEventListener("click", (e) => { const b = e.target.closest("[data-sv]"); if (!b) return; closePopover(); S.ask.scope = b.dataset.sv; rerender(); $(".scope-btn") && $(".scope-btn").focus(); });
  },
  "ask-starter"(el) { askSend(el.dataset.v); },
  "chat-starter"(el) { chatSend(el.dataset.v); },
  "toggle-sources"(el) { const s = el.nextElementSibling; s.hidden = !s.hidden; el.setAttribute("aria-expanded", String(!s.hidden)); },
  cite(el) {
    const r = REC[el.dataset.id];
    const fmt = {
      APA: `${r.authors.map((a) => { const p = a.split(" "); return `${p[p.length - 1]}, ${p.slice(0, -1).map((x) => x[0] + ".").join(" ")}`; }).join(", & ")} (${r.year}). <i>${esc(r.title)}</i> [${r.type}]. Cebu Institute of Technology – University.`,
      MLA: `${r.authors[0].split(" ").slice(-1)}, ${r.authors[0].split(" ").slice(0, -1).join(" ")}${r.authors.length > 1 ? ", et al" : ""}. <i>${esc(r.title)}</i>. Cebu Institute of Technology – University, ${r.year}.`,
      BibTeX: `@thesis{${slug(r.authors[0]).split("-").pop()}${r.year},<br>&nbsp;&nbsp;title = {${esc(r.title)}},<br>&nbsp;&nbsp;author = {${r.authors.join(" and ")}},<br>&nbsp;&nbsp;school = {Cebu Institute of Technology – University},<br>&nbsp;&nbsp;year = {${r.year}}<br>}`,
    };
    let cur = "APA";
    const body = () => `<div class="seg" role="group" aria-label="Citation style">${Object.keys(fmt).map((k) => `<button type="button" data-style="${k}" aria-pressed="${k === cur}">${k}</button>`).join("")}</div><div class="card" style="background:var(--endpaper);font-size:15px;line-height:1.7;${cur === "BibTeX" ? "font-family:ui-monospace,monospace;font-size:13px" : ""}" id="cite-text">${fmt[cur]}</div>`;
    const d = dialog({ title: "Cite this paper", body: body(), foot: `<button class="btn btn-ghost" type="button" data-x>Close</button><button class="btn btn-primary" type="button" data-copy>${ic("copy")}Copy ${cur}</button>` });
    d.el.addEventListener("click", (e) => {
      const s = e.target.closest("[data-style]"); if (s) { cur = s.dataset.style; $(".dialog-body", d.el).innerHTML = body(); $("[data-copy]", d.el).innerHTML = `${ic("copy")}Copy ${cur}`; $(`[data-style="${cur}"]`, d.el).focus(); }
      if (e.target.closest("[data-copy]")) { try { navigator.clipboard.writeText($("#cite-text", d.el).innerText); } catch { /* not allowed */ } d.close(); toast(`${cur} citation copied`); }
    });
  },
  share() { try { navigator.clipboard.writeText(location.href); } catch { /* not allowed */ } toast("Link copied"); },
  notes() { S.ask.open = false; S.notesOpen = true; rerender(); setTimeout(() => $("#notes-t") && $("#notes-t").focus(), 0); },
  "notes-dialog"() {
    const d = dialog({ title: "Your notes", body: `<div class="field"><label for="note-t">Notes on this paper</label><textarea class="textarea" id="note-t" rows="7" placeholder="What you want to remember, quotes with page numbers…"></textarea><span class="hint">Only you can see your notes.</span></div>`, foot: `<button class="btn btn-ghost" type="button" data-x>Cancel</button><button class="btn btn-primary" type="button" data-ok>Save notes</button>` });
    $("[data-ok]", d.el).addEventListener("click", () => { d.close(); toast("Notes saved"); });
  },
  "request-download"(el) {
    const r = REC[el.dataset.id];
    const d = dialog({ title: "Request a PDF copy", body: `<p class="small">RDCO approves PDF copies of <b class="strong">${esc(r.title)}</b>. You can keep reading it here meanwhile.</p><div class="field"><label for="dl-why">Why do you need a copy?</label><textarea class="textarea" id="dl-why" rows="3" placeholder="For example: related literature for my thesis"></textarea><span class="err" hidden>${ic("alert")}Tell RDCO why you need it.</span></div>`, foot: `<button class="btn btn-ghost" type="button" data-x>Cancel</button><button class="btn btn-primary" type="button" data-ok>Send request</button>` });
    $("[data-ok]", d.el).addEventListener("click", () => { const t = $("#dl-why", d.el); if (!t.value.trim()) { t.setAttribute("aria-invalid", "true"); t.nextElementSibling.hidden = false; t.focus(); return; } d.close(); toast("Request sent to RDCO. Track it in My Library."); });
  },
  zoom(el) { const p = $("#pages"); const z = Math.max(60, Math.min(160, (Number(p.dataset.z) || 100) + Number(el.dataset.v) * 20)); p.dataset.z = z; $$(".pdf-page", p).forEach((x) => (x.style.width = `min(${6.8 * z}px, 100%)`)); $("#zoom-l").textContent = z + "%"; },
  route(el) {
    const d = dialog({ title: "Clear and route", body: `<p class="small">You clear it as adviser. Choose the offices that review it next. They review at the same time.</p>${[["ITSO", "Intellectual property and technology"], ["IERC", "Research ethics"], ["KTTO", "Knowledge and technology transfer"]].map(([o, t]) => `<label class="check"><input type="checkbox" checked> <span><b class="strong">${o}</b> · ${t}</span></label>`).join("")}<p class="small muted">RDCO publishes it after every office you choose has cleared.</p>`, foot: `<button class="btn btn-ghost" type="button" data-x>Cancel</button><button class="btn btn-primary" type="button" data-ok>Clear and send to 3 offices</button>` });
    $("[data-ok]", d.el).addEventListener("click", () => { d.close(); toast("Cleared and sent to ITSO, IERC and KTTO"); });
    d.el.addEventListener("change", () => { const n = $$("input:checked", d.el).length; const b = $("[data-ok]", d.el); b.disabled = !n; b.textContent = n ? `Clear and send to ${n} office${n > 1 ? "s" : ""}` : "Choose at least one office"; });
  },
  claim(el) { S.claimed.add(Number(el.dataset.id)); toast("You claimed this review"); rerender(); },
  clear(el) {
    const d = dialog({ title: `Clear for ${me().office}`, body: `<p class="small">Clearing says ${me().office} has no objection to publishing version ${REC[el.dataset.id].version}. If the authors revise for another office later, your clearance is kept.</p><div class="field"><label for="cl-n">Note to the authors <span class="opt">(optional)</span></label><textarea class="textarea" id="cl-n" rows="3"></textarea></div>`, foot: `<button class="btn btn-ghost" type="button" data-x>Cancel</button><button class="btn btn-primary" type="button" data-ok>${ic("check")}Clear</button>` });
    $("[data-ok]", d.el).addEventListener("click", () => { d.close(); toast(`Cleared for ${me().office}`); });
  },
  finding(el) {
    const kind = el.dataset.kind;
    const d = dialog({ title: kind === "office" ? "Record a finding" : "Request a revision", body: `${kind === "office" ? `<fieldset class="stack-sm" style="border:0;padding:0;margin:0"><legend class="strong" style="font-size:13px;margin-bottom:6px">What did you find?</legend><label class="check"><input type="radio" name="fk" checked> <span><b class="strong">Changes requested</b> · the authors revise and send a new version. Only ${me().office} reviews it again.</span></label><label class="check"><input type="radio" name="fk"> <span><b class="strong">Negative finding</b> · ${me().office} cannot clear this paper.</span></label></fieldset>` : `<p class="small">The authors revise and send a new version. Clearances already given are kept.</p>`}<div class="field"><label for="fd-n">What should the authors change?</label><textarea class="textarea" id="fd-n" rows="4" required></textarea><span class="err" hidden>${ic("alert")}Say what needs to change, so the authors can act on it.</span></div>`, foot: `<button class="btn btn-ghost" type="button" data-x>Cancel</button><button class="btn btn-primary" type="button" data-ok>Send to the authors</button>` });
    $("[data-ok]", d.el).addEventListener("click", () => { const t = $("#fd-n", d.el); if (!t.value.trim()) { t.setAttribute("aria-invalid", "true"); t.nextElementSibling.hidden = false; t.focus(); return; } d.close(); toast("Sent. The authors were notified."); });
  },
  "publish-rec"(el) { confirmDialog({ title: "Publish this paper?", body: `<p><b>${esc(REC[el.dataset.id].title)}</b> becomes visible in Discover to every IRIS account, and Ask IRIS can cite it.</p>`, label: "Accept & publish", done: "Published. The authors were notified." }); },
  assign() {
    const d = dialog({ title: "Assign a reviewer", body: `<div class="field"><label for="as-who">Reviewer</label><select class="select" id="as-who"><option>Irene Villanueva (you)</option><option>Carlo Mendoza · 2 open reviews</option><option>Mark Abellana · locked account</option></select></div><div class="field"><label for="as-due">Due date</label><input class="input" id="as-due" type="date" value="2026-11-22" style="max-width:220px"></div>`, foot: `<button class="btn btn-ghost" type="button" data-x>Cancel</button><button class="btn btn-primary" type="button" data-ok>Assign</button>` });
    $("[data-ok]", d.el).addEventListener("click", () => { d.close(); toast("Assigned. The reviewer was notified."); });
  },
  "row-more"(el) {
    popover(el, `${mi("Reassign…", 'data-sub="reassign"', "users")}${mi("Extend due date…", 'data-sub="extend"', "calendar")}`, { align: "end", width: 220 });
    pop?.el.addEventListener("click", (e) => {
      const s = e.target.closest("[data-sub]"); if (!s) return; closePopover();
      if (s.dataset.sub === "extend") { const d = dialog({ title: "Extend due date", body: `<p class="small">Currently assigned to ${el.dataset.who}.</p><div class="field"><label for="ex-d">New due date</label><input class="input" id="ex-d" type="date" value="2026-11-20" style="max-width:220px"></div><div class="field"><label for="ex-r">Reason <span class="opt">(shared with the reviewer)</span></label><input class="input" id="ex-r"></div>`, foot: `<button class="btn btn-ghost" type="button" data-x>Cancel</button><button class="btn btn-primary" type="button" data-ok>Extend</button>` }); $("[data-ok]", d.el).addEventListener("click", () => { d.close(); toast("Due date moved to 20 Nov"); }); }
      else ACTIONS.assign();
    });
  },
  "user-more"(el) {
    const locked = el.dataset.locked === "true";
    popover(el, `${mi("View profile", `data-go="#/people/${slug(el.dataset.name)}"`, "user")}${mi("Change role…", 'data-toast="Prototype: the change-role dialog would open."', "users")}<div class="menu-sep"></div>${mi(locked ? "Unlock account…" : "Lock account…", 'data-lock="1"', "lock", "danger")}`, { align: "end", width: 220 });
    pop?.el.addEventListener("click", (e) => {
      if (e.target.closest("[data-lock]")) { closePopover(); confirmDialog({ title: `${locked ? "Unlock" : "Lock"} ${el.dataset.name}'s account?`, body: locked ? "<p>They can sign in again straight away.</p>" : "<p>They are signed out everywhere and can't sign in until someone unlocks the account. Their papers and reviews stay as they are.</p>", label: locked ? "Unlock account" : "Lock account", danger: !locked, done: `${el.dataset.name}'s account was ${locked ? "unlocked" : "locked"}` }); }
      const g = e.target.closest("[data-go]"); if (g) { closePopover(); location.hash = g.dataset.go; }
    });
  },
  decide(el) {
    if (el.dataset.v === "approve") { toast(`Approved. ${el.dataset.who} can download the PDF for 14 days.`); return; }
    const d = dialog({ title: `Decline ${el.dataset.who}'s request`, body: `<div class="field"><label for="dc-r">Reason, shown to ${el.dataset.who.split(" ")[0]}</label><textarea class="textarea" id="dc-r" rows="3"></textarea></div>`, foot: `<button class="btn btn-ghost" type="button" data-x>Cancel</button><button class="btn btn-danger" type="button" data-ok>Decline request</button>` });
    $("[data-ok]", d.el).addEventListener("click", () => { d.close(); toast("Declined. They were notified."); });
  },
  "review-delete"(el) {
    const d = dialog({ title: `Delete ${el.dataset.who}'s account?`, body: `<div class="prose" style="font-size:15px"><p>Their sign-in, notes, saved papers and Ask IRIS conversations are deleted after 30 days. Papers they published stay in the repository with their name.</p></div><div class="field"><label for="rd-r">Note for the record <span class="opt">(optional)</span></label><input class="input" id="rd-r"></div>`, foot: `<button class="btn btn-ghost" type="button" data-x>Cancel</button><button class="btn btn-secondary" type="button" data-no>Decline</button><button class="btn btn-danger" type="button" data-ok>Approve deletion</button>` });
    d.el.addEventListener("click", (e) => { if (e.target.closest("[data-ok]")) { d.close(); toast("Approved. The account is deleted in 30 days."); } if (e.target.closest("[data-no]")) { d.close(); toast("Declined. They were notified."); } });
  },
  "delete-draft"() { confirmDialog({ title: "Delete this draft?", body: "<p>The draft and its uploaded manuscript are removed. This can't be undone.</p>", label: "Delete draft", danger: true, done: "Draft deleted" }); },
  "delete-account"() { confirmDialog({ title: "Ask to delete your account?", body: "<p>A System Admin reviews the request, usually within a week. You can keep using IRIS until they decide. Your published papers stay in the repository.</p>", label: "Send request", danger: true, done: "Request sent to the System Admin" }); },
  "role-request"() { const d = dialog({ title: "Request a role change", body: `<div class="field"><label for="rr-role">Role you need</label><select class="select" id="rr-role"><option>Office reviewer · ITSO</option><option>Office reviewer · IERC</option><option>Office reviewer · KTTO</option><option>Adviser</option></select></div><div class="field"><label for="rr-why">Why</label><textarea class="textarea" id="rr-why" rows="3"></textarea></div>`, foot: `<button class="btn btn-ghost" type="button" data-x>Cancel</button><button class="btn btn-primary" type="button" data-ok>Send to RDCO</button>` }); $("[data-ok]", d.el).addEventListener("click", () => { d.close(); toast("Request sent to RDCO"); }); },
  /* ----- review workspace ----- */
  "split-menu"(el) { splitMenu(el); },
  "split-close"() { const was = S.ws.side; S.ws.side = null; store.set("ws-side", ""); rerender(); const b = $(".tabs-split"); if (b) b.focus(); toast(`Closed ${TAB_NAMES[was] || "the right column"} on the right`); },
  "nav-rail"() {
    if (S.readingRail !== null) S.readingRail = !S.readingRail;
    else { S.navRail = !S.navRail; store.set("nav-rail", S.navRail ? "1" : "0"); }
    rerender(); const b = $(".rail-toggle"); if (b) b.focus();
  },
  anno(el, e) {
    if (e) e.preventDefault();
    const id = Number(el.dataset.t); S.ws.anno = id; S.ws.filter = "all";
    if (S.ws.side !== "threads") S.ws.tab = "threads";
    const ws = $("#ws"); if (ws && ws.dataset.mode === "drawer") S.ws.paneOpen = true;
    rerender();
    const c = $("#th-" + id); if (c) { c.scrollIntoView({ block: "nearest", behavior: "smooth" }); c.setAttribute("tabindex", "-1"); c.focus({ preventScroll: true }); }
  },
  "ws-tab"(el) { S.ws.tab = el.dataset.v; const ws = $("#ws"); if (ws && ws.dataset.mode === "drawer") S.ws.paneOpen = true; rerender(); const t = $(`#wst-${S.ws.tab}`); if (t) t.focus(); },
  "pane-open"() { setPane(true); },
  "pane-close"() { setPane(false); },
  "tour-start"() { S.ws.tourOffer = false; store.set("tour-offer", "0"); const o = $(".tour-offer"); if (o) o.remove(); tourStep(0); },
  "tour-dismiss"() { S.ws.tourOffer = false; store.set("tour-offer", "0"); rerender(); $("#wst-" + S.ws.tab) && $("#wst-" + S.ws.tab).focus(); },
  "th-filter"(el) { S.ws.filter = el.dataset.v; rerender(); $(`[data-action="th-filter"][data-v="${el.dataset.v}"]`).focus(); },
  "new-comment"(el) { newComment(Number(el.dataset.id)); },
  "draft-remove"(el) { const id = Number(el.dataset.id); S.ws.drafts[id] = (S.ws.drafts[id] || []).filter((d) => String(d.id) !== el.dataset.t); toast("Draft removed"); rerender(); },
  "th-address"(el) { threadAnswer(el, "addressed"); },
  "th-decline"(el) { threadAnswer(el, "declined"); },
  "th-resolve"(el) { const t = findThread(el); t.state = "resolved"; toast("Thread resolved"); rerender(); },
  "th-reopen"(el) { const t = findThread(el); t.state = "open"; toast("Thread reopened. The authors were notified."); rerender(); },
  reply(el) {
    const d = dialog({ title: `Reply to ${el.dataset.who}`, body: `<div class="field"><label for="rp-t">Your reply</label><textarea class="textarea" id="rp-t" rows="4"></textarea><span class="err" hidden>${ic("alert")}Write a reply first.</span></div>`, foot: `<button class="btn btn-ghost" type="button" data-x>Cancel</button><button class="btn btn-primary" type="button" data-ok>Post reply</button>` });
    $("[data-ok]", d.el).addEventListener("click", () => { const t = $("#rp-t", d.el); if (!t.value.trim()) { t.setAttribute("aria-invalid", "true"); t.nextElementSibling.hidden = false; t.focus(); return; } d.close(); toast("Reply posted. Everyone on this review can read it."); });
  },
  "saved-replies"(el) {
    const R = ["Thank you. This is cleared on our side.", "Please attach the signed consent form, then send a new version.", "Could you point to the page where this is answered?"];
    popover(el, `<p class="menu-head">Saved replies</p>${R.map((t, i) => `<button class="menu-item" type="button" role="menuitem" data-sr="${i}" style="min-height:44px;line-height:18px">${t}</button>`).join("")}<div class="menu-sep"></div>${mi("Manage saved replies…", 'data-toast="Prototype: saved replies would be edited in Settings."', "settings")}`, { width: 320, label: "Saved replies" });
    pop?.el.addEventListener("click", (e) => { const b = e.target.closest("[data-sr]"); if (!b) return; closePopover(); const ta = $("#ws-c"); ta.value = R[b.dataset.sr]; ta.focus(); });
  },
  mention(el) {
    const r = REC[el.dataset.id];
    const ppl = [...new Set([...r.authors, r.adviser, ...(CLEARANCE[r.id] || []).map((c) => c.who).filter(Boolean)])].filter((p) => p !== me().name);
    popover(el, `<p class="menu-head">Mention someone on this review</p>${ppl.map((p) => `<button class="menu-item" type="button" role="menuitem" data-mn="${p}"><span class="avatar sm" aria-hidden="true">${initials(p)}</span>${p}</button>`).join("")}<p class="menu-note">They get a notification with your comment.</p>`, { width: 280, label: "Mention" });
    pop?.el.addEventListener("click", (e) => { const b = e.target.closest("[data-mn]"); if (!b) return; closePopover(); const ta = $("#ws-c"); ta.value = `${ta.value ? ta.value.trimEnd() + " " : ""}@${b.dataset.mn} `; ta.focus(); });
  },
  diff(el) { S.ws.diff = el.dataset.v; rerender(); },
  "chg-viewed"(el) { const k = el.dataset.k; if (S.ws.viewed.has(k)) S.ws.viewed.delete(k); else S.ws.viewed.add(k); rerender(); const n = $(`[data-k="${k}"]`); if (n) n.focus(); },
  "show-unchanged"() { S.ws.showUnchanged = !S.ws.showUnchanged; rerender(); },
  "goto-page"(el) {
    closePopover();
    if (el.dataset.t) { S.ws.anno = Number(el.dataset.t); rerender(); }
    const ws = $("#ws"); if (ws && ws.dataset.mode === "drawer") setPane(false);
    const p = $("#pg-" + el.dataset.p) || $("#pg-" + (Number(el.dataset.p) > 1 ? 2 : 1)); const box = $("#ws-paper");
    if (p && box) box.scrollTo({ top: p.offsetTop - 64, behavior: "smooth" }); else if (p) p.scrollIntoView({ behavior: "smooth", block: "start" });
    const l = $(".pg-l"); if (l) l.textContent = l.textContent.replace(/Page \d+/, `Page ${el.dataset.p}`);
  },
  docs(el) { docsDialog(REC[el.dataset.id]); },
  "request-review"(el) {
    const r = REC[el.dataset.id];
    const d = dialog({ title: "Request a review", body: `<p class="small">Ask another office to review <b class="strong">${esc(r.title)}</b>. The offices already reviewing keep going.</p><div class="field"><label for="rq-o">Office</label><select class="select" id="rq-o"><option>ITSO · Intellectual property and technology</option><option>IERC · Research ethics</option><option>KTTO · Knowledge and technology transfer</option></select></div><div class="field"><label for="rq-n">Why <span class="opt">(shown to the office)</span></label><textarea class="textarea" id="rq-n" rows="3"></textarea></div>`, foot: `<button class="btn btn-ghost" type="button" data-x>Cancel</button><button class="btn btn-primary" type="button" data-ok>Send request</button>` });
    $("[data-ok]", d.el).addEventListener("click", () => { d.close(); toast("Review requested. The office was notified."); });
  },
  "add-colleague"() {
    const d = dialog({ title: "Add a colleague", body: `<p class="small">They review with you and can comment. The clearance is still one decision for ITSO.</p><div class="field"><label for="ac-w">Colleague</label><select class="select" id="ac-w"><option>Carlo Mendoza · ITSO reviewer</option><option>Ivan Santos · ITSO reviewer</option></select></div>`, foot: `<button class="btn btn-ghost" type="button" data-x>Cancel</button><button class="btn btn-primary" type="button" data-ok>Add</button>` });
    $("[data-ok]", d.el).addEventListener("click", () => { d.close(); toast("Colleague added to this review"); });
  },
  "foot-more"(el) {
    const id = el.dataset.id; const items = el.dataset.items.split(",");
    const M = {
      docs: mi("Request documents…", 'data-fm="docs"', "file-up"),
      colleague: mi("Add a colleague…", 'data-fm="colleague"', "user-plus"),
      revise: mi("Request revision…", 'data-fm="revise"', "rotate"),
      reject: mi("Reject…", 'data-fm="reject"', "x", "danger"),
      withdraw: mi("Withdraw paper…", 'data-fm="withdraw"', "file-x", "danger"),
    };
    popover(el, items.map((k) => (k === "reject" || k === "withdraw" ? '<div class="menu-sep"></div>' : "") + M[k]).join("").replace(/^<div class="menu-sep"><\/div>/, ""), { align: "end", width: 230 });
    pop?.el.addEventListener("click", (e) => {
      const b = e.target.closest("[data-fm]"); if (!b) return; closePopover();
      const r = REC[id];
      if (b.dataset.fm === "docs") { const d = dialog({ title: "Request documents", body: `<p class="small">The authors see this in the review and in their notifications. The paper stays with you meanwhile.</p><div class="field"><label for="rd-w">What do you need?</label><textarea class="textarea" id="rd-w" rows="3" placeholder="For example: the signed consent forms"></textarea></div>`, foot: `<button class="btn btn-ghost" type="button" data-x>Cancel</button><button class="btn btn-primary" type="button" data-ok>Send request</button>` }); $("[data-ok]", d.el).addEventListener("click", () => { d.close(); toast("Request sent to the authors"); }); }
      if (b.dataset.fm === "colleague") ACTIONS["add-colleague"]();
      if (b.dataset.fm === "revise") ACTIONS.finding({ dataset: { kind: "rdco", id } });
      if (b.dataset.fm === "reject") confirmDialog({ title: "Reject this paper?", body: `<p><b>${esc(r.title)}</b> is closed and not published. The authors are told why, and the clearances stay in the record.</p>`, label: "Reject paper", danger: true, done: "Rejected. The authors were notified." });
      if (b.dataset.fm === "withdraw") confirmDialog({ title: "Withdraw this paper?", body: `<p>Review of <b>${esc(r.title)}</b> stops and every office is told. You can submit it again later as a new version.</p>`, label: "Withdraw paper", danger: true, done: "Withdrawn. Your adviser and the offices were notified." });
    });
  },
  finish(el) { finishReview(REC[el.dataset.id]); },
  "withdraw-paper"(el) { const r = REC[el.dataset.id]; confirmDialog({ title: "Withdraw this paper?", body: `<p>Review of <b>${esc(r.title)}</b> stops and every office is told. You can submit it again later as a new version.</p>`, label: "Withdraw paper", danger: true, done: "Withdrawn. Your adviser and the offices were notified." }); },
  "send-version"(el) { sendVersion(REC[el.dataset.id]); },
  "keep-unlisted"(el) { confirmDialog({ title: "Keep this paper unlisted?", body: `<p><b>${esc(REC[el.dataset.id].title)}</b> is accepted but stays out of Discover and Ask IRIS. You can publish it later from the record.</p>`, label: "Keep unlisted", done: "Accepted and kept unlisted" }); },
  find(el) {
    const bar = $("#find-bar"); const open = bar.hidden;
    bar.hidden = !open; el.setAttribute("aria-expanded", String(open));
    if (open) {
      bar.innerHTML = `<label class="sr-only" for="find-q">Find in this paper</label><input class="input" id="find-q" type="search" placeholder="Find in this paper" autocomplete="off"><span class="small muted num" id="find-n" aria-live="polite"></span><button class="icon-btn" type="button" aria-label="Previous match">${ic("chev-left")}</button><button class="icon-btn" type="button" aria-label="Next match">${ic("chev-right")}</button><button class="icon-btn" type="button" data-action="find" aria-label="Close find">${ic("x")}</button>`;
      const q = $("#find-q"); q.focus();
      q.addEventListener("input", () => {
        const v = q.value.trim(); let n = 0;
        $$(".anno", $("#pages") || document).forEach((a) => {
          const pin = $(".anno-pin", a).outerHTML; const txt = a.textContent.replace(/^\d+/, "");
          const lo = txt.toLowerCase(), k = v.toLowerCase(); let out = "", i = 0, j;
          while (v && (j = lo.indexOf(k, i)) > -1) { out += esc(txt.slice(i, j)) + `<mark class="${n === 0 ? "now" : ""}">${esc(txt.slice(j, j + v.length))}</mark>`; i = j + v.length; n++; }
          a.innerHTML = pin + out + esc(txt.slice(i));
        });
        $("#find-n").textContent = v ? (n ? `1 of ${n}` : "No matches") : "";
        const first = $("#pages mark.now"); if (first) first.scrollIntoView({ block: "center", behavior: "smooth" });
      });
      q.addEventListener("keydown", (e) => { if (e.key === "Escape") { e.stopPropagation(); ACTIONS.find(el); } });
    } else { el.focus(); }
  },
  outline(el) {
    const S2 = [["Title page", 1], ["Abstract", 2], ["1. Introduction", 3], ["2. Review of related literature", 6], ["3. Methodology", 14], ["4. Results", 24], ["5. Discussion", 33], ["References", 40]];
    popover(el, `<p class="menu-head">Contents</p>${S2.map(([t, p]) => `<button class="menu-item" type="button" role="menuitem" data-action="goto-page" data-p="${p}"><span style="flex:1">${t}</span><span class="small muted num">p. ${p}</span></button>`).join("")}`, { align: "end", width: 280, label: "Contents" });
  },
  "decide-record-delete"(el) {
    const ok = el.dataset.v === "approve";
    const d = dialog({ title: ok ? "Delete this record?" : "Decline this request?", body: `<p class="small"><b class="strong">${esc(el.dataset.t)}</b></p>${ok ? `<div class="prose" style="font-size:15px"><p>It disappears from Discover, My Library and Ask IRIS straight away. The audit log keeps the decision and who made it.</p></div>` : ""}<div class="field"><label for="dr-r">${ok ? "Note for the record" : "Reason, shown to the author"} ${ok ? '<span class="opt">(optional)</span>' : ""}</label><textarea class="textarea" id="dr-r" rows="3"></textarea><span class="err" hidden>${ic("alert")}Tell the author why.</span></div>`, foot: `<button class="btn btn-ghost" type="button" data-x>Cancel</button><button class="btn ${ok ? "btn-danger" : "btn-primary"}" type="button" data-ok>${ok ? "Delete record" : "Decline request"}</button>` });
    $("[data-ok]", d.el).addEventListener("click", () => { const t = $("#dr-r", d.el); if (!ok && !t.value.trim()) { t.setAttribute("aria-invalid", "true"); t.nextElementSibling.hidden = false; t.focus(); return; } d.close(); toast(ok ? "Record deleted. The author was notified." : "Declined. The author was notified."); });
  },
  "edit-retention"(el) {
    const d = dialog({ title: `Change retention: ${el.dataset.v}`, body: `<div class="field"><label for="rt-d">Keep for</label><select class="select" id="rt-d"><option>90 days</option><option selected>180 days</option><option>1 year</option><option>2 years</option></select></div><p class="small muted">The new period applies from the next run. Nothing is removed straight away.</p>`, foot: `<button class="btn btn-ghost" type="button" data-x>Cancel</button><button class="btn btn-primary" type="button" data-ok>Save</button>` });
    $("[data-ok]", d.el).addEventListener("click", () => { d.close(); toast("Saved. It applies from the next run."); });
  },
  "edit-details"(el) {
    const r = REC[el.dataset.id];
    const d = dialog({ title: "Edit details", size: "lg", body: `${r.status === "review" ? `<div class="notice">${ic("info")}<div>Reviewers see the new details straight away. Editing them doesn't send a new version; use <b>Send version 2</b> in Review for that.</div></div>` : ""}<div class="field"><label for="ed-t">Title</label><input class="input" id="ed-t" value="${esc(r.title)}"></div><div class="field"><label for="ed-a">Abstract</label><textarea class="textarea" id="ed-a" rows="6">${esc(r.abstract)}</textarea></div><div class="field"><label for="ed-k">Keywords <span class="opt">(comma-separated)</span></label><input class="input" id="ed-k" value="${r.keywords.join(", ")}"></div>`, foot: `<button class="btn btn-ghost" type="button" data-x>Cancel</button><button class="btn btn-primary" type="button" data-ok>Save details</button>` });
    $("[data-ok]", d.el).addEventListener("click", () => { d.close(); toast("Details saved"); });
  },
  "manage-record"(el) {
    const r = REC[el.dataset.id];
    popover(el, `${mi("Add an owner…", 'data-mr="owner"', "user-plus")}${mi("Replace the adviser…", 'data-mr="adviser"', "users")}${r.status === "review" ? mi("Withdraw paper…", 'data-mr="withdraw"', "file-x") : ""}<div class="menu-sep"></div>${mi("Delete record…", 'data-mr="delete"', "trash", "danger")}`, { align: "end", width: 240, label: "Manage this record" });
    pop?.el.addEventListener("click", (e) => {
      const b = e.target.closest("[data-mr]"); if (!b) return; closePopover(); const k = b.dataset.mr;
      if (k === "owner" || k === "adviser") { const d = dialog({ title: k === "owner" ? "Add an owner" : "Replace the adviser", body: `<div class="field"><label for="mr-w">${k === "owner" ? "Person to add" : "New adviser"}</label><input class="input" id="mr-w" type="search" placeholder="Search by name or email"><span class="hint">${k === "owner" ? "Owners can edit the record and send new versions." : "The new adviser takes over any review still waiting on the adviser. Their clearance, if given, is kept."}</span></div>`, foot: `<button class="btn btn-ghost" type="button" data-x>Cancel</button><button class="btn btn-primary" type="button" data-ok>${k === "owner" ? "Add owner" : "Replace adviser"}</button>` }); $("[data-ok]", d.el).addEventListener("click", () => { d.close(); toast(k === "owner" ? "Owner added" : "Adviser replaced. Both were notified."); }); }
      if (k === "withdraw") confirmDialog({ title: "Withdraw this paper?", body: `<p>Review of <b>${esc(r.title)}</b> stops and every office is told. The authors can submit it again later.</p>`, label: "Withdraw paper", danger: true, done: "Withdrawn. The authors and offices were notified." });
      if (k === "delete") confirmDialog({ title: "Delete this record?", body: `<p><b>${esc(r.title)}</b> is removed from Discover, My Library and Ask IRIS. The audit log keeps the decision. This can't be undone.</p>`, label: "Delete record", danger: true, done: "Record deleted" });
    });
  },
  release(el) { confirmDialog({ title: "Release this paper?", body: `<p><b>${esc(REC[el.dataset.id].title)}</b> leaves embargo. Ask IRIS can read and cite it once it's published, and it can appear in Discover.</p>`, label: "Release", done: "Released from embargo" }); },
  "embargo-date"(el) {
    const d = dialog({ title: "Embargo review date", body: `<div class="field"><label for="em-d">Review the embargo on</label><input class="input" id="em-d" type="date" value="2026-12-02" style="max-width:220px"><span class="hint">Nothing is released automatically. You get a reminder on this date.</span></div>`, foot: `<button class="btn btn-ghost" type="button" data-x>Cancel</button><button class="btn btn-primary" type="button" data-ok>Save date</button>` });
    $("[data-ok]", d.el).addEventListener("click", () => { d.close(); toast("Review date saved"); });
  },
  "comment-more"(el) {
    popover(el, mi("Report comment…", 'data-rc="1"', "flag"), { align: "end", width: 200 });
    pop?.el.addEventListener("click", (e) => { if (!e.target.closest("[data-rc]")) return; closePopover(); const d = dialog({ title: `Report ${el.dataset.who}'s comment`, body: `<fieldset class="stack-sm" style="border:0;padding:0;margin:0"><legend class="strong" style="font-size:13px;margin-bottom:6px">What's wrong with it?</legend>${["Rude or harassing", "Shares someone's personal information", "Spam or off-topic"].map((t, i) => `<label class="check"><input type="radio" name="rc" ${i ? "" : "checked"}> <span>${t}</span></label>`).join("")}</fieldset><p class="small muted">RDCO reads every report. The person isn't told who reported it.</p>`, foot: `<button class="btn btn-ghost" type="button" data-x>Cancel</button><button class="btn btn-primary" type="button" data-ok>Send report</button>` }); $("[data-ok]", d.el).addEventListener("click", () => { d.close(); toast("Reported to RDCO"); }); });
  },
  "rev-sort"(el) { S.revSort = el.dataset.v; rerender(); $(`[data-action="rev-sort"][data-v="${el.dataset.v}"]`).focus(); },
  "done-filter"(el) { S.doneFilter = el.dataset.v; rerender(); $(`[data-action="done-filter"][data-v="${el.dataset.v}"]`).focus(); },
  "rev-scope"(el) { S.revScope = el.dataset.v; rerender(); },
  "mark-all"() { (NOTIFS[S.role] || []).forEach((_, i) => S.read.add(S.role + i)); toast("All notifications marked as read"); rerender(); },
  "notif-filter"(el) { location.hash = el.dataset.v === "all" ? "#/notifications" : "#/notifications?show=unread"; },
  go(el) { location.hash = el.dataset.v; },
  jump(el) { const t = document.getElementById(el.dataset.v); if (t) { t.scrollIntoView({ behavior: "smooth" }); t.querySelector("h2").setAttribute("tabindex", "-1"); t.querySelector("h2").focus({ preventScroll: true }); } },
  "fake-import"() {
    $("#import-check").innerHTML = `<div class="table-wrap" style="margin-top:16px"><table class="stack-sm-table"><caption>Checked 13 rows</caption><thead><tr><th scope="col">Row</th><th scope="col">Title</th><th scope="col">Result</th></tr></thead><tbody>
      <tr><td class="num">2–12</td><td data-label="Title">11 papers, 2019–2023</td><td data-label="Result">${status("settled", "Ready", "check")}</td></tr>
      <tr><td class="num">13</td><td data-label="Title">Rainwater Harvesting Potential of CIT-U Buildings</td><td data-label="Result">${status("settled", "Ready", "check")}</td></tr>
      <tr><td class="num">14</td><td data-label="Title">Traffic Signal Timing at Natalio Bacalso Avenue</td><td data-label="Result">${status("attention", "PDF missing", "alert")}<span class="cell-sub" style="margin-top:4px">Add traffic_signal_bacalso.pdf, or remove the row. Other rows can still be imported.</span></td></tr></tbody></table></div>`;
    const b = $("#import-go"); b.disabled = false; b.textContent = "Import 12 records";
  },
  reveal(el) { const i = document.getElementById(el.getAttribute("aria-controls")); const show = i.type === "password"; i.type = show ? "text" : "password"; el.textContent = show ? "Hide" : "Show"; el.setAttribute("aria-pressed", String(show)); },
  depth(el) { popover(el, `${[["Standard", "A shorter search for a quicker answer", "search"], ["Thorough research", "Searches and reads more before answering", "book"]].map(([l, t, i]) => `<button class="menu-item" type="button" role="menuitemradio" aria-checked="${S.chat.depth === l.split(" ")[0] || S.chat.depth === l}" data-depth="${l}" style="align-items:flex-start;padding:8px 10px;min-height:52px">${ic(i)}<span><b style="display:block;color:var(--ink)">${l}</b><span class="small muted">${t}</span></span></button>`).join("")}`, { width: 300, label: "Research depth" }); pop?.el.addEventListener("click", (e) => { const b = e.target.closest("[data-depth]"); if (b) { S.chat.depth = b.dataset.depth === "Standard" ? "Standard" : "Thorough"; closePopover(); rerender(); } }); },
  "new-chat"() { S.chat.msgs = []; S.chat.seeded = null; },
  "convo-del"(el) {
    const id = Number(el.dataset.id), c = CONVOS.find((x) => x.id === id); if (!c) return;
    const d = dialog({ title: "Delete conversation?", body: `<p>Delete “${esc(c.title)}” and its messages? This cannot be undone.</p>`, foot: `<button class="btn btn-ghost" type="button" data-x>Cancel</button><button class="btn btn-danger" type="button" data-ok>Delete conversation</button>` });
    const cancel = $(".dialog-foot [data-x]", d.el); if (cancel) cancel.focus();
    $("[data-ok]", d.el).addEventListener("click", () => {
      d.close(); CONVO_GONE.add(id);
      const open = parse().path === `/ai/c/${id}`;
      if (open) location.hash = "#/ai"; else rerender();
      setTimeout(() => { const next = $(".convos-list .convo") || $(".convos-head .btn"); if (next) next.focus(); }, 0);
      toast("Conversation deleted");
    });
  },
  "show-convos"() { $("#chat-layout").classList.toggle("show-list"); },
};
/* ------------------------------------------------- review workspace dialogs */
function setPane(open) {
  S.ws.paneOpen = open;
  const ws = $("#ws"); if (!ws) return;
  ws.dataset.pane = String(open);
  const drawer = ws.dataset.mode === "drawer";
  $(".ws-scrim", ws).hidden = !(drawer && open);
  $("#ws-pane").inert = drawer && !open;
  $$('[data-action="pane-open"]').forEach((b) => b.setAttribute("aria-expanded", String(open)));
  if (open) setTimeout(() => $("#pane-h") && ($("#pane-h").setAttribute("tabindex", "-1"), $("#pane-h").focus()), 30);
  else if (drawer) $('[data-action="pane-open"]') && $('[data-action="pane-open"]').focus();
}
const findThread = (el) => (THREADS[el.dataset.id] || []).find((t) => String(t.id) === el.dataset.t);
function threadAnswer(el, state) {
  const t = findThread(el);
  const addr = state === "addressed";
  const d = dialog({ title: addr ? "Mark this thread addressed" : "Decline this request", body: `<blockquote class="cmt-quote">${esc(t.text)}</blockquote><div class="field"><label for="ta-t">${addr ? "What you changed, and where" : "Why you're not changing it"}</label><textarea class="textarea" id="ta-t" rows="4" placeholder="${addr ? "For example: added the consent form as Appendix C, p. 47" : "Reviewers read this before they decide"}"></textarea><span class="hint">${t.party} reads this with your next version, under Response to reviewers.</span><span class="err" hidden>${ic("alert")}${addr ? "Say what you changed, so the reviewer can check it." : "Give a reason, so the reviewer can decide."}</span></div>`, foot: `<button class="btn btn-ghost" type="button" data-x>Cancel</button><button class="btn btn-primary" type="button" data-ok>${addr ? "Mark addressed" : "Decline request"}</button>` });
  $("[data-ok]", d.el).addEventListener("click", () => { const a = $("#ta-t", d.el); if (!a.value.trim()) { a.setAttribute("aria-invalid", "true"); a.parentElement.querySelector(".err").hidden = false; a.focus(); return; } t.state = state; t.answer = a.value.trim(); d.close(); toast(addr ? "Marked addressed. It goes out with version 2." : "Declined. It goes out with version 2."); rerender(); });
}
function newComment(id) {
  const r = REC[id];
  const d = dialog({ title: "Comment on a passage", body: `<div class="field"><span class="label">Passage · p. 4</span><blockquote class="cmt-quote" style="margin:0">Respondents completed the questionnaire during office hours over two weeks.</blockquote><span class="hint">In IRIS, the passage you select in the paper fills this in.</span></div>
      <fieldset class="stack-sm" style="border:0;padding:0;margin:0"><legend class="strong" style="font-size:13px;margin-bottom:6px">How important is it?</legend>
        <label class="check"><input type="radio" name="sev" value="must" checked> <span><b class="strong">Must fix</b> · the authors have to answer it before you can clear the paper</span></label>
        <label class="check"><input type="radio" name="sev" value="suggest"> <span><b class="strong">Suggestion</b> · they can take it or leave it</span></label></fieldset>
      <div class="field"><label for="nc-t">Comment</label><textarea class="textarea" id="nc-t" rows="4"></textarea><span class="err" hidden>${ic("alert")}Write the comment first.</span></div>`,
    foot: `<p class="note">Held as a draft until you finish your review.</p><button class="btn btn-ghost" type="button" data-x>Cancel</button><button class="btn btn-primary" type="button" data-ok>Save draft</button>` });
  $("[data-ok]", d.el).addEventListener("click", () => {
    const t = $("#nc-t", d.el); if (!t.value.trim()) { t.setAttribute("aria-invalid", "true"); t.nextElementSibling.hidden = false; t.focus(); return; }
    const list = (S.ws.drafts[id] = S.ws.drafts[id] || []);
    list.push({ id: "d" + Date.now(), sev: $("input[name=sev]:checked", d.el).value, party: myParty(r), who: me().name, v: r.version, page: 4, quote: "Respondents completed the questionnaire during office hours over two weeks.", text: t.value.trim(), state: "open" });
    d.close(); S.ws.tab = "threads"; toast("Draft saved. It's sent when you finish your review."); rerender();
  });
}
function finishReview(r) {
  const id = r.id, adv = S.role === "adviser";
  const drafts = (S.ws.drafts[id] || []).length;
  const verdicts = adv
    ? [["clear", "Clear and route", "You clear it and choose the offices that review it next."], ["revise", "Request a revision", `${r.authors[0].split(" ")[0]} revises and sends it back to you.`], ["reject", "Reject", "The paper is closed. The authors are told why."]]
    : [["clear", `Clear for ${me().office}`, `${me().office} has no objection to publishing v${r.version}. If the authors revise for another office, this is kept.`], ["finding", "Record a finding", `The authors revise. Only ${me().office} reviews the next version again.`]];
  const offices = `<div class="route-box" id="route-box"><p class="small strong">Offices that review it next</p>${[["ITSO", "Intellectual property and technology"], ["IERC", "Research ethics"], ["KTTO", "Knowledge and technology transfer"]].map(([o, t]) => `<label class="check"><input type="checkbox" checked> <span><b class="strong">${o}</b> · ${t}</span></label>`).join("")}<p class="small muted">They review at the same time. RDCO publishes once every office has cleared.</p></div>`;
  const d = dialog({ title: "Finish your review", body: `<fieldset class="stack-sm" style="border:0;padding:0;margin:0"><legend class="strong" style="font-size:13px;margin-bottom:6px">Your decision</legend>${verdicts.map(([k, l, t], i) => `<label class="check"><input type="radio" name="vd" value="${k}" ${i ? "" : "checked"}> <span><b class="strong">${l}</b> · ${t}</span></label>`).join("")}</fieldset>
      ${adv ? offices : ""}
      <div class="field"><label for="fr-s">Summary <span class="opt">(what the authors and other reviewers read first)</span></label><textarea class="textarea" id="fr-s" rows="4"></textarea><span class="err" hidden>${ic("alert")}Say what the authors must change, so they can act on it.</span></div>
      ${drafts ? `<p class="small">${ic("msg", "icon-16")} Your ${drafts} draft comment${drafts > 1 ? "s are" : " is"} sent with this decision.</p>` : ""}`,
    foot: `<button class="btn btn-ghost" type="button" data-x>Keep reviewing</button><button class="btn btn-primary" type="button" data-ok>Send review</button>` });
  const sync = () => { const v = $("input[name=vd]:checked", d.el).value; const rb = $("#route-box", d.el); if (rb) rb.hidden = v !== "clear"; };
  d.el.addEventListener("change", sync);
  $("[data-ok]", d.el).addEventListener("click", () => {
    const v = $("input[name=vd]:checked", d.el).value; const s = $("#fr-s", d.el);
    if (v !== "clear" && !s.value.trim()) { s.setAttribute("aria-invalid", "true"); s.parentElement.querySelector(".err").hidden = false; s.focus(); return; }
    const word = { clear: adv ? "Cleared and routed" : "Cleared", revise: "Revision requested", reject: "Rejected", finding: "Finding recorded" }[v];
    S.finished[id] = word; delete S.ws.drafts[id]; d.close(); toast(`${word}. The authors${adv && v === "clear" ? " and the offices" : ""} were notified.`); rerender();
  });
}
function sendVersion(r) {
  const open = (THREADS[r.id] || []).filter((t) => t.state === "open");
  const rows = CLEARANCE[r.id] || [];
  const kept = rows.filter((c) => c.state === "cleared").map((c) => c.party);
  const d = dialog({ title: "Send version 2", size: "lg", body: `<div class="notice">${ic("shield")}<div><b>${kept.join(", ")} ${kept.length > 1 ? "keep their clearances" : "keeps its clearance"}.</b> Only IERC reviews version 2. ITSO and KTTO carry on with their reviews.</div></div>
      <div class="field"><span class="label">Revised manuscript</span><div class="file-chip" id="sv-file">${ic("upload")}<span class="small" style="flex:1">No file chosen yet</span><button class="btn btn-secondary btn-sm" type="button" id="sv-pick">Choose PDF…</button></div><span class="err" hidden>${ic("alert")}Add the revised manuscript.</span></div>
      <div class="stack-sm"><p class="strong" style="font-size:13px">Response to reviewers</p>${open.length ? open.map((t) => `<div class="field"><label for="sv-${t.id}">${t.sev === "must" ? "Must fix" : "Suggestion"} · ${t.party}, p. ${t.page}: ${esc(t.text)}</label><textarea class="textarea" id="sv-${t.id}" rows="2" placeholder="What you changed, and where"></textarea></div>`).join("") : `<p class="small muted">Every thread already has an answer.</p>`}<span class="hint">A thread you leave blank goes out as "No answer given".</span></div>
      <div class="field"><label for="sv-n">Note to your reviewers <span class="opt">(optional)</span></label><textarea class="textarea" id="sv-n" rows="2"></textarea></div>`,
    foot: `<button class="btn btn-ghost" type="button" data-x>Cancel</button><button class="btn btn-primary" type="button" data-ok>Send version 2</button>` });
  let picked = false;
  $("#sv-pick", d.el).addEventListener("click", () => { picked = true; $("#sv-file", d.el).innerHTML = `${ic("file")}<span class="small" style="flex:1"><b class="strong">activity-preference-v2.pdf</b> · 2.1 MB · 11 pages</span><button class="btn btn-ghost btn-sm" type="button" data-toast="Prototype: the file would be removed.">Remove</button>`; $("#sv-file", d.el).nextElementSibling.hidden = true; });
  $("[data-ok]", d.el).addEventListener("click", () => {
    if (!picked) { $("#sv-file", d.el).nextElementSibling.hidden = false; $("#sv-pick", d.el).focus(); return; }
    open.forEach((t) => { const a = $(`#sv-${t.id}`, d.el).value.trim(); t.state = "addressed"; t.answer = a; });
    S.sentV2.add(r.id);
    VERSIONS[r.id].push({ v: 2, kind: "Revision", date: "13 Nov 2026", pages: 11 }); r.version = 2;
    const c = (CLEARANCE[r.id] || []).find((x) => x.state === "revising");
    if (c) Object.assign(c, { state: "reviewing", text: "Reviewing v2", date: "Since 13 Nov 2026", was: "Asked for a revision on v1, 11 Nov" });
    (CONVO[r.id] = CONVO[r.id] || []).push({ ev: "upload", text: "Sam Student sent v2 · answers IERC's request", date: "13 Nov 2026", mark: true });
    CHANGES[r.id] = { from: 1, to: 2, changed: 1, added: 4, removed: 1, unchanged: 6, names: ["Abstract", "1. Introduction", "2. Related literature", "4. Results", "5. Discussion", "References"], sections: [
      { name: "3. Methodology", page: 4, changed: 1, added: 3, removed: 1, items: [
        { kind: "Removed", text: "Respondents were invited through the HR mailing list and answered anonymously.", page: 4 },
        { kind: "Added", text: "The researcher, not HR, sent the invitation through a link that collected no names. The signed consent form is Appendix B.", page: 4 }] },
      { name: "Appendix B. Informed consent", page: 11, changed: 0, added: 1, removed: 0, items: [{ kind: "Added", text: "The signed informed consent form.", page: 11 }] }] };
    d.close(); toast("Version 2 sent. IERC was notified; the other clearances are kept."); rerender();
  });
}
function docsDialog(r) {
  const owner = relation(r) === "owner";
  const vs = (VERSIONS[r.id] || [{ v: 1, kind: "Submission", date: r.submitted || r.published }]).slice().reverse();
  const m = DOCS.manuscript(r);
  const row = (icon, name, meta, act) => `<li class="doc-row">${ic(icon)}<span class="doc-t"><b class="strong">${name}</b><span class="small muted">${meta}</span></span>${act}</li>`;
  const sup = DOCS.supporting[r.id] || [], ext = DOCS.supplementary[r.id] || [];
  const d = dialog({ title: "Documents", size: "lg", body: `<section class="stack-sm"><h3 class="card-title">Manuscript</h3><ul class="doc-list">${vs.map((v, i) => row("file", `Version ${v.v} · ${v.kind}${i === 0 ? " (current)" : ""}`, `${i === 0 ? m.name + " · " + m.size + " · " : ""}sent ${v.date}`, `<button class="btn btn-ghost btn-sm" type="button" data-toast="Prototype: v${v.v} would open in the reader.">Open</button>`)).join("")}</ul>
      ${owner ? `<button class="btn btn-secondary btn-sm" type="button" data-up style="justify-self:start">${ic("upload", "icon-16")}Upload revised manuscript</button>` : ""}</section>
      <section class="stack-sm"><h3 class="card-title">Supporting documents</h3>${sup.length ? `<ul class="doc-list">${sup.map(([t, f, s]) => row("file", t, `${f} · ${s}`, `<button class="icon-btn" type="button" aria-label="Download ${t}" data-toast="Prototype: ${f} would download.">${ic("download")}</button>`)).join("")}</ul>` : `<p class="small muted">None yet. Offices ask for these with Request documents.</p>`}</section>
      <section class="stack-sm"><h3 class="card-title">Supplementary attachments</h3>${ext.length ? `<ul class="doc-list">${ext.map(([t, f, s]) => row("file", t, `${f} · ${s}`, `<button class="icon-btn" type="button" aria-label="Download ${t}" data-toast="Prototype: ${f} would download.">${ic("download")}</button>`)).join("")}</ul>` : `<p class="small muted">None.</p>`}
      ${owner ? `<button class="btn btn-ghost btn-sm" type="button" data-toast="Prototype: the file picker would open." style="justify-self:start">${ic("plus", "icon-16")}Add a document</button>` : ""}</section>`,
    foot: `<button class="btn btn-secondary" type="button" data-x>Close</button>` });
  const up = $("[data-up]", d.el); if (up) up.addEventListener("click", () => { d.close(); sendVersion(r); });
}
function askSend(text) {
  if (!text.trim()) return;
  const all = S.ask.scope === "all", qs = S.ask.msgs.filter((m) => m.q);
  if (!qs.length) S.ask.startedAll = all;
  else if (qs[qs.length - 1].all !== all) S.ask.msgs.push({ divider: S.ask.scope });
  S.ask.msgs.push({ q: text, all }, { typing: true });
  rerender();
  setTimeout(() => { S.ask.msgs.pop(); S.ask.msgs.push({ a: true, all }); if (location.hash.startsWith("#/records")) rerender(); const sc = $("#ask-scroll"); if (sc) sc.scrollTop = sc.scrollHeight; }, 900);
}
function chatSend(text) {
  if (!text.trim()) return;
  S.chat.msgs = [...S.chat.msgs.filter((m) => !m.typing), { q: text }, { typing: true }];
  rerender();
  setTimeout(() => { S.chat.msgs = S.chat.msgs.filter((m) => !m.typing).concat({ a: CANNED }); if (location.hash.startsWith("#/ai")) rerender(); const b = $("#thread-body"); if (b) b.scrollTop = b.scrollHeight; }, 900);
}

document.addEventListener("click", (e) => {
  const t = e.target;
  const role = t.closest(".proto-roles [data-role]");
  if (role) { S.role = role.dataset.role; store.set("role", S.role); S.ask.msgs = []; S.revScope = "mine"; const { path } = parse(); const allowed = path.startsWith("/admin") ? me().admin : path.startsWith("/rdco") ? me().rdco : path.startsWith("/reviews") ? me().reviews && (!/console|analytics/.test(path) || me().coordinator) : true;
    if (!allowed) location.hash = "#/discover"; else render(); toast(`Viewing as ${me().name}, ${me().label}`); return; }
  const pub = t.closest("[data-publish]"); if (pub && !canAuthor()) { toast("Only students and advisers publish papers"); return; } if (pub) { closeDrawer(); openPublish(pub.dataset.resume); return; }
  if (t.closest("[data-open-drawer]")) { openDrawer(); return; }
  if (t.closest("[data-close-drawer]") || (t.closest("#sidebar a") && innerWidth < 768)) closeDrawer();
  const nb = t.closest("[data-notif]");
  if (nb) { popover(nb, `<p class="menu-head" style="display:flex;justify-content:space-between;align-items:center">Notifications <a class="small" href="#/notifications">See all</a></p><div class="notif-list" style="border:0;max-height:min(420px,60vh);overflow:auto">${notifItems(3, false, true)}</div>`, { width: 380, role: "dialog", label: "Notifications" }); return; }
  const ab = t.closest("[data-acct]");
  if (ab) { popover(ab, `<p class="menu-head">${me().name}<span class="small muted" style="display:block;font-weight:400">${me().email}</span></p><div class="menu-sep"></div><a class="menu-item" role="menuitem" href="#/profile">${ic("user")}Your profile</a><a class="menu-item" role="menuitem" href="#/settings">${ic("settings")}Settings</a><a class="menu-item" role="menuitem" href="#/notifications">${ic("bell")}Notifications</a><div class="menu-sep"></div><a class="menu-item" role="menuitem" href="#/login">${ic("logout")}Sign out</a>`, { width: 260, label: "Account" }); return; }
  const rd = t.closest("[data-read]"); if (rd) { S.read.add(S.role + rd.dataset.read); closePopover(); }
  const ts = t.closest("[data-toast]"); if (ts && !ts.disabled) { closePopover(); toast(ts.dataset.toast); return; }
  const a = t.closest("[data-action]");
  if (a && ACTIONS[a.dataset.action]) { e.preventDefault(); ACTIONS[a.dataset.action](a, e); }
  if (pop && t.closest(".menu a")) closePopover();
});
document.addEventListener("change", (e) => {
  const f = e.target.closest("[data-filter]"); if (f) { S.disc[f.dataset.filter] = f.value; render.keepScroll = true; const id = f.id; render(); const n = document.getElementById(id); if (n) n.focus(); return; }
  if (e.target.dataset.actionChange === "sort") { S.disc.sort = e.target.value; rerender(); }
  if (e.target.dataset.actionChange === "com-sort") { S.comSort = e.target.value; rerender(); $("#com-sort").focus(); }
  if (e.target.dataset.actionChange === "audit-type") { location.hash = e.target.value === "all" ? "#/admin/audit" : "#/admin/audit?type=" + e.target.value; }
  if (e.target.dataset.actionChange === "version") {
    const id = Number(parse().path.split("/")[2]); const v = Number(e.target.value); const cur = VERSIONS[id].length;
    S.ws.ver[id] = v; toast(v === cur ? `Showing v${v}, the current version` : `Showing v${v}. Comments you make now attach to v${v}.`);
    rerender(); $("#ver-pick") && $("#ver-pick").focus();
  }
});
document.addEventListener("submit", (e) => {
  const f = e.target.closest("[data-form]"); if (!f) return;
  e.preventDefault();
  const kind = f.dataset.form;
  if (kind === "search") {
    const v = $("#disc-q").value.trim(); S.disc.q = v; S.disc.busy = true;
    location.hash = v ? `#/discover?q=${encodeURIComponent(v)}` : "#/discover"; rerender();
    setTimeout(() => { S.disc.busy = false; if (location.hash.startsWith("#/discover")) rerender(); }, 550);
  }
  if (kind === "ask") { const i = $("#ask-in"); askSend(i.value); }
  if (kind === "post-comment") {
    const ta = $("#com-in"); const v = ta.value.trim();
    if (!v) { ta.setAttribute("aria-invalid", "true"); ta.focus(); toast("Write a comment first"); return; }
    const list = COMMENTS[f.dataset.id]; const id = Math.max(0, ...list.map((c) => c.id)) + 1;
    list.push({ id, who: me().name, d: "2026-11-13", text: v }); S.comSort = "newest"; S.cmt.hl = id; toast("Comment posted"); rerender(); setTimeout(() => { S.cmt.hl = null; }, 1600);
  }
  if (kind === "cmt-reply") {
    const ta = $("#cr-in"); const v = ta.value.trim();
    if (!v) { ta.setAttribute("aria-invalid", "true"); ta.focus(); toast("Write a reply first"); return; }
    const list = COMMENTS[f.dataset.id]; const id = Math.max(0, ...list.map((c) => c.id)) + 1; const to = S.cmt.replyTo;
    list.push({ id, to, who: me().name, d: "2026-11-13", text: v }); delete S.cmt.drafts[to];
    const root = (function up(c) { return c.to ? up(list.find((x) => x.id === c.to)) : c; })(list.find((x) => x.id === to));
    S.cmt.open[root.id] = true; S.cmt.replyTo = null; S.cmt.hl = id; toast("Reply posted"); rerender(); setTimeout(() => { S.cmt.hl = null; }, 1600);
    const b = $(`#cmt-${id} [data-action="cmt-reply"]`); if (b) b.focus();
  }
  if (kind === "cmt-edit") {
    const id = Number(f.dataset.id); const ta = $(`#ce-${id}`); const v = ta.value.trim();
    if (!v) { ta.setAttribute("aria-invalid", "true"); ta.focus(); return; }
    const c = COMMENTS[Number(parse().path.split("/")[2])].find((x) => x.id === id); if (c.text !== v) { c.text = v; c.edited = true; }
    S.cmt.editing = null; toast("Comment saved"); rerender(); $(`#cmt-${id} .cmt-more`) && $(`#cmt-${id} .cmt-more`).focus();
  }
  if (kind === "ws-comment") {
    const ta = $("#ws-c"); const v = ta.value.trim();
    if (!v) { ta.setAttribute("aria-invalid", "true"); ta.focus(); toast("Write a comment first"); return; }
    const id = Number(f.dataset.id); const r = REC[id];
    if (!CONVO[id]) CONVO[id] = (HISTORY[id] || []).slice().reverse().map(([i, t, d, m]) => ({ ev: i, text: t, date: d, mark: m }));
    CONVO[id].push({ who: me().name, role: relation(r) === "owner" ? "Author" : myParty(r) || me().label, date: "Today", v: r.version, text: v, replies: [] });
    toast("Comment posted. Everyone on this review was notified."); rerender();
    const pb = $("#wsp"); if (pb) pb.scrollTop = pb.scrollHeight;
  }
  if (kind === "chat") { const i = $("#chat-in"); chatSend(i.value); }
  if (["login", "signup", "password", "forgot", "profile"].includes(kind)) {
    let ok = true;
    $$("input[required]", f).forEach((inp) => {
      const err = inp.closest(".field").querySelector(".err");
      let msg = "";
      if (!inp.value.trim()) msg = `Enter your ${inp.closest(".field").querySelector("label").textContent.toLowerCase()}.`;
      else if (inp.type === "email" && !/@cit\.edu$/i.test(inp.value.trim())) msg = "Use your institutional email, ending in @cit.edu.";
      else if (inp.id === "pw1" && inp.value.length < 12) msg = "Use at least 12 characters.";
      inp.setAttribute("aria-invalid", String(!!msg));
      if (err) { err.hidden = !msg; err.innerHTML = msg ? `${ic("alert")}${msg}` : ""; }
      if (msg && ok) { inp.focus(); ok = false; }
    });
    if (ok) { if (kind === "login") { toast("Prototype: signed in without checking anything"); location.hash = "#/discover"; } else if (kind === "signup") toast("Prototype: step 2 (Affiliation) would open."); else if (kind === "forgot") { toast("If that address has an account, a reset link is on its way."); location.hash = "#/login"; } else if (kind === "profile") { toast("Profile saved"); location.hash = "#/profile"; } else toast("Prototype: password not changed."); }
  }
  if (kind === "notice") confirmDialog({ title: "Publish version 4 of the notice?", body: "<p>Every account is asked to read and accept it at their next sign-in. Version 3 stays in the record.</p>", label: "Publish version 4", done: "Version 4 published" });
});
let noteTimer = 0;
document.addEventListener("input", (e) => {
  if (e.target.id === "notes-t") {
    S.notes[e.target.dataset.id] = e.target.value; const st = $("#notes-status"); st.textContent = "Saving…";
    clearTimeout(noteTimer); noteTimer = setTimeout(() => { const x = $("#notes-status"); if (x) x.textContent = "Saved"; }, 700);
  }
  if (e.target.id === "cr-in" && S.cmt.replyTo) S.cmt.drafts[S.cmt.replyTo] = e.target.value;
  if (e.target.matches(".composer textarea")) {
    const ta = e.target; ta.style.height = "auto"; ta.style.height = Math.min(ta.scrollHeight, 160) + "px";
    const s = ta.closest(".composer-box").querySelector(".send"); s.classList.toggle("ready", !!ta.value.trim());
  }
});
document.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey && e.target.matches(".composer textarea")) { e.preventDefault(); e.target.closest("form").requestSubmit(); }
  if (e.key === "Enter" && (e.ctrlKey || e.metaKey) && e.target.matches(".cmt-compose textarea, .cmt-edit textarea")) { e.preventDefault(); e.target.closest("form").requestSubmit(); }
  if (e.key === "Escape" && e.target.id === "cr-in") ACTIONS["cmt-cancel"]();
  if (e.key === "Escape" && e.target.matches(".cmt-edit textarea")) ACTIONS["cmt-edit-cancel"]();
  if (e.key === "Escape" && S.notesOpen && !$(".scrim") && !pop && $("#notes-panel") && $("#notes-panel").contains(document.activeElement)) ACTIONS["close-notes"]();
  if (e.key === "Escape" && $("#sidebar.open")) closeDrawer();
  if (e.key === "Escape" && $("#ws") && $("#ws").dataset.mode === "drawer" && S.ws.paneOpen && !$(".scrim") && !pop && !tourEl) setPane(false);
  if ((e.key === "c" || e.key === "C") && !e.ctrlKey && !e.metaKey && !e.altKey && $("#ws") && !/input|textarea|select/i.test(document.activeElement.tagName) && !$(".scrim") && (S.role === "office" || S.role === "adviser")) { e.preventDefault(); newComment(Number(parse().path.split("/")[2])); }
  if (e.key === "/" && !/input|textarea|select/i.test(document.activeElement.tagName) && $("#disc-q")) { e.preventDefault(); $("#disc-q").focus(); }
  if (e.key === "ArrowRight" || e.key === "ArrowLeft") {
    const tab = e.target.closest("[role=tab]"); if (!tab) return;
    const list = $$("[role=tab]", tab.parentElement); const i = list.indexOf(tab);
    const n = list[(i + (e.key === "ArrowRight" ? 1 : -1) + list.length) % list.length]; n.focus(); n.click();
  }
});
function openDrawer() { const s = $("#sidebar"); s.classList.add("open"); $(".drawer-scrim").hidden = false; $("[data-open-drawer]").setAttribute("aria-expanded", "true"); setTimeout(() => $(".nav-item", s).focus(), 50); }
function closeDrawer() { const s = $("#sidebar"); if (!s || !s.classList.contains("open")) return; s.classList.remove("open"); $(".drawer-scrim").hidden = true; const b = $("[data-open-drawer]"); b.setAttribute("aria-expanded", "false"); b.focus(); }

render();
