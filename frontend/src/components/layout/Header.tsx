import { useAuth } from "@/hooks/useAuth";
import { authApi } from "@/api/auth";
import { useUIStore } from "@/store/ui.store";
import { NotificationBell } from "./NotificationBell";

export function Header() {
  const { logout, user } = useAuth();
  const toggleSidebar = useUIStore((s) => s.toggleSidebar);

  const handleLogout = async () => {
    const refresh = localStorage.getItem("refresh_token") ?? "";
    await authApi.logout(refresh).catch(() => {});
    logout();
  };

  return (
    <header className="fixed top-0 left-0 lg:left-[230px] right-0 h-[58px] bg-white border-b border-gray-200 flex items-center px-4 lg:px-6 gap-3 z-40">
      <button
        type="button"
        onClick={toggleSidebar}
        className="lg:hidden w-[34px] h-[34px] rounded-lg border border-gray-200 flex items-center justify-center text-gray-600 hover:bg-gray-50"
        aria-label="Open menu"
      >
        <i className="fas fa-bars text-[14px]" />
      </button>

      <div className="relative flex-1 max-w-md min-w-0 hidden md:block">
        <i className="fas fa-search absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 text-[12px]" />
        <input
          type="text"
          placeholder="Search records, authors, topics..."
          className="w-full pl-8 pr-3 py-1.5 border border-gray-200 rounded-lg text-[13px] bg-gray-50 focus:outline-none focus:border-[#6B0F12]"
        />
      </div>

      <div className="ml-auto flex items-center gap-2 flex-shrink-0">
        <span className="hidden sm:inline text-[12px] text-gray-500 truncate max-w-[120px]">
          {user?.first_name}
        </span>

        <NotificationBell />

        <button
          type="button"
          onClick={handleLogout}
          className="flex items-center gap-2 px-3 py-1.5 border border-slate-200 text-slate-600 rounded-lg hover:bg-slate-50 text-[12px] font-semibold transition-colors whitespace-nowrap"
        >
          <i className="fas fa-sign-out-alt text-[13px]" />
          <span className="hidden sm:inline">Sign Out</span>
        </button>
      </div>
    </header>
  );
}
