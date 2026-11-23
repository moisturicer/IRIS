import { forwardRef, useEffect, useRef, useState } from "react";
import { Link, NavLink, useLocation } from "react-router-dom";
import { dashboardApi, type QueueCounts } from "@/api/dashboard";
import { onQueueCountsChanged } from "@/lib/queueCounts";
import { useLiveRefresh } from "@/hooks/useLiveRefresh";
import { useAuth } from "@/hooks/useAuth";
import { useRole } from "@/hooks/useRole";
import { selectSidebarCollapsed, useUIStore } from "@/store/ui.store";
import { cn } from "@/lib/utils";
import { ASK_PATH } from "@/lib/askHandoff";
import { COLOUR_TRANSITION, FOCUS_RING } from "@/components/ui/interaction";
import { NotificationBell } from "./NotificationBell";
import { AccountMenu } from "./AccountMenu";
import { ASK_IRIS_ICON, navFor, canAccess, NAV_SECTION_ORDER, type NavEntry, type NavSectionName } from "@/lib/access";
import { AskIrisGlyph, IrisMark, IrisWordmark } from "@/components/brand/IrisBrand";
import { Tooltip } from "@/components/ui/Tooltip";
import { isRail, useSidebarMode } from "@/lib/layout";
import { landingPathFor } from "@/lib/landing";
import { HERE } from "@/components/ui/highlightRoles";
import { preloadScreen } from "@/router/lazyScreens";

interface NavItem {
  to:     string;
  label:  string;
  icon:   string;
  badge?: number;
  /**
   * An attention dot with no number, for something that is waiting on the
   * user rather than a count worth reading (IR-534). The string is what a
   * screen reader hears in its place.
   */
  dot?: string;
  /**
   * Pages listed under this row (IR-1085, D5): My Reviews' Office console
   * (Workflow analytics moved to the RDCO group, IR-1216). A list inside the
   * row, so it reads as part of it.
   */
  children?: NavItem[];
}


// There is no `comingSoon` flag. Nav items are derived from `lib/access.ts`,
// which maps a role to screens that exist and are routed -- so a dead-end entry
// is not something you have to remember not to add. IR-160: "a dead end is
// worse than an absence."

