/**
 * Another person's public Profile: the draft shape IR-700 is built against
 * (IR-694, IR-696) and the sample people the prototype shows.
 *
 * PROTOTYPE. `IR-696` is not in code yet, so nothing here comes from the API.
 * The types are the contract as the design session left it, and the sample
 * people are invented, and every paper is a made-up title. When IR-696 ships,
 * `PUBLIC_PROFILE_SAMPLES` and `resolveSample` are deleted and the page reads
 * the endpoint instead.
 *
 * What the server never sends, and so what no type here carries: an email
 * address, coordinator status, lock state, or anything unpublished.
 */

/** Student, Adviser, or the office a staff member works for. Never "Faculty". */
export type RoleLabel = "Student" | "Adviser" | "ITSO" | "IERC" | "KTTO" | "RDCO";

/** A published paper the person owns or advised, with the one figure a reader may see. */
export interface ProfilePaper {
  id:                number;
  title:             string;
  /** Byline names, not accounts. */
  authors:           string[];
  classification_name: string;
  record_type_name:  string;
  publication_year:  number | null;
  /** Distinct accounts that opened it (the glossary's View). No totals are summed from this. */
  views:             number;
}

/** Another account that shared a published paper with this person. */
export interface Collaborator {
  id:             number;
  first_name:     string;
  middle_initial: string;
  last_name:      string;
  role_label:     RoleLabel;
  /** Relative to the API base; `null` when they added no photo. */
  photo_url:      string | null;
  /** How many published papers they shared. */
  shared_papers:  number;
}

export interface PublicProfile {
  id:              number;
  first_name:      string;
  middle_initial:  string;
  last_name:       string;
  role_label:      RoleLabel;
  college_name:    string;
  department_name: string;
  course_name:     string;
  bio:             string;
  research_interests: string[];
  photo_url:       string | null;
  /** Published papers they own, newest first. The real endpoint pages these. */
  research:        ProfilePaper[];
  /** Published papers they advised, newest first. */
  advised:         ProfilePaper[];
  /** Most papers shared first. */
  collaborators:   Collaborator[];
}

/** What the real endpoint pages by (settled in the IR-694 grilling). */
export const PAGE_SIZE = { papers: 10, collaborators: 12 } as const;

/** The one institution; IRIS has no multi-institution feature. */
export const UNIVERSITY = "Cebu Institute of Technology – University";

/** `/people/<id>`: where a name leads. */
export const personPath = (id: number) => `/people/${id}`;

/* ── Sample people (prototype only) ────────────────────────────────────── */

/** Served from `public/`; stands in for the authenticated photo fetch. */
export const SAMPLE_PHOTO = "/prototype-portrait.svg";

const TITLES = [
  "Flood Susceptibility Mapping of the Mananga Watershed Using Sentinel-2 Imagery",
  "A Low-Cost Sensor Network for River Level Monitoring in Barangay Pasil",
  "Predicting Landslide Risk in Cebu's Hill Barangays with Gradient Boosting",
  "Mangrove Cover Change Along the Mactan Channel, 2014 to 2024",
  "Community-Based Early Warning for Urban Flooding: A Pilot in Mandaue",
  "Estimating Rooftop Rainwater Harvest Potential from Open Building Footprints",
  "Satellite Radar for Reservoir Siltation: A Case Study of the Buhisan Dam",
  "Machine Learning for Short-Term Rainfall Nowcasting over the Visayas",
  "Participatory Mapping of Informal Settlements at Flood Risk",
  "Groundwater Level Forecasting for Cebu City Using Recurrent Networks",
  "Comparing Optical and Radar Indices for Paddy Field Monitoring",
  "Design of a Solar-Powered Telemetry Node for Remote Weather Stations",
  "Coastal Erosion Hotspots in Northern Cebu from a Decade of Shoreline Data",
  "A Web Platform for Reporting Drainage Blockages: Design and Usability Study",
  "Spatial Analysis of Typhoon Damage to School Buildings in the Visayas",
  "Evaluating Open Elevation Models for Small-Catchment Hydrology",
];

const AUTHORS = [
  ["Reyes, A.", "Santos, M.", "Villanueva, M."],
  ["Ybañez, J.", "Cabahug, R.", "Villanueva, M."],
  ["Tan, K.", "Villanueva, M."],
  ["Lim, G.", "Reyes, A.", "Ybañez, J.", "Villanueva, M."],
];

function paper(i: number, over: Partial<ProfilePaper> = {}): ProfilePaper {
  return {
    id: 500 + i,
    title: TITLES[i % TITLES.length],
    authors: AUTHORS[i % AUTHORS.length],
    classification_name: ["Environmental Engineering", "Computer Science", "Geomatics"][i % 3],
    record_type_name: i % 4 === 3 ? "Project" : "Thesis / Research",
    publication_year: 2025 - Math.floor(i / 3),
    views: [48, 112, 7, 63, 21, 190, 3, 36, 84, 15, 52, 9, 71, 27, 140, 5][i % 16],
    ...over,
  };
}

const COLLAB_NAMES: [string, string, string, RoleLabel][] = [
  ["Ana", "L", "Reyes", "Student"], ["Jomar", "D", "Ybañez", "Student"], ["Grace", "T", "Lim", "Student"],
  ["Rafael", "", "Cabahug", "Student"], ["Mei", "S", "Tan", "Student"], ["Paolo", "", "Santos", "Student"],
  ["Elena", "R", "Duterte", "Adviser"], ["Noel", "", "Abella", "Student"], ["Karla", "M", "Osmeña", "Student"],
  ["Ricardo", "", "Go", "Adviser"], ["Bianca", "", "Lapu", "Student"], ["Arvin", "J", "Pacaña", "Student"],
  ["Hazel", "", "Montecillo", "Student"], ["Dennis", "", "Uy", "Student"], ["Liza", "C", "Quiñones", "Student"],
];

