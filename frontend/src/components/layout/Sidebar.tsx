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
import irisLogo from "@/assets/images/iris_logo.png";

interface NavItemDef {
  to:      string;
  label:   string;
  icon:    string;
  visible: (role: RoleName | null, isDjangoStaff: boolean) => boolean;
  badge?:  number;
}

const ALL: NavItemDef["visible"] = () => true;

const ROLES_ONLY =
  (...roles: RoleName[]): NavItemDef["visible"] =>
  (role) =>
    role !== null && roles.includes(role);

const ADMIN_OR_STAFF: NavItemDef["visible"] = (role, isDjangoStaff) =>
  isDjangoStaff || role === ROLES.ADMIN;

const NAV_ITEMS: NavItemDef[] = [
  { to: "/", label: "Discover", icon: "fa-compass", visible: ALL },
  { to: "/ai", label: "Ask IRIS", icon: "fa-comments", visible: ALL },
  {
    to: "/ai/summarize",
    label: "AI Summarizer",
    icon: "fa-file-lines",
    visible: ROLES_ONLY(ROLES.ADVISER, ROLES.KTTO, ROLES.TBI, ROLES.ITSO, ROLES.IERC, ROLES.RDCO),
  },
  { to: "/records", label: "Browse Collections", icon: "fa-book-open", visible: ALL },
  { to: "/storage", label: "My Library", icon: "fa-bookmark", visible: ALL },
  { to: "/records/add", label: "Submit Disclosure", icon: "fa-circle-plus", visible: ROLES_ONLY(ROLES.STUDENT) },
  { to: "/records/mine", label: "My Workspace", icon: "fa-briefcase", visible: ROLES_ONLY(ROLES.STUDENT) },
  {
    to: "/review/pending",
    label: "Review Submissions",
    icon: "fa-clipboard-check",
    visible: ROLES_ONLY(ROLES.ADVISER, ROLES.KTTO, ROLES.TBI, ROLES.IERC, ROLES.RDCO),
  },
  {
    to: "/requests/access",
    label: "Access Requests",
    icon: "fa-download",
    visible: ROLES_ONLY(ROLES.KTTO, ROLES.TBI, ROLES.RDCO),
  },
  {
    to: "/requests/deletion",
    label: "Deletion Requests",
    icon: "fa-trash-can",
    visible: ROLES_ONLY(ROLES.KTTO, ROLES.TBI, ROLES.RDCO),
  },
  {
    to: "/notifications",
    label: "Notifications",
    icon: "fa-bell",
    visible: ALL,
  },
  { to: "/admin/users", label: "User Management", icon: "fa-users-gear", visible: ADMIN_OR_STAFF },
  { to: "/admin/role-requests", label: "Role Requests", icon: "fa-user-check", visible: ADMIN_OR_STAFF },
  {
    to: "/admin/audit",
    label: "System Audit Logs",
    icon: "fa-history",
    visible: (role, isDjangoStaff) =>
      isDjangoStaff || role === ROLES.ADMIN || role === ROLES.RDCO,
  },
  { to: "/help", label: "Settings & Profile", icon: "fa-gear", visible: ALL },
];

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

  useEffect(() => {
    if (!isStudent) return;
    dashboardApi.stats()
      .then(({ data }) => setWorkspaceCount(data.total_mine > 0 ? data.total_mine : undefined))
      .catch(() => setWorkspaceCount(undefined));
  }, [isStudent]);

  useEffect(() => {
    if (!isDjangoStaff && roleName !== ROLES.ADMIN) return;
    apiClient
      .get<{ count: number }>("/users/role-requests/")
      .then(({ data }) => setRoleRequestBadge(data.count ?? 0))
      .catch(() => {});
  }, [isDjangoStaff, roleName]);

  const visibleItems = NAV_ITEMS.filter((item) => item.visible(roleName, isDjangoStaff));
  const initials = `${user?.first_name?.[0] ?? ""}${user?.last_name?.[0] ?? ""}`.toUpperCase();

  const badgeFor = (to: string) => {
    if (to === "/records/mine" && isStudent) return workspaceCount;
    if (to === "/notifications") return unreadCount > 0 ? unreadCount : undefined;
    if (to === "/admin/role-requests") return roleRequestBadge > 0 ? roleRequestBadge : undefined;
    return undefined;
  };

  return (
    <aside
      className={cn(
        "fixed top-0 left-0 w-[230px] h-screen bg-white border-r border-gray-200 flex flex-col z-50",
        className
      )}
    >
      <div className="px-4 py-4 border-b border-gray-100 flex items-start gap-3">
        <img src={irisLogo} alt="IRIS" className="w-10 h-10 object-contain flex-shrink-0" />
        <div className="min-w-0 pt-0.5 flex-1">
          <div className="text-[22px] font-extrabold tracking-[4px] text-[#6B0F12] leading-none">IRIS</div>
          <div className="text-[9px] font-bold tracking-[2px] text-gold uppercase mt-1 leading-snug">
            CIT-U Research Hub
          </div>
        </div>
        <button
          type="button"
          onClick={closeSidebar}
          className="lg:hidden p-1.5 text-gray-400 hover:text-brand rounded-md"
          aria-label="Close menu"
        >
          <i className="fas fa-times text-[14px]" />
        </button>
      </div>

      <nav className="flex-1 overflow-y-auto py-2 scrollbar-thin">
        {visibleItems.map((item) => {
          const badge = badgeFor(item.to);
          return (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === "/"}
              onClick={closeSidebar}
              className={({ isActive }) =>
                cn(
                  "flex items-center gap-2.5 mx-2 px-4 py-2 rounded-md text-[13px] font-medium transition-colors",
                  isActive
                    ? "bg-[#8B1A1A] text-white"
                    : "text-gray-600 hover:bg-red-50 hover:text-[#8B1A1A]"
                )
              }
            >
              <i className={cn("fa-solid", item.icon, "w-4 shrink-0 text-[14px]")} aria-hidden />
              <span className="flex-1">{item.label}</span>
              {badge != null && badge > 0 && (
                <span className="min-w-[18px] h-[18px] px-1 rounded-full bg-[#6B0F12] text-white text-[10px] font-bold flex items-center justify-center">
                  {badge > 99 ? "99+" : badge}
                </span>
              )}
            </NavLink>
          );
        })}
      </nav>

      <div className="px-4 py-3 border-t border-gray-100">
        <div className="flex items-center gap-2.5">
          <div className="w-[34px] h-[34px] rounded-full bg-[#8B1A1A] text-white flex items-center justify-center text-[13px] font-bold flex-shrink-0">
            {initials || "?"}
          </div>
          <div className="min-w-0">
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
