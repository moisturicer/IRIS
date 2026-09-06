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
  ROLES.STUDENT, ROLES.ADVISER, ROLES.RDCO, ROLES.ITSO, ROLES.IERC, ROLES.KTTO,
];

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

export type NavSectionName =
  | "Research Exploration"
  | "IP Management"
  | "Review Queue"
  | "Tools"
  | "Administration";

interface ScreenDef {
  /** Route path, as registered in `router/index.tsx`. */
  path: string;
  roles: RoleName[];
  /** Present only for screens that appear in the sidebar. */
  nav?: { label: string; icon: string; section: NavSectionName };
}

export const SCREEN_ACCESS = {
  // --- open to every authenticated role ---------------------------------
  discover:      { path: "/",              roles: EVERYONE,
                   nav: { label: "Discover", icon: "fa-compass", section: "Research Exploration" } },
  ai:            { path: "/ai",            roles: EVERYONE,
                   nav: { label: "Ask IRIS", icon: "fa-brain", section: "Research Exploration" } },
  library:       { path: "/records/mine",  roles: EVERYONE,
                   nav: { label: "My Library", icon: "fa-bookmark", section: "Research Exploration" } },
  opportunities: { path: "/opportunities", roles: EVERYONE,
                   nav: { label: "Calls & Conferences", icon: "fa-bullhorn", section: "Research Exploration" } },
  notifications: { path: "/notifications", roles: EVERYONE,
                   nav: { label: "Notifications", icon: "fa-bell", section: "Tools" } },
  settings:      { path: "/settings",      roles: EVERYONE,
                   nav: { label: "Settings & Profile", icon: "fa-cog", section: "Tools" } },
  help:          { path: "/help",          roles: EVERYONE },
  // Reached from Discover and the queues, never from the nav. Which *records*
  // are visible is the server's decision (IR-153), not this map's.
  paper:         { path: "/records/:id",           roles: EVERYONE },
  documents:     { path: "/records/:id/documents", roles: EVERYONE },

  // --- authoring ---------------------------------------------------------
  submit:     { path: "/records/add",       roles: AUTHORS,
                nav: { label: "Submit Disclosure", icon: "fa-file-signature", section: "IP Management" } },
  workspace:  { path: "/workspace",         roles: AUTHORS,
                nav: { label: "My Workspace", icon: "fa-briefcase", section: "IP Management" } },
  editRecord: { path: "/records/:id/edit",  roles: AUTHORS },

  // --- review ------------------------------------------------------------
  reviewQueue: { path: "/review/pending",  roles: REVIEWERS,
                 nav: { label: "Pending Records", icon: "fa-hourglass-half", section: "Review Queue" } },
  reviewApproved: { path: "/review/approved", roles: REVIEWERS,
                 nav: { label: "Approved", icon: "fa-check-circle", section: "Review Queue" } },
  reviewDeclined: { path: "/review/declined", roles: REVIEWERS,
                 nav: { label: "Declined", icon: "fa-times-circle", section: "Review Queue" } },
  evaluate:    { path: "/review/:id/evaluate", roles: REVIEWERS },

  // --- RDCO coordination -------------------------------------------------
  approvedProposals: { path: "/review/approved-proposals", roles: COORDINATOR,
                 nav: { label: "Approved Proposals", icon: "fa-flag-checkered", section: "Review Queue" } },
  importRecords: { path: "/records/import", roles: COORDINATOR,
                 nav: { label: "Import Records", icon: "fa-file-import", section: "IP Management" } },
  roleRequests:  { path: "/admin/role-requests", roles: COORDINATOR,
                 nav: { label: "Role Requests", icon: "fa-user-check", section: "Administration" } },
  downloadRequests: { path: "/admin/download-requests", roles: COORDINATOR,
                 nav: { label: "Download Requests", icon: "fa-download", section: "Administration" } },
  deleteRequests: { path: "/admin/delete-requests", roles: COORDINATOR,
                 nav: { label: "Delete Requests", icon: "fa-trash-alt", section: "Administration" } },
  audit:         { path: "/admin/audit", roles: COORDINATOR,
                 nav: { label: "Audit Log", icon: "fa-clipboard-list", section: "Administration" } },
} as const satisfies Record<string, ScreenDef>;

export type ScreenKey = keyof typeof SCREEN_ACCESS;

export const ALL_SCREENS = Object.keys(SCREEN_ACCESS) as ScreenKey[];

/** The roles permitted on a screen -- pass straight to `ProtectedRoute`. */
export function rolesFor(key: ScreenKey): RoleName[] {
  return SCREEN_ACCESS[key].roles as unknown as RoleName[];
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
 */
export function navFor(role: RoleName | null | undefined): NavEntry[] {
  if (!role) return [];
  return ALL_SCREENS.flatMap((key) => {
    const def = SCREEN_ACCESS[key];
    if (!("nav" in def) || !def.nav) return [];
    if (!canAccess(role, key)) return [];
    return [{ key, to: def.path, ...def.nav }];
  });
}

/** The sidebar's section order. */
export const NAV_SECTION_ORDER: NavSectionName[] = [
  "Research Exploration",
  "IP Management",
  "Review Queue",
  "Tools",
  "Administration",
];
