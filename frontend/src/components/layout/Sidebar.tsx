import { useEffect, useState } from "react";
import { NavLink } from "react-router-dom";
import { dashboardApi } from "@/api/dashboard";
import { apiClient } from "@/api/client";
import { useAuth } from "@/hooks/useAuth";
import { useRole } from "@/hooks/useRole";
import { useUIStore } from "@/store/ui.store";
import { useNotifications } from "@/hooks/useNotifications";
import { ROLES, type RoleName } from "@/lib/constants";
import { cn } from "@/lib/utils";
import { STAFF_ROLES, REVIEWER_ROLES } from "@/lib/constants";
import irisLogo from "@/assets/images/iris_logo.png";

interface NavItem {
  to:          string;
  label:       string;
  icon:        string;
  badge?:      number;
  comingSoon?: boolean;
}

function NavSection({
  title,
  items,
  onNavigate,
}: {
  title: string;
  items: NavItem[];
  onNavigate?: () => void;
}) {
  return (
    <>
      {/* Section title: visible only on desktop (≥1280px) */}
      <div className="px-4 py-2 text-[10px] font-bold tracking-widest text-gray-400 uppercase hidden xl:block">
        {title}
      </div>
      {items.map((item) => (
        <NavLink
          key={item.to}
          to={item.to}
          end
          onClick={onNavigate}
          className={({ isActive }) =>
            cn(
              // Base layout: centered icon on tablet, left-aligned with label on desktop
              "flex items-center gap-2.5 mx-2 px-2 xl:px-4 py-2 rounded-md text-[13px] font-medium transition-colors relative",
              "justify-center xl:justify-start",
              isActive
                ? "bg-red-50 text-[#6B0F12] font-semibold before:absolute before:left-0 before:top-1 before:bottom-1 before:w-1 before:rounded-r before:bg-[#6B0F12]"
                : "text-gray-600 hover:bg-red-50/60 hover:text-[#6B0F12]"
            )
          }
        >
          <i className={cn("fas", item.icon, "w-4 text-center text-[13px] flex-shrink-0")} />
          {/* Label + coming-soon badge stacked; hidden on tablet, shown on desktop */}
          <div className="flex-1 hidden xl:flex flex-col gap-0.5 min-w-0">
            <span>{item.label}</span>
            {item.comingSoon && (
              <span className="self-start px-1.5 py-0.5 bg-amber-50 text-amber-600 text-[9px] font-bold rounded-full border border-amber-200 uppercase tracking-wider leading-none">
                coming soon
              </span>
            )}
          </div>
          {/* Numeric badge: hidden on tablet, shown on desktop */}
          {item.badge != null && item.badge > 0 && (
            <span className="min-w-[18px] h-[18px] px-1 rounded-full bg-red-500 text-white text-[10px] font-bold hidden xl:flex items-center justify-center">
              {item.badge > 9 ? "9+" : item.badge}
            </span>
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
  const { roleName, isStudent, isDjangoStaff } = useRole();
  const { unreadCount } = useNotifications();
  const closeSidebar = useUIStore((s) => s.closeSidebar);
  const [workspaceCount, setWorkspaceCount] = useState<number | undefined>();
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
    if (!isDjangoStaff && roleName !== ROLES.ADMIN) return;
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

  const visibleItems = NAV_ITEMS.filter((item) => item.visible(roleName, isDjangoStaff));
  const initials = `${user?.first_name?.[0] ?? ""}${user?.last_name?.[0] ?? ""}`.toUpperCase();

  const explorationNav: NavItem[] = [
    { to: "/", label: "Discover", icon: "fa-compass" },
    { to: "/ai", label: "Ask IRIS (AI Assistant)", icon: "fa-brain", comingSoon: true },
    { to: "/records", label: "Browse Collections", icon: "fa-layer-group" },
    { to: "/records/mine", label: "My Library", icon: "fa-bookmark" },
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
    { to: "/review/analytics",          label: "Review Analytics",    icon: "fa-chart-line", comingSoon: true },
  ];

  const toolsNav: NavItem[] = [
    {
      to: "/notifications",
      label: "Notifications",
      icon: "fa-bell",
      badge: unreadCount,
    },
    { to: "/storage", label: "Storage", icon: "fa-folder-open", comingSoon: true },
    { to: "/settings", label: "Settings & Profile", icon: "fa-cog" },
  ];

  return (
    <aside
      className={cn(
        // Mobile (<768px): full 230px drawer
        // Tablet (768–1279px): narrow 60px icon-only rail, always visible
        // Desktop (≥1280px): full 230px sidebar, always visible
        "fixed top-0 left-0 w-[230px] md:w-[60px] xl:w-[230px] h-screen bg-white border-r border-gray-200 flex flex-col z-50",
        className
      )}
    >
      {/* ── Logo / Brand header ─────────────────────────────────────── */}
      <div className="px-2 xl:px-4 py-4 border-b border-gray-100 flex items-center justify-center xl:items-start xl:justify-start gap-3">
        <img src={irisLogo} alt="IRIS" className="w-10 h-10 object-contain flex-shrink-0" />
        {/* Brand text: hidden on tablet, shown on desktop */}
        <div className="hidden xl:block min-w-0 pt-0.5 flex-1">
          <div className="text-[22px] font-extrabold tracking-[4px] text-[#6B0F12] leading-none">
            IRIS
          </div>
          <div className="text-[9px] font-bold tracking-[2px] text-gold uppercase mt-1 leading-snug">
            CIT-U Research Hub
          </div>
        </div>
        {/* Close button: mobile-only drawer control, hidden on tablet+ */}
        <button
          type="button"
          onClick={closeSidebar}
          className="md:hidden p-1.5 text-gray-400 hover:text-brand rounded-md"
          aria-label="Close menu"
        >
          <i className="fas fa-times text-[14px]" />
        </button>
      </div>

      {/* ── Navigation ──────────────────────────────────────────────── */}
      <nav className="flex-1 overflow-y-auto py-2 scrollbar-thin">
        <NavSection title="Research Exploration" items={explorationNav} onNavigate={onNavigate} />
        <NavSection title="IP Management" items={ipNav} onNavigate={onNavigate} />
        {isReviewer && (
          <NavSection title="Review Queue" items={reviewNav} onNavigate={onNavigate} />
        )}
        <NavSection title="Tools" items={toolsNav} onNavigate={onNavigate} />
        {isStaff && (
          <NavSection
            title="Administration"
            onNavigate={onNavigate}
            items={[
              { to: "/admin/users",             label: "Manage Users",      icon: "fa-users" },
              ...(isDjangoAdmin ? [{ to: "/admin/role-requests", label: "Role Requests", icon: "fa-user-check", badge: roleRequestBadge }] : []),
              { to: "/admin/download-requests", label: "Download Requests", icon: "fa-download" },
              { to: "/admin/delete-requests",   label: "Delete Requests",   icon: "fa-trash-alt" },
              ...(isDjangoAdmin ? [{ to: "/admin/audit", label: "Audit Log", icon: "fa-clipboard-list" }] : []),
              { to: "/admin/sessions",          label: "Active Sessions",    icon: "fa-shield-alt" },
              { to: "/admin/document-reviews",  label: "Document Reviews",   icon: "fa-file-check", comingSoon: true },
            ]}
          />
        )}
      </nav>

      {/* ── User footer ─────────────────────────────────────────────── */}
      <div className="px-2 xl:px-4 py-3 border-t border-gray-100">
        <div className="flex items-center justify-center xl:justify-start gap-2.5">
          <div className="w-[34px] h-[34px] rounded-full bg-[#6B0F12] text-white flex items-center justify-center text-[13px] font-bold flex-shrink-0">
            {initials || "?"}
          </div>
          {/* User info: hidden on tablet, shown on desktop */}
          <div className="min-w-0 hidden xl:block">
            <div className="text-[12px] font-semibold text-gray-900 truncate">
              {user?.first_name} {user?.last_name}
            </div>
            <div className="text-[11px] text-gray-500 truncate">
              {roleName ?? user?.email}
            </div>
          </div>
        </div>
      </div>
    </aside>
  );
}
