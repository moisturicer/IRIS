import { useLocation } from "react-router-dom";
import { useUIStore } from "@/store/ui.store";
import { cn } from "@/lib/utils";
import { NotificationBell } from "./NotificationBell";

export function Header() {
  const toggleSidebar = useUIStore((s) => s.toggleSidebar);
  const collapsed = useUIStore((s) => s.sidebarCollapsed);
  // Paper View is a reading surface; a search box there was one more thing
  // above the paper with nothing to do (IR-356). It is also inert on every
  // other screen -- it has no handler -- which is a separate fix.
  const { pathname } = useLocation();
  const showSearch = !/^\/records\/\d+\/?$/.test(pathname);

  return (
    <header
      className={cn(
        "fixed top-0 left-0 right-0 h-[58px] bg-white border-b border-gray-200 flex items-center px-4 lg:px-6 gap-3 z-40",
        "transition-[left] duration-200 ease-out",
        collapsed ? "md:left-[60px]" : "md:left-[230px]",
      )}
    >
      <button
        type="button"
        onClick={toggleSidebar}
        className="md:hidden w-[34px] h-[34px] rounded-lg border border-gray-200 flex items-center justify-center text-gray-600 hover:bg-gray-50"
        aria-label="Open menu"
      >
        <i className="fas fa-bars text-base" aria-hidden />
      </button>

      {showSearch && (
        <div className="relative flex-1 max-w-md min-w-0 hidden md:block">
          <i className="fas fa-search absolute left-3 top-1/2 -translate-y-1/2 text-gray-500 text-xs" aria-hidden />
          <input
            type="search"
            aria-label="Search records, authors, topics"
            placeholder="Search records, authors, topics..."
            className="w-full pl-8 pr-3 py-1.5 border border-gray-200 rounded-lg text-sm bg-gray-50 focus:outline-none focus:border-brand"
          />
        </div>
      )}

      <div className="ml-auto">
        <NotificationBell />
      </div>
    </header>
  );
}
