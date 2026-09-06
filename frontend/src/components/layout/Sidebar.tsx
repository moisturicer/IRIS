import { useEffect, useState } from "react";
import { NavLink } from "react-router-dom";
import { apiClient } from "@/api/client";
import { authApi } from "@/api/auth";
import { useAuth } from "@/hooks/useAuth";
import { useRole } from "@/hooks/useRole";
import { useUIStore } from "@/store/ui.store";
import { useNotifications } from "@/hooks/useNotifications";
import { cn } from "@/lib/utils";
import { STAFF_ROLES, REVIEWER_ROLES } from "@/lib/constants";
import irisLogo from "@/assets/images/iris_logo.png";

interface NavItem {
  to:          string;
  label:       string;
  icon:        string;
  badge?:      number;
  /**
   * Renders a COMING SOON badge. **No nav item uses this any more**, and none
   * should: IR-160's acceptance criteria require that every remaining nav item
   * leads somewhere real. Kept only so the badge markup below stays typed --
   * if you find yourself setting it, the screen belongs out of the nav instead.
   */
  comingSoon?: boolean;
}

function NavSection({
  title,
  items,
  onNavigate,
  collapsed,
}: {
  title: string;
  items: NavItem[];
  onNavigate?: () => void;
  collapsed: boolean;
}) {
  return (
    <>
      {/* Section title: hidden while the desktop rail is collapsed. The mobile
          drawer is always full width, so it keeps its titles either way. */}
      <div
        className={cn(
          "px-4 py-2 text-[10px] font-bold tracking-widest text-gray-500 uppercase",
          collapsed ? "block md:hidden" : "block",
        )}
      >
        {title}
      </div>
      {items.map((item) => (
        <NavLink
          key={item.to}
          to={item.to}
          end
          onClick={onNavigate}
          title={collapsed ? item.label : undefined}
          className={({ isActive }) =>
            cn(
              "flex items-center gap-3 mx-2 py-2.5 rounded-md text-[13px] font-medium transition-colors relative",
              collapsed ? "px-4 md:px-2 justify-start md:justify-center" : "px-4 justify-start",
              isActive
                ? "bg-red-50 text-[#6B0F12] font-semibold before:absolute before:left-0 before:top-1 before:bottom-1 before:w-1 before:rounded-r before:bg-[#6B0F12]"
                : "text-gray-600 hover:bg-red-50/60 hover:text-[#6B0F12]"
            )
          }
        >
          <i className={cn("fas", item.icon, "w-5 text-center text-[16px] flex-shrink-0")} aria-hidden />
          {/* The visible label below is `md:hidden` while the rail is collapsed,
              which leaves the link with no accessible name on tablet and up --
              `title` is a tooltip, not a reliable name. This carries the name at
              exactly those widths: `hidden` keeps it out of the mobile drawer
              (where the real label is already showing, and announcing both would
              double up), `md:inline` brings it back, and `sr-only` keeps it
              visually absent. */}
          {collapsed && <span className="sr-only hidden md:inline">{item.label}</span>}
          {/* Label + coming-soon badge stacked; hidden while collapsed */}
          <div
            className={cn(
              "flex-1 flex-col gap-0.5 min-w-0",
              collapsed ? "flex md:hidden" : "flex",
            )}
          >
            <span>{item.label}</span>
            {item.comingSoon && (
              <span className="self-start px-1.5 py-0.5 bg-amber-50 text-amber-600 text-[9px] font-bold rounded-full border border-amber-200 uppercase tracking-wider leading-none">
                coming soon
              </span>
            )}
          </div>
          {/* Numeric badge: hidden on tablet, shown on desktop */}
          {item.badge != null && item.badge > 0 && (
            <span
              className={cn(
                "min-w-[18px] h-[18px] px-1 rounded-full bg-red-500 text-white text-[10px] font-bold items-center justify-center",
                collapsed ? "flex md:hidden" : "flex",
              )}
            >
              {item.badge > 9 ? "9+" : item.badge}
            </span>
          )}
          {/* Collapsed: a dot keeps unread counts visible without the label */}
          {collapsed && item.badge != null && item.badge > 0 && (
            <span className="hidden md:block absolute top-1 right-1 w-2 h-2 rounded-full bg-red-500" />
          )}
        </NavLink>
      ))}
    </>
  );
}

interface SidebarProps {
  className?: string;
}

