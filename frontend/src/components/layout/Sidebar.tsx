import { forwardRef, useEffect, useState } from "react";
import { NavLink, useLocation } from "react-router-dom";
import { apiClient } from "@/api/client";
import { dashboardApi } from "@/api/dashboard";
import { useAuth } from "@/hooks/useAuth";
import { useRole } from "@/hooks/useRole";
import { selectSidebarCollapsed, useUIStore } from "@/store/ui.store";
import { cn } from "@/lib/utils";
import { ASK_PATH } from "@/lib/askHandoff";
import { COLOUR_TRANSITION, FOCUS_RING } from "@/components/ui/interaction";
import { NotificationBell } from "./NotificationBell";
import { AccountMenu } from "./AccountMenu";
import { navFor, canAccess, pathFor, NAV_SECTION_ORDER, type NavEntry, type NavSectionName } from "@/lib/access";
import { IrisMark, IrisWordmark } from "@/components/brand/IrisBrand";
import { Tooltip } from "@/components/ui/Tooltip";
import { isRail, useSidebarMode } from "@/lib/layout";
import { HERE } from "@/components/ui/highlightRoles";

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
   * Pages listed under this row (IR-1085, D5): My Reviews' Office console and
   * Workflow analytics. A list inside the row, so it reads as part of it.
   */
  children?: NavItem[];
}

/** Help's own link in the sidebar's footer, outside the nav list (IR-1085). */
const HELP_ITEM: NavItem = { to: pathFor("help"), label: "Help", icon: "fa-circle-question" };

// There is no `comingSoon` flag. Nav items are derived from `lib/access.ts`,
// which maps a role to screens that exist and are routed -- so a dead-end entry
// is not something you have to remember not to add. IR-160: "a dead end is
// worse than an absence."

