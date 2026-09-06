import { useUIStore } from "@/store/ui.store";
import { cn } from "@/lib/utils";
import { NotificationBell } from "./NotificationBell";

export function Header() {
  const toggleSidebar = useUIStore((s) => s.toggleSidebar);
  const collapsed = useUIStore((s) => s.sidebarCollapsed);

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
        <i className="fas fa-bars text-[14px]" aria-hidden />
      </button>

      <div className="relative flex-1 max-w-md min-w-0 hidden md:block">
        <i className="fas fa-search absolute left-3 top-1/2 -translate-y-1/2 text-gray-500 text-[12px]" aria-hidden />
        <input
          type="text"
          placeholder="Search records, authors, topics..."
          className="w-full pl-8 pr-3 py-1.5 border border-gray-200 rounded-lg text-[13px] bg-gray-50 focus:outline-none focus:border-[#6B0F12]"
        />
      </div>

      <div className="ml-auto">
        <NotificationBell />
      </div>
    </header>
  );
}
