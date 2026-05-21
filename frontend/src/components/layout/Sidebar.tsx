import { NavLink } from "react-router-dom";
import { useRole } from "@/hooks/useRole";
import { useAuth } from "@/hooks/useAuth";
import { cn } from "@/lib/utils";

interface NavItem {
  to:    string;
  label: string;
  icon:  string;
}

const mainNav: NavItem[] = [
  { to: "/",        label: "Dashboard",         icon: "fa-home" },
  { to: "/records", label: "Published Records", icon: "fa-newspaper" },
];

const recordsNav: NavItem[] = [
  { to: "/records/add",    label: "Add Record",     icon: "fa-plus-circle" },
  { to: "/records/import", label: "Import Records", icon: "fa-file-import" },
  { to: "/records/mine",   label: "My Records",     icon: "fa-folder" },
];

const reviewNav: NavItem[] = [
  { to: "/review/pending",  label: "Pending",  icon: "fa-hourglass-half" },
  { to: "/review/approved", label: "Approved", icon: "fa-check-circle" },
  { to: "/review/declined", label: "Declined", icon: "fa-times-circle" },
];

const toolsNav: NavItem[] = [
  { to: "/ai",            label: "AI Research Hub", icon: "fa-brain" },
  { to: "/storage",       label: "Storage",         icon: "fa-folder-open" },
  { to: "/notifications", label: "Notifications",   icon: "fa-bell" },
  { to: "/help",          label: "Help",            icon: "fa-question-circle" },
];

const adminNav: NavItem[] = [
  { to: "/admin/users",    label: "Manage Users", icon: "fa-users" },
  { to: "/admin/audit",    label: "Audit Log",    icon: "fa-list-alt" },
  { to: "/admin/sessions", label: "Sessions",     icon: "fa-desktop" },
];

function NavSection({ title, items }: { title: string; items: NavItem[] }) {
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
          className={({ isActive }) =>
            cn(
              "flex items-center gap-2.5 mx-2 px-4 py-2 rounded-md text-[13px] font-medium transition-colors",
              isActive
                ? "bg-[#6B0F12] text-white"
                : "text-gray-600 hover:bg-red-50 hover:text-[#6B0F12]"
            )
          }
        >
          <i className={cn("fas", item.icon, "w-4 text-center text-[13px]")} />
          {item.label}
        </NavLink>
      ))}
    </>
  );
}

export function Sidebar() {
  const { user }                                = useAuth();
  const { isReviewer, isStaff }                 = useRole();

  const initials = `${user?.first_name?.[0] ?? ""}${user?.last_name?.[0] ?? ""}`.toUpperCase();

  return (
    <aside className="fixed top-0 left-0 w-[230px] h-screen bg-white border-r border-gray-200 flex flex-col z-50">
      {/* Brand */}
      <div className="px-5 py-5 border-b border-gray-100">
        <div className="text-[28px] font-extrabold tracking-[6px] text-[#6B0F12] leading-none">IRIS</div>
        <div className="text-[9px] font-bold tracking-[3px] text-yellow-500 uppercase mt-1">Academic Curator</div>
      </div>

      {/* Nav */}
      <nav className="flex-1 overflow-y-auto py-2">
        <NavSection title="Main"    items={mainNav} />
        <NavSection title="Records" items={recordsNav} />
        {isReviewer && <NavSection title="Review Queue" items={reviewNav} />}
        <NavSection title="Tools" items={toolsNav} />
        {isStaff && <NavSection title="Admin" items={adminNav} />}
      </nav>

      {/* User card */}
      <div className="px-4 py-3 border-t border-gray-100">
        <div className="flex items-center gap-2.5">
          <div className="w-[34px] h-[34px] rounded-full bg-[#6B0F12] text-white flex items-center justify-center text-[13px] font-bold flex-shrink-0">
            {initials || "?"}
          </div>
          <div className="min-w-0">
            <div className="text-[12px] font-semibold text-gray-900 truncate">
              {user?.first_name} {user?.last_name}
            </div>
            <div className="text-[11px] text-gray-500">{user?.username}</div>
          </div>
        </div>
      </div>
    </aside>
  );
}
