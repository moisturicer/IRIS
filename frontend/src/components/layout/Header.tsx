import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useNotifications } from "@/hooks/useNotifications";
import { useAuth } from "@/hooks/useAuth";
import { authApi } from "@/api/auth";
import { useHeaderSearchVisible } from "@/contexts/DiscoverSearchContext";
import { cn } from "@/lib/utils";

export function Header() {
  const navigate = useNavigate();
  const { logout, refreshToken } = useAuth();
  const { unreadCount } = useNotifications();
  const showSearch = useHeaderSearchVisible();
  const [query, setQuery] = useState("");

  const handleLogout = async () => {
    await authApi.logout(refreshToken ?? "").catch(() => {});
    logout();
  };

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = query.trim();
    if (!trimmed) return;
    navigate(`/ai?q=${encodeURIComponent(trimmed)}`);
  };

  return (
    <header className="fixed top-0 left-[230px] right-0 h-[58px] bg-white border-b border-gray-200 flex items-center px-6 gap-4 z-40">
      <div className="flex-1 flex items-center min-w-0">
        <form
          onSubmit={handleSearch}
          className={cn(
            "relative w-full max-w-md transition-all duration-300",
            showSearch
              ? "opacity-100 translate-y-0"
              : "opacity-0 pointer-events-none max-w-0 overflow-hidden"
          )}
          aria-hidden={!showSearch}
        >
          <i
            className="fa-solid fa-magnifying-glass absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 text-[12px]"
            aria-hidden
          />
          <input
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search records, authors, topics..."
            className="w-full pl-8 pr-3 py-1.5 border border-gray-200 rounded-lg text-[13px] bg-gray-50 focus:outline-none focus:border-brand"
          />
        </form>
      </div>

      <div className="flex items-center gap-2 shrink-0 ml-auto">
        <Link
          to="/notifications"
          title="Notifications"
          aria-label={`Notifications${unreadCount > 0 ? `, ${unreadCount} unread` : ""}`}
          className="relative w-[34px] h-[34px] rounded-lg border border-gray-200 flex items-center justify-center text-gray-600 hover:bg-gray-50 hover:text-brand transition-colors"
        >
          <i className="fa-solid fa-bell text-[15px]" aria-hidden />
          {unreadCount > 0 && (
            <span className="absolute -top-0.5 -right-0.5 min-w-[16px] h-4 px-1 rounded-full bg-red-500 text-white text-[10px] font-bold flex items-center justify-center">
              {unreadCount > 9 ? "9+" : unreadCount}
            </span>
          )}
        </Link>

        <Link
          to="/settings"
          title="Settings"
          aria-label="Settings and profile"
          className="w-[34px] h-[34px] rounded-lg border border-gray-200 flex items-center justify-center text-gray-600 hover:bg-gray-50 hover:text-brand transition-colors"
        >
          <i className="fa-solid fa-gear text-[15px]" aria-hidden />
        </Link>

        <button
          type="button"
          onClick={handleLogout}
          className="px-3 py-1.5 rounded-lg bg-brand text-white text-[12px] font-semibold hover:bg-brand-dark transition-colors inline-flex items-center gap-1.5"
        >
          <i className="fa-solid fa-right-from-bracket text-[12px]" aria-hidden />
          Sign Out
        </button>
      </div>
    </header>
  );
}