function NavItemLink({ item, collapsed, onNavigate, nested }: { item: NavItem; collapsed: boolean; onNavigate?: () => void; nested?: boolean }) {
  const badge = item.badge != null && item.badge > 0 ? item.badge : null;
  const dot = badge == null ? item.dot : undefined;
  return (
    <li>
      {/* A tooltip for the rail, on hover and focus. Not the accessible name:
          the label inside stays in the tree as `sr-only` while hidden. */}
      <Tooltip label={item.label} disabled={!collapsed} className="block">
      <NavLink
        to={item.to}
        // Ask IRIS stays current on its conversation addresses (IR-548).
        end={item.to !== ASK_PATH}
        onClick={onNavigate}
        // Screens load on demand (IR-1248): start this one's download when the
        // link is pointed at or reached by keyboard, so the click finds it here.
        onMouseEnter={() => void preloadScreen(item.to)}
        onFocus={() => void preloadScreen(item.to)}
        className={({ isActive }) =>
          cn(
            // 44px on the phone drawer; compact from md, where a pointer is (IR-1092).
            // A nested row gives up some padding and gap so a name like "Workflow
            // analytics" fits without being cut short (IR-1180).
            "group relative flex min-h-11 md:min-h-0 touch:min-h-11 items-center rounded-control py-2 text-sm",
            nested ? "gap-2 px-2" : "gap-3 px-3",
            collapsed && "md:h-10 md:justify-center md:px-0",
            // Active is "here" (a Desk Stone fill); hover is the lighter Bar Stone, so a
            // hovered row can never be mistaken for the page you are on (IR-1097).
            isActive
              ? HERE
              : "font-medium text-stone-700 hover:bg-stone-100 hover:text-stone-900",
            COLOUR_TRANSITION,
            FOCUS_RING,
          )
        }
      >
        {({ isActive }) => {
          const iconTone = isActive ? "text-brand" : "text-stone-500 group-hover:text-stone-700";
          return (
          <>
            {item.icon === ASK_IRIS_ICON ? (
              // Ask IRIS is the one row drawn with the brand's speech bubble,
              // the mark it carries everywhere else (audit VIS-08).
              <AskIrisGlyph className={cn("h-5 w-5 flex-shrink-0", iconTone)} />
            ) : (
              <i
                aria-hidden
                className={cn("fas w-5 flex-shrink-0 text-center text-base", item.icon, iconTone)}
              />
            )}
            <span className={cn("min-w-0 flex-1 break-words", collapsed && "md:sr-only")}>{item.label}</span>
            {badge != null && (
              <span
                className={cn(
                  "inline-flex h-5 min-w-5 flex-shrink-0 items-center justify-center rounded-full bg-brand px-1.5 text-3xs font-semibold text-white",
                  collapsed && "md:sr-only",
                )}
              >
                <span aria-hidden>{badge > 9 ? "9+" : badge}</span>
                <span className="sr-only">, {badge} pending</span>
              </span>
            )}
            {dot != null && (
              <>
                <span
                  aria-hidden
                  className={cn("h-2 w-2 flex-shrink-0 rounded-full bg-brand", collapsed && "md:hidden")}
                />
                <span className="sr-only">, {dot}</span>
              </>
            )}
            {/* The rail has no room for the number, so a dot marks it; the
                count itself is still read out from the sr-only badge above. */}
            {collapsed && (badge != null || dot != null) && (
              <span aria-hidden className="absolute right-2 top-1.5 hidden h-2 w-2 rounded-full bg-brand ring-2 ring-white md:block" />
            )}
          </>
          );
        }}
      </NavLink>
      </Tooltip>
      {item.children && item.children.length > 0 && (
        // Indented under its parent with a rule, and level with it on the rail,
        // where each page is its own icon.
        <ul
          role="list"
          className={cn(
            "ml-3 mt-0.5 space-y-0.5 border-l border-stone-200 pl-1.5",
            collapsed && "md:ml-0 md:border-l-0 md:pl-0",
          )}
        >
          {item.children.map((child) => (
            <NavItemLink key={child.to} item={child} collapsed={collapsed} onNavigate={onNavigate} nested />
          ))}
        </ul>
      )}
    </li>
  );
}

function NavGroup({
  section,
  items,
  collapsed,
  onNavigate,
}: {
  section: NavSectionName;
  items: NavItem[];
  collapsed: boolean;
  onNavigate?: () => void;
}) {
  const list = (
    <ul role="list" className="space-y-0.5" aria-labelledby={section === "Main" ? undefined : `nav-${section}`}>
      {items.map((item) => (
        <NavItemLink key={item.to} item={item} collapsed={collapsed} onNavigate={onNavigate} />
      ))}
    </ul>
  );
  // The main list needs no heading: it is the sidebar. Only a role-specific
  // group is named, so its items read as belonging together.
  if (section === "Main") return list;
  return (
    <div className="mt-6">
      {/* The rail keeps the name for screen readers and shows a rule instead. */}
      {collapsed && <div aria-hidden className="mx-2 mb-3 hidden border-t border-stone-200 md:block" />}
      <p
        id={`nav-${section}`}
        className={cn(
          "px-3 pb-2 text-3xs font-semibold text-stone-500",
          collapsed && "md:sr-only",
        )}
      >
        {section}
      </p>
      {list}
    </div>
  );
}

/**
 * The sidebar toggle's icon (IR-1260): a window with its left pane filled,
 * and a chevron for the way the sidebar will move. Drawn rather than a Font
 * Awesome glyph because the free set has no sidebar icon; the filled pane
 * and 2 px strokes match the weight of the solid icons beside it.
 */
