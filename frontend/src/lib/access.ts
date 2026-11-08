/**
 * Who may reach which screen (IR-160).
 *
 * **One map, two consumers.** `router/index.tsx` reads `rolesFor()` to gate a
 * route; `components/layout/Sidebar.tsx` reads `navFor()` to build the menu.
 * Before this file they decided separately -- the sidebar from Django's
 * `is_staff` flag, the router from application role names -- and disagreed:
 * migration `accounts/0005` set `is_staff = True` on all four office roles, so
 * ITSO and IERC were *shown* Role Requests and Audit Log and then bounced with a
 * 403 by the router. A nav item the user cannot open is a defect that only
 * appears for the roles nobody happens to test as, and there are six of them.
 *
 * Deriving the nav from the same map makes that class of bug unrepresentable:
 * a link cannot exist without a matching gate.
 *
 * **This is UX, not security.** `ProtectedRoute`'s own docstring already says
 * so, and it stays true: the Django API is the enforcement boundary
 * (`core/permissions.py`, and IR-165 for the role checks behind it). Hiding a
 * nav item is a courtesy. If a user reaches a forbidden route by URL, the server
 * refuses and the UI shows the forbidden state -- it does not pretend the route
 * is absent.
 *
 * Source of truth: `docs/ui-ux/02-information-architecture.md` section 5, as
 * amended 2026-09-06. Asserted by `access.test.ts`.
 */
import { ROLES, type RoleName } from "./constants";

const EVERYONE: RoleName[] = [
  ROLES.STUDENT, ROLES.ADVISER, ROLES.RDCO, ROLES.ITSO, ROLES.IERC, ROLES.KTTO, ROLES.SYSTEM_ADMIN,
];

/** The research navigation; System Admin uses its own Administration section. */
const RESEARCH_ROLES = EVERYONE.filter((role) => role !== ROLES.SYSTEM_ADMIN);

/**
 * Student and Adviser. The SRS names the actor of "Create IP Disclosure Draft"
 * and "Submit Record for Review" as *Record Owner (Student or Adviser)*.
 * Excludes the clearing offices, which must not author what they later clear,
 * and RDCO, which performs both intake and final review -- authoring would mean
 * reviewing its own record at two of the three gates. RDCO files on behalf of
 * others through Import Records instead.
 */
const AUTHORS: RoleName[] = [ROLES.STUDENT, ROLES.ADVISER];

/** Everyone who decides something about a record at some stage. */
const REVIEWERS: RoleName[] = [
  ROLES.ADVISER, ROLES.RDCO, ROLES.ITSO, ROLES.IERC, ROLES.KTTO,
];

/**
 * RDCO alone. This replaces `REQUEST_QUEUE_ROLES`, which was named for the
 * download/delete queues but had grown to gate user management, role requests,
 * the audit log and active sessions -- and admitted KTTO, a technology-transfer
 * office with no reason to administer accounts.
 */
const COORDINATOR: RoleName[] = [ROLES.RDCO];

/** The four offices (`IsStaff` on the server). Not the Adviser, who has no office. */
const OFFICES: RoleName[] = [ROLES.RDCO, ROLES.ITSO, ROLES.IERC, ROLES.KTTO];
/** The System Admin alone: the Audit Log (ADR-051 §3, IR-781). */
const SYSTEM_ADMIN: RoleName[] = [ROLES.SYSTEM_ADMIN];

/**
 * The sidebar's groups (IR-413, spec §4.1). "Main" is one short, unlabelled
 * list with Discover for every role; "RDCO" groups office coordination.
 * "Administration" is the System Admin's group. The five
 * sections before IR-413 (Research Exploration, IP Management, Review Queue,
 * Tools, Administration) made a one-item "Tools" heading the commonest sight.
 */
export type NavSectionName = "Main" | "RDCO" | "Administration";

interface ScreenDef {
  /** Route path, as registered in `router/index.tsx`. */
  path: string;
  roles: RoleName[];
  /** Present only for screens that appear in the sidebar. */
  nav?: {
    label: string;
    icon: string;
    section: NavSectionName;
    /**
     * Narrows who sees the sidebar item, never who may open the route: a
     * role outside it can still reach the screen by link or redirect.
     */
    onlyFor?: readonly RoleName[];
    /**
     * Shown only when the server says the user has review work
     * (`review_access.my_reviews`, IR-415). The role stays the outer gate;
     * this narrows it, so an Adviser with no advisees sees no My Reviews.
     */
    needsReviewAccess?: true;
  };
}

