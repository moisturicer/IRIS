import { Link } from "react-router-dom";
import { useNotifications } from "@/hooks/useNotifications";
import { useAuth } from "@/hooks/useAuth";
import { authApi } from "@/api/auth";

export function Header() {
  const { logout, refreshToken } = useAuth();
  const { unreadCount }          = useNotifications();

  const handleLogout = async () => {
    await authApi.logout(refreshToken ?? "").catch(() => {});
    logout();
  };

  return (
    <header className="fixed top-0 left-[230px] right-0 h-[58px] bg-white border-b border-gray-200 flex items-center px-6 gap-4 z-40">
      {/* Global search -- TODO: wire up to /records/?search= */}
      <div className="relative flex-1 max-w-md">
        <i className="fas fa-search absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 text-[12px]" />
        <input
          type="text"
          placeholder="Search records, authors, topics..."
          className="w-full pl-8 pr-3 py-1.5 border border-gray-200 rounded-lg text-[13px] bg-gray-50 focus:outline-none focus:border-[#6B0F12]"
        />
      </div>

      <div className="ml-auto flex items-center gap-2">
        {/* Notifications */}
        <Link
          to="/notifications"
          className="relative w-[34px] h-[34px] rounded-lg border border-gray-200 flex items-center justify-center text-gray-600 hover:bg-gray-50"
        >
          <i className="fas fa-bell text-[13px]" />
          {unreadCount > 0 && (
            <span className="absolute top-1 right-1 w-2 h-2 rounded-full bg-red-500" />
          )}
        </Link>

        {/* Sign Out */}
        <button
          onClick={handleLogout}
          className="px-3 py-1.5 rounded-lg bg-[#6B0F12] text-white text-[12px] font-semibold hover:bg-[#7d1215] transition-colors"
        >
          <i className="fas fa-sign-out-alt mr-1" /> Sign Out
        </button>
      </div>
    </header>
  );
}
