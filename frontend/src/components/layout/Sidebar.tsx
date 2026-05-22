import { useEffect, useState } from "react";
import { NavLink } from "react-router-dom";
import { useAuth } from "@/hooks/useAuth";
import { useUIStore } from "@/store/ui.store";
import { useNotifications } from "@/hooks/useNotifications";
import { apiClient } from "@/api/client";
import { cn } from "@/lib/utils";
import irisLogo from "@/assets/images/iris_logo.png";

interface NavItem {
  to:     string;
  label:  string;
  icon:   string;
  badge?: number;
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
      <div className="px-4 py-2 text-[10px] font-bold tracking-widest text-gray-400 uppercase">
        {title}
      </div>
      {items.map((item) => (
        <NavLink
          key={item.to}
          to={item.to}
          end={item.to === "/"}
          onClick={onNavigate}
          className={({ isActive }) =>
            cn(
              "flex items-center gap-2.5 mx-2 px-4 py-2 rounded-md text-[13px] font-medium transition-colors relative",
              isActive
                ? "bg-red-50 text-[#6B0F12] font-semibold before:absolute before:left-0 before:top-1 before:bottom-1 before:w-1 before:rounded-r before:bg-[#6B0F12]"
                : "text-gray-600 hover:bg-red-50/60 hover:text-[#6B0F12]"
            )
          }
        >
          <i className={cn("fas", item.icon, "w-4 text-center text-[13px]")} />
          <span className="flex-1">{item.label}</span>
          {item.badge != null && item.badge > 0 && (
            <span className="min-w-[18px] h-[18px] px-1 rounded-full bg-red-500 text-white text-[10px] font-bold flex items-center justify-center">
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
  const { unreadCount } = useNotifications();
  const closeSidebar = useUIStore((s) => s.closeSidebar);
  const [workspaceBadge, setWorkspaceBadge] = useState(0);

  useEffect(() => {
    apiClient
      .get<{ pending_mine: number }>("/dashboard/stats/")
      .then(({ data }) => setWorkspaceBadge(data.pending_mine ?? 0))
      .catch(() => {});
  }, []);

  const initials = `${user?.first_name?.[0] ?? ""}${user?.last_name?.[0] ?? ""}`.toUpperCase();
  const onNavigate = () => closeSidebar();

  const explorationNav: NavItem[] = [
    { to: "/", label: "Discover", icon: "fa-compass" },
    { to: "/ai", label: "Ask IRIS (AI Assistant)", icon: "fa-brain" },
    { to: "/records", label: "Browse Collections", icon: "fa-layer-group" },
    { to: "/records/mine", label: "My Library", icon: "fa-bookmark" },
  ];

  const ipNav: NavItem[] = [
    { to: "/records/add", label: "Submit Disclosure", icon: "fa-file-signature" },
    {
      to: "/records/mine",
      label: "My Workspace",
      icon: "fa-briefcase",
      badge: workspaceBadge,
    },
  ];

  const toolsNav: NavItem[] = [
    {
      to: "/notifications",
      label: "Notifications",
      icon: "fa-bell",
      badge: unreadCount,
    },
    { to: "/storage", label: "Storage", icon: "fa-folder-open" },
    { to: "/help", label: "Settings & Profile", icon: "fa-cog" },
  ];

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
          <div className="text-[22px] font-extrabold tracking-[4px] text-[#6B0F12] leading-none">
            IRIS
          </div>
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
        <NavSection title="Research Exploration" items={explorationNav} onNavigate={onNavigate} />
        <NavSection title="IP Management" items={ipNav} onNavigate={onNavigate} />
        <NavSection title="Tools" items={toolsNav} onNavigate={onNavigate} />
      </nav>

      <div className="px-4 py-3 border-t border-gray-100">
        <div className="flex items-center gap-2.5">
          <div className="w-[34px] h-[34px] rounded-full bg-[#6B0F12] text-white flex items-center justify-center text-[13px] font-bold flex-shrink-0">
            {initials || "?"}
          </div>
          <div className="min-w-0">
            <div className="text-[12px] font-semibold text-gray-900 truncate">
              {user?.first_name} {user?.last_name}
            </div>
            <div className="text-[11px] text-gray-500 truncate">
              {user?.role_name ?? user?.username}
            </div>
          </div>
        </div>
      </div>
    </aside>
  );
}