function SidebarPanelGlyph({ expand }: { expand: boolean }) {
  return (
    <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" aria-hidden focusable={false}>
      <rect x="3" y="4" width="18" height="16" rx="3" stroke="currentColor" strokeWidth="2" />
      <path d="M4 5h5v14H4z" fill="currentColor" />
      <path
        d={expand ? "M13 9l3 3-3 3" : "M16 9l-3 3 3 3"}
        stroke="currentColor"
        strokeWidth="2.2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

/** The key that collapses and expands the sidebar (IR-1260). */
export const SIDEBAR_KEY = "[";

/**
 * Whether a key press belongs to something else: typing in a field, a chord
 * with a modifier, or a dialog open over the page. Only a bare `[` with focus
 * on the page toggles the sidebar.
 */
function isOwnedElsewhere(e: KeyboardEvent): boolean {
  if (e.defaultPrevented || e.repeat || e.ctrlKey || e.metaKey || e.altKey) return true;
  const target = e.target instanceof Element ? e.target : null;
  if (!target) return false;
  if (target.closest("input, textarea, select, [contenteditable=''], [contenteditable='true']")) return true;
  return target.closest("[role='dialog'], [role='alertdialog'], [aria-modal='true']") != null;
}

interface SidebarProps {
  className?: string;
  /** Set by `AppShell` while the phone drawer is closed: out of the tab order. */
  inert?: boolean;
  /**
   * The drawer's Close menu button. `AppShell` passes one that also returns
   * focus to Open menu; choosing a link closes the drawer without it.
   */
  onDismiss?: () => void;
}

/**
 * The app's navigation (IR-413, spec §4.1).
 *
 * Discover and research links, RDCO's coordination group, and the System
 * Admin's Administration group. My Reviews carries the Office console under
 * it for coordinators (IR-1085, D5); Workflow analytics is RDCO's (IR-1216). The
 * bell is at the top (IR-519); the account menu is at the bottom, and Help is
 * in Settings (IR-1217). Below `md` it is a
 * drawer `AppShell` opens and closes. From 768 to 1023 px it is the 76 px icon
 * rail, and the sidebar button opens the full sidebar over the page (IR-1086).
 * From 1024 px it is at full width, or as the rail if the user chooses (stored
 * per browser; the choice is not read below 1024 px).
 *
 * The sidebar button (IR-1260) is a visible control beside the bell, and `[`
 * does the same. On the rail the IRIS mark is the expand button: the logo at
 * rest, the sidebar icon on hover or focus, so it shows what it does before
 * it is pressed. On the full sidebar the mark is the logo, a link home.
 */
const NO_QUEUES: QueueCounts = {};

/** Each count the reply holds as a number; anything else is no count rather than a wrong one (F1). */
function countsIn(data: unknown): QueueCounts {
  const reply = (data ?? {}) as Record<string, unknown>;
  const keys = ["download_requests", "delete_requests", "role_change_requests", "reported_comments"] as const;
  return Object.fromEntries(keys.filter((key) => typeof reply[key] === "number").map((key) => [key, reply[key]]));
}

export const Sidebar = forwardRef<HTMLElement, SidebarProps>(function Sidebar({ className, inert, onDismiss }, ref) {
  const { user } = useAuth();
  const { roleName } = useRole();
  const closeSidebar = useUIStore((s) => s.closeSidebar);
  const setSidebarOpen = useUIStore((s) => s.setSidebarOpen);
  const sidebarOpen = useUIStore((s) => s.sidebarOpen);
  const preferCollapsed = useUIStore(selectSidebarCollapsed);
  const toggleCollapsed = useUIStore((s) => s.toggleSidebarCollapsed);
  const mode = useSidebarMode();
  const collapsed = isRail(mode, sidebarOpen, preferCollapsed);
  // The sidebar button's job: on the desktop it saves a collapse preference;
  // on a tablet it opens and closes the full sidebar over the page and saves
  // nothing. The phone has its own Open and Close menu buttons.
  const dismiss = onDismiss ?? closeSidebar;
  const onToggle = mode !== "rail" ? toggleCollapsed : collapsed ? () => setSidebarOpen(true) : dismiss;
  const toggleLabel = collapsed ? "Expand sidebar" : "Collapse sidebar";

  // `[` does what the button does, from 768 px up (IR-1260). Read through a
  // ref so the listener is added once, not on every render.
  const toggleRef = useRef(onToggle);
  toggleRef.current = onToggle;
  useEffect(() => {
    if (mode === "drawer") return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key !== SIDEBAR_KEY || isOwnedElsewhere(e)) return;
      e.preventDefault();
      toggleRef.current();
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [mode]);
  const [queueCounts, setQueueCounts] = useState<QueueCounts>(NO_QUEUES);
  const [needsAction, setNeedsAction] = useState(false);
  /** My Reviews' To review count, from the same stats read (IR-1208). */
  const [reviewsWaiting, setReviewsWaiting] = useState<number | undefined>(undefined);
  const { pathname, search } = useLocation();

  // Every nav decision comes from lib/access.ts, the same map the router gates
  // on, and My Reviews from the same `review_access` flag its route reads.
  const nav = navFor(roleName as Parameters<typeof navFor>[0], user?.review_access);
  // The mark goes where signing in goes (IR-534). Named "IRIS home", not
  // "IRIS, go to Discover": a name holding a page action's words ("Go to
  // Discover" on the not-found screen) would be a second match for it.
  const home = user ? landingPathFor(user) : "/";

  // The queues' counts, in one call (IR-1138): RDCO's three and the Reported
  // comments queue RDCO shares with the System Admin (IR-693). Read again when
  // the address changes, as the Library dot is, and when a decision is made on
  // a queue page. Only those two roles ask; a failed read shows no count
  // rather than a stale one.
  const showsQueues = canAccess(roleName as never, "roleRequests")
    || canAccess(roleName as never, "adminReportedComments");
  // Live updates (ADR-073): a hint re-runs the reads below, as the address does.
  const [queuesTick, setQueuesTick] = useState(0);
  const [statsTick, setStatsTick] = useState(0);
  useLiveRefresh(["queues"], () => setQueuesTick((t) => t + 1), showsQueues);
  useLiveRefresh(["reviews", "library"], () => setStatsTick((t) => t + 1));
  useEffect(() => {
    if (!showsQueues) { setQueueCounts(NO_QUEUES); return; }
    let live = true;
    const read = () => {
      dashboardApi
        .queueCounts()
        .then(({ data }) => { if (live) setQueueCounts(countsIn(data)); })
        .catch(() => { if (live) setQueueCounts(NO_QUEUES); });
    };
    read();
    const off = onQueueCountsChanged(read);
    return () => { live = false; off(); };
  }, [showsQueues, pathname, search, queuesTick]);

  // My Library's dot: some record of the user's waits on them -- a revision or
  // a document was asked for (B2, `needs_action_mine`). The same read carries
  // My Reviews' count, the reviews waiting on the user (IR-1208, the To review
  // tab's own number, `reviews_waiting_mine`). Asked again whenever
  // the address changes, query string included -- Paper View's sections are
  // `?section=` -- so answering the request clears it without a reload.
  // A failed read shows no dot rather than a stale one.
  const showsLibrary = nav.some((entry) => entry.key === "library");
  useEffect(() => {
    if (!showsLibrary) { setNeedsAction(false); setReviewsWaiting(undefined); return; }
    let live = true;
    dashboardApi
      .stats()
      .then(({ data }) => {
        if (!live) return;
        setNeedsAction((data.needs_action_mine ?? 0) > 0);
        // The same number as My Reviews' To review tab (IR-1208).
        setReviewsWaiting(data.reviews_waiting_mine);
      })
      .catch(() => { if (live) { setNeedsAction(false); setReviewsWaiting(undefined); } });
    return () => { live = false; };
  }, [pathname, search, showsLibrary, statsTick]);

  // Badges are the only per-item state the map does not carry: the map answers
  // "may this role open it", never "how many are waiting". RDCO's three request
  // queues are the counts that are someone's to act on.
  const BADGES: Partial<Record<NavEntry["key"], number | undefined>> = {
    // Reviews waiting on the user, for every reviewer with work (IR-1208).
    reviewQueue: reviewsWaiting,
    roleRequests: queueCounts.role_change_requests,
    downloadRequests: queueCounts.download_requests,
    deleteRequests: queueCounts.delete_requests,
    reportedComments: queueCounts.reported_comments,
    adminReportedComments: queueCounts.reported_comments,
  };
  // A dot, not a count: what matters is that something waits (spec §4.2).
  const DOTS: Partial<Record<NavEntry["key"], string | undefined>> = {
    library: needsAction ? "something needs your action" : undefined,
  };

  const toItem = (entry: NavEntry): NavItem => {
    const children = nav.filter((child) => child.parent === entry.key).map(toItem);
    return {
      to: entry.to, label: entry.label, icon: entry.icon,
      badge: BADGES[entry.key], dot: DOTS[entry.key],
      ...(children.length > 0 ? { children } : {}),
    };
  };

  const groups = NAV_SECTION_ORDER
    .map((section) => ({
      section,
      // Nested entries are drawn inside their parent's row, not beside it.
      items: nav
        .filter((entry) => entry.section === section && !entry.parent)
        .map(toItem),
    }))
    // A group with nothing in it for this role is not rendered at all, which is
    // what keeps an empty "Administration" heading off a student's sidebar.
    .filter((g) => g.items.length > 0);

  return (
    <aside
      ref={ref}
      id="app-sidebar"
      aria-label="Sidebar"
      // React 18 has no `inert` prop; an empty string sets the attribute.
      {...(inert ? { inert: "" } : {})}
      className={cn(
        // Below md: a 256px drawer over the page. From md: 256px, or the 76px
        // rail when collapsed. AppShell's left margin follows the same widths,
        // except that an opened tablet sidebar overlaps the page instead.
        // 256, not 240 (IR-1276): at 240 "Download requests" and "Reported
        // comments" wrapped to two lines beside their count badge.
        "fixed left-0 top-0 z-50 flex h-screen w-64 flex-col border-r border-stone-200 bg-surface",
        // `shell` carries transform (the drawer's slide) and width (the rail)
        // together; AppShell sets the translate classes, not a transition.
        "transition-shell duration-200 ease-out motion-reduce:transition-none",
        collapsed ? "md:w-rail" : "md:w-64",
        mode === "rail" && !collapsed && "shadow-card-md",
        className,
      )}
    >
      {/* ── Brand ──────────────────────────────────────────────────────── */}
      <div className={cn("px-4 pb-4 pt-5", collapsed && "md:px-0 md:pb-3")}>
        <div className={cn("flex items-center gap-3", collapsed && "md:justify-center")}>
          {collapsed ? (
            // The rail's one control at the top (IR-1260): the logo at rest,
            // the sidebar icon on hover or keyboard focus, so the reader sees
            // what pressing it does before pressing. It expands the sidebar.
            <Tooltip label={toggleLabel} shortcut={SIDEBAR_KEY} className="flex-shrink-0">
              <button
                type="button"
                onClick={onToggle}
                aria-label={toggleLabel}
                aria-expanded={false}
                aria-controls="app-sidebar"
                // Where AppShell puts focus back when a tablet's full sidebar
                // closes.
                data-sidebar-toggle
                className={cn(
                  "group relative flex h-9 w-9 touch:h-11 touch:w-11 items-center justify-center rounded-control text-stone-600 hover:bg-stone-100 hover:text-stone-900 focus-visible:bg-stone-100 active:bg-stone-200",
                  COLOUR_TRANSITION,
                  FOCUS_RING,
                )}
              >
                <IrisMark className="h-9 w-9 text-brand transition-opacity duration-150 group-hover:opacity-0 group-focus-visible:opacity-0 motion-reduce:transition-none" />
                <span className="absolute inset-0 flex items-center justify-center opacity-0 transition-opacity duration-150 group-hover:opacity-100 group-focus-visible:opacity-100 motion-reduce:transition-none">
                  <SidebarPanelGlyph expand />
                </span>
              </button>
            </Tooltip>
          ) : (
            // The logo, and a way home.
            <Link
              to={home}
              onClick={closeSidebar}
              aria-label="IRIS home"
              className={cn(
                "flex h-9 w-9 flex-shrink-0 touch:h-11 touch:w-11 items-center justify-center rounded-control text-brand",
                FOCUS_RING,
              )}
            >
              <IrisMark className="h-9 w-9" />
            </Link>
          )}
          <p
            className={cn(
              "min-w-0 flex-1 leading-none text-brand",
              collapsed && "md:sr-only",
            )}
          >
            <IrisWordmark className="h-4 w-auto" />
            <span className="sr-only">IRIS</span>
          </p>
          {/* From md only: below it the phone bar carries the bell, and a
              second one in the drawer would put two on screen at once. The
              phone's drawer has Close menu instead of the sidebar button. */}
          {!collapsed && (
            <div className="hidden flex-shrink-0 items-center gap-1 md:flex">
              <NotificationBell align="start" />
              <Tooltip label={toggleLabel} shortcut={SIDEBAR_KEY} className="block">
                <button
                  type="button"
                  onClick={onToggle}
                  aria-label={toggleLabel}
                  aria-expanded
                  aria-controls="app-sidebar"
                  // Where AppShell puts focus when a tablet's full sidebar opens,
                  // and puts it back when that closes.
                  data-sidebar-toggle
                  {...(mode === "rail" ? { "data-drawer-focus": "" } : {})}
                  className={cn(
                    "flex h-9 w-9 touch:h-11 touch:w-11 items-center justify-center rounded-control text-stone-600 hover:bg-stone-100 hover:text-stone-900 active:bg-stone-200",
                    COLOUR_TRANSITION,
                    FOCUS_RING,
                  )}
                >
                  <SidebarPanelGlyph expand={false} />
                </button>
              </Tooltip>
            </div>
          )}
          <button
            type="button"
            onClick={onDismiss ?? closeSidebar}
            aria-label="Close menu"
            // Where AppShell puts focus when the phone drawer opens.
            {...(mode === "rail" ? {} : { "data-drawer-focus": "" })}
            className={cn(
              "flex h-11 w-11 flex-shrink-0 items-center justify-center rounded-control text-stone-500 hover:bg-stone-100 hover:text-stone-900 md:hidden",
              COLOUR_TRANSITION,
              FOCUS_RING,
            )}
          >
            <i className="fas fa-xmark text-base" aria-hidden />
          </button>
        </div>
        {/* Its own line, under the wordmark, so it never wraps beside the bell. */}
        <p className={cn("mt-1.5 break-words pl-12 text-3xs text-stone-500", collapsed && "md:hidden")}>
          Research-to-IP Platform
        </p>
        {collapsed && (
          <div className="mt-2.5 hidden justify-center md:flex">
            <Tooltip label="Notifications">
              <NotificationBell align="start" showTitle={false} />
            </Tooltip>
          </div>
        )}
      </div>

      {/* ── Navigation ─────────────────────────────────────────────────── */}
      <nav aria-label="Main" className="flex-1 overflow-y-auto px-3 py-2 scrollbar-thin">
        {groups.map(({ section, items }) => (
          <NavGroup key={section} section={section} items={items} collapsed={collapsed} onNavigate={closeSidebar} />
        ))}
      </nav>

      {/* ── Footer: the account menu. Help is in Settings (IR-1217). ─── */}
      <div className={cn("border-t border-stone-200 p-3", collapsed && "md:px-2")}>
        <AccountMenu collapsed={collapsed} onNavigate={closeSidebar} />
      </div>
    </aside>
  );
});