export const SCREEN_ACCESS = {
  // --- open to every authenticated role ---------------------------------
  discover:      { path: "/",              roles: EVERYONE,
                   nav: { label: "Discover", icon: "fa-compass", section: "Main" } },
  ai:            { path: "/ai",            roles: EVERYONE,
                   nav: { label: "Ask IRIS", icon: "fa-brain", section: "Main", onlyFor: RESEARCH_ROLES } },
  library:       { path: "/records/mine",  roles: EVERYONE,
                   nav: { label: "My Library", icon: "fa-bookmark", section: "Main", onlyFor: RESEARCH_ROLES } },
  // The bell at the top of the sidebar is the entry; its "View all" opens the
  // page, so a sidebar link would say the same thing twice (IR-519).
  notifications: { path: "/notifications", roles: EVERYONE },
  // Profile, Settings and Help live in the account menu in the sidebar's user
  // block (IR-413, spec §4.2), not in the nav list. Profile (who you are) and
  // Settings (your account) are separate pages since IR-933.
  profile:       { path: "/profile",       roles: EVERYONE },
  profileEdit:   { path: "/profile/edit",  roles: EVERYONE },
  // Another person's Profile (IR-700), opened by clicking their name. Who may be
  // opened is the server's decision: a hidden account answers 404.
  person:        { path: "/people/:id",    roles: EVERYONE },
  settings:      { path: "/settings",      roles: EVERYONE },
  help:          { path: "/help",          roles: EVERYONE },
  // Reached from Discover and the queues, never from the nav. Which *records*
  // are visible is the server's decision (IR-153), not this map's, and what a
  // viewer may do there is the capabilities adapter's (IR-411). The documents
  // and edit pages became its Files section and Edit details dialog; their
  // URLs are redirects (`router/redirects.tsx`).
  paper:         { path: "/records/:id",           roles: EVERYONE },

  // --- authoring ---------------------------------------------------------
  // Not a sidebar item and not really a screen any more: `/records/add`
  // redirects to the Publish dialog (IR-408), which every author reaches from
  // Discover's Publish button now that Discover is everyone's home (IR-534).
  // The entry stays as the authors gate the Publish button, My Library and
  // Help read; spec §4.2 renames it `publish`, which no ticket has done yet.
  submit:     { path: "/records/add",       roles: AUTHORS },

  // --- review ------------------------------------------------------------
  // One queue, three filters (IR-143). Approved and Declined were separate nav
  // entries and separate pages differing only by endpoint; they are now
  // `?status=` on this screen, so the sidebar stops implying three destinations
  // for one job. Named My Reviews since IR-268; the sidebar shows it only to a
  // user with review work, and `/review` sends anyone else to Discover
  // (IR-413, `ReviewAccessRoute`).
  reviewQueue: { path: "/review",  roles: REVIEWERS,
                 nav: { label: "My Reviews", icon: "fa-list-check", section: "Main",
                        needsReviewAccess: true } },

  // Workflow analytics (IR-626): an office's own figures, every office's for
  // RDCO. Reached from My Reviews, not the sidebar.
  reviewAnalytics: { path: "/review/analytics", roles: OFFICES },

  // Declared after My Reviews because the sidebar lists entries in
  // declaration order, and spec §4.1 puts it last in the main list.
  opportunities: { path: "/opportunities", roles: EVERYONE,
                   nav: { label: "Calls & Conferences", icon: "fa-bullhorn", section: "Main", onlyFor: RESEARCH_ROLES } },

  // --- RDCO coordination (ADR-051, IR-783) ----------------------------
  importRecords: { path: "/records/import", roles: COORDINATOR,
                 nav: { label: "Import Records", icon: "fa-file-import", section: "RDCO" } },
  users:         { path: "/rdco/users", roles: COORDINATOR,
                 nav: { label: "Users", icon: "fa-users", section: "RDCO" } },
  roleRequests:  { path: "/rdco/role-requests", roles: COORDINATOR,
                 nav: { label: "Role Requests", icon: "fa-user-check", section: "RDCO" } },
  downloadRequests: { path: "/rdco/download-requests", roles: COORDINATOR,
                 nav: { label: "Download Requests", icon: "fa-download", section: "RDCO" } },
  deleteRequests: { path: "/rdco/delete-requests", roles: COORDINATOR,
                 nav: { label: "Delete Requests", icon: "fa-trash-alt", section: "RDCO" } },

  // Both roles use the same Users page, with distinct addresses and server permissions.
  adminUsers:    { path: "/admin/users", roles: SYSTEM_ADMIN,
                 nav: { label: "Users", icon: "fa-users", section: "Administration" } },
  audit:         { path: "/admin/audit", roles: SYSTEM_ADMIN,
                 nav: { label: "Audit Log", icon: "fa-clipboard-list", section: "Administration" } },
  // ADR-051 §8: the System Admin confirms or rejects account deletions (IR-788).
  accountDeletionRequests: { path: "/admin/account-deletion-requests", roles: SYSTEM_ADMIN,
                 nav: { label: "Account Deletions", icon: "fa-user-slash", section: "Administration" } },
  // ADR-051 §3 and §19: the System Admin sets retention periods (IR-795).
  retention:     { path: "/admin/retention", roles: SYSTEM_ADMIN,
                 nav: { label: "Retention", icon: "fa-clock-rotate-left", section: "Administration" } },
} as const satisfies Record<string, ScreenDef>;