function NavItemLink({ item, collapsed, onNavigate }: { item: NavItem; collapsed: boolean; onNavigate?: () => void }) {
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
        className={({ isActive }) =>
          cn(
            // 44px on the phone drawer; compact from md, where a pointer is (IR-1092).
            "group relative flex min-h-11 md:min-h-0 touch:min-h-11 items-center gap-3 rounded-lg px-3 py-2 text-sm",
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
        {({ isActive }) => (
          <>
            <i
              aria-hidden
              className={cn(
                "fas w-5 flex-shrink-0 text-center text-base",
                item.icon,
                isActive ? "text-brand" : "text-stone-500 group-hover:text-stone-700",
              )}
            />
            <span className={cn("min-w-0 flex-1 truncate", collapsed && "md:sr-only")}>{item.label}</span>
            {badge != null && (
              <span
                className={cn(
                  "inline-flex h-5 min-w-5 flex-shrink-0 items-center justify-center rounded-full bg-brand px-1.5 text-3xs font-semibold text-white",
                  collapsed && "md:sr-only",
                )}
              >
                <span aria-hidden>{badge > 9 ? "9+" : badge}</span>
                <span className="sr-only">, {badge} waiting</span>
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
        )}
      </NavLink>
      </Tooltip>
      {item.children && item.children.length > 0 && (
        // Indented under its parent with a rule, and level with it on the rail,
        // where each page is its own icon.
        <ul
          role="list"
          className={cn(
            "ml-5 mt-0.5 space-y-0.5 border-l border-stone-200 pl-2",
            collapsed && "md:ml-0 md:border-l-0 md:pl-0",
          )}
        >
          {item.children.map((child) => (
            <NavItemLink key={child.to} item={child} collapsed={collapsed} onNavigate={onNavigate} />
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
          "px-3 pb-2 text-3xs font-semibold uppercase tracking-wider text-stone-500",
          collapsed && "md:sr-only",
        )}
      >
        {section}
      </p>
      {list}
    </div>
  );
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
 * Admin's Administration group. My Reviews carries the Office console and
 * Workflow analytics under it, for the roles that have them (IR-1085, D5). The
 * bell is at the top (IR-519); Help and the account menu are at the bottom. Below `md` it is a
 * drawer `AppShell` opens and closes. From 768 to 1023 px it is the 76 px icon
 * rail, and the IRIS mark opens the full sidebar over the page (IR-1086). From
 * 1024 px it is at full width, or as the rail if the user chooses (stored per
 * browser; the choice is not read below 1024 px).
 */
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
  // The mark's job: on the desktop it saves a collapse preference; on a tablet
  // it opens and closes the full sidebar over the page and saves nothing.
  const dismiss = onDismiss ?? closeSidebar;
  const onMark = mode !== "rail" ? toggleCollapsed : collapsed ? () => setSidebarOpen(true) : dismiss;
  const [roleRequestBadge, setRoleRequestBadge] = useState(0);
  const [needsAction, setNeedsAction] = useState(false);
  const { pathname, search } = useLocation();

  // Every nav decision comes from lib/access.ts, the same map the router gates
  // on, and My Reviews from the same `review_access` flag its route reads.
  const nav = navFor(roleName as Parameters<typeof navFor>[0], user?.review_access);

  useEffect(() => {
    if (!canAccess(roleName as never, "roleRequests")) return;
    apiClient
      .get<{ count: number; results: unknown[] }>("/users/role-requests/")
      .then(({ data }) => setRoleRequestBadge(data.count ?? 0))
      .catch(() => {});
  }, [roleName]);

  // My Library's dot: some record of the user's waits on them -- a revision or
  // a document was asked for (B2, `needs_action_mine`). Asked again whenever
  // the address changes, query string included -- Paper View's sections are
  // `?section=` -- so answering the request clears it without a reload.
  // A failed read shows no dot rather than a stale one.
  const showsLibrary = nav.some((entry) => entry.key === "library");
  useEffect(() => {
    if (!showsLibrary) { setNeedsAction(false); return; }
    let live = true;
    dashboardApi
      .stats()
      .then(({ data }) => { if (live) setNeedsAction((data.needs_action_mine ?? 0) > 0); })
      .catch(() => { if (live) setNeedsAction(false); });
    return () => { live = false; };
  }, [pathname, search, showsLibrary]);

  // Badges are the only per-item state the map does not carry: the map answers
  // "may this role open it", never "how many are waiting". Role requests are
  // the one count that is someone's to act on.
  const BADGES: Partial<Record<NavEntry["key"], number | undefined>> = {
    roleRequests: roleRequestBadge,
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
        // Below md: a 240px drawer over the page. From md: 240px, or the 76px
        // rail when collapsed. AppShell's left margin follows the same widths,
        // except that an opened tablet sidebar overlaps the page instead.
        "fixed left-0 top-0 z-50 flex h-screen w-60 flex-col border-r border-stone-200 bg-surface",
        // `shell` carries transform (the drawer's slide) and width (the rail)
        // together; AppShell sets the translate classes, not a transition.
        "transition-shell duration-200 ease-out motion-reduce:transition-none",
        collapsed ? "md:w-rail" : "md:w-60",
        mode === "rail" && !collapsed && "shadow-card-md",
        className,
      )}
    >
      {/* ── Brand ──────────────────────────────────────────────────────── */}
      <div className={cn("px-4 pb-4 pt-5", collapsed && "md:px-0 md:pb-3")}>
        <div className={cn("flex items-center gap-3", collapsed && "md:justify-center")}>
          <Tooltip label="Open sidebar" disabled={!collapsed} className="hidden flex-shrink-0 md:block">
            <button
              type="button"
              onClick={onMark}
              aria-label={collapsed ? "Open sidebar" : "Collapse sidebar"}
              title={collapsed ? undefined : "Collapse sidebar"}
              // Where AppShell puts focus when a tablet's full sidebar opens,
              // and puts it back when that closes.
              data-sidebar-mark
              {...(mode === "rail" ? { "data-drawer-focus": "" } : {})}
              className={cn("block h-9 w-9 touch:h-11 touch:w-11 rounded-lg", FOCUS_RING)}
            >
              <IrisMark className="h-9 w-9 text-brand" />
            </button>
          </Tooltip>
          <IrisMark className="h-9 w-9 flex-shrink-0 text-brand md:hidden" />
          <p
            className={cn(
              "min-w-0 flex-1 leading-none text-brand",
              collapsed && "md:sr-only",
            )}
          >
            <IrisWordmark className="h-4 w-auto" />
            <span className="sr-only">IRIS</span>
          </p>
          {/* Desktop only: below md the phone bar carries the bell, and a
              second one in the drawer would put two on screen at once. */}
          {!collapsed && (
            <div className="hidden flex-shrink-0 md:block">
              <NotificationBell align="start" />
            </div>
          )}
          <button
            type="button"
            onClick={onDismiss ?? closeSidebar}
            aria-label="Close menu"
            // Where AppShell puts focus when the phone drawer opens.
            {...(mode === "rail" ? {} : { "data-drawer-focus": "" })}
            className={cn(
              "flex h-11 w-11 flex-shrink-0 items-center justify-center rounded-lg text-stone-500 hover:bg-stone-100 hover:text-stone-900 md:hidden",
              COLOUR_TRANSITION,
              FOCUS_RING,
            )}
          >
            <i className="fas fa-xmark text-base" aria-hidden />
          </button>
        </div>
        {/* Its own line, under the wordmark, so it never wraps beside the bell. */}
        <p className={cn("mt-1.5 truncate pl-12 text-3xs text-stone-500", collapsed && "md:hidden")}>
          Research-to-IP Platform
        </p>
        {collapsed && (
          <div className="mt-3 hidden justify-center md:flex">
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

      {/* ── Footer: Help, then the account menu ───────────────────────── */}
      <div className={cn("border-t border-stone-200 p-3", collapsed && "md:px-2")}>
        <ul role="list" className="mb-2">
          <NavItemLink item={HELP_ITEM} collapsed={collapsed} onNavigate={closeSidebar} />
        </ul>
        <AccountMenu collapsed={collapsed} onNavigate={closeSidebar} />
      </div>
    </aside>
  );
});