export function Sidebar({ className }: SidebarProps) {
  const { user } = useAuth();
  const { roleName, isDjangoStaff } = useRole();
  const { unreadCount } = useNotifications();
  const closeSidebar = useUIStore((s) => s.closeSidebar);
  const collapsed = useUIStore((s) => s.sidebarCollapsed);
  const toggleCollapsed = useUIStore((s) => s.toggleSidebarCollapsed);
  const { logout, refreshToken } = useAuth();

  const handleSignOut = async () => {
    await authApi.logout(refreshToken ?? "").catch(() => {});
    logout();
  };
  const [workspaceBadge, setWorkspaceBadge] = useState<number | undefined>();
  const [roleRequestBadge, setRoleRequestBadge] = useState(0);

  const isRDCO = user?.role_name === "RDCO" || user?.is_staff === true || user?.is_superuser === true;

  const isStaff =
    user?.is_staff === true ||
    user?.is_superuser === true ||
    (user?.role_name != null && STAFF_ROLES.includes(user.role_name as typeof STAFF_ROLES[number]));

  // Django admin only (is_staff=True) — gates role requests, audit log
  const isDjangoAdmin = user?.is_staff === true || user?.is_superuser === true;

  const isReviewer =
    user?.role_name != null &&
    REVIEWER_ROLES.includes(user.role_name as typeof REVIEWER_ROLES[number]);

  useEffect(() => {
    if (!isDjangoStaff) return;
    apiClient
      .get<{ pending_mine: number }>("/dashboard/stats/")
      .then(({ data }) => setWorkspaceBadge(data.pending_mine ?? 0))
      .catch(() => {});
  }, []);

  useEffect(() => {
    if (!isDjangoAdmin) return;
    apiClient
      .get<{ count: number; results: unknown[] }>("/users/role-requests/")
      .then(({ data }) => setRoleRequestBadge(data.count ?? 0))
      .catch(() => {});
  }, [isDjangoAdmin]);

  const initials = `${user?.first_name?.[0] ?? ""}${user?.last_name?.[0] ?? ""}`.toUpperCase();

  const explorationNav: NavItem[] = [
    { to: "/", label: "Discover", icon: "fa-compass" },
    { to: "/ai", label: "Ask IRIS", icon: "fa-brain" },
    { to: "/records/mine", label: "My Library", icon: "fa-bookmark" },
    { to: "/opportunities", label: "Calls & Conferences", icon: "fa-bullhorn" },
  ];

  const ipNav: NavItem[] = [
    { to: "/records/add", label: "Submit Disclosure", icon: "fa-file-signature" },
    {
      to: "/workspace",
      label: "My Workspace",
      icon: "fa-briefcase",
      badge: workspaceBadge,
    },
  ];

  const reviewNav: NavItem[] = [
    { to: "/review/pending",            label: "Pending Records",     icon: "fa-hourglass-half" },
    { to: "/review/approved",           label: "Approved",            icon: "fa-check-circle"   },
    { to: "/review/declined",           label: "Declined",            icon: "fa-times-circle"   },
    ...(isRDCO ? [{ to: "/review/approved-proposals", label: "Approved Proposals", icon: "fa-flag-checkered" }] : []),
  ];

  const toolsNav: NavItem[] = [
    {
      to: "/notifications",
      label: "Notifications",
      icon: "fa-bell",
      badge: unreadCount,
    },
    { to: "/settings", label: "Settings & Profile", icon: "fa-cog" },
  ];

  return (
    <aside
      className={cn(
        // Mobile (<768px): always a full 230px drawer, overlaid.
        // Desktop (≥768px): 230px, or a 60px icon rail when collapsed.
        "fixed top-0 left-0 w-[230px] h-screen bg-white border-r border-gray-200 flex flex-col z-50",
        "transition-[width] duration-200 ease-out",
        collapsed ? "md:w-[60px]" : "md:w-[230px]",
        className
      )}
    >
      {/* ── Logo / Brand header ─────────────────────────────────────── */}
      <div
        className={cn(
          "py-4 border-b border-gray-100 flex items-center gap-3",
          collapsed ? "px-4 md:px-2 md:justify-center" : "px-4",
        )}
      >
        {/* Collapsed: the mark stands alone and only swaps to the toggle on
            hover. Expanded: the mark is static and the toggle sits at the far
            right of the brand block. */}
        <div className={cn("relative w-10 h-10 flex-shrink-0 hidden md:block", collapsed && "group")}>
          <img
            src={irisLogo}
            alt="IRIS"
            className={cn(
              "w-10 h-10 object-contain transition-opacity",
              collapsed && "group-hover:opacity-0",
            )}
          />
          {collapsed && (
            <button
              type="button"
              onClick={toggleCollapsed}
              aria-label="Expand sidebar"
              aria-expanded={false}
              title="Expand sidebar"
              className="absolute inset-0 w-10 h-10 rounded-lg border border-gray-200 bg-white text-gray-500 flex items-center justify-center opacity-0 transition-opacity hover:text-brand hover:border-brand-200 group-hover:opacity-100 focus-visible:opacity-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/30"
            >
              <i className="fas fa-chevron-right text-[13px]" aria-hidden />
            </button>
          )}
        </div>

        {/* Mobile drawer keeps a plain, non-interactive mark */}
        <img src={irisLogo} alt="IRIS" className="w-10 h-10 object-contain flex-shrink-0 md:hidden" />

        {/* Brand text: hidden while the rail is collapsed */}
        <div
          className={cn(
            "min-w-0 pt-0.5 flex-1",
            collapsed ? "block md:hidden" : "block",
          )}
        >
          <div className="text-[22px] font-extrabold tracking-[4px] text-[#6B0F12] leading-none">
            IRIS
          </div>
          <div className="text-[9px] font-bold tracking-[2px] text-gold uppercase mt-1 leading-snug">
            Research-to-IP Platform
          </div>
        </div>

        {/* Expanded: the collapse control sits at the right of the brand block. */}
        {!collapsed && (
          <button
            type="button"
            onClick={toggleCollapsed}
            aria-label="Collapse sidebar"
            aria-expanded
            title="Collapse sidebar"
            className="hidden md:flex w-8 h-8 flex-shrink-0 items-center justify-center rounded-lg border border-gray-200 bg-white text-gray-500 transition-colors hover:text-brand hover:border-brand-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/30"
          >
            <i className="fas fa-chevron-left text-[13px]" aria-hidden />
          </button>
        )}

        {/* Close button: mobile-only drawer control, hidden on tablet+ */}
        <button
          type="button"
          onClick={closeSidebar}
          className="md:hidden p-1.5 text-gray-500 hover:text-brand rounded-md"
          aria-label="Close menu"
        >
          <i className="fas fa-times text-[14px]" aria-hidden />
        </button>
      </div>

      {/* ── Navigation ──────────────────────────────────────────────── */}
      <nav className="flex-1 overflow-y-auto py-2 scrollbar-thin">
        <NavSection collapsed={collapsed} title="Research Exploration" items={explorationNav} onNavigate={closeSidebar} />
        <NavSection collapsed={collapsed} title="IP Management" items={ipNav} onNavigate={closeSidebar} />
        {isReviewer && (
          <NavSection collapsed={collapsed} title="Review Queue" items={reviewNav} onNavigate={closeSidebar} />
        )}
        <NavSection collapsed={collapsed} title="Tools" items={toolsNav} onNavigate={closeSidebar} />
        {isStaff && (
          <NavSection collapsed={collapsed}
            title="Administration"
            onNavigate={closeSidebar}
            items={[
              { to: "/admin/users",             label: "Manage Users",      icon: "fa-users" },
              ...(isDjangoAdmin ? [{ to: "/admin/role-requests", label: "Role Requests", icon: "fa-user-check", badge: roleRequestBadge }] : []),
              { to: "/admin/download-requests", label: "Download Requests", icon: "fa-download" },
              { to: "/admin/delete-requests",   label: "Delete Requests",   icon: "fa-trash-alt" },
              ...(isDjangoAdmin ? [{ to: "/admin/audit", label: "Audit Log", icon: "fa-clipboard-list" }] : []),
              { to: "/admin/sessions",          label: "Active Sessions",    icon: "fa-shield-alt" },
            ]}
          />
        )}
      </nav>

      {/* ── User footer ─────────────────────────────────────────────── */}
      <div
        className={cn(
          "py-3 border-t border-gray-100",
          collapsed ? "px-4 md:px-2" : "px-4",
        )}
      >
        <div
          className={cn(
            "flex items-center gap-2.5",
            collapsed ? "justify-start md:justify-center" : "justify-start",
          )}
        >
          <div className="w-[34px] h-[34px] rounded-full bg-[#6B0F12] text-white flex items-center justify-center text-[13px] font-bold flex-shrink-0">
            {initials || "?"}
          </div>

          <div className={cn("min-w-0 flex-1", collapsed ? "block md:hidden" : "block")}>
            <div className="text-[12px] font-semibold text-gray-900 truncate">
              {user?.first_name} {user?.last_name}
            </div>
            <div className="text-[11px] text-gray-500 truncate">
              {roleName ?? user?.email}
            </div>
          </div>

          {/* Sign out lives here because AppShell hides its Header on "/" */}
          <button
            type="button"
            onClick={handleSignOut}
            aria-label="Sign out"
            title="Sign out"
            className={cn(
              "p-1.5 rounded-md text-gray-500 hover:text-brand hover:bg-red-50 transition-colors flex-shrink-0",
              collapsed ? "block md:hidden" : "block",
            )}
          >
            <i className="fas fa-arrow-right-from-bracket text-[13px]" aria-hidden />
          </button>
        </div>

        {/* Collapsed rail: sign out gets its own row under the avatar */}
        {collapsed && (
          <button
            type="button"
            onClick={handleSignOut}
            aria-label="Sign out"
            title="Sign out"
            className="hidden md:flex w-full mt-2 py-1.5 rounded-md text-gray-500 hover:text-brand hover:bg-red-50 transition-colors items-center justify-center"
          >
            <i className="fas fa-arrow-right-from-bracket text-[13px]" aria-hidden />
          </button>
        )}
      </div>
    </aside>
  );
}