export type ScreenKey = keyof typeof SCREEN_ACCESS;

export const ALL_SCREENS = Object.keys(SCREEN_ACCESS) as ScreenKey[];

/** The roles permitted on a screen -- pass straight to `ProtectedRoute`. */
export function rolesFor(key: ScreenKey): RoleName[] {
  return SCREEN_ACCESS[key].roles as unknown as RoleName[];
}

/**
 * The route a screen is registered at.
 *
 * Exists so nothing outside this file writes a path string of its own. Before
 * IR-201, `roleDashboard.ts` (now `landing.ts`) kept its own copy of the login landing paths and
 * still pointed at `/review/pending` long after IR-143 replaced it with
 * `/review` — four of the six roles 404'd immediately after signing in, and
 * nothing caught it, because a hand-written string cannot be checked against
 * the router. Ask for a `ScreenKey` and the compiler does that work.
 */
export function pathFor(key: ScreenKey): string {
  return SCREEN_ACCESS[key].path;
}

/** `/people/<id>`: where a person's name leads. */
export function personPath(id: number): string {
  return SCREEN_ACCESS.person.path.replace(":id", String(id));
}

export function canAccess(role: RoleName | null | undefined, key: ScreenKey): boolean {
  if (!role) return false;
  return (SCREEN_ACCESS[key].roles as readonly RoleName[]).includes(role);
}

export interface NavEntry {
  key: ScreenKey;
  to: string;
  label: string;
  icon: string;
  section: NavSectionName;
}

/**
 * Every nav entry this role may open, in declaration order.
 *
 * Sections are not listed separately: a section exists for a role exactly when
 * it has an entry here, which is what keeps an empty "Administration" heading
 * off a student's screen without a second rule to maintain.
 *
 * `reviewAccess` is the user's own `review_access` from `/users/me/`. An entry
 * marked `needsReviewAccess` is left out unless it says `my_reviews`; a
 * missing object counts as no review work, the same answer the route guard
 * gives, so the link and the page cannot disagree.
 */
export function navFor(
  role: RoleName | null | undefined,
  reviewAccess?: { my_reviews: boolean } | null,
): NavEntry[] {
  if (!role) return [];
  return ALL_SCREENS.flatMap((key) => {
    const def = SCREEN_ACCESS[key];
    if (!("nav" in def) || !def.nav) return [];
    if (!canAccess(role, key)) return [];
    const { onlyFor, needsReviewAccess, ...item } = def.nav as NonNullable<ScreenDef["nav"]>;
    if (onlyFor && !onlyFor.includes(role)) return [];
    if (needsReviewAccess && !hasReviewWork(reviewAccess)) return [];
    return [{ key, to: def.path, ...item }];
  });
}

/**
 * Whether the server says this user has review work (IR-415's
 * `review_access.my_reviews`). The one reading of the flag, shared by the
 * sidebar and `ReviewAccessRoute`.
 */
export function hasReviewWork(reviewAccess?: { my_reviews: boolean } | null): boolean {
  return reviewAccess?.my_reviews === true;
}

/** The sidebar's section order. */
export const NAV_SECTION_ORDER: NavSectionName[] = ["Main", "RDCO", "Administration"];