function collaborators(count: number): Collaborator[] {
  return COLLAB_NAMES.slice(0, count).map(([first, mi, last, role], i) => ({
    id: 201 + i, first_name: first, middle_initial: mi, last_name: last, role_label: role,
    photo_url: i === 2 || i === 7 ? SAMPLE_PHOTO : null,
    shared_papers: Math.max(1, 14 - i),
  }));
}

/** An adviser with a full page: every section, and enough papers to need Show more. */
const FULL: PublicProfile = {
  id: 101, first_name: "Marites", middle_initial: "C", last_name: "Villanueva", role_label: "Adviser",
  college_name: "College of Engineering and Architecture", department_name: "Department of Computer Engineering", course_name: "",
  bio: "I work on how communities in Cebu see and prepare for flooding: sensors in the creeks, satellite imagery of the watersheds, and the models that connect the two. Most of my advisees start from a drainage problem in their own barangay. I advise theses in environmental and geospatial computing and welcome questions about field data collection.",
  research_interests: ["Flood risk", "Remote sensing", "GIS", "Machine learning", "Environmental sensing"],
  photo_url: SAMPLE_PHOTO,
  research: [paper(0, { authors: ["Villanueva, M.", "Tan, K."] }), paper(5, { authors: ["Villanueva, M."] }), paper(9, { authors: ["Villanueva, M.", "Abella, N."] })],
  advised: Array.from({ length: 14 }, (_, i) => paper(i + 1)),
  collaborators: collaborators(15),
};

/** A student with a short page: no advised papers, two collaborators, a short bio. */
const SPARSE: PublicProfile = {
  id: 102, first_name: "Ana", middle_initial: "L", last_name: "Reyes", role_label: "Student",
  college_name: "College of Computer Studies", department_name: "Department of Computer Science", course_name: "BS Computer Science",
  bio: "Fourth-year student. My thesis maps drainage blockages with residents' reports.",
  research_interests: ["Civic technology", "GIS"],
  photo_url: null,
  research: [paper(13, { authors: ["Reyes, A.", "Ybañez, J."], publication_year: 2025 }), paper(8, { authors: ["Reyes, A.", "Santos, M."], publication_year: 2024 })],
  advised: [],
  collaborators: [
    { id: 101, first_name: "Marites", middle_initial: "C", last_name: "Villanueva", role_label: "Adviser", photo_url: SAMPLE_PHOTO, shared_papers: 2 },
    { id: 203, first_name: "Grace", middle_initial: "T", last_name: "Lim", role_label: "Student", photo_url: null, shared_papers: 1 },
  ],
};

/** Someone who added nothing and has published nothing: the header and one line. */
const EMPTY: PublicProfile = {
  id: 103, first_name: "Jomar", middle_initial: "D", last_name: "Ybañez", role_label: "Student",
  college_name: "College of Engineering and Architecture", department_name: "Department of Civil Engineering", course_name: "BS Civil Engineering",
  bio: "", research_interests: [], photo_url: null,
  research: [], advised: [], collaborators: [],
};

/** Office staff: a role label that is an office, and no college or department on record. */
const STAFF: PublicProfile = {
  id: 105, first_name: "Teresita", middle_initial: "G", last_name: "Lim", role_label: "RDCO",
  college_name: "", department_name: "", course_name: "",
  bio: "Research and Development Coordinating Office. I answer questions about publishing, embargoes and download requests.",
  research_interests: [], photo_url: null,
  research: [], advised: [], collaborators: [],
};

/** Suspended: the server answers 404, so there is no profile to sample. */
export const SAMPLE_HIDDEN_ID = 104;

export const PUBLIC_PROFILE_SAMPLES: PublicProfile[] = [FULL, SPARSE, EMPTY, STAFF];

/** Where the prototype's own links go. */
export const SAMPLE_LINKS: { id: number; label: string }[] = [
  { id: 101, label: "Adviser, full page" },
  { id: 102, label: "Student, short page" },
  { id: 103, label: "Nothing added yet" },
  { id: 105, label: "Office staff" },
  { id: SAMPLE_HIDDEN_ID, label: "Suspended" },
];

/**
 * The sample for an id, or `null` where the real API would answer 404.
 * A collaborator nobody wrote a page for gets a short one made from what the
 * rail already knows, so every name in the prototype opens something.
 */
export function resolveSample(id: number): PublicProfile | null {
  if (id === SAMPLE_HIDDEN_ID) return null;
  const known = PUBLIC_PROFILE_SAMPLES.find((p) => p.id === id);
  if (known) return known;
  const person = PUBLIC_PROFILE_SAMPLES.flatMap((p) => p.collaborators).find((c) => c.id === id);
  if (!person) return null;
  return {
    id: person.id, first_name: person.first_name, middle_initial: person.middle_initial, last_name: person.last_name,
    role_label: person.role_label,
    college_name: "College of Engineering and Architecture",
    department_name: person.role_label === "Adviser" ? "Department of Civil Engineering" : "",
    course_name: person.role_label === "Student" ? "BS Civil Engineering" : "",
    bio: "", research_interests: [], photo_url: person.photo_url,
    research: [paper(person.id % 16)], advised: [], collaborators: [],
  };
}
