import { forwardRef, useEffect, useState } from "react";
import { NavLink } from "react-router-dom";
import { apiClient } from "@/api/client";
import { useAuth } from "@/hooks/useAuth";
import { useRole } from "@/hooks/useRole";
import { selectSidebarCollapsed, useUIStore } from "@/store/ui.store";
import { cn } from "@/lib/utils";
import { ASK_PATH } from "@/lib/askHandoff";
import { COLOUR_TRANSITION, FOCUS_RING } from "@/components/ui/interaction";
import { NotificationBell } from "./NotificationBell";
import { AccountMenu } from "./AccountMenu";
import { navFor, canAccess, NAV_SECTION_ORDER, type NavEntry, type NavSectionName } from "@/lib/access";
import { IrisMark, IrisWordmark } from "@/components/brand/IrisBrand";

interface NavItem {
  to:     string;
  label:  string;
  icon:   string;
  badge?: number;
}

// There is no `comingSoon` flag. Nav items are derived from `lib/access.ts`,
// which maps a role to screens that exist and are routed -- so a dead-end entry
// is not something you have to remember not to add. IR-160: "a dead end is
// worse than an absence."

function NavItemLink({ item, collapsed, onNavigate }: { item: NavItem; collapsed: boolean; onNavigate?: () => void }) {
  const badge = item.badge != null && item.badge > 0 ? item.badge : null;
  return (
    <li>
      <NavLink
        to={item.to}
        // Ask IRIS stays current on its conversation addresses (IR-548).
        end={item.to !== ASK_PATH}
        onClick={onNavigate}
        // A tooltip for the rail. Not the accessible name: the label below
        // stays in the tree as `sr-only` while it is visually hidden.
        title={collapsed ? item.label : undefined}
        className={({ isActive }) =>
          cn(
            "group relative flex items-center gap-3 rounded-lg px-3 py-2 text-sm",
            collapsed && "md:h-10 md:justify-center md:px-0",
            // Active is the brand tint; hover is neutral stone, so a hovered
            // row can never be mistaken for the page you are on.
            isActive
              ? "bg-brand-50 font-semibold text-brand"
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
            {/* The rail has no room for the number, so a dot marks it; the
                count itself is still read out from the sr-only badge above. */}
            {collapsed && badge != null && (
              <span aria-hidden className="absolute right-2 top-1.5 hidden h-2 w-2 rounded-full bg-brand ring-2 ring-white md:block" />
            )}
          </>
        )}
      </NavLink>
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
 * One short list every role shares, RDCO's Administration group, the bell at
 * the top (IR-519) and the account menu at the bottom. Below `md` it is a
 * drawer `AppShell` opens and closes; from `md` up it is always on screen, at
 * full width or as an icon rail the user chooses (stored per browser).
 */
export const Sidebar = forwardRef<HTMLElement, SidebarProps>(function Sidebar({ className, inert, onDismiss }, ref) {
  const { user } = useAuth();
  const { roleName } = useRole();
  const closeSidebar = useUIStore((s) => s.closeSidebar);
  const collapsed = useUIStore(selectSidebarCollapsed);
  const toggleCollapsed = useUIStore((s) => s.toggleSidebarCollapsed);
  const [roleRequestBadge, setRoleRequestBadge] = useState(0);

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

  // Badges are the only per-item state the map does not carry: the map answers
  // "may this role open it", never "how many are waiting". Role requests are
  // the one count that is someone's to act on.
  const BADGES: Partial<Record<NavEntry["key"], number | undefined>> = {
    roleRequests: roleRequestBadge,
  };

  const groups = NAV_SECTION_ORDER
    .map((section) => ({
      section,
      items: nav
        .filter((entry) => entry.section === section)
        .map((entry): NavItem => ({ to: entry.to, label: entry.label, icon: entry.icon, badge: BADGES[entry.key] })),
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
        // Below md: a 240px drawer over the page. From md: 240px, or a 64px
        // rail when collapsed. AppShell's left margin follows the same widths.
        "fixed left-0 top-0 z-50 flex h-screen w-60 flex-col border-r border-stone-200 bg-surface",
        // `shell` carries transform (the drawer's slide) and width (the rail)
        // together; AppShell sets the translate classes, not a transition.
        "transition-shell duration-200 ease-out motion-reduce:transition-none",
        collapsed ? "md:w-16" : "md:w-60",
        className,
      )}
    >
      {/* ── Brand ──────────────────────────────────────────────────────── */}
      <div className={cn("px-4 pb-4 pt-5", collapsed && "md:px-0 md:pb-3")}>
        <div className={cn("flex items-center gap-3", collapsed && "md:justify-center")}>
          <button
            type="button"
            onClick={toggleCollapsed}
            aria-label={collapsed ? "Open sidebar" : "Collapse sidebar"}
            title={collapsed ? "Open sidebar" : "Collapse sidebar"}
            className={cn("hidden h-9 w-9 flex-shrink-0 rounded-lg md:block", FOCUS_RING)}
          >
            <IrisMark className="h-9 w-9 text-brand" />
          </button>
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
            // Where AppShell puts focus when the drawer opens.
            data-drawer-focus
            className={cn(
              "flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-lg text-stone-500 hover:bg-stone-100 hover:text-stone-900 md:hidden",
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
            <NotificationBell align="start" />
          </div>
        )}
      </div>

      {/* ── Navigation ─────────────────────────────────────────────────── */}
      <nav aria-label="Main" className="flex-1 overflow-y-auto px-3 py-2 scrollbar-thin">
        {groups.map(({ section, items }) => (
          <NavGroup key={section} section={section} items={items} collapsed={collapsed} onNavigate={closeSidebar} />
        ))}
      </nav>

      {/* ── Account menu ──────────────────────────────────────────────── */}
      <div className={cn("border-t border-stone-200 p-3", collapsed && "md:px-2")}>
        <AccountMenu collapsed={collapsed} onNavigate={closeSidebar} />
      </div>
    </aside>
  );
});
